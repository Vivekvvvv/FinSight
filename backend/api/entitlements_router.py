# -*- coding: utf-8 -*-
"""Entitlements / Plan API.

GET  /api/me                       当前请求主体身份
GET  /api/me/entitlements          当前用户的 plan + features + limits
POST /api/admin/entitlements/plan  admin 更改任意用户 plan (开发/演示用)
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.security.auth import (
    Principal,
    get_current_user,
    require_admin_principal,
)
from backend.services.entitlements import (
    PLAN_FEATURES,
    PLAN_LIMITS,
    VALID_PLANS,
    build_usage_view,
    get_entitlements_service,
    normalize_plan,
)

logger = logging.getLogger(__name__)


class SetPlanRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    plan: str = Field(..., description=f"One of: {', '.join(VALID_PLANS)}")
    source: str | None = Field(default="admin_api", max_length=64)


def create_entitlements_router() -> APIRouter:
    router = APIRouter(tags=["Entitlements"])

    @router.get("/api/me")
    async def get_me(current_user: Principal = Depends(get_current_user)) -> Dict[str, Any]:
        """当前请求主体身份, 供 Vue 启动时初始化本地身份状态。"""
        return {
            "success": True,
            "user_id": current_user.user_id,
            "email": current_user.email,
            "role": current_user.role,
            "auth_type": current_user.auth_type,
        }

    @router.get("/api/me/entitlements")
    async def get_my_entitlements(current_user: Principal = Depends(get_current_user)) -> Dict[str, Any]:
        service = get_entitlements_service()
        ent = service.get_entitlements(current_user.user_id, role=current_user.role)
        # 同时返回 usage view, 前端一次拉取就能拿到 plan + 实时配额
        usage = build_usage_view(current_user.user_id, email=current_user.email)
        return {"success": True, "usage": usage, **ent}

    @router.get("/api/me/usage")
    async def get_my_usage(current_user: Principal = Depends(get_current_user)) -> Dict[str, Any]:
        """轻量端点 — 用于前端定时刷新 usage (例如 PlanBadge tooltip)。"""
        usage = build_usage_view(current_user.user_id, email=current_user.email)
        plan = get_entitlements_service().get_plan(current_user.user_id, role=current_user.role)
        return {"success": True, "user_id": current_user.user_id, "plan": plan, "usage": usage}

    @router.get("/api/plans")
    async def list_plans() -> Dict[str, Any]:
        """公开端点 — 列出所有 plan 的 features 与 limits, 用于前端套餐对比页。"""
        plans = []
        for plan_id in VALID_PLANS:
            plans.append({
                "id": plan_id,
                "name": plan_id.capitalize(),
                "features": dict(PLAN_FEATURES.get(plan_id, {})),
                "limits": dict(PLAN_LIMITS.get(plan_id, {})),
            })
        return {"success": True, "plans": plans}

    @router.post("/api/admin/entitlements/plan")
    async def admin_set_plan(
        request: SetPlanRequest,
        current_user: Principal = Depends(require_admin_principal),
    ) -> Dict[str, Any]:
        if request.plan.strip().lower() not in VALID_PLANS:
            raise HTTPException(status_code=422, detail=f"plan must be one of {VALID_PLANS}")

        service = get_entitlements_service()
        try:
            normalized = service.set_plan(
                request.user_id,
                normalize_plan(request.plan),
                source=request.source or "admin_api",
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid entitlement request") from exc

        logger.info(
            "[Audit] admin set plan user_id=%s plan=%s actor=%s",
            request.user_id,
            normalized,
            current_user.user_id,
        )
        return {"success": True, "user_id": request.user_id, "plan": normalized}

    return router


__all__ = ["create_entitlements_router"]
