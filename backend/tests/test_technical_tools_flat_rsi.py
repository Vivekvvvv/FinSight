# -*- coding: utf-8 -*-
"""R58：tools/technical._calc_rsi 与 agents/technical_agent._calc_rsi 同一缺陷——
平线序列（停牌/重复收盘价）avg_gain=avg_loss=0，0/0 无意义但旧代码
`last_loss==0 → return 100.0`，把停牌股标成 RSI=100 超买，dashboard
insights（insights_scorer "RSI 处于超买区间"）与技术 agent 摘要同步失真。
"""
from __future__ import annotations

import pandas as pd

from backend.tools.technical import _calc_adx, _calc_rsi, compute_technical_indicators


def test_adx_symmetric_expansion_bars_give_no_direction():
    """R91：_calc_adx 先把 plus_dm 清零再让 minus_dm 跟它比较——判定用的
    是"已修改的 +DM"而非原始涨幅。对称扩张 bar（up==down，如高低点
    围绕收盘价等距的十字星，或低价股 ±0.01 横盘）按 Wilder 定义两侧
    DM 都应为 0，旧代码单边错记 -DM → -DI 虚高、DX/ADX 系统性漂移
    （实测连续对称 bar ADX 62.7 vs 正确值 81.3，方向相反）。
    用二进制精确的 0.25 步长保证 diff 位级相等；全部对称 → 无方向
    运动 → pdi=mdi=0 → dx 分母为 0 → adx=None。"""
    n = 60
    close = pd.Series([10.0] * n)
    high = pd.Series([10.0 + 0.25 * i for i in range(n)])
    low = pd.Series([10.0 - 0.25 * i for i in range(n)])
    assert _calc_adx(high, low, close) is None


def test_adx_uptrend_still_positive():
    """非对称上涨 bar 不受影响：单向趋势仍有正 ADX。"""
    n = 60
    close = pd.Series([10.0 + 0.2 * i for i in range(n)])
    high = close + 0.05
    low = close - 0.05
    adx = _calc_adx(high, low, close)
    assert adx is not None and adx > 0


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
