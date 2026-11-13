"""漏斗留存增量刷新引擎：漏斗与同期群作为联合业务入口，共享划分事件和观察窗口。

核心规则：
- 按 漏斗版本 + 划分事件 + 观察周期 + 已覆盖群组 计算待重算窗口，只处理
  新增、失效与待补窗口，其余留存结果沿用；
- 完成水位只在一个群组的观察周期连续成功后推进，失败窗口保留已成功的转化率，
  下次刷新从缺口续做；
- 重复刷新同一窗口只生效一次；两个任务并发更新同一观察周期时，以已落库的完整
  结果为准，较旧版本不能回写；
- 保存前按明确规则与阈值校验（观察窗口标准、样本量允许范围、留存上限、触发
  条件），超界时不允许保存；
- 每次刷新写入审计记录，漏斗详情与同期群结果读取同一覆盖版本。
"""
from __future__ import annotations

import hashlib
import threading
from datetime import datetime, timezone
from typing import Any

from app.store import store

MODULE_PLAN = "retention_plan"
MODULE_WINDOW = "retention_window"
MODULE_CHECKPOINT = "retention_checkpoint"
MODULE_RUN = "retention_run"

# 窗口分类：验收时按这四类区分每个观察窗口的去向
CLASS_NEW = "新增"
CLASS_STALE = "失效"
CLASS_REUSED = "复用"
CLASS_GAP = "待补"
CLASS_ORDER = [CLASS_NEW, CLASS_STALE, CLASS_REUSED, CLASS_GAP]

# 判定规则与阈值：超界时不允许保存
MAX_WINDOW_DAY = 365  # 观察窗口标准：单个窗口天数上限
MAX_WINDOWS = 12  # 观察窗口标准：观察周期数量上限
MIN_SAMPLE_SIZE = 10  # 样本量允许范围下限（计划只能收紧，不能放宽）
MAX_SAMPLE_SIZE = 1_000_000  # 样本量允许范围上限
RETENTION_CAP = 1.0  # 留存上限（计划只能收紧，不能放宽）
FULL_RECOMPUTE_RATIO = 0.5  # 失效窗口占比超过该阈值时整体重算
ENABLED_STATUS = "已启用"  # 触发条件：漏斗与同期群都必须是已启用


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _window_key(cohort_batch: str, window_day: int) -> str:
    return f"{cohort_batch}#{window_day}"


def _split_window_key(key: str) -> tuple[str, int]:
    batch, _, day = key.rpartition("#")
    return batch, int(day)


class RetentionService:
    """漏斗留存增量刷新：窗口分类、缺口续算、水位推进、并发守卫与审计。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    # ---------- 计划与定义 ----------

    def get_plan(self, plan_key: str) -> dict[str, Any] | None:
        for plan in store.rows(MODULE_PLAN):
            if plan.get("plan_key") == plan_key:
                return plan
        return None

    def list_plans(self) -> list[dict[str, Any]]:
        return [self._plan_summary(plan) for plan in store.rows(MODULE_PLAN)]

    def _plan_summary(self, plan: dict[str, Any]) -> dict[str, Any]:
        summary = dict(plan)
        checkpoints = [
            cp for cp in store.rows(MODULE_CHECKPOINT)
            if cp.get("plan_key") == plan.get("plan_key")
        ]
        summary["完成水位"] = {cp["cohort_batch"]: cp["window_day"] for cp in checkpoints}
        return summary

    def _find_definitions(
        self, plan: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        funnel = next(
            (row for row in store.rows("funnel") if row.get("漏斗编号") == plan.get("漏斗编号")),
            None,
        )
        cohort = next(
            (row for row in store.rows("cohort") if row.get("群组编号") == plan.get("群组编号")),
            None,
        )
        return funnel, cohort

    def check_trigger(self, plan: dict[str, Any]) -> str | None:
        """触发条件：定义齐全，且漏斗与同期群都处于已启用状态。"""
        funnel, cohort = self._find_definitions(plan)
        if funnel is None:
            return f"漏斗定义 {plan.get('漏斗编号')} 不存在，刷新未触发"
        if cohort is None:
            return f"同期群定义 {plan.get('群组编号')} 不存在，刷新未触发"
        if funnel.get("status") != ENABLED_STATUS or cohort.get("status") != ENABLED_STATUS:
            return "触发条件未满足：漏斗与同期群都必须是已启用状态"
        return None

    # ---------- 窗口分类与增量策略 ----------

    def _find_window(
        self, plan_key: str, cohort_batch: str, window_day: int
    ) -> dict[str, Any] | None:
        for row in store.rows(MODULE_WINDOW):
            if (
                row.get("plan_key") == plan_key
                and row.get("cohort_batch") == cohort_batch
                and int(row.get("window_day", -1)) == window_day
            ):
                return row
        return None

    def _covered_batches(self, plan: dict[str, Any]) -> list[str]:
        """已覆盖群组 = 已有窗口结果的群组 ∪ 计划上登记的待算群组。"""
        batches = {
            row["cohort_batch"]
            for row in store.rows(MODULE_WINDOW)
            if row.get("plan_key") == plan.get("plan_key")
        }
        batches.update(str(batch) for batch in plan.get("待算群组") or [])
        return sorted(batches)

    def classify_windows(self, plan: dict[str, Any]) -> dict[str, list[str]]:
        """按漏斗版本、划分事件、观察周期和已覆盖群组，把窗口分成 新增/失效/复用/待补。"""
        days = [int(day) for day in plan.get("观察周期列表") or []]
        classified: dict[str, list[str]] = {name: [] for name in CLASS_ORDER}
        for batch in self._covered_batches(plan):
            for day in days:
                row = self._find_window(plan["plan_key"], batch, day)
                key = _window_key(batch, day)
                if row is None:
                    classified[CLASS_NEW].append(key)
                elif (
                    row.get("漏斗版本") != plan.get("漏斗版本")
                    or row.get("划分事件") != plan.get("划分事件")
                ):
                    classified[CLASS_STALE].append(key)
                elif row.get("status") == "success":
                    classified[CLASS_REUSED].append(key)
                else:
                    classified[CLASS_GAP].append(key)
        return classified

    def choose_strategy(self, classified: dict[str, list[str]]) -> str:
        """根据现有窗口数据选择增量策略：无历史全量、失效过半整体重算、否则增量。"""
        history = (
            len(classified[CLASS_STALE])
            + len(classified[CLASS_REUSED])
            + len(classified[CLASS_GAP])
        )
        if history == 0:
            return "initial"
        if len(classified[CLASS_STALE]) / history > FULL_RECOMPUTE_RATIO:
            return "full"
        return "incremental"

    # ---------- 判定规则与阈值 ----------

    def validate_plan_windows(self, plan: dict[str, Any]) -> list[str]:
        """观察窗口标准：周期为正整数、严格递增、数量与单窗天数都在上限内。"""
        errors: list[str] = []
        days = plan.get("观察周期列表") or []
        if not days or len(days) > MAX_WINDOWS:
            errors.append(f"观察周期数量须在 1~{MAX_WINDOWS} 个之间，当前 {len(days)} 个")
        if any(not isinstance(day, int) or day <= 0 for day in days):
            errors.append("观察周期必须都是正整数")
        if list(days) != sorted(set(days)):
            errors.append("观察周期必须严格递增且无重复")
        if days and max(days) > MAX_WINDOW_DAY:
            errors.append(f"单个观察窗口最大 {MAX_WINDOW_DAY} 天，当前第 {max(days)} 天")
        return errors

    def validate_window_result(
        self,
        plan: dict[str, Any],
        window_day: int,
        covered_members: Any,
        retention_rate: Any,
        conversion_rate: Any,
    ) -> list[str]:
        """保存前校验：观察窗口标准、样本量允许范围、留存上限。超界时不允许保存。"""
        errors: list[str] = []
        days = [int(day) for day in plan.get("观察周期列表") or []]
        if not isinstance(window_day, int) or window_day <= 0 or window_day > MAX_WINDOW_DAY:
            errors.append(f"窗口第 {window_day} 天超出观察窗口标准（1~{MAX_WINDOW_DAY} 的正整数）")
        elif window_day not in days:
            errors.append(f"窗口第 {window_day} 天不在计划观察周期 {days} 内")
        min_sample = max(MIN_SAMPLE_SIZE, int(plan.get("最小样本量") or MIN_SAMPLE_SIZE))
        max_sample = min(MAX_SAMPLE_SIZE, int(plan.get("最大样本量") or MAX_SAMPLE_SIZE))
        if not isinstance(covered_members, int) or not (min_sample <= covered_members <= max_sample):
            errors.append(f"样本量 {covered_members} 超出允许范围 [{min_sample}, {max_sample}]")
        cap = min(RETENTION_CAP, float(plan.get("留存上限") or RETENTION_CAP))
        if not isinstance(retention_rate, (int, float)) or not (0 <= retention_rate <= cap):
            errors.append(f"留存率 {retention_rate} 超出留存上限 {cap}")
        if not isinstance(conversion_rate, (int, float)) or not (0 <= conversion_rate <= 1):
            errors.append(f"转化率 {conversion_rate} 超出允许范围 [0, 1]")
        return errors

    # ---------- 窗口结果保存（幂等 + 并发守卫） ----------

    def save_window_result(
        self,
        plan_key: str,
        cohort_batch: str,
        window_day: int,
        payload: dict[str, Any],
        *,
        checkpoint_seq: int,
    ) -> tuple[bool, str]:
        """写入窗口结果：超界不允许保存；重复刷新只生效一次；较旧版本不能回写。"""
        plan = self.get_plan(plan_key)
        if plan is None:
            return False, f"留存刷新计划 {plan_key} 不存在"
        errors = self.validate_window_result(
            plan,
            window_day,
            payload.get("covered_members"),
            payload.get("retention_rate"),
            payload.get("conversion_rate"),
        )
        if errors:
            return False, "；".join(errors)
        existing = self._find_window(plan_key, cohort_batch, window_day)
        if existing is not None and existing.get("status") == "success":
            existing_seq = int(existing.get("checkpoint_seq", 0))
            # 并发：已落库的完整结果序号更新 → 较旧版本不能回写
            if existing_seq > checkpoint_seq:
                return False, "已落库的完整结果更新，较旧版本不能回写"
            # 幂等：同序号同覆盖版本的重复刷新 → 只生效一次
            incoming_coverage = payload.get("coverage_version") or plan.get("coverage_version")
            if existing_seq == checkpoint_seq and existing.get("coverage_version") == incoming_coverage:
                return False, "重复刷新同一窗口只生效一次，本次写入被忽略"
        row = {
            "plan_key": plan_key,
            "cohort_batch": cohort_batch,
            "window_day": window_day,
            "status": "success",
            "conversion_rate": payload.get("conversion_rate"),
            "retention_rate": payload.get("retention_rate"),
            "covered_members": payload.get("covered_members"),
            "failed_members": int(payload.get("failed_members") or 0),
            # 越界成员单列，不计入留存率
            "out_of_bound_members": int(payload.get("out_of_bound_members") or 0),
            "漏斗版本": plan.get("漏斗版本"),
            "划分事件": plan.get("划分事件"),
            "checkpoint_seq": checkpoint_seq,
            "coverage_version": payload.get("coverage_version") or plan.get("coverage_version"),
            "run_id": payload.get("run_id"),
            "computed_at": _now(),
        }
        if existing is None:
            row["id"] = max(
                (int(item.get("id", 0)) for item in store.rows(MODULE_WINDOW)), default=0
            ) + 1
            row["history"] = []
            store.rows(MODULE_WINDOW).append(row)
        else:
            # 保留历史审计：被覆盖的版本留在行内 history 里
            history = existing.setdefault("history", [])
            history.append(
                {
                    "status": existing.get("status"),
                    "conversion_rate": existing.get("conversion_rate"),
                    "retention_rate": existing.get("retention_rate"),
                    "漏斗版本": existing.get("漏斗版本"),
                    "checkpoint_seq": existing.get("checkpoint_seq"),
                    "coverage_version": existing.get("coverage_version"),
                    "run_id": existing.get("run_id"),
                    "computed_at": existing.get("computed_at"),
                }
            )
            existing.update(row)
        return True, "窗口结果已保存"

    # ---------- 增量刷新 ----------

    def refresh(
        self, plan_key: str, *, idempotency_key: str | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        """执行一次增量刷新：只处理新增、失效与待补窗口，其余留存结果沿用。"""
        with self._lock:
            plan = self.get_plan(plan_key)
            if plan is None:
                return None, f"留存刷新计划 {plan_key} 不存在"
            # 幂等：同一 idempotency_key 的刷新只生效一次
            if idempotency_key:
                for run in store.rows(MODULE_RUN):
                    if run.get("plan_key") == plan_key and run.get("idempotency_key") == idempotency_key:
                        replay = dict(run)
                        replay["duplicate"] = True
                        return replay, "重复刷新已被忽略，同一窗口只生效一次"
            # 触发条件
            reason = self.check_trigger(plan)
            if reason is not None:
                self._record_run(
                    plan,
                    strategy="rejected",
                    classified=None,
                    status="rejected",
                    message=reason,
                    idempotency_key=idempotency_key,
                )
                return None, reason
            # 观察窗口标准
            errors = self.validate_plan_windows(plan)
            if errors:
                message = "；".join(errors)
                self._record_run(
                    plan,
                    strategy="rejected",
                    classified=None,
                    status="rejected",
                    message=message,
                    idempotency_key=idempotency_key,
                )
                return None, message

            classified = self.classify_windows(plan)
            strategy = self.choose_strategy(classified)
            todo = (
                list(classified[CLASS_NEW])
                + list(classified[CLASS_STALE])
                + list(classified[CLASS_GAP])
            )
            if strategy == "full":
                # 失效占比过半：现有窗口数据不可信，整体重算
                todo += classified[CLASS_REUSED]
            coverage_before = plan.get("coverage_version")
            if not todo:
                run = self._record_run(
                    plan,
                    strategy=strategy,
                    classified=classified,
                    status="success",
                    message="没有待重算窗口，已完成与空窗口不重复计入，留存结果全部沿用",
                    idempotency_key=idempotency_key,
                    coverage_before=coverage_before,
                    coverage_after=coverage_before,
                )
                return run, "没有待重算窗口，留存结果全部沿用"

            next_seq = int(plan.get("coverage_seq", 0)) + 1
            new_coverage = f"cov-{next_seq}"
            run_id = f"RUN-{plan_key}-{next_seq:04d}"
            succeeded = 0
            skipped = 0
            failed_items: list[dict[str, str]] = []
            for key in todo:
                batch, day = _split_window_key(key)
                computed = self._compute_window(plan, batch, day)
                computed["run_id"] = run_id
                computed["coverage_version"] = new_coverage
                ok, message = self.save_window_result(
                    plan_key, batch, day, computed, checkpoint_seq=next_seq
                )
                if ok:
                    succeeded += 1
                elif "只生效一次" in message or "不能回写" in message:
                    skipped += 1
                else:
                    failed_items.append({"window": key, "reason": message})

            # 完成水位：只在一个群组的所有观察周期连续成功后推进
            for batch in self._covered_batches(plan):
                self._advance_checkpoint(plan, batch, next_seq)

            if succeeded:
                plan["coverage_seq"] = next_seq
                plan["coverage_version"] = new_coverage
                plan["最后计算时间"] = _now()[:10]
                # 漏斗详情与同期群结果读取同一覆盖版本
                funnel, cohort = self._find_definitions(plan)
                for definition in (funnel, cohort):
                    if definition is not None:
                        definition["最后计算时间"] = plan["最后计算时间"]
                        definition["覆盖版本"] = new_coverage
            # 已产生窗口记录的群组移出待算清单，后续由 新增/待补 机制跟踪
            plan["待算群组"] = [
                batch
                for batch in plan.get("待算群组") or []
                if not any(
                    row.get("plan_key") == plan_key and row.get("cohort_batch") == str(batch)
                    for row in store.rows(MODULE_WINDOW)
                )
            ]

            status = "success" if not failed_items else "partial"
            message = (
                f"增量刷新完成：新增 {len(classified[CLASS_NEW])}、失效 {len(classified[CLASS_STALE])}、"
                f"复用 {len(classified[CLASS_REUSED])}、待补 {len(classified[CLASS_GAP])}；"
                f"本次重算 {succeeded} 个窗口"
            )
            if failed_items:
                message += f"，{len(failed_items)} 个窗口超界未保存"
            run = self._record_run(
                plan,
                strategy=strategy,
                classified=classified,
                status=status,
                message=message,
                idempotency_key=idempotency_key,
                coverage_before=coverage_before,
                coverage_after=plan.get("coverage_version"),
                succeeded=succeeded,
                skipped=skipped,
                failed_items=failed_items,
            )
            return run, message

    def _compute_window(
        self, plan: dict[str, Any], cohort_batch: str, window_day: int
    ) -> dict[str, Any]:
        """模拟窗口计算：对同一 计划+群组+窗口+版本 结果确定，便于审计与复算核对。"""
        seed = int(
            hashlib.sha256(
                f"{plan['plan_key']}|{cohort_batch}|{window_day}|{plan.get('漏斗版本')}".encode()
            ).hexdigest()[:12],
            16,
        )
        covered = MIN_SAMPLE_SIZE + seed % 5000  # 落在样本量允许范围内
        out_of_bound = seed % 7  # 越界成员单列，不计入留存率
        retained = int(covered * (0.25 + (seed % 55) / 100))
        return {
            "covered_members": covered,
            "failed_members": seed % 9,
            "out_of_bound_members": out_of_bound,
            "retention_rate": round(retained / covered, 4),
            "conversion_rate": round(0.3 + (seed % 50) / 100, 4),
        }

    def _advance_checkpoint(
        self, plan: dict[str, Any], cohort_batch: str, checkpoint_seq: int
    ) -> dict[str, Any] | None:
        """完成水位沿连续成功的观察周期推进，遇到缺口即停；水位只前进不后退。"""
        days = sorted(int(day) for day in plan.get("观察周期列表") or [])
        streak: list[dict[str, Any]] = []
        for day in days:
            row = self._find_window(plan["plan_key"], cohort_batch, day)
            if (
                row is not None
                and row.get("status") == "success"
                and row.get("漏斗版本") == plan.get("漏斗版本")
                and row.get("划分事件") == plan.get("划分事件")
            ):
                streak.append(row)
            else:
                break
        if not streak:
            return None
        high = int(streak[-1]["window_day"])
        existing = next(
            (
                cp
                for cp in store.rows(MODULE_CHECKPOINT)
                if cp.get("plan_key") == plan["plan_key"] and cp.get("cohort_batch") == cohort_batch
            ),
            None,
        )
        if existing is not None and int(existing.get("window_day", 0)) >= high:
            return existing
        covered = sum(int(row.get("covered_members", 0)) for row in streak)
        failed = sum(int(row.get("failed_members", 0)) for row in streak)
        if existing is None:
            existing = {
                "id": max(
                    (int(cp.get("id", 0)) for cp in store.rows(MODULE_CHECKPOINT)), default=0
                )
                + 1,
                "plan_key": plan["plan_key"],
                "cohort_batch": cohort_batch,
            }
            store.rows(MODULE_CHECKPOINT).append(existing)
        existing.update(
            {
                "window_day": high,
                "covered_members": covered,
                "failed_members": failed,
                "checkpoint_seq": checkpoint_seq,
                "updated_at": _now(),
            }
        )
        return existing

    def _record_run(
        self,
        plan: dict[str, Any],
        *,
        strategy: str,
        classified: dict[str, list[str]] | None,
        status: str,
        message: str,
        idempotency_key: str | None,
        coverage_before: str | None = None,
        coverage_after: str | None = None,
        succeeded: int = 0,
        skipped: int = 0,
        failed_items: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """刷新审计：每次刷新都留痕，含四类窗口清单与覆盖版本变化。"""
        runs = store.rows(MODULE_RUN)
        run = {
            "id": max((int(item.get("id", 0)) for item in runs), default=0) + 1,
            "run_id": f"RUN-{max((int(item.get('id', 0)) for item in runs), default=0) + 1:04d}",
            "plan_key": plan.get("plan_key"),
            "strategy": strategy,
            "新增": list((classified or {}).get(CLASS_NEW, [])),
            "失效": list((classified or {}).get(CLASS_STALE, [])),
            "复用": list((classified or {}).get(CLASS_REUSED, [])),
            "待补": list((classified or {}).get(CLASS_GAP, [])),
            "succeeded": succeeded,
            "failed": len(failed_items or []),
            "skipped": skipped,
            "failed_items": list(failed_items or []),
            "status": status,
            "message": message,
            "idempotency_key": idempotency_key,
            "coverage_before": coverage_before,
            "coverage_after": coverage_after,
            "created_at": _now(),
        }
        runs.append(run)
        return run

    # ---------- 读取：覆盖版本视图与审计 ----------

    def get_plan_detail(self, plan_key: str) -> dict[str, Any] | None:
        plan = self.get_plan(plan_key)
        if plan is None:
            return None
        classified = self.classify_windows(plan)
        detail = self._plan_summary(plan)
        detail["窗口分类"] = classified
        detail["建议策略"] = self.choose_strategy(classified)
        detail["窗口明细"] = [
            row for row in store.rows(MODULE_WINDOW) if row.get("plan_key") == plan_key
        ]
        detail["水位明细"] = [
            row for row in store.rows(MODULE_CHECKPOINT) if row.get("plan_key") == plan_key
        ]
        return detail

    def get_coverage(self, plan_key: str) -> dict[str, Any] | None:
        """覆盖版本视图：漏斗详情与同期群结果读取同一覆盖版本。"""
        plan = self.get_plan(plan_key)
        if plan is None:
            return None
        funnel, cohort = self._find_definitions(plan)
        effective = [
            row
            for row in store.rows(MODULE_WINDOW)
            if row.get("plan_key") == plan_key
            and row.get("status") == "success"
            and row.get("漏斗版本") == plan.get("漏斗版本")
            and row.get("划分事件") == plan.get("划分事件")
        ]
        effective.sort(key=lambda row: (row["cohort_batch"], int(row["window_day"])))
        checkpoints = [
            row for row in store.rows(MODULE_CHECKPOINT) if row.get("plan_key") == plan_key
        ]
        return {
            "plan_key": plan_key,
            "coverage_version": plan.get("coverage_version"),
            "funnel": {
                "漏斗编号": plan.get("漏斗编号"),
                "漏斗版本": plan.get("漏斗版本"),
                "观察周期天": (funnel or {}).get("观察周期天"),
                "最后计算时间": (funnel or {}).get("最后计算时间"),
                "覆盖版本": (funnel or {}).get("覆盖版本"),
            },
            "cohort": {
                "群组编号": plan.get("群组编号"),
                "划分事件": plan.get("划分事件"),
                "观察周期天": (cohort or {}).get("观察周期天"),
                "最后计算时间": (cohort or {}).get("最后计算时间"),
                "覆盖版本": (cohort or {}).get("覆盖版本"),
            },
            "windows": effective,
            "checkpoints": checkpoints,
            "最后计算时间": plan.get("最后计算时间"),
        }

    def list_audits(self, plan_key: str | None = None) -> list[dict[str, Any]]:
        runs = store.rows(MODULE_RUN)
        if plan_key:
            runs = [run for run in runs if run.get("plan_key") == plan_key]
        return sorted(runs, key=lambda run: int(run.get("id", 0)), reverse=True)
