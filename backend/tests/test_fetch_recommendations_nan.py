# -*- coding: utf-8 -*-
"""R60 回归：fetch_recommendations 遇 NaN 评级桶不崩溃。

int(row.get(bucket, 0)) 的默认 0 只挡 key 缺失；单元格存在但为 NaN
（yfinance 部分数据）时 int(nan) 抛 ValueError，被外层 except 吞成整块
None → 一个桶 NaN 丢掉整个分析师评级。safe_float 让 NaN 桶降级为 0。
"""
from __future__ import annotations

import pandas as pd

from backend.dashboard import data_service as ds


class _FakeTicker:
    def __init__(self, df):
        self.recommendations_summary = df


def test_fetch_recommendations_survives_nan_bucket(monkeypatch):
    # 一行数据：hold 为 NaN，其余有效
    df = pd.DataFrame([
        {"strongBuy": 5, "buy": 10, "hold": float("nan"), "sell": 2, "strongSell": 1},
    ])
    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", lambda _symbol: _FakeTicker(df))

    result = ds.fetch_recommendations("AAPL")

    assert result is not None, "NaN 桶不应丢掉整个评级组件"
    assert result["strong_buy"] == 5
    assert result["buy"] == 10
    assert result["hold"] == 0  # NaN 降级为 0
    assert result["sell"] == 2
    assert result["strong_sell"] == 1


def test_fetch_recommendations_all_zero_returns_none(monkeypatch):
    # 全 0（含 NaN 全降级）→ 仍按原语义返回 None
    df = pd.DataFrame([
        {"strongBuy": 0, "buy": float("nan"), "hold": 0, "sell": 0, "strongSell": 0},
    ])
    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", lambda _symbol: _FakeTicker(df))

    assert ds.fetch_recommendations("AAPL") is None


def test_fetch_recommendations_valid_data(monkeypatch):
    df = pd.DataFrame([
        {"strongBuy": 3, "buy": 4, "hold": 5, "sell": 1, "strongSell": 0},
    ])
    import yfinance as yf
    monkeypatch.setattr(yf, "Ticker", lambda _symbol: _FakeTicker(df))

    result = ds.fetch_recommendations("AAPL")
    assert result == {
        "strong_buy": 3, "buy": 4, "hold": 5, "sell": 1, "strong_sell": 0,
    }
