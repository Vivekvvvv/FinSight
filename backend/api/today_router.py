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
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.security.auth import Principal, get_current_user, require_matching_identity
from backend.demo_mode import demo_today_workspace, is_demo_mode
from backend.services.next_actions import generate_next_actions
from backend.services.reports_to_review import get_reports_to_review

logger = logging.getLogger(__name__)


# 候选字段按"最后写入该行记录的时刻"排序；portfolio_store 用 updated_at，
# memory 的自选股用 created_at。
_AS_OF_FIELDS = ("as_of", "updated_at", "created_at")


def _latest_as_of(*rows: Any) -> str:
    """取本地持仓/自选记录里最新的写入时刻；一条都取不到时返回 ""。

    此前这里恒填 `datetime.now()`——前端 DataSourceBadge 会把它渲染成
    "10/19 15:04 本地缓存"，也就是"这些持仓/自选是此刻的"。实际上接口只读本地
    存储，从没做过实时取数；一条记录都没有时更是把一个空的本地读操作标成刚更新
    （项目规则 2、finsight-silent-success-forbidden）。
    """
    latest = ""
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in _AS_OF_FIELDS:
            value = row.get(key)
            if not isinstance(value, str):
                continue
            text = value.strip()
            if text and text > latest:
                latest = text
    return latest


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
            positions_diagnostics: dict[str, Any] = {}
            positions_raw, watchlist_items = await asyncio.gather(
                asyncio.to_thread(get_positions, normalized_session, positions_diagnostics),
                asyncio.to_thread(deps.memory_service.list_watchlist_items, resolved_user_id) if deps.memory_service else asyncio.sleep(0, result=[]),
                return_exceptions=True,
            )

            # 存储故障必须显式失败：替换成 [] 会让前端把“读取失败”渲染成
            # “没有持仓/自选”，用户以为数据没了，监控也看不到信号（项目规则 2）。
            if isinstance(positions_raw, Exception):
                logger.error("today portfolio store failed")
                raise HTTPException(status_code=503, detail="Portfolio data unavailable") from positions_raw
            if isinstance(watchlist_items, Exception):
                logger.error("today watchlist store failed")
                raise HTTPException(status_code=503, detail="Watchlist data unavailable") from watchlist_items

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
            alert_feed_unavailable = False
            if deps.subscription_service:
                # 订阅按邮箱存储（/api/subscribe 用 principal.email 落库）。以前这里
                # 用 user_id 拼 "<user_id>@example.com" 去查，而 JWT/api_key 用户的
                # user_id 普遍不是邮箱，查询键永远对不上，提醒面板对这类用户恒为空。
                email = (current_user.email or "").strip()
                if not email and "@" in resolved_user_id:
                    email = resolved_user_id
                if email:
                    try:
                        alert_events = await asyncio.to_thread(
                            deps.subscription_service.list_alert_events, email, limit=10
                        )
                    except Exception as exc:
                        logger.warning("today alert events unavailable")
                        # 空列表会被前端渲染成“没有告警”；读取失败必须显式标记，
                        # 否则用户和监控都看不到告警服务故障（项目规则 2）。
                        alert_feed_unavailable = True

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
            invalid_positions = positions_diagnostics.get("invalid_positions") or []
            if invalid_positions:
                # 解析不出的持仓行被逐条跳过：它们不会出现在 portfolio_count /
                # next_actions 里，不标注会让工作台读成"组合本来就这么大"（项目规则 2）。
                summary_parts.append(f"{len(invalid_positions)} 行持仓无法解析")
            summary = "今日关注：" + "、".join(summary_parts) if summary_parts else "暂无数据，建议添加自选或持仓"

            response = {
                "success": True,
                "as_of": _latest_as_of(*watchlist_items, *(portfolio_summary.get("positions") or [])),
                # 该接口只读本地持仓/自选/报告存储，不调用任何实时行情
                # （total_value/total_pnl 为 None、watchlist_movers 恒为空），
                # 不能对外声称 live；cached 表示"本地持久化数据，非实时报价"。
                "freshness_status": "cached",
                "summary": summary,
                "portfolio_snapshot": {
                    "total_value": portfolio_summary.get("total_value"),
                    "total_pnl": portfolio_summary.get("total_pnl"),
                    "total_cost": portfolio_summary.get("total_cost"),
                    "risk_positions": risk_positions,
                    "position_count": portfolio_count,
                },
                "watchlist_movers": [],  # P2：实时涨跌幅需额外行情调用
                # movers 恒为空只代表异动未取数，不代表用户没有自选；前端据此
                # 区分"没有自选"与"有自选但异动暂不可用"（项目规则 2）。
                "watchlist_count": watchlist_count,
                "alert_feed": alert_events[:5],
                "alert_feed_unavailable": alert_feed_unavailable,
                "degraded": alert_feed_unavailable or bool(invalid_positions),
                "reports_to_review": reports_to_review,
                "next_actions": next_actions,
            }
            if invalid_positions:
                response["invalid_positions"] = invalid_positions
                response["fallback_reason"] = "invalid_stored_positions"
            return response

        except HTTPException:
            raise
        except Exception as exc:
            # 不再压成 200+空骨架（审计 F/项目规则 3）：空骨架会被前端当正常数据渲染，
            # 后端故障对用户和监控完全不可见；WelcomePage 已有 catch+errorMsg 处理 500。
            logger.error("今日工作台生成失败")
            raise HTTPException(status_code=500, detail="Internal server error") from exc

    return router
