# -*- coding: utf-8 -*-
"""Portfolio Risk Lens API Router"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.security.auth import Principal, get_current_user, require_matching_identity
from backend.services.portfolio_risk_lens import calculate_portfolio_risk_lens
from backend.services.risk_snapshots import get_risk_snapshots_history


@dataclass(frozen=True)
class RiskLensRouterDeps:
    """Risk Lens 路由依赖注入"""
    resolve_thread_id: Callable[[Optional[str]], str]


def _provided_user_id(value: str | None) -> str | None:
    """标准化 user_id"""
    text = str(value or "").strip()
    return None if text in {"", "default_user"} else text


def create_risk_lens_router(deps: RiskLensRouterDeps) -> APIRouter:
    router = APIRouter(tags=["Risk Lens"])

    @router.get("/api/portfolio/risk-lens")
    async def get_portfolio_risk_lens(
        session_id: str,
        user_id: str = "default_user",
        current_user: Principal = Depends(get_current_user),
    ):
        """Portfolio 风险透镜

        分析持仓风险：集中度、行业暴露、币种暴露、亏损、数据新鲜度、研究覆盖

        返回：
        - risk_score: 总风险评分（0-100）
        - concentration_risk: 集中度风险列表
        - sector_exposure: 行业暴露
        - currency_exposure: 币种暴露
        - market_exposure: 市场暴露
        - loss_positions: 亏损持仓
        - stale_research: 过期研究
        - missing_coverage: 缺少研究覆盖
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
            # session_id 是持仓查询键，必须绑定认证主体防止读取他人持仓。
            require_matching_identity(
                principal=current_user,
                provided=session_id,
                expected=current_user.session_id,
                field_name="session_id",
            )
            normalized_session = deps.resolve_thread_id(session_id)

            # 导入必要的服务
            from backend.services.portfolio_store import get_positions
            from backend.services.report_index import get_report_index_store

            # 获取持仓数据
            positions = get_positions(normalized_session)

            # 获取相关报告（用于评估研究覆盖质量）
            store = get_report_index_store()
            tickers = [p["ticker"] for p in positions if p.get("ticker")]
            reports = []
            for ticker in tickers:
                # list_reports 返回 list[dict]，不是 {"items": [...]}
                ticker_reports = store.list_reports(
                    session_id=normalized_session,
                    ticker=ticker,
                    limit=1,  # 每个 ticker 只取最新报告
                )
                reports.extend(ticker_reports)

            # 计算风险透镜
            risk_lens = calculate_portfolio_risk_lens(positions, reports)

            return risk_lens

        except HTTPException:
            raise
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "risk_score": 0,
                "concentration_risk": [],
                "sector_exposure": [],
                "currency_exposure": [],
                "market_exposure": [],
                "stale_research": [],
                "loss_positions": [],
                "missing_coverage": [],
                "next_actions": [],
            }

    @router.get("/api/portfolio/risk-lens/history")
    async def get_risk_lens_history(
        session_id: str,
        user_id: str = "default_user",
        days: int = 30,
        current_user: Principal = Depends(get_current_user),
    ):
        """Portfolio 风险透镜历史趋势

        Args:
            session_id: 会话 ID
            user_id: 用户 ID
            days: 返回最近 N 天数据（默认 30 天）

        Returns:
            历史快照列表，按日期升序排列
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
            # session_id 是持仓查询键，必须绑定认证主体防止读取他人持仓。
            require_matching_identity(
                principal=current_user,
                provided=session_id,
                expected=current_user.session_id,
                field_name="session_id",
            )
            normalized_session = deps.resolve_thread_id(session_id)

            # 获取历史快照
            history = get_risk_snapshots_history(
                session_id=normalized_session,
                user_id=effective_user_id,
                days=max(1, min(days, 90)),  # 夹紧到 [1, 90]，负值/0 不透传（审计 E2）
            )

            return {
                "success": True,
                "days": len(history),
                "snapshots": history,
            }

        except HTTPException:
            raise
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
                "snapshots": [],
            }

    return router
