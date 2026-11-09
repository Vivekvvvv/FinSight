# -*- coding: utf-8 -*-
"""R77：get_factor_exposure 对 yf.download 返回的全 NaN 列（退市/错名标的）
未过滤——该列在 returns.columns 里通过检查，weighted_series 求和后逐行
NaN 传染（NaN + x = NaN），dropna 后 portfolio_returns 全空 →
portfolio_returns_empty，一个坏持仓杀掉整个因子暴露/压力测试。
应跳过无数据列，让有效持仓照常计算。"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from backend.tools import price_portfolio


def _frame(dead_symbols=()):
    idx = pd.date_range("2025-01-01", periods=60, freq="B")
    rng = np.random.RandomState(0)
    data = {
        "AAPL": 150 + np.linspace(0, 10, 60) + rng.randn(60),
        "MSFT": 400 + np.linspace(0, 15, 60) + rng.randn(60),
        "SPY": 500 + np.linspace(0, 20, 60),
        "QQQ": 400 + np.linspace(0, 18, 60),
        "IWM": 200 + np.linspace(0, 8, 60),
        "TLT": 90 - np.linspace(0, 2, 60),
        "GLD": 180 + np.linspace(0, 6, 60),
        "UUP": 27 + np.linspace(0, 0.5, 60),
    }
    for sym in dead_symbols:
        data[sym] = [float("nan")] * 60
    return pd.DataFrame(data, index=idx)


def test_missing_close_does_not_create_a_flat_return_observation(monkeypatch):
    frame = _frame()
    frame.loc[frame.index[10], "AAPL"] = np.nan
    monkeypatch.setattr(price_portfolio, "_download_close_frame", lambda *args, **kwargs: frame)

    result = price_portfolio.get_factor_exposure([{"ticker": "AAPL", "weight": 1.0}])

    assert result["error"] is None
    assert result["observation_count"] == 57


def test_single_return_has_no_measured_volatility(monkeypatch):
    monkeypatch.setattr(price_portfolio, "_download_close_frame", lambda *args, **kwargs: _frame().iloc[:2])

    result = price_portfolio.get_factor_exposure([{"ticker": "AAPL", "weight": 1.0}])

    assert result["annualized_volatility"] is None
    json.dumps(result, allow_nan=False)


def test_overflowing_returns_are_not_counted_as_observations(monkeypatch):
    frame = _frame()
    frame.loc[frame.index[0], "AAPL"] = 1e-320
    monkeypatch.setattr(price_portfolio, "_download_close_frame", lambda *args, **kwargs: frame)

    result = price_portfolio.get_factor_exposure([{"ticker": "AAPL", "weight": 1.0}])

    assert result["observation_count"] == 58
    json.dumps(result, allow_nan=False)


def test_overflowing_beta_statistics_are_unavailable():
    returns = pd.Series([1e160, -1e160] * 30)

    assert price_portfolio._compute_beta(returns, returns) is None


@pytest.mark.parametrize("field", ["weight", "quantity"])
def test_large_finite_positions_keep_their_relative_weights(field):
    result = price_portfolio._normalize_positions([
        {"ticker": "AAPL", field: 1e308},
        {"ticker": "MSFT", field: 1e308},
        {"ticker": "NVDA", field: 5e307},
    ])

    assert [row["weight"] for row in result] == pytest.approx([0.4, 0.4, 0.2])


def test_dead_symbol_does_not_poison_portfolio(monkeypatch):
    """DEAD 列全 NaN：应被跳过，AAPL 持仓照常出因子暴露。"""
    monkeypatch.setattr(
        price_portfolio, "_download_close_frame",
        lambda symbols, lookback_days: _frame(dead_symbols=("DEAD",)),
    )
    out = price_portfolio.get_factor_exposure([
        {"ticker": "AAPL", "weight": 0.6},
        {"ticker": "DEAD", "weight": 0.4},
    ])
    assert out["error"] is None
    assert out["observation_count"] > 20
    assert out["factor_beta"]["market"] is not None
    assert out["missing_tickers"] == ["DEAD"]
    assert out["fallback_reason"] == "portfolio_history_incomplete"


def test_all_symbols_dead_still_errors(monkeypatch):
    """全部持仓无数据仍如实报错——不是静默成功。"""
    monkeypatch.setattr(
        price_portfolio, "_download_close_frame",
        lambda symbols, lookback_days: _frame(dead_symbols=("DEAD", "GONE")),
    )
    out = price_portfolio.get_factor_exposure([
        {"ticker": "DEAD", "weight": 0.5},
        {"ticker": "GONE", "weight": 0.5},
    ])
    assert out["error"] is not None


def test_all_alive_regression(monkeypatch):
    """两个有效持仓正常出结果——回归保护。"""
    monkeypatch.setattr(
        price_portfolio, "_download_close_frame",
        lambda symbols, lookback_days: _frame(),
    )
    out = price_portfolio.get_factor_exposure([
        {"ticker": "AAPL", "weight": 0.5},
        {"ticker": "MSFT", "weight": 0.5},
    ])
    assert out["error"] is None
    assert out["factor_beta"]["market"] is not None
    assert out["annualized_volatility"] is not None
    assert out["missing_tickers"] == []
    assert out["fallback_reason"] is None
