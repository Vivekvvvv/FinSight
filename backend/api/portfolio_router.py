# -*- coding: utf-8 -*-
"""Portfolio position management router.

CRUD operations for positions stored in independent ``portfolio.db``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.services.portfolio_store import (
    get_positions,
    remove_position,
    sync_positions,
    update_position,
)
from backend.demo_mode import demo_portfolio_summary, is_demo_mode
from backend.security.auth import Principal, get_current_user, require_matching_identity
from backend.tools import get_stock_price
from backend.utils.quote import resolve_live_quote, safe_float

logger = logging.getLogger(__name__)

portfolio_router = APIRouter(tags=["Portfolio"])


class PortfolioPositionPayload(BaseModel):
    """Single portfolio position payload used by update and CSV/bulk sync."""

    ticker: str = Field(..., min_length=1, max_length=32)
    shares: float = Field(..., ge=0)
    avg_cost: float | None = Field(default=None, ge=0)
    name: str | None = Field(default=None, max_length=128)
    tags: list[str] | None = Field(default=None, max_length=20)
    note: str | None = Field(default=None, max_length=2000)


class SyncPositionsRequest(BaseModel):
    """Bulk-replace all positions for a session."""

    session_id: str
    positions: list[PortfolioPositionPayload] = Field(default_factory=list)


class BulkImportRequest(BaseModel):
    """Merge-import positions (upsert by ticker, existing positions not in list are preserved)."""

    session_id: str
    positions: list[PortfolioPositionPayload] = Field(default_factory=list)


class UpdatePositionRequest(BaseModel):
    """Upsert a single position."""

    shares: float = Field(..., ge=0)
    avg_cost: float | None = Field(default=None, ge=0)
    name: str | None = Field(default=None, max_length=128)
    tags: list[str] | None = Field(default=None, max_length=20)
    note: str | None = Field(default=None, max_length=2000)


@portfolio_router.get("/api/portfolio/summary")
async def get_portfolio_summary(session_id: str, current_user: Principal = Depends(get_current_user)):
    """Return all positions with calculated market values."""
    if not session_id:
        raise HTTPException(status_code=422, detail="session_id is required")
    require_matching_identity(principal=current_user, provided=session_id, expected=current_user.session_id, field_name="session_id")
    resolved_session_id = session_id if current_user.auth_type == "dev" else current_user.session_id

    positions = get_positions(resolved_session_id)
    if is_demo_mode() and not positions:
        return demo_portfolio_summary(resolved_session_id)

    total_value = 0.0
    total_cost = 0.0
    total_day_change = 0.0
    priced_positions = 0
    enriched: list[dict[str, Any]] = []

    quote_tasks = [
        asyncio.to_thread(
            resolve_live_quote,
            str(pos.get("ticker", "")).strip().upper(),
            get_stock_price,
        )
        for pos in positions
    ]
    live_quotes = await asyncio.gather(*quote_tasks) if quote_tasks else []

    for pos, quote_result in zip(positions, live_quotes):
        quote = quote_result[0] if isinstance(quote_result, tuple) else None
        shares = float(pos.get("shares", 0))
        avg_cost = safe_float(pos.get("avg_cost"))
        live_price = safe_float((quote or {}).get("price")) if quote else None
        live_change = safe_float((quote or {}).get("change")) if quote else None
        live_change_pct = safe_float((quote or {}).get("change_percent")) if quote else None

        if live_price is not None:
            used_price = live_price
            price_source = str((quote or {}).get("source") or "live")
            priced_positions += 1
        elif avg_cost is not None:
            used_price = avg_cost
            price_source = "avg_cost_fallback"
        else:
            used_price = 0.0
            price_source = "unavailable"

        market_value = shares * used_price
        cost_basis = shares * (avg_cost or 0.0)
        unrealized_pnl = (market_value - cost_basis) if avg_cost is not None else None
        day_change = (shares * live_change) if live_change is not None else None

        enriched.append(
            {
                **pos,
                "live_price": round(live_price, 6) if live_price is not None else None,
                "live_change": round(live_change, 6) if live_change is not None else None,
                "live_change_percent": round(live_change_pct, 6) if live_change_pct is not None else None,
                "price_source": price_source,
                "market_value": round(market_value, 2),
                "cost_basis": round(cost_basis, 2),
                "unrealized_pnl": round(unrealized_pnl, 2) if unrealized_pnl is not None else None,
                "day_change": round(day_change, 2) if day_change is not None else None,
            }
        )

        total_value += market_value
        total_cost += cost_basis
        total_day_change += day_change or 0.0

    return {
        "success": True,
        "session_id": resolved_session_id,
        "positions": enriched,
        "count": len(enriched),
        "priced_count": priced_positions,
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "total_pnl": round(total_value - total_cost, 2),
        "total_day_change": round(total_day_change, 2),
    }


@portfolio_router.post("/api/portfolio/bulk")
async def bulk_import_positions(request: BulkImportRequest, current_user: Principal = Depends(get_current_user)):
    """Merge-import positions: upsert each item by ticker, preserving positions not in the payload."""
    if not request.session_id:
        raise HTTPException(status_code=422, detail="session_id is required")
    require_matching_identity(principal=current_user, provided=request.session_id, expected=current_user.session_id, field_name="session_id")
    resolved_session_id = request.session_id if current_user.auth_type == "dev" else current_user.session_id

    imported = 0
    for item in request.positions:
        clean_ticker = item.ticker.strip().upper()
        if not clean_ticker:
            continue
        update_position(
            session_id=resolved_session_id,
            ticker=clean_ticker,
            shares=item.shares,
            avg_cost=item.avg_cost,
            name=item.name,
            tags=item.tags,
            note=item.note,
        )
        imported += 1

    return {
        "success": True,
        "session_id": resolved_session_id,
        "imported_count": imported,
    }


@portfolio_router.post("/api/portfolio/positions")
async def sync_positions_endpoint(request: SyncPositionsRequest, current_user: Principal = Depends(get_current_user)):
    """Bulk-replace all positions for a session."""
    if not request.session_id:
        raise HTTPException(status_code=422, detail="session_id is required")
    require_matching_identity(principal=current_user, provided=request.session_id, expected=current_user.session_id, field_name="session_id")
    resolved_session_id = request.session_id if current_user.auth_type == "dev" else current_user.session_id

    count = sync_positions(
        resolved_session_id,
        [item.model_dump(exclude_none=True) for item in request.positions],
    )
    return {
        "success": True,
        "session_id": resolved_session_id,
        "synced_count": count,
    }


@portfolio_router.put("/api/portfolio/positions/{ticker}")
async def update_position_endpoint(
    ticker: str,
    session_id: str,
    request: UpdatePositionRequest,
    current_user: Principal = Depends(get_current_user),
):
    """Upsert a single position (create or update)."""
    if not session_id:
        raise HTTPException(status_code=422, detail="session_id is required")
    require_matching_identity(principal=current_user, provided=session_id, expected=current_user.session_id, field_name="session_id")
    resolved_session_id = session_id if current_user.auth_type == "dev" else current_user.session_id

    clean_ticker = ticker.strip().upper()
    if not clean_ticker:
        raise HTTPException(status_code=422, detail="ticker is required")

    update_position(
        session_id=resolved_session_id,
        ticker=clean_ticker,
        shares=request.shares,
        avg_cost=request.avg_cost,
        name=request.name,
        tags=request.tags,
        note=request.note,
    )
    return {
        "success": True,
        "session_id": resolved_session_id,
        "ticker": clean_ticker,
        "shares": request.shares,
        "avg_cost": request.avg_cost,
        "name": request.name,
        "tags": request.tags,
        "note": request.note,
    }


@portfolio_router.delete("/api/portfolio/positions/{ticker}")
async def remove_position_endpoint(ticker: str, session_id: str, current_user: Principal = Depends(get_current_user)):
    """Remove a single position from the portfolio."""
    if not session_id:
        raise HTTPException(status_code=422, detail="session_id is required")
    require_matching_identity(principal=current_user, provided=session_id, expected=current_user.session_id, field_name="session_id")
    resolved_session_id = session_id if current_user.auth_type == "dev" else current_user.session_id

    clean_ticker = ticker.strip().upper()
    if not clean_ticker:
        raise HTTPException(status_code=422, detail="ticker is required")

    remove_position(session_id=resolved_session_id, ticker=clean_ticker)
    return {
        "success": True,
        "session_id": resolved_session_id,
        "removed_ticker": clean_ticker,
    }


# ── 组合优化 ──────────────────────────────────────────────────────────────────

class PortfolioOptimizeRequest(BaseModel):
    tickers: list[str]
    risk_free_rate: float = 0.02
    n_simulations: int = 2000


@portfolio_router.post("/api/portfolio/optimize")
async def optimize_portfolio_endpoint(request: PortfolioOptimizeRequest):
    """
    马科维茨均值方差组合优化

    - 输入：股票列表（2-10只）
    - 输出：有效前沿、最大夏普组合、最小波动率组合、相关系数矩阵
    """
    if len(request.tickers) < 2:
        raise HTTPException(status_code=422, detail="至少需要2只股票")
    if len(request.tickers) > 10:
        raise HTTPException(status_code=422, detail="最多支持10只股票")

    tickers = [t.strip().upper() for t in request.tickers]

    from backend.tools import get_stock_historical_data
    from backend.services.portfolio_optimizer import optimize_portfolio

    returns_matrix: list[list[float]] = []
    failed: list[str] = []

    for t in tickers:
        try:
            payload = get_stock_historical_data(t, period="2y", interval="1d")
            kline: list = []
            if isinstance(payload, dict):
                kline = payload.get("kline_data") or []
            closes = [float(p["close"]) for p in kline if p.get("close") is not None]
            if len(closes) < 20:
                failed.append(t)
                continue
            daily_returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
            returns_matrix.append(daily_returns)
        except Exception as e:
            logger.warning("获取 %s 历史数据失败: %s", t, e)
            failed.append(t)

    valid_tickers = [t for t in tickers if t not in failed]
    if len(valid_tickers) < 2:
        raise HTTPException(status_code=422, detail=f"有效股票不足2只，失败: {failed}")

    # 对齐数据长度
    min_len = min(len(r) for r in returns_matrix)
    aligned = [r[-min_len:] for r in returns_matrix]

    try:
        result = optimize_portfolio(
            returns_matrix=aligned,
            tickers=valid_tickers,
            risk_free_rate=request.risk_free_rate,
            n_simulations=request.n_simulations,
        )
        if failed:
            result["warnings"] = [f"{t} 数据不足，已跳过" for t in failed]
        return result
    except Exception as e:
        logger.exception("组合优化失败: %s", e)
        raise HTTPException(status_code=500, detail=f"优化失败: {e}")


__all__ = ["portfolio_router"]
