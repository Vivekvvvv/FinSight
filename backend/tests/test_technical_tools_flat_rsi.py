# -*- coding: utf-8 -*-
"""R58：tools/technical._calc_rsi 与 agents/technical_agent._calc_rsi 同一缺陷——
平线序列（停牌/重复收盘价）avg_gain=avg_loss=0，0/0 无意义但旧代码
`last_loss==0 → return 100.0`，把停牌股标成 RSI=100 超买，dashboard
insights（insights_scorer "RSI 处于超买区间"）与技术 agent 摘要同步失真。
"""
from __future__ import annotations

import pandas as pd

from backend.tools.technical import _calc_rsi, compute_technical_indicators


def _flat_series(n=120, price=50.0) -> pd.Series:
    return pd.Series([price] * n)


def _flat_kline_payload(n=120, price=50.0) -> dict:
    return {
        "kline_data": [{"close": price, "time": f"2025-03-{i + 1:02d}"} for i in range(n)],
        "source": "test",
    }


def test_calc_rsi_flat_series_returns_neutral_50():
    assert _calc_rsi(_flat_series(), 14) == 50.0


def test_calc_rsi_rising_series_still_100():
    rising = pd.Series([100.0 + i * 0.5 for i in range(120)])
    assert _calc_rsi(rising, 14) == 100.0


def test_compute_technical_indicators_flat_not_overbought():
    flat = pd.DataFrame(
        {
            "Open": [50.0] * 120,
            "High": [50.0] * 120,
            "Low": [50.0] * 120,
            "Close": [50.0] * 120,
            "Volume": [0.0] * 120,
        }
    )
    result = compute_technical_indicators(flat)
    assert result, "120 根数据应正常出指标"
    assert result["rsi"] == 50.0
    assert result["rsi_state"] == "neutral"


def test_langchain_snapshot_flat_not_overbought(monkeypatch):
    """langchain_technical.compute_technical_snapshot 同款第三处：
    平线 kline → rsi14=100/rsi_state=overbought 进入 planner/synthesize。"""
    import json

    import backend.langchain_technical as lt

    monkeypatch.setattr(lt, "_get_stock_historical_data", lambda *a, **k: _flat_kline_payload())
    payload = json.loads(lt.compute_technical_snapshot("HALT"))
    assert payload["rsi14"] == 50.0
    assert payload["rsi_state"] == "neutral"
