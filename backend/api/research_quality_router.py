# -*- coding: utf-8 -*-
"""Research Quality API Router"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from backend.security.auth import Principal, get_current_user, require_matching_identity
from backend.services import research_quality


def create_research_quality_router() -> APIRouter:
    """创建 Research Quality 路由"""
    router = APIRouter()

    @router.get("/api/research-quality")
    async def get_research_quality_endpoint(
        session_id: str = Query(..., description="会话 ID"),
        user_id: str = Query("default_user", description="用户 ID"),
        symbol: str | None = Query(None, description="可选：只看某个标的的质量"),
        current_user: Principal = Depends(get_current_user),
    ) -> dict[str, Any]:
        """
        获取研究库健康度

        返回研究库的健康分数、质量问题清单和建议操作。
        """
        require_matching_identity(
            principal=current_user,
            provided=session_id,
            expected=current_user.session_id,
            field_name="session_id",
        )

        result = research_quality.get_research_quality(
            session_id=session_id,
            user_id=user_id,
            symbol=symbol,
        )

        return result

    return router
