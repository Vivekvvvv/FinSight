# -*- coding: utf-8 -*-
"""R58：tools/technical._calc_rsi 与 agents/technical_agent._calc_rsi 同一缺陷——
平线序列（停牌/重复收盘价）avg_gain=avg_loss=0，0/0 无意义但旧代码
`last_loss==0 → return 100.0`，把停牌股标成 RSI=100 超买，dashboard
insights（insights_scorer "RSI 处于超买区间"）与技术 agent 摘要同步失真。
"""
from __future__ import annotations

import pandas as pd

from backend.tools.technical import _calc_adx, _calc_rsi, compute_technical_indicators


def test_flat_macd_does_not_claim_bearish_momentum(monkeypatch):
    import json
    import backend.langchain_technical as module
    frame = pd.DataFrame({"Open": [100.0] * 40, "High": [101.0] * 40,
                          "Low": [99.0] * 40, "Close": [100.0] * 40})
    assert compute_technical_indicators(frame)["momentum"] == "neutral"
    monkeypatch.setattr(module, "_get_stock_historical_data", lambda *args, **kwargs: _flat_kline_payload())
    assert json.loads(module.compute_technical_snapshot("AAPL"))["momentum"] == "neutral"


def test_chat_snapshot_excludes_price_rows_for_unrelated_stocks(monkeypatch):
    import json
    import backend.langchain_technical as module
    for field in ("symbol", "ticker"):
        rows = [{"close": 100.0}] * 29 + [{"close": 999.0, field: "MSFT"}]
        monkeypatch.setattr(module, "_get_stock_historical_data", lambda *args, **kwargs: {"kline_data": rows})
        result = json.loads(module.compute_technical_snapshot("AAPL"))
        assert result["error"] == "insufficient_points"
        assert result["points"] == 29


def test_chat_snapshot_failed_rows_cannot_hide_insufficient_history(monkeypatch):
    import json
    import backend.langchain_technical as module
    for failure in ({"success": False}, {"status": " Failed "}, {"error": "row"}):
        rows = [{"close": 100.0}] * 29 + [{"close": 999.0, **failure}]
        monkeypatch.setattr(module, "_get_stock_historical_data", lambda *args, **kwargs: {"kline_data": rows})
        result = json.loads(module.compute_technical_snapshot("AAPL"))
        assert result["error"] == "insufficient_points"
        assert result["points"] == 29


def test_nonpositive_chat_snapshot_prices_cannot_count_as_valid_points(monkeypatch):
    import json
    import backend.langchain_technical as module
    rows = [{"close": 100.0}] * 29
    for invalid in (0, -1):
        monkeypatch.setattr(module, "_get_stock_historical_data",
                            lambda *args, **kwargs: {"kline_data": [*rows, {"close": invalid}]})
        result = json.loads(module.compute_technical_snapshot("AAPL"))
        assert result["error"] == "insufficient_points"
        assert result["points"] == 29


def test_chat_technical_snapshot_cannot_use_another_stock_history(monkeypatch):
    import json
    import backend.langchain_technical as module
    for field in ("symbol", "ticker"):
        monkeypatch.setattr(module, "_get_stock_historical_data",
                            lambda *args, **kwargs: {**_flat_kline_payload(), field: "MSFT"})
        result = json.loads(module.compute_technical_snapshot("AAPL"))
        assert "error" in result
        assert "close" not in result


def test_chat_technical_snapshot_rejects_failed_history_envelopes(monkeypatch):
    import json
    import backend.langchain_technical as module
    for failure in ({"error": "bad"}, {"success": False}, {"status": " Failed "}):
        monkeypatch.setattr(module, "_get_stock_historical_data",
                            lambda *args, **kwargs: {**_flat_kline_payload(), **failure})
        result = json.loads(module.compute_technical_snapshot("AAPL"))
        assert "error" in result
        assert "close" not in result


def test_unsorted_snapshot_history_uses_the_latest_chronological_price():
    closes = [100.0 + i for i in range(40)]
    frame = pd.DataFrame({"Open": closes, "High": [p + 1 for p in closes],
                          "Low": [p - 1 for p in closes], "Close": closes},
                         index=pd.date_range("2025-01-01", periods=40)).iloc[::-1]
    result = compute_technical_indicators(frame)
    assert result["close"] == 139.0
    assert result["rsi"] == 100.0


def test_duplicate_snapshot_dates_cannot_count_as_extra_trading_days():
    dates = pd.date_range("2025-01-01", periods=20)
    frame = pd.DataFrame({"Open": [100.0] * 40, "High": [101.0] * 40,
                          "Low": [99.0] * 40, "Close": [100.0] * 40}, index=dates.append(dates))
    assert compute_technical_indicators(frame) == {}


def test_unsorted_chart_observations_are_evaluated_in_chronological_order():
    from backend.tools.technical import compute_indicator_series
    dates = pd.date_range("2025-01-01", periods=40)
    frame = pd.DataFrame({"Close": [100.0 + i for i in range(40)]}, index=dates).iloc[::-1]
    result = compute_indicator_series(frame)
    assert result["dates"] == [date.strftime("%Y-%m-%d") for date in dates]
    assert result["rsi"][-1] == 100.0


def test_duplicate_chart_dates_cannot_inflate_indicator_history():
    from backend.tools.technical import compute_indicator_series
    dates = pd.date_range("2025-01-01", periods=20)
    frame = pd.DataFrame({"Close": [100.0] * 40}, index=dates.append(dates))
    assert compute_indicator_series(frame) == {}


def test_invalid_closes_do_not_destroy_valid_indicator_chart_rows():
    from backend.tools.technical import compute_indicator_series
    frame = pd.DataFrame({"Close": pd.Series([100.0] * 39 + ["bad"], dtype=object)})
    result = compute_indicator_series(frame)
    assert len(result["dates"]) == 39
    assert result["rsi"][-1] == 50.0


def test_invalid_volume_does_not_destroy_valid_price_indicators():
    frame = pd.DataFrame({"Open": [100.0] * 40, "High": [101.0] * 40,
                          "Low": [99.0] * 40, "Close": [100.0] * 40,
                          "Volume": pd.Series([100.0] * 39 + ["bad"], dtype=object)})
    result = compute_technical_indicators(frame)
    assert result["close"] == 100.0
    assert result["avg_volume"] == 100.0


def test_impossible_ohlc_geometry_cannot_produce_indicators():
    for field, value in (("High", 98.0), ("Low", 102.0), ("Open", 105.0), ("Close", 95.0)):
        frame = pd.DataFrame({"Open": [100.0] * 30, "High": [101.0] * 30,
                              "Low": [99.0] * 30, "Close": [100.0] * 30})
        frame.loc[5, field] = value
        assert compute_technical_indicators(frame) == {}


def test_nonpositive_ohlc_rows_do_not_count_as_valid_indicator_history():
    for price in (0.0, -1.0):
        frame = pd.DataFrame({"Open": [100.0] * 30, "High": [101.0] * 30,
                              "Low": [99.0] * 30, "Close": [100.0] * 30})
        frame.loc[5, "Close"] = price
        assert compute_technical_indicators(frame) == {}


def test_nonnumeric_ohlc_rows_do_not_destroy_valid_technical_history():
    frame = pd.DataFrame({"Open": [100.0] * 40, "High": [101.0] * 40,
                          "Low": [99.0] * 40, "Close": [100.0] * 40})
    frame["Close"] = frame["Close"].astype(object)
    frame.loc[5, "Close"] = "not-a-price"
    result = compute_technical_indicators(frame)
    assert result["close"] == 100.0
    assert result["rsi"] == 50.0
    assert frame.loc[5, "Close"] == "not-a-price"


def test_unrepresentable_pivot_levels_cannot_leak_infinity_into_json():
    import json
    from backend.tools.technical import _calc_pivot_points
    levels = _calc_pivot_points(pd.Series([1.7e308]), pd.Series([1.0]), pd.Series([1.7e308]))
    json.dumps(levels, allow_nan=False)
    assert all(value > 0 for side in levels for value in side)


def test_pivot_levels_do_not_overflow_for_large_finite_flat_prices():
    import math
    from backend.tools.technical import _calc_pivot_points
    series = pd.Series([1e308])
    supports, resistances = _calc_pivot_points(series, series, series)
    assert all(math.isfinite(value) for value in supports + resistances)
    assert supports == resistances == [1e308, 1e308]


def test_nonpositive_indicator_series_limits_do_not_return_full_or_tail_history():
    from backend.tools.technical import compute_indicator_series
    frame = pd.DataFrame({"Close": [100.0 + i for i in range(40)]})
    assert compute_indicator_series(frame, n_days=0) == {}
    assert compute_indicator_series(frame, n_days=-1) == {}


def test_rsi_chart_requires_fourteen_price_changes_before_reporting_a_value():
    from backend.tools.technical import compute_indicator_series
    result = compute_indicator_series(pd.DataFrame({"Close": [100.0 + i for i in range(40)]}))
    assert result["rsi"][:14] == [None] * 14
    assert result["rsi"][14] == 100.0


def test_rsi_chart_matches_snapshot_when_prices_never_fall():
    from backend.tools.technical import compute_indicator_series
    for closes, expected in (([50.0] * 40, 50.0), ([100.0 + i for i in range(40)], 100.0)):
        result = compute_indicator_series(pd.DataFrame({"Close": closes}))
        assert result["rsi"][-1] == expected
        assert _calc_rsi(pd.Series(closes)) == expected


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
