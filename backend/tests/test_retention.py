"""漏斗留存增量刷新引擎测试：续算样例、幂等、并发守卫、校验阈值与审计。"""
from __future__ import annotations

import copy
import unittest

from app.seed import SEED_ROWS
from app.services.retention import (
    CLASS_GAP,
    CLASS_NEW,
    CLASS_REUSED,
    CLASS_STALE,
    MODULE_CHECKPOINT,
    MODULE_PLAN,
    MODULE_RUN,
    MODULE_WINDOW,
    RetentionService,
)
from app.store import store

PLAN = "COHO-ACTIVATION_30D"
BATCH = "2026-10-08"


def reset_tables() -> None:
    for name in (MODULE_PLAN, MODULE_WINDOW, MODULE_CHECKPOINT, MODULE_RUN, "funnel", "cohort"):
        store._tables[name] = copy.deepcopy(SEED_ROWS[name])


def good_payload(**overrides):
    payload = {
        "covered_members": 500,
        "failed_members": 2,
        "out_of_bound_members": 1,
        "retention_rate": 0.4,
        "conversion_rate": 0.5,
    }
    payload.update(overrides)
    return payload


class RefreshSampleTest(unittest.TestCase):
    """续算样例：已覆盖第 1、2、3、7、14 天，第 30 天窗口在 2026-10-08 失败。"""

    def setUp(self) -> None:
        reset_tables()
        self.service = RetentionService()

    def windows(self, batch: str) -> dict[int, dict]:
        return {
            int(row["window_day"]): row
            for row in store.rows(MODULE_WINDOW)
            if row["plan_key"] == PLAN and row["cohort_batch"] == batch
        }

    def checkpoint(self, batch: str) -> dict | None:
        for row in store.rows(MODULE_CHECKPOINT):
            if row["plan_key"] == PLAN and row["cohort_batch"] == batch:
                return row
        return None

    def test_classify_distinguishes_four_window_kinds(self):
        plan = self.service.get_plan(PLAN)
        classified = self.service.classify_windows(plan)
        # 待补：第 30 天失败窗口
        self.assertEqual(classified[CLASS_GAP], [f"{BATCH}#30"])
        # 失效：2026-10-07 第 1 天是旧漏斗版本 v2 算的
        self.assertEqual(classified[CLASS_STALE], ["2026-10-07#1"])
        # 复用：前五个成功窗口 + 2026-10-07 第 2 天
        self.assertEqual(len(classified[CLASS_REUSED]), 6)
        # 新增：缺失群组 2026-10-09 全部窗口 + 2026-10-07 缺失窗口
        self.assertIn("2026-10-09#1", classified[CLASS_NEW])
        self.assertIn("2026-10-07#30", classified[CLASS_NEW])
        self.assertEqual(len(classified[CLASS_NEW]), 10)

    def test_incremental_refresh_resumes_from_gap(self):
        before = {day: dict(row) for day, row in self.windows(BATCH).items()}
        run, message = self.service.refresh(PLAN, idempotency_key="sample")
        self.assertIsNotNone(run, message)
        self.assertEqual(run["strategy"], "incremental")
        after = self.windows(BATCH)
        # 前五个窗口的转化率与留存结果继续复用，未被重算
        for day in (1, 2, 3, 7, 14):
            self.assertEqual(after[day]["conversion_rate"], before[day]["conversion_rate"])
            self.assertEqual(after[day]["retention_rate"], before[day]["retention_rate"])
            self.assertEqual(after[day]["computed_at"], before[day]["computed_at"])
        # 只补第 30 天：失败窗口重算成功
        self.assertEqual(after[30]["status"], "success")
        self.assertIsNotNone(after[30]["retention_rate"])
        # 失败窗口已成功的转化率留在 history 里供审计
        self.assertEqual(after[30]["history"][-1]["conversion_rate"], 0.31)
        # 完成水位从第 14 天推进到第 30 天
        checkpoint = self.checkpoint(BATCH)
        self.assertEqual(checkpoint["window_day"], 30)
        self.assertEqual(checkpoint["cohort_batch"], BATCH)
        self.assertIn("covered_members", checkpoint)
        self.assertIn("failed_members", checkpoint)
        self.assertIn("checkpoint_seq", checkpoint)
        # 覆盖版本推进到 cov-6
        plan = self.service.get_plan(PLAN)
        self.assertEqual(plan["coverage_version"], "cov-6")

    def test_checkpoint_records_required_fields(self):
        self.service.refresh(PLAN, idempotency_key="fields")
        checkpoint = self.checkpoint(BATCH)
        for field in ("window_day", "cohort_batch", "covered_members", "failed_members", "checkpoint_seq"):
            self.assertIn(field, checkpoint)
        # 越界成员单列，不计入留存率
        window = self.windows(BATCH)[30]
        self.assertIn("out_of_bound_members", window)
        self.assertGreaterEqual(window["out_of_bound_members"], 0)

    def test_repeat_refresh_same_windows_only_once(self):
        run1, _ = self.service.refresh(PLAN, idempotency_key="same-key")
        run2, message = self.service.refresh(PLAN, idempotency_key="same-key")
        self.assertTrue(run2["duplicate"])
        self.assertEqual(run1["run_id"], run2["run_id"])
        self.assertIn("只生效一次", message)
        # 窗口没有产生额外历史版本
        for row in store.rows(MODULE_WINDOW):
            if row["plan_key"] == PLAN:
                self.assertLessEqual(len(row.get("history", [])), 1)

    def test_second_refresh_reuses_everything(self):
        self.service.refresh(PLAN, idempotency_key="first")
        run, message = self.service.refresh(PLAN, idempotency_key="second")
        self.assertEqual(run["succeeded"], 0)
        self.assertIn("沿用", message)
        # 已完成窗口不重复计入
        self.assertEqual(run["新增"], [])
        self.assertEqual(run["待补"], [])

    def test_older_version_cannot_overwrite_committed_result(self):
        ok, _ = self.service.save_window_result(
            PLAN, BATCH, 30, good_payload(), checkpoint_seq=6
        )
        self.assertTrue(ok)
        # 较旧版本回写同一观察周期：以已落库的完整结果为准
        ok, message = self.service.save_window_result(
            PLAN, BATCH, 30, good_payload(retention_rate=0.9), checkpoint_seq=5
        )
        self.assertFalse(ok)
        self.assertIn("不能回写", message)
        window = self.windows(BATCH)[30]
        self.assertEqual(window["retention_rate"], 0.4)
        # 同版本重复写入也只生效一次
        ok, message = self.service.save_window_result(
            PLAN, BATCH, 30, good_payload(retention_rate=0.9), checkpoint_seq=6
        )
        self.assertFalse(ok)
        self.assertIn("只生效一次", message)

    def test_out_of_bound_results_are_not_saved(self):
        # 样本量低于允许范围下限
        ok, message = self.service.save_window_result(
            PLAN, BATCH, 30, good_payload(covered_members=3), checkpoint_seq=6
        )
        self.assertFalse(ok)
        self.assertIn("样本量", message)
        # 留存率超过留存上限
        ok, message = self.service.save_window_result(
            PLAN, BATCH, 30, good_payload(retention_rate=1.2), checkpoint_seq=6
        )
        self.assertFalse(ok)
        self.assertIn("留存上限", message)
        # 窗口不在观察周期标准内
        ok, message = self.service.save_window_result(
            PLAN, BATCH, 5, good_payload(), checkpoint_seq=6
        )
        self.assertFalse(ok)
        self.assertIn("观察周期", message)
        # 超界结果确实没有落库
        self.assertEqual(self.windows(BATCH)[30]["status"], "failed")

    def test_trigger_condition_blocks_refresh_and_audits(self):
        funnel = next(row for row in store.rows("funnel") if row["漏斗编号"] == "FUNN-ACTIVATION")
        funnel["status"] = "草稿"
        run, message = self.service.refresh(PLAN)
        self.assertIsNone(run)
        self.assertIn("触发条件", message)
        audits = self.service.list_audits(PLAN)
        self.assertEqual(audits[0]["status"], "rejected")

    def test_coverage_view_shared_by_funnel_and_cohort(self):
        self.service.refresh(PLAN, idempotency_key="coverage")
        coverage = self.service.get_coverage(PLAN)
        self.assertEqual(coverage["coverage_version"], "cov-6")
        # 漏斗详情与同期群结果读取同一覆盖版本
        self.assertEqual(coverage["funnel"]["覆盖版本"], "cov-6")
        self.assertEqual(coverage["cohort"]["覆盖版本"], "cov-6")
        self.assertEqual(coverage["funnel"]["最后计算时间"], coverage["cohort"]["最后计算时间"])
        # 覆盖视图只含当前版本一致的成功窗口
        for window in coverage["windows"]:
            self.assertEqual(window["status"], "success")
            self.assertEqual(window["漏斗版本"], "v3")

    def test_audit_trail_kept_for_every_refresh(self):
        before = len(self.service.list_audits(PLAN))
        self.service.refresh(PLAN, idempotency_key="audit")
        audits = self.service.list_audits(PLAN)
        self.assertEqual(len(audits), before + 1)
        latest = audits[0]
        self.assertEqual(latest["coverage_before"], "cov-5")
        self.assertEqual(latest["coverage_after"], "cov-6")
        self.assertEqual(latest["待补"], [f"{BATCH}#30"])
        self.assertEqual(latest["失效"], ["2026-10-07#1"])


if __name__ == "__main__":
    unittest.main()
