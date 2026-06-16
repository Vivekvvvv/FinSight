"""
马科维茨均值方差组合优化
用numpy计算有效前沿，返回最大夏普比率组合和最小波动率组合
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_TRADING_DAYS = 252


def optimize_portfolio(
    returns_matrix: list[list[float]],
    tickers: list[str],
    risk_free_rate: float = 0.02,
    n_simulations: int = 3000,
) -> dict[str, Any]:
    """
    马科维茨均值方差优化

    Args:
        returns_matrix: shape (n_tickers, n_days) 的日收益率矩阵
        tickers: 股票代码列表
        risk_free_rate: 无风险利率（年化，默认2%）
        n_simulations: 蒙特卡洛模拟次数

    Returns:
        efficient_frontier, max_sharpe_portfolio, min_vol_portfolio
    """
    arr = np.array(returns_matrix, dtype=float)  # (n, T)
    n = len(tickers)

    if arr.shape[0] != n or arr.shape[1] < 20:
        raise ValueError(f"数据不足：需要至少20天历史数据，当前 {arr.shape[1]} 天")

    mean_returns = arr.mean(axis=1) * _TRADING_DAYS           # 年化期望收益
    cov_matrix   = np.cov(arr) * _TRADING_DAYS                # 年化协方差矩阵

    # 蒙特卡洛模拟
    frontier: list[dict[str, Any]] = []
    for _ in range(n_simulations):
        w = np.random.dirichlet(np.ones(n))
        ret = float(w @ mean_returns)
        vol = float(np.sqrt(w @ cov_matrix @ w))
        sharpe = (ret - risk_free_rate) / vol if vol > 0 else 0.0
        frontier.append({"weights": w.tolist(), "return": ret, "volatility": vol, "sharpe": sharpe})

    # 最大夏普组合
    max_sharpe = max(frontier, key=lambda x: x["sharpe"])
    # 最小波动率组合
    min_vol = min(frontier, key=lambda x: x["volatility"])

    # 等权基准
    eq_w = np.ones(n) / n
    eq_ret = float(eq_w @ mean_returns)
    eq_vol = float(np.sqrt(eq_w @ cov_matrix @ eq_w))

    def _fmt_portfolio(p: dict[str, Any], label: str) -> dict[str, Any]:
        return {
            "label": label,
            "weights": {t: round(w, 4) for t, w in zip(tickers, p["weights"])},
            "expected_annual_return": round(p["return"] * 100, 2),
            "annual_volatility": round(p["volatility"] * 100, 2),
            "sharpe_ratio": round(p["sharpe"], 3),
        }

    # 压缩有效前沿点（取300个代表点）
    frontier_pts = sorted(frontier, key=lambda x: x["volatility"])
    step = max(1, len(frontier_pts) // 300)
    compact = frontier_pts[::step]

    return {
        "tickers": tickers,
        "efficient_frontier": [
            {"return": round(p["return"] * 100, 2), "volatility": round(p["volatility"] * 100, 2), "sharpe": round(p["sharpe"], 2)}
            for p in compact
        ],
        "max_sharpe_portfolio": _fmt_portfolio(max_sharpe, "最大夏普"),
        "min_vol_portfolio":    _fmt_portfolio(min_vol,    "最小波动"),
        "equal_weight_baseline": {
            "label": "等权基准",
            "expected_annual_return": round(eq_ret * 100, 2),
            "annual_volatility": round(eq_vol * 100, 2),
            "sharpe_ratio": round((eq_ret - risk_free_rate) / eq_vol, 3) if eq_vol > 0 else 0,
        },
        "correlation_matrix": {
            "tickers": tickers,
            "data": np.corrcoef(arr).round(3).tolist(),
        },
    }
