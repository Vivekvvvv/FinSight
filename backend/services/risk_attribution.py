# -*- coding: utf-8 -*-
"""
组合风险归因分析

基于 OLS 回归分解：市场风险（系统性）、个股特质风险、行业风险贡献度。
数据不足时返回仅基于权重的简化结果。
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

from backend.utils.quote import safe_float

logger = logging.getLogger(__name__)

_MARKET_TICKER = "000300.SS"   # 沪深300作为市场基准


def _market_value(position: dict[str, Any]) -> float:
    value = safe_float(position.get("market_value"))
    return value if value is not None and value > 0 else 0.0


def _fetch_returns(ticker: str, period: str = "1y") -> list[float] | None:
    ticker = str(ticker or "").strip().upper()
    if not ticker or len(ticker) > 32:
        return None
    try:
        from backend.tools import get_stock_historical_data
        payload = get_stock_historical_data(ticker, period=period, interval="1d")
        if not isinstance(payload, dict):
            return None
        kline: list = payload.get("kline_data") or []
        closes = []
        for point in kline:
            close = safe_float(point.get("close")) if isinstance(point, dict) else None
            if close is not None and close > 0:
                closes.append(close)
        if len(closes) < 30:
            return None
        return [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
    except Exception as e:
        logger.debug("_fetch_returns failed: %s", type(e).__name__)
        return None


def _ols_beta(r_stock: np.ndarray, r_market: np.ndarray) -> tuple[float, float]:
    """返回 (beta, idiosyncratic_vol)"""
    n = min(len(r_stock), len(r_market))
    rs, rm = r_stock[-n:], r_market[-n:]
    var_m = float(np.var(rm, ddof=1))
    if var_m < 1e-12:
        return 1.0, float(np.std(rs, ddof=1))
    beta = float(np.cov(rs, rm, ddof=1)[0, 1] / var_m)
    residuals = rs - beta * rm
    idio_vol = float(np.std(residuals, ddof=1))
    return beta, idio_vol


def calculate_risk_attribution(
    positions: list[dict[str, Any]],
    market_ticker: str = _MARKET_TICKER,
    period: str = "1y",
) -> dict[str, Any]:
    """
    组合风险归因

    Returns:
        {
          total_portfolio_vol, market_risk_pct, idiosyncratic_risk_pct,
          positions: [...{ticker, weight, beta, market_risk_contrib, idio_risk_contrib}],
          sector_attribution: [...{sector, weight, risk_contribution}],
          method: "ols" | "simplified"
        }
    """
    if not positions:
        return _empty_result()

    total_val = sum(_market_value(p) for p in positions)
    if total_val <= 0:
        return _empty_result()

    # 拉取市场基准
    market_rets = _fetch_returns(market_ticker, period)
    sigma_market = float(np.std(market_rets, ddof=1)) if market_rets else 0.0

    pos_details: list[dict] = []
    sector_map: dict[str, float] = {}

    for p in positions:
        ticker = str(p.get("ticker") or "").upper()
        mv = _market_value(p)
        weight = mv / total_val if total_val > 0 else 0.0
        sector = str(p.get("sector") or "其他")

        sector_map[sector] = sector_map.get(sector, 0.0) + weight

        # 计算 beta
        beta = 1.0
        idio_vol = 0.0
        if market_rets and ticker:
            stock_rets = _fetch_returns(ticker, period)
            if stock_rets and len(stock_rets) >= 30:
                rm_arr = np.array(market_rets, dtype=float)
                rs_arr = np.array(stock_rets, dtype=float)
                beta, idio_vol = _ols_beta(rs_arr, rm_arr)

        market_risk_contrib = weight * abs(beta) * sigma_market * np.sqrt(252)
        idio_risk_contrib = weight * idio_vol * np.sqrt(252)

        pos_details.append({
            "ticker": ticker,
            "weight": round(weight, 4),
            "beta": round(beta, 3),
            "market_risk_contrib": round(float(market_risk_contrib), 4),
            "idio_risk_contrib": round(float(idio_risk_contrib), 4),
        })

    # 组合总指标
    total_market = sum(p["market_risk_contrib"] for p in pos_details)
    total_idio = sum(p["idio_risk_contrib"] for p in pos_details)
    total_vol = total_market + total_idio

    market_pct = round(total_market / total_vol * 100, 1) if total_vol > 0 else 50.0
    idio_pct = round(100 - market_pct, 1)

    # 行业归因
    sector_attr = []
    for sec, w in sorted(sector_map.items(), key=lambda x: -x[1]):
        # 行业风险贡献 ≈ 行业权重 × 行业成员平均市场+特质风险
        sec_risk = sum(
            p["market_risk_contrib"] + p["idio_risk_contrib"]
            for p in pos_details
            if str(positions[pos_details.index(p)].get("sector") or "其他") == sec
        )
        sector_attr.append({
            "sector": sec,
            "weight": round(w, 4),
            "risk_contribution": round(float(sec_risk), 4),
        })

    method = "ols" if (market_rets and sigma_market > 0) else "simplified"
    return {
        "total_portfolio_vol": round(float(total_vol), 4),
        "market_risk_pct": market_pct,
        "idiosyncratic_risk_pct": idio_pct,
        "positions": pos_details,
        "sector_attribution": sector_attr,
        "method": method,
        "note": "风险贡献为年化估算，OLS回归基于近1年日收益率" if method == "ols" else "数据不足，使用简化模型",
    }


def _empty_result() -> dict[str, Any]:
    return {
        "total_portfolio_vol": 0.0,
        "market_risk_pct": 0.0,
        "idiosyncratic_risk_pct": 0.0,
        "positions": [],
        "sector_attribution": [],
        "method": "no_data",
        "note": "持仓数据不足",
    }
