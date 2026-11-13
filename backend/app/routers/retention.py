"""漏斗留存增量刷新接口：漏斗与同期群联合入口，按覆盖版本增量重算观察窗口。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload
from app.services.retention import RetentionService

router = APIRouter(prefix="/api/retention", tags=["漏斗留存刷新"])

service = RetentionService()


@router.get("/plans", response_model=dict)
def list_plans() -> dict[str, Any]:
    """联合计划列表：每个计划绑定一个漏斗版本与一个同期群划分事件。"""
    plans = service.list_plans()
    return {"items": plans, "total": len(plans)}


@router.get("/plans/{plan_key}", response_model=dict)
def get_plan_detail(plan_key: str) -> dict[str, Any]:
    """计划详情：窗口按 新增/失效/复用/待补 分类预览，并给出建议增量策略。"""
    detail = service.get_plan_detail(plan_key)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"留存刷新计划 {plan_key} 不存在")
    return detail


@router.post("/plans/{plan_key}/refresh", response_model=ActionResult)
def refresh_plan(plan_key: str, payload: EntryPayload) -> ActionResult:
    """触发增量刷新：只处理新增、失效与待补窗口；带幂等键时重复刷新只生效一次。"""
    idempotency_key = payload.values.get("idempotency_key")
    idempotency_key = str(idempotency_key).strip() if idempotency_key else None
    run, message = service.refresh(plan_key, idempotency_key=idempotency_key or None)
    if run is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=run)


@router.get("/plans/{plan_key}/coverage", response_model=dict)
def get_coverage(plan_key: str) -> dict[str, Any]:
    """覆盖版本视图：漏斗详情与同期群结果读取同一覆盖版本。"""
    coverage = service.get_coverage(plan_key)
    if coverage is None:
        raise HTTPException(status_code=404, detail=f"留存刷新计划 {plan_key} 不存在")
    return coverage


@router.get("/audits", response_model=dict)
def list_audits(
    plan_key: str | None = Query(default=None, description="按计划标识过滤刷新审计"),
) -> dict[str, Any]:
    """刷新审计历史：每次刷新的窗口分类、成败与覆盖版本变化都留痕。"""
    audits = service.list_audits(plan_key)
    return {"items": audits, "total": len(audits)}
