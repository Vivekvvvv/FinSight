# -*- coding: utf-8 -*-
"""Evidence Timeline API Router"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.security.auth import Principal, get_current_user, require_matching_identity
from backend.demo_mode import demo_timeline, is_demo_mode
from backend.services import timeline_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TimelineRouterDeps:
    """Timeline 路由依赖注入"""
    resolve_thread_id: Callable[[Optional[str]], str]


def _provided_user_id(value: str | None) -> str | None:
    """标准化 user_id"""
    text = str(value or "").strip()
    return None if text in {"", "default_user"} else text


def create_timeline_router(deps: TimelineRouterDeps) -> APIRouter:
    router = APIRouter(tags=["Timeline"])

    @router.get("/api/timeline/{symbol}")
    def get_timeline(
        symbol: str,
        session_id: str = Query(..., description="会话 ID"),
        user_id: str = Query("default_user", description="用户 ID"),
        event_type: Optional[str] = Query(None, description="事件类型过滤"),
        from_date: Optional[str] = Query(None, alias="from", description="开始日期 ISO"),
        to_date: Optional[str] = Query(None, alias="to", description="结束日期 ISO"),
        limit: int = Query(50, ge=1, le=200, description="返回数量限制"),
        current_user: Principal = Depends(get_current_user),
    ):
        """获取指定标的的事件时间线

        聚合 Reports / Notes / Alerts / Risk 等多个来源的事件，
        提供统一的研究过程复盘视图。

        def 而非 async def：timeline_service.get_timeline 是同步 SQLite 聚合读，
        async 下直接调用会占用事件循环；def 由 FastAPI 放线程池执行。
        """
        try:
            # 身份校验
            provided_user_id = _provided_user_id(user_id)
            require_matching_identity(
                principal=current_user,
                provided=provided_user_id,
                expected=current_user.user_id,
                field_name="user_id",
            )
            effective_user_id = provided_user_id or current_user.user_id
            # session_id 是报告事件的查询键（timeline_service 仅按它过滤），
            # 必须绑定认证主体，防止伪造 session_id 读取他人报告时间线。
            require_matching_identity(
                principal=current_user,
                provided=session_id,
                expected=current_user.session_id,
                field_name="session_id",
            )
            normalized_session = deps.resolve_thread_id(session_id)

            # 验证 event_type
            valid_types = {"report", "alert", "note", "risk", "evidence", "watchlist", None}
            if event_type and event_type not in valid_types:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid event_type: {event_type}. Must be one of {valid_types}",
                )

            # 获取时间线
            events = timeline_service.get_timeline(
                symbol=symbol.upper(),
                session_id=normalized_session,
                user_id=effective_user_id,
                event_type=event_type,  # type: ignore
                from_date=from_date,
                to_date=to_date,
                limit=limit,
            )
            if is_demo_mode() and not events and event_type in {None, "report", "note"}:
                events = [
                    event for event in demo_timeline(symbol.upper(), normalized_session, limit=limit)
                    if event_type is None or event.get("event_type") == event_type
                ]

            return {
                "success": True,
                "symbol": symbol.upper(),
                "count": len(events),
                "events": events,
            }

        except HTTPException:
            raise  # 身份 403 / event_type 400 在 try 内抛出，不得被下面的宽 except 重包成 500
        except ValueError as exc:
            # 路由层无显式 raise ValueError；服务层 ISO 解析会吞掉 ValueError。
            # 该分支仅作防御，禁止回传 str(exc) 以免未来服务/解析路径泄露内部细节。
            logger.warning("timeline invalid value: %s", type(exc).__name__)
            raise HTTPException(status_code=400, detail="Invalid timeline request") from exc
        except Exception as exc:
            logger.error("获取时间线失败: %s", type(exc).__name__)
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    return router
