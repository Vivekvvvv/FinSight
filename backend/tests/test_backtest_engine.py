# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.services import backtest_engine as backtest_engine_module


def test_overflowing_macd_period_is_a_parameter_error_instead_of_a_crash(monkeypatch):
    monkeypatch.setattr(backtest_engine_module, "get_stock_historical_data",
                        lambda *args, **kwargs: {"kline_data": _build_series()})
    result = backtest_engine_module.BacktestEngine().run(ticker="AAPL", strategy="macd",
                                                        params={"slow": 10 ** 1000})
    assert result["success"] is False
    assert result["error"] == "invalid_strategy_params"


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("field", ["symbol", "ticker"])
def test_mixed_history_identities_cannot_mix_in_other_instruments(monkeypatch, fallback, field):
    rows = _build_series(days=40)
    rows[10][field] = "MSFT"
    monkeypatch.setattr(backtest_engine_module, "get_stock_historical_data",
                        lambda *args, **kwargs: None if fallback else {"kline_data": rows})
    monkeypatch.setattr(backtest_engine_module, "fetch_cn_hk_kline", lambda *args, **kwargs: rows)
    result = backtest_engine_module.BacktestEngine().run(ticker="0700.HK", strategy="ma_cross",
                                                        market="HK" if fallback else "US")
    assert result["success"] is False
    assert result["points"] == 39


@pytest.mark.parametrize("failure", [{"error": "stale row"}, {"success": False}, {"status": " Failed "}])
def test_failed_price_rows_do_not_count_as_valid_history(monkeypatch, failure):
    rows = _build_series(days=40)
    rows[10].update(failure)
    monkeypatch.setattr(backtest_engine_module, "get_stock_historical_data",
                        lambda *args, **kwargs: {"kline_data": rows})
    result = backtest_engine_module.BacktestEngine().run(ticker="AAPL", strategy="ma_cross")
    assert result["success"] is False
    assert result["points"] == 39


@pytest.mark.parametrize("status", ["failed", " Error ", "UNAVAILABLE"])
def test_failed_history_status_cannot_produce_successful_backtest(monkeypatch, status):
    monkeypatch.setattr(backtest_engine_module, "get_stock_historical_data",
                        lambda *args, **kwargs: {"status": status, "kline_data": _build_series()})
    result = backtest_engine_module.BacktestEngine().run(ticker="AAPL", strategy="ma_cross")
    assert result["success"] is False
    assert result["source"] == "unavailable"


def test_cn_hk_fallback_exception_is_reported_as_unavailable_data(monkeypatch, caplog):
    monkeypatch.setattr(backtest_engine_module, "get_stock_historical_data", lambda *args, **kwargs: None)
    def fetch(*args, **kwargs):
        raise RuntimeError("provider failed")
    monkeypatch.setattr(backtest_engine_module, "fetch_cn_hk_kline", fetch)
    result = backtest_engine_module.BacktestEngine().run(ticker="0700.HK", strategy="ma_cross")
    assert result["success"] is False
    assert result["source"] == "unavailable"
    assert "CN/HK" in caplog.text


def test_strategy_catalog_returns_independent_nested_values():
    engine = backtest_engine_module.BacktestEngine()
    catalog = engine.list_strategies()
    original = catalog[0]["default_params"]["short_window"]
    catalog[0]["default_params"]["short_window"] = 999
    assert engine.list_strategies()[0]["default_params"]["short_window"] == original


def test_strategy_averages_remain_finite_for_large_valid_prices():
    from backend.services.backtest_strategies import _rsi, ma_cross_signals
    assert ma_cross_signals([1e308] * 20 + [1.2e308] * 20, short_window=5, long_window=20)["signals"][25] == 1
    assert _rsi([1e308, 1.5e308] * 20)[-1] == 50.0


@pytest.mark.parametrize("oversold, overbought", [(70.0, 30.0), (-1.0, 70.0), (30.0, 101.0)])
def test_invalid_rsi_thresholds_are_reported_as_parameter_errors(monkeypatch, oversold, overbought):
    from backend.services.backtest_strategies import rsi_mean_reversion_signals
    with pytest.raises(ValueError):
        rsi_mean_reversion_signals([100.0] * 40, oversold=oversold, overbought=overbought)
    monkeypatch.setattr(backtest_engine_module, "get_stock_historical_data", lambda *args, **kwargs: {"kline_data": _build_series()})
    result = backtest_engine_module.BacktestEngine().run(ticker="AAPL", strategy="rsi", params={"oversold": oversold, "overbought": overbought})
    assert result["success"] is False
    assert result["error"] == "invalid_strategy_params"


def test_unknown_strategy_does_not_silently_run_ma_cross(monkeypatch):
    calls = []
    def fetch(*args, **kwargs):
        calls.append(args)
        return {"kline_data": _build_series()}
    monkeypatch.setattr(backtest_engine_module, "get_stock_historical_data", fetch)
    result = backtest_engine_module.BacktestEngine().run(ticker="AAPL", strategy="macd_typo")
    assert result["success"] is False
    assert result["error"] == "unsupported_strategy"
    assert not calls


@pytest.mark.parametrize("signal", [0.5, 2, -1, True])
def test_nonbinary_strategy_signals_are_rejected_instead_of_truncated(monkeypatch, signal):
    monkeypatch.setattr(backtest_engine_module, "get_stock_historical_data", lambda *args, **kwargs: {"kline_data": _build_series(days=40)})
    monkeypatch.setattr(backtest_engine_module, "build_strategy_signals", lambda *args: {"signals": [signal] * 40})
    result = backtest_engine_module.BacktestEngine().run(ticker="AAPL", strategy="ma_cross", t_plus_one=False)
    assert result["success"] is False
    assert result["error"] == "invalid_strategy_signals"


def test_daily_timestamp_variants_do_not_inflate_history_length(monkeypatch):
    rows = _build_series(days=20)
    duplicates = [{**row, "time": row["time"] + "T16:00:00+08:00"} for row in rows]
    monkeypatch.setattr(backtest_engine_module, "get_stock_historical_data", lambda *args, **kwargs: {"kline_data": rows + duplicates})
    result = backtest_engine_module.BacktestEngine().run(ticker="AAPL", strategy="ma_cross")
    assert result["success"] is False
    assert result["points"] == 20


def test_unparseable_dates_do_not_count_as_price_history(monkeypatch):
    rows = [{"time": f"invalid-{index}", "close": 100.0} for index in range(40)]
    monkeypatch.setattr(backtest_engine_module, "get_stock_historical_data", lambda *args, **kwargs: {"kline_data": rows})
    result = backtest_engine_module.BacktestEngine().run(ticker="AAPL", strategy="ma_cross")
    assert result["success"] is False
    assert result["source"] == "unavailable"


@pytest.mark.parametrize("timestamp", ["2025-01-02 16:00:00", "2025-01-02 16:00:00+08:00"])
def test_end_date_includes_the_whole_daily_bar_despite_timestamp_format(timestamp):
    point = backtest_engine_module.PricePoint(timestamp, 100.0)
    assert backtest_engine_module.BacktestEngine._filter_by_date([point], "2025-01-02", "2025-01-02") == [point]


@pytest.mark.parametrize("dates", [{"start_date": "bad"}, {"end_date": "2026-02-30"},
                                   {"start_date": "2025-02-01", "end_date": "2025-01-01"}])
def test_invalid_date_ranges_do_not_silently_expand_the_backtest(monkeypatch, dates):
    calls = []
    def fetch(*args, **kwargs):
        calls.append(args)
        return {"kline_data": _build_series()}
    monkeypatch.setattr(backtest_engine_module, "get_stock_historical_data", fetch)
    result = backtest_engine_module.BacktestEngine().run(ticker="AAPL", strategy="ma_cross", **dates)
    assert result["success"] is False
    assert result["error"] == "invalid_date_range"
    assert not calls


@pytest.mark.parametrize("symbol", ["600519.SH", "300750.SZ", "0700.HK"])
def test_cn_hk_fallback_is_inferred_from_symbol_when_market_is_omitted(monkeypatch, symbol):
    monkeypatch.setattr(backtest_engine_module, "get_stock_historical_data", lambda *args, **kwargs: None)
    monkeypatch.setattr(backtest_engine_module, "fetch_cn_hk_kline", lambda *args, **kwargs: _build_series())
    result = backtest_engine_module.BacktestEngine().run(ticker=symbol, strategy="ma_cross")
    assert result["success"] is True
    assert result["source"] == "eastmoney_kline"


@pytest.mark.parametrize("field", ["symbol", "ticker"])
def test_backtest_rejects_history_for_a_different_instrument(monkeypatch, field):
    monkeypatch.setattr(backtest_engine_module, "get_stock_historical_data", lambda *args, **kwargs:
                        {field: "MSFT", "kline_data": _build_series()})
    result = backtest_engine_module.BacktestEngine().run(ticker="AAPL", strategy="ma_cross")
    assert result["success"] is False
    assert result["source"] == "unavailable"


def test_error_payload_with_residual_prices_is_not_backtested(monkeypatch):
    monkeypatch.setattr(backtest_engine_module, "get_stock_historical_data", lambda *args, **kwargs:
                        {"error": "provider failed", "kline_data": _build_series(), "source": "failed"})
    result = backtest_engine_module.BacktestEngine().run(ticker="AAPL", strategy="ma_cross")
    assert result["success"] is False
    assert result["source"] == "unavailable"


def _build_series(start_price: float = 100.0, days: int = 120) -> list[dict]:
    rows: list[dict] = []
    price = start_price
    base = datetime(2025, 1, 1)
    for i in range(days):
        price += 0.5
        rows.append({"time": (base + timedelta(days=i)).date().isoformat(), "close": round(price, 2)})
    return rows


@pytest.mark.parametrize("market", ["US", "CN"])
def test_failed_historical_payload_cannot_be_used_as_backtest_data(monkeypatch, market):
    monkeypatch.setattr(backtest_engine_module, "get_stock_historical_data", lambda *args, **kwargs: {
        "success": False, "kline_data": _build_series(), "source": "failed_primary",
    })
    monkeypatch.setattr(backtest_engine_module, "fetch_cn_hk_kline", lambda *args, **kwargs: _build_series(80.0))

    result = backtest_engine_module.BacktestEngine().run(ticker="AAPL", strategy="ma_cross", market=market)

    if market == "US":
        assert result["success"] is False
        assert result["source"] == "unavailable"
    else:
        assert result["success"] is True
        assert result["source"] == "eastmoney_kline"


def test_primary_historical_exception_allows_cn_fallback(monkeypatch, caplog):
    def failed_primary(*args, **kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(backtest_engine_module, "get_stock_historical_data", failed_primary)
    monkeypatch.setattr(backtest_engine_module, "fetch_cn_hk_kline", lambda *args, **kwargs: _build_series(80.0))

    result = backtest_engine_module.BacktestEngine().run(ticker="600519.SH", strategy="macd", market="CN")

    assert result["success"] is True
    assert result["source"] == "eastmoney_kline"
    assert "historical" in caplog.text.lower()


@pytest.mark.parametrize("field", ["fee_bps", "slippage_bps"])
@pytest.mark.parametrize("value", [-1, 10000, 11000])
def test_backtest_rejects_cost_rates_that_cannot_price_a_trade(monkeypatch, field, value):
    monkeypatch.setattr(backtest_engine_module, "get_stock_historical_data", lambda *args, **kwargs: {"kline_data": _build_series()})

    result = backtest_engine_module.BacktestEngine().run(ticker="AAPL", strategy="ma_cross", **{field: value})

    assert result["success"] is False
    assert result["error"] == "invalid_numeric_input"


@pytest.mark.parametrize("first, later, cash, rate, sell", [
    (1e-320, 1e-320, 100000.0, 0, False),
    (1e308, 1e308, 100000.0, 9000, False),
    (1.0, 1e308, 1e308, 0, False),
    (1e-308, 1000.0, 1e-308, 0, False),
    (1.0, 1e308, 100.0, 0, True),
    (1e308, 1e308, 1e-308, 0, False),
])
def test_backtest_rejects_overflowing_and_underflowing_calculations(monkeypatch, first, later, cash, rate, sell):
    series = _build_series(days=40)
    for index, row in enumerate(series):
        row["close"] = first if index == 0 else later
    monkeypatch.setattr(backtest_engine_module, "get_stock_historical_data", lambda *args, **kwargs: {"kline_data": series})
    monkeypatch.setattr(backtest_engine_module, "build_strategy_signals", lambda *args: {
        "signals": [1] + [0 if sell else 1] * 39,
    })

    result = backtest_engine_module.BacktestEngine().run(
        ticker="AAPL", strategy="ma_cross", t_plus_one=False, initial_cash=cash, fee_bps=rate, slippage_bps=rate,
    )

    assert result["success"] is False
    assert result["error"] == "invalid_backtest_calculation"


@pytest.mark.parametrize("t_plus_one", [False, True])
def test_initial_trade_costs_are_included_in_max_drawdown(monkeypatch, t_plus_one):
    series = _build_series(days=40)
    for row in series:
        row["close"] = 100.0
    monkeypatch.setattr(backtest_engine_module, "get_stock_historical_data", lambda *args, **kwargs: {"kline_data": series})
    monkeypatch.setattr(backtest_engine_module, "build_strategy_signals", lambda *args: {"signals": [1] * 40})

    result = backtest_engine_module.BacktestEngine().run(
        ticker="AAPL", strategy="ma_cross", fee_bps=50, slippage_bps=50, t_plus_one=t_plus_one,
    )

    assert result["metrics"]["total_return_pct"] < 0
    assert result["metrics"]["max_drawdown_pct"] == pytest.approx(result["metrics"]["total_return_pct"])


def test_flat_rsi_does_not_force_an_overbought_exit():
    from backend.services.backtest_strategies import _rsi, rsi_mean_reversion_signals
    assert _rsi([100.0] * 30)[-1] == 50.0
    closes = [100.0 - i for i in range(20)] + [81.0] * 30
    assert rsi_mean_reversion_signals(closes)["signals"][-1] == 1


def test_duplicate_daily_bars_are_not_counted_as_extra_trading_days(monkeypatch):
    series = _build_series(days=80)
    duplicate = {**series[10], "close": series[10]["close"] + 1}
    monkeypatch.setattr(backtest_engine_module, "get_stock_historical_data", lambda *args, **kwargs: {"kline_data": [*series, duplicate]})
    result = backtest_engine_module.BacktestEngine().run(ticker="AAPL", strategy="ma_cross")
    assert result["period"]["bars"] == 80
    assert len({row["time"] for row in result["equity_curve"]}) == 80
    assert result["equity_curve"][10]["price"] == duplicate["close"]


def test_backtest_engine_runs_with_primary_historical_source(monkeypatch):
    monkeypatch.setattr(
        backtest_engine_module,
        "get_stock_historical_data",
        lambda ticker, period="5y", interval="1d": {"kline_data": _build_series(), "source": "unit_test_hist"},
    )
    monkeypatch.setattr(backtest_engine_module, "fetch_cn_hk_kline", lambda ticker, limit=1200: [])

    engine = backtest_engine_module.BacktestEngine()
    result = engine.run(ticker="AAPL", strategy="ma_cross", t_plus_one=True)

    assert result["success"] is True
    assert result["source"] == "unit_test_hist"
    assert result["ticker"] == "AAPL"
    assert result["metrics"]["final_equity"] > 0
    assert len(result["equity_curve"]) > 0


def test_backtest_engine_uses_cn_hk_fallback(monkeypatch):
    monkeypatch.setattr(
        backtest_engine_module,
        "get_stock_historical_data",
        lambda ticker, period="5y", interval="1d": {"kline_data": [], "source": "empty"},
    )
    monkeypatch.setattr(backtest_engine_module, "fetch_cn_hk_kline", lambda ticker, limit=1200: _build_series(80.0, 150))

    engine = backtest_engine_module.BacktestEngine()
    result = engine.run(ticker="600519.SH", strategy="macd", market="CN")

    assert result["success"] is True
    assert result["source"] == "eastmoney_kline"
    assert result["period"]["bars"] >= 100


def test_backtest_engine_returns_insufficient_data(monkeypatch):
    monkeypatch.setattr(
        backtest_engine_module,
        "get_stock_historical_data",
        lambda ticker, period="5y", interval="1d": {"kline_data": _build_series(days=10), "source": "short"},
    )
    monkeypatch.setattr(backtest_engine_module, "fetch_cn_hk_kline", lambda ticker, limit=1200: [])

    engine = backtest_engine_module.BacktestEngine()
    result = engine.run(ticker="AAPL", strategy="rsi_mean_reversion")

    assert result["success"] is False
    assert result["error"] == "insufficient_price_data"


def test_backtest_engine_t_plus_one_uses_previous_bar_signal(monkeypatch):
    series = _build_series(days=80)

    monkeypatch.setattr(
        backtest_engine_module,
        "get_stock_historical_data",
        lambda ticker, period="5y", interval="1d": {"kline_data": series, "source": "unit_test_hist"},
    )
    monkeypatch.setattr(backtest_engine_module, "fetch_cn_hk_kline", lambda ticker, limit=1200: [])

    signals = [1] + [0] * (len(series) - 1)

    def _fake_signals(_strategy, closes, params=None):
        return {"name": "unit_test", "signals": signals[: len(closes)], "params": {}}

    monkeypatch.setattr(backtest_engine_module, "build_strategy_signals", _fake_signals)

    engine = backtest_engine_module.BacktestEngine()
    t1_result = engine.run(ticker="AAPL", strategy="ma_cross", t_plus_one=True)
    t0_result = engine.run(ticker="AAPL", strategy="ma_cross", t_plus_one=False)

    t1_buy = next(item for item in t1_result["trades"] if item.get("type") == "buy")
    t0_buy = next(item for item in t0_result["trades"] if item.get("type") == "buy")
    assert t1_buy["time"] == series[1]["time"]
    assert t0_buy["time"] == series[0]["time"]


def test_backtest_engine_filters_zero_price_bars(monkeypatch):
    """R24 回归：close=0 的脏 bar 必须在归一化时剔除，否则买入路径
    cash/(0*(1+fee)) 除零，整个回测 500。"""
    series = _build_series()
    series[3]["close"] = 0.0  # 混入停牌/脏数据 0 价 bar

    monkeypatch.setattr(
        backtest_engine_module,
        "get_stock_historical_data",
        lambda ticker, period="5y", interval="1d": {"kline_data": series, "source": "unit_test_hist"},
    )
    monkeypatch.setattr(backtest_engine_module, "fetch_cn_hk_kline", lambda ticker, limit=1200: [])

    engine = backtest_engine_module.BacktestEngine()
    result = engine.run(ticker="AAPL", strategy="ma_cross", t_plus_one=True)

    assert result["success"] is True  # 旧代码在此抛 ZeroDivisionError
    assert len(result["equity_curve"]) > 0


def test_backtest_engine_filters_non_finite_price_bars(monkeypatch):
    series = _build_series()
    series[3]["close"] = "nan"
    series[4]["close"] = "inf"

    monkeypatch.setattr(
        backtest_engine_module,
        "get_stock_historical_data",
        lambda ticker, period="5y", interval="1d": {
            "kline_data": series,
            "source": "unit_test_hist",
        },
    )
    monkeypatch.setattr(
        backtest_engine_module,
        "fetch_cn_hk_kline",
        lambda ticker, limit=1200: [],
    )

    result = backtest_engine_module.BacktestEngine().run(
        ticker="AAPL",
        strategy="ma_cross",
        t_plus_one=True,
    )

    assert result["success"] is True
    assert result["period"]["bars"] == len(series) - 2


def test_backtest_engine_cost_and_slippage_reduce_final_equity(monkeypatch):
    series = _build_series(days=120)

    monkeypatch.setattr(
        backtest_engine_module,
        "get_stock_historical_data",
        lambda ticker, period="5y", interval="1d": {"kline_data": series, "source": "unit_test_hist"},
    )
    monkeypatch.setattr(backtest_engine_module, "fetch_cn_hk_kline", lambda ticker, limit=1200: [])

    def _fake_signals(_strategy, closes, params=None):
        return {"name": "unit_test", "signals": [1 for _ in closes], "params": {}}

    monkeypatch.setattr(backtest_engine_module, "build_strategy_signals", _fake_signals)

    engine = backtest_engine_module.BacktestEngine()
    no_cost = engine.run(ticker="AAPL", strategy="ma_cross", t_plus_one=False, fee_bps=0.0, slippage_bps=0.0)
    with_cost = engine.run(ticker="AAPL", strategy="ma_cross", t_plus_one=False, fee_bps=50.0, slippage_bps=50.0)

    assert no_cost["success"] is True
    assert with_cost["success"] is True
    assert with_cost["metrics"]["final_equity"] < no_cost["metrics"]["final_equity"]


def test_backtest_engine_t_plus_one_prevents_same_day_round_trip(monkeypatch):
    series = _build_series(days=90)

    monkeypatch.setattr(
        backtest_engine_module,
        "get_stock_historical_data",
        lambda ticker, period="5y", interval="1d": {"kline_data": series, "source": "unit_test_hist"},
    )
    monkeypatch.setattr(backtest_engine_module, "fetch_cn_hk_kline", lambda ticker, limit=1200: [])

    def _fake_signals(_strategy, closes, params=None):
        return {"name": "unit_test", "signals": [1 if idx % 2 == 0 else 0 for idx, _ in enumerate(closes)], "params": {}}

    monkeypatch.setattr(backtest_engine_module, "build_strategy_signals", _fake_signals)

    engine = backtest_engine_module.BacktestEngine()
    result = engine.run(ticker="AAPL", strategy="ma_cross", t_plus_one=True)

    assert result["success"] is True
    trades = result["trades"]
    for idx in range(1, len(trades)):
        prev_trade = trades[idx - 1]
        curr_trade = trades[idx]
        if prev_trade.get("type") == "buy" and curr_trade.get("type") == "sell":
            assert curr_trade.get("time") != prev_trade.get("time")
