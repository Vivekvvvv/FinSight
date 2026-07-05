# -*- coding: utf-8 -*-
"""Today Workspace 聚合路由

聚合用户每日工作台所需的全部数据：
- Portfolio 风险快照
- Watchlist 动态
- Alert 事件
- 待复查报告
- 下一步操作建议
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.security.auth import Principal, get_current_user, require_matching_identity
from backend.demo_mode import demo_today_workspace, is_demo_mode
from backend.services.next_actions import generate_next_actions
from backend.services.reports_to_review import get_reports_to_review


@dataclass(frozen=True)
class TodayRouterDeps:
    """Today 路由依赖注入"""

    resolve_thread_id: Callable[[Optional[str]], str]
    memory_service: Any  # MemoryService instance
    subscription_service: Any  # SubscriptionService instance


def _provided_user_id(value: str | None) -> str | None:
    """标准化 user_id"""
    text = str(value or "").strip()
    return None if text in {"", "default_user"} else text


def create_today_router(deps: TodayRouterDeps) -> APIRouter:
    router = APIRouter(tags=["Today"])

    @router.get("/api/today")
    async def get_today_workspace(
        session_id: str,
        user_id: str = "default_user",
        current_user: Principal = Depends(get_current_user),
    ):
        """今日工作台聚合数据

        返回：
        - as_of: 数据时间戳
        - freshness_status: 数据新鲜度
        - summary: 今日摘要
        - portfolio_snapshot: 持仓快照（总市值、总盈亏、风险持仓）
        - watchlist_movers: 自选股动态（P2）
        - alert_feed: 最近告警事件
        - reports_to_review: 待复查报告
        - next_actions: 推荐操作
        """
        try:
            # 身份校验
            require_matching_identity(
                principal=current_user,
                provided=_provided_user_id(user_id),
                expected=current_user.user_id,
                field_name="user_id",
            )
            # session_id 是持仓/报告的查询键（get_positions），必须绑定认证主体，
            # 否则可传他人 session_id（private:<victim>:default）读取其持仓。
            require_matching_identity(
                principal=current_user,
                provided=session_id,
                expected=current_user.session_id,
                field_name="session_id",
            )
            normalized_session = deps.resolve_thread_id(session_id)
            resolved_user_id = user_id if current_user.auth_type == "dev" and user_id else current_user.user_id
            if is_demo_mode():
                return demo_today_workspace(normalized_session)

            # 导入必要的服务
            from backend.services.portfolio_store import get_positions
            from backend.services.report_index import get_report_index_store

            # 并发获取基础数据
            positions_raw, watchlist_items = await asyncio.gather(
                asyncio.to_thread(get_positions, normalized_session),
                asyncio.to_thread(deps.memory_service.list_watchlist_items, resolved_user_id) if deps.memory_service else asyncio.sleep(0, result=[]),
                return_exceptions=True,
            )

            # 处理异常
            if isinstance(positions_raw, Exception):
                positions_raw = []
            if isinstance(watchlist_items, Exception):
                watchlist_items = []

            # 构造 portfolio_summary（简化版，不调用实时行情）
            portfolio_summary = {
                "success": True,
                "session_id": normalized_session,
                "positions": positions_raw,
                "count": len(positions_raw),
                "total_value": None,
                "total_cost": sum(p.get("shares", 0) * (p.get("avg_cost") or 0) for p in positions_raw),
                "total_pnl": None,
            }

            # 获取 alerts
            alert_events = []
            if deps.subscription_service:
                try:
                    # 尝试从 memory_service 获取 email（假设存储在 user_profile 中）
                    email = resolved_user_id if "@" in resolved_user_id else f"{resolved_user_id}@example.com"
                    alert_events = await asyncio.to_thread(deps.subscription_service.list_alert_events, email, limit=10)
                except Exception:
                    pass

            # 计算待复查报告
            watchlist_tickers = [w.get("ticker", "") for w in watchlist_items if w.get("ticker")]
            portfolio_tickers = [
                p.get("ticker", "")
                for p in portfolio_summary.get("positions", [])
                if p.get("ticker")
            ]
            reports_to_review = await asyncio.to_thread(
                get_reports_to_review,
                normalized_session,
                watchlist_tickers,
                portfolio_tickers,
                stale_days=7,
                limit=10,
            )

            # 生成操作建议
            next_actions = generate_next_actions(
                portfolio_summary,
                watchlist_items,
                reports_to_review,
                alert_events,
            )

            # 计算风险持仓
            risk_positions = []
            for pos in portfolio_summary.get("positions", []):
                unrealized_pnl = pos.get("unrealized_pnl")
                cost_basis = pos.get("cost_basis")
                if unrealized_pnl is not None and cost_basis and cost_basis > 0:
                    pnl_pct = unrealized_pnl / cost_basis
                    if pnl_pct < -0.05:
                        risk_positions.append(pos)

            # 生成摘要
            watchlist_count = len(watchlist_items)
            portfolio_count = len(portfolio_summary.get("positions", []))
            risk_count = len(risk_positions)
            summary_parts = []
            if watchlist_count > 0:
                summary_parts.append(f"{watchlist_count} 只自选")
            if portfolio_count > 0:
                summary_parts.append(f"{portfolio_count} 只持仓")
            if risk_count > 0:
                summary_parts.append(f"{risk_count} 只风险提示")
            summary = "今日关注：" + "、".join(summary_parts) if summary_parts else "暂无数据，建议添加自选或持仓"

            return {
                "success": True,
                "as_of": datetime.now(timezone.utc).isoformat(),
                "freshness_status": "live",
                "summary": summary,
                "portfolio_snapshot": {
                    "total_value": portfolio_summary.get("total_value"),
                    "total_pnl": portfolio_summary.get("total_pnl"),
                    "total_cost": portfolio_summary.get("total_cost"),
                    "risk_positions": risk_positions,
                    "position_count": portfolio_count,
                },
                "watchlist_movers": [],  # P2：实时涨跌幅需额外行情调用
                "alert_feed": alert_events[:5],
                "reports_to_review": reports_to_review,
                "next_actions": next_actions,
            }

        except HTTPException:
            raise
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "as_of": datetime.now(timezone.utc).isoformat(),
                "summary": "数据加载失败",
                "portfolio_snapshot": {"total_value": None, "total_pnl": None, "risk_positions": []},
                "watchlist_movers": [],
                "alert_feed": [],
                "reports_to_review": [],
                "next_actions": [],
            }

    return router
