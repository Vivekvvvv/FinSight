# -*- coding: utf-8 -*-
"""What Changed API Router"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query

from backend.security.auth import Principal, get_current_user, require_matching_identity
from backend.services import what_changed


def create_what_changed_router() -> APIRouter:
    """创建 What Changed 路由"""
    router = APIRouter()

    @router.get("/api/what-changed")
    async def get_what_changed_endpoint(
        session_id: str = Query(..., description="会话 ID"),
        user_id: str = Query("default_user", description="用户 ID"),
        symbol: str | None = Query(None, description="可选：只看某个标的的变化"),
        limit: int = Query(5, ge=1, le=20, description="返回数量，默认 5，最多 20"),
        current_user: Principal = Depends(get_current_user),
    ) -> dict[str, Any]:
        """
        获取最重要的变化列表

        聚合 Timeline、Reports、Notes 等数据源，
        按规则评分并返回最重要的 3-5 条变化。
        """
        require_matching_identity(
            principal=current_user,
            provided=session_id,
            expected=current_user.session_id,
            field_name="session_id",
        )

        items = what_changed.get_what_changed(
            session_id=session_id,
            user_id=user_id,
            symbol=symbol,
            limit=limit,
        )

        return {
            "success": True,
            "as_of": datetime.now(timezone.utc).isoformat(),
            "items": items,
            "count": len(items),
        }

    return router
