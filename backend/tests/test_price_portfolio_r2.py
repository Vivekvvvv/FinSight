# -*- coding: utf-8 -*-
"""R64：get_factor_exposure 的 market_r2 路径只查 corr is not None——
常数组合（平盘价格→全零收益）时 pandas corr 返回 NaN 而非 None，
NaN 直接漏进 payload（同函数 _compute_beta 对退化方差已返回 None，
r2 漏判与 beta 判空不一致），下游 JSON 序列化产出非法 NaN 字面量。"""
from __future__ import annotations

import math

import pandas as pd

import backend.tools.price_portfolio as pp

_FACTOR_COLS = ["AAA", "SPY", "QQQ", "IWM", "TLT", "GLD", "UUP"]


def _flat_close_frame(days: int = 60) -> pd.DataFrame:
    dates = pd.date_range("2025-01-02", periods=days, freq="B")
    return pd.DataFrame({c: 100.0 for c in _FACTOR_COLS}, index=dates)


def _correlated_close_frame(days: int = 60) -> pd.DataFrame:
    """AAA 与 SPY 完全同涨同跌 → corr=1 → r2=1。"""
    dates = pd.date_range("2025-01-02", periods=days, freq="B")
    base = [100.0 * (1.0 + 0.001 * i) for i in range(days)]
    frame = {c: base for c in _FACTOR_COLS}
    return pd.DataFrame(frame, index=dates)


def test_factor_exposure_flat_prices_r2_is_none_not_nan(monkeypatch):
    monkeypatch.setattr(
        pp, "_download_close_frame", lambda symbols, lookback_days: _flat_close_frame()
    )
    result = pp.get_factor_exposure([{"ticker": "AAA", "weight": 1.0}])

    assert result["error"] is None
    # beta 退化已正确判 None；r2 应一致判 None 而非漏出 NaN
    assert result["factor_beta"]["market"] is None
    r2 = result["market_r2"]
    assert r2 is None or (isinstance(r2, float) and not math.isnan(r2))
    assert r2 is None


def test_factor_exposure_correlated_prices_still_compute_r2(monkeypatch):
    monkeypatch.setattr(
        pp, "_download_close_frame", lambda symbols, lookback_days: _correlated_close_frame()
    )
    result = pp.get_factor_exposure([{"ticker": "AAA", "weight": 1.0}])

    assert result["error"] is None
    assert result["market_r2"] == 1.0
