from __future__ import annotations

import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.dashboard import data_fetchers_equity as equity


@pytest.mark.parametrize("ticker", ["600519", "000001", "832000"])
def test_plain_six_digit_symbols_use_cn_equity_sources(monkeypatch, ticker):
    calls = []
    monkeypatch.setattr(equity, "_fetch_valuation_from_cn_hk_market",
                        lambda symbol: calls.append(symbol) or {"trailing_pe": 20})
    assert equity._infer_equity_market(ticker) == "CN"
    assert equity.fetch_valuation(ticker)["trailing_pe"] == 20
    assert calls == [ticker]


@pytest.mark.parametrize("bad_meta", [{"error": "bad"}, {"ticker": "MSFT"}, {"symbol": "MSFT"}])
def test_sparse_primary_history_metadata_does_not_discard_unlabeled_valid_rows(monkeypatch, bad_meta):
    from backend.tools import price
    good = {"Open": 100, "High": 120, "Low": 90, "Close": 100}
    hist = pd.DataFrame([{**good, **bad_meta, "Close": 110}, good],
                        index=pd.to_datetime(["2026-01-01", "2026-01-02"]), dtype=object)
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(
        Ticker=lambda symbol: SimpleNamespace(history=lambda **kwargs: hist)))
    monkeypatch.setattr(price, "_fetch_with_stooq_history", lambda *args, **kwargs: None)
    monkeypatch.setattr(price, "get_stock_historical_data", lambda *args, **kwargs: None)
    result = equity._load_ohlcv_frame("AAPL")
    assert result is not None and len(result) == 1
    assert result.iloc[0]["Close"] == 100


def test_yfinance_history_is_validated_before_it_blocks_fallback_technical_evidence(monkeypatch):
    from backend.tools import price
    good = {"Open": 100, "High": 120, "Low": 90, "Close": 100, "Volume": 10}
    hist = pd.DataFrame([good, {**good, "Close": 110, "status": " Failed "}],
                         index=pd.to_datetime(["2026-01-01", "2026-01-02"]), dtype=object)
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(
        Ticker=lambda symbol: SimpleNamespace(history=lambda **kwargs: hist)))
    fallback = {"time": "2026-01-03", "open": 100, "high": 120, "low": 90, "close": 115}
    monkeypatch.setattr(price, "_fetch_with_stooq_history", lambda *args, **kwargs: {"kline_data": [fallback]})
    result = equity._load_ohlcv_frame("AAPL")
    assert len(result) == 1 and result.iloc[-1]["Close"] == 100
    hist.iloc[0, hist.columns.get_loc("Close")] = -1
    result = equity._load_ohlcv_frame("AAPL")
    assert len(result) == 1 and result.iloc[-1]["Close"] == 115


@pytest.mark.parametrize("identity", [{"symbol": "MSFT"}, {"ticker": "MSFT"}, {"symbol": {}}])
def test_recommendation_summary_requires_matching_instrument(monkeypatch, identity):
    def install(values):
        rec = pd.DataFrame([{"strongBuy": 10, "buy": 5, **values}], dtype=object)
        monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(
            Ticker=lambda symbol: SimpleNamespace(recommendations_summary=rec)))
    install(identity)
    assert equity.fetch_recommendations("AAPL") is None
    install({"symbol": " aapl ", "ticker": "AAPL"})
    assert equity.fetch_recommendations("AAPL")["strong_buy"] == 10


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "failed"}, {"status": " Unavailable "}])
def test_failed_recommendation_summary_cannot_publish_analyst_counts(monkeypatch, failure):
    rec = pd.DataFrame([{"strongBuy": 10, "buy": 5, **failure}], dtype=object)
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(
        Ticker=lambda symbol: SimpleNamespace(recommendations_summary=rec)))
    assert equity.fetch_recommendations("AAPL") is None


@pytest.mark.parametrize("field", ["symbol", "ticker"])
def test_earnings_history_excludes_other_instrument_observations(monkeypatch, field):
    good = {"epsEstimate": 1.0, "epsActual": 1.2, field: " aapl "}
    history = pd.DataFrame([{**good, field: "MSFT"}, good],
        index=pd.to_datetime(["2025-03-31", "2025-06-30"]), dtype=object)
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(
        Ticker=lambda symbol: SimpleNamespace(earnings_history=history)))
    result = equity.fetch_earnings_history("AAPL")
    assert [item["quarter"] for item in result] == ["2025-06-30"]


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "failed"}, {"status": " Failed "}])
def test_failed_earnings_rows_cannot_be_published_beside_valid_eps(monkeypatch, failure):
    good = {"epsEstimate": 1.0, "epsActual": 1.2, "surprisePercent": 20.0}
    history = pd.DataFrame([{**good, **failure}, good],
        index=pd.to_datetime(["2025-03-31", "2025-06-30"]), dtype=object)
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(
        Ticker=lambda symbol: SimpleNamespace(earnings_history=history)))
    result = equity.fetch_earnings_history("AAPL")
    assert result == [{"quarter": "2025-06-30", "eps_estimate": 1.0, "eps_actual": 1.2, "surprise_pct": 20.0}]


@pytest.mark.parametrize("as_frame", [False, True])
@pytest.mark.parametrize("identity", [{"symbol": "MSFT"}, {"ticker": "MSFT"},
                                    {"ticker": {}, "symbol": "AAPL"}])
def test_analyst_targets_must_match_requested_instrument(monkeypatch, as_frame, identity):
    payload = {"low": 80, "high": 150, "mean": 120, **identity}
    def install(value):
        targets = pd.DataFrame([value], dtype=object) if as_frame else value
        monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(
            Ticker=lambda symbol: SimpleNamespace(analyst_price_targets=targets)))
    install(payload)
    assert equity.fetch_analyst_targets("AAPL") is None
    install({"low": 80, "high": 150, "mean": 120, "ticker": " aapl ", "symbol": "AAPL"})
    assert equity.fetch_analyst_targets("AAPL")["mean"] == 120


@pytest.mark.parametrize("as_frame", [False, True])
@pytest.mark.parametrize("failure", [{"success": False}, {"error": "failed"}, {"status": " Unavailable "}])
def test_failed_analyst_targets_are_unavailable_even_when_prices_are_present(monkeypatch, as_frame, failure):
    payload = {"low": 80, "high": 150, "mean": 120, **failure}
    targets = pd.DataFrame([payload], dtype=object) if as_frame else payload
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(
        Ticker=lambda symbol: SimpleNamespace(analyst_price_targets=targets)))
    assert equity.fetch_analyst_targets("AAPL") is None


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_failed_nested_finnhub_metrics_cannot_supply_retained_valuation(monkeypatch, failure):
    from backend.dashboard import data_providers as module
    profile = {"marketCapitalization": 10}
    metric = {"peTTM": 20, "52WeekHigh": 120, "52WeekLow": 80, **failure}
    monkeypatch.setattr(module, "_finnhub_request", lambda path, *args, **kwargs:
                        profile if path == "stock/profile2" else {"metric": metric})
    result = module._fetch_valuation_from_finnhub("AAPL")
    assert result["market_cap"] == 10_000_000
    assert all(value is None for key, value in result.items() if key != "market_cap")
    profile.clear()
    assert module._fetch_valuation_from_finnhub("AAPL") is None
    metric.clear()
    metric["peTTM"] = 20
    assert module._fetch_valuation_from_finnhub("AAPL")["trailing_pe"] == 20


@pytest.mark.parametrize("provider", ["finnhub", "cn_hk"])
@pytest.mark.parametrize("yield_value", [-0.1, 0, 0.02])
def test_fallback_dividend_yields_reject_negative_values_and_keep_valid_ratios(monkeypatch, provider, yield_value):
    from backend.dashboard import data_providers as module
    from backend.tools import cn_hk_market
    monkeypatch.setattr(module, "_finnhub_request", lambda path, *args, **kwargs:
        {} if path == "stock/profile2" else {"metric": {"peTTM": 20,
            "dividendYieldIndicatedAnnual": yield_value * 100}})
    monkeypatch.setattr(cn_hk_market, "fetch_cn_hk_quote_metrics", lambda *args, **kwargs:
        {"trailing_pe": 20, "dividend_yield": yield_value})
    result = (module._fetch_valuation_from_finnhub("AAPL") if provider == "finnhub"
              else module._fetch_valuation_from_cn_hk_market("600519.SS"))
    if yield_value < 0:
        assert result["dividend_yield"] is None
    else:
        assert result["dividend_yield"] == pytest.approx(yield_value)
    assert result["trailing_pe"] == 20


@pytest.mark.parametrize("provider", ["finnhub", "cn_hk"])
@pytest.mark.parametrize("high, low, expected", [
    (-1, 80, (None, 80)), (120, 0, (120, None)), (90, 100, (None, None)), (120, 80, (120, 80)),
])
def test_fallback_annual_price_ranges_require_positive_ordered_bounds(monkeypatch, provider, high, low, expected):
    from backend.dashboard import data_providers as module
    from backend.tools import cn_hk_market
    monkeypatch.setattr(module, "_finnhub_request", lambda path, *args, **kwargs:
        {} if path == "stock/profile2" else {"metric": {"peTTM": 20, "52WeekHigh": high, "52WeekLow": low}})
    monkeypatch.setattr(cn_hk_market, "fetch_cn_hk_quote_metrics", lambda *args, **kwargs:
        {"trailing_pe": 20, "week52_high": high, "week52_low": low, "market_cap": -1})
    result = (module._fetch_valuation_from_finnhub("AAPL") if provider == "finnhub"
              else module._fetch_valuation_from_cn_hk_market("600519.SS"))
    assert (result["week52_high"], result["week52_low"]) == expected
    assert result["trailing_pe"] == 20
    assert result["market_cap"] is None


@pytest.mark.parametrize("provider", ["sec", "cn_hk"])
def test_statement_adapters_bound_periods_and_metrics_to_requested_limit(monkeypatch, provider):
    from backend.dashboard import data_providers as module
    from backend.tools import sec, cn_hk_market
    payload = {"periods": ["2025Q1", "2024Q4", "2024Q3"], "revenue": [100, 90, 80], "eps": [1]}
    monkeypatch.setattr(sec, "get_sec_company_facts_quarterly", lambda *args, **kwargs: payload)
    monkeypatch.setattr(cn_hk_market, "fetch_cn_hk_financial_statements", lambda *args, **kwargs: payload)
    result = (module._fetch_financial_statements_from_sec_companyfacts("AAPL", periods=2)
              if provider == "sec" else module._fetch_financial_statements_from_cn_hk_market("600519.SS", periods=2))
    assert result["periods"] == ["2025Q1", "2024Q4"]
    assert result["revenue"] == [100, 90]
    assert result["eps"] == [1, None]
    assert all(len(values) == 2 for values in result.values())
    assert payload["periods"] == ["2025Q1", "2024Q4", "2024Q3"]
    assert payload["revenue"] == [100, 90, 80]


@pytest.mark.parametrize("provider", ["sec", "cn_hk"])
def test_financial_statement_metrics_align_with_period_count(monkeypatch, provider):
    from backend.dashboard import data_providers as module
    from backend.tools import sec, cn_hk_market
    payload = {"periods": ["2025Q1", "2024Q4"], "revenue": [100, 90, 80], "eps": [1]}
    monkeypatch.setattr(sec, "get_sec_company_facts_quarterly", lambda *args, **kwargs: payload)
    monkeypatch.setattr(cn_hk_market, "fetch_cn_hk_financial_statements", lambda *args, **kwargs: payload)
    result = (module._fetch_financial_statements_from_sec_companyfacts("AAPL")
              if provider == "sec" else module._fetch_financial_statements_from_cn_hk_market("600519.SS"))
    assert result["revenue"] == [100, 90]
    assert result["eps"] == [1, None]
    assert result["gross_profit"] == [None, None]
    assert payload["revenue"] == [100, 90, 80]


@pytest.mark.parametrize("provider", ["sec", "cn_hk"])
@pytest.mark.parametrize("periods", [None, "2025Q1", [], [None], ["  "]])
def test_statement_adapters_require_usable_period_arrays(monkeypatch, provider, periods):
    from backend.dashboard import data_providers as module
    from backend.tools import sec, cn_hk_market
    payload = {"periods": periods, "revenue": [100]}
    monkeypatch.setattr(sec, "get_sec_company_facts_quarterly", lambda *args, **kwargs: payload)
    monkeypatch.setattr(cn_hk_market, "fetch_cn_hk_financial_statements", lambda *args, **kwargs: payload)
    result = (module._fetch_financial_statements_from_sec_companyfacts("AAPL")
              if provider == "sec" else module._fetch_financial_statements_from_cn_hk_market("600519.SS"))
    assert result is None


@pytest.mark.parametrize("provider", ["sec", "cn_hk"])
def test_statement_metric_arrays_normalize_invalid_and_nonfinite_values(monkeypatch, provider):
    from backend.dashboard import data_providers as module
    from backend.tools import sec, cn_hk_market
    payload = {"periods": ["2025Q1", "2024Q4", "2024Q3", "2024Q2"],
               "revenue": ["100", float("inf"), True, "bad"]}
    monkeypatch.setattr(sec, "get_sec_company_facts_quarterly", lambda *args, **kwargs: payload)
    monkeypatch.setattr(cn_hk_market, "fetch_cn_hk_financial_statements", lambda *args, **kwargs: payload)
    result = (module._fetch_financial_statements_from_sec_companyfacts("AAPL")
              if provider == "sec" else module._fetch_financial_statements_from_cn_hk_market("600519.SS"))
    assert result["revenue"] == [100.0, None, None, None]
    assert payload["revenue"][0] == "100"


@pytest.mark.parametrize("n_days", [0, -1])
def test_empty_indicator_series_requests_stop_before_ohlcv_io(monkeypatch, n_days):
    calls = []
    monkeypatch.setattr(equity, "_load_ohlcv_frame", lambda *args, **kwargs: calls.append(args))
    assert equity.fetch_indicator_series("AAPL", n_days) is None
    assert calls == []


@pytest.mark.parametrize("provider", ["sec", "cn_hk"])
@pytest.mark.parametrize("periods", [0, -1])
def test_statement_adapters_honor_nonpositive_limits_before_io(monkeypatch, provider, periods):
    from backend.dashboard import data_providers as module
    from backend.tools import sec, cn_hk_market
    calls = []
    def fetch(*args, **kwargs):
        calls.append(args)
        return {"periods": ["2025Q1"], "revenue": [100]}
    monkeypatch.setattr(sec, "get_sec_company_facts_quarterly", fetch)
    monkeypatch.setattr(cn_hk_market, "fetch_cn_hk_financial_statements", fetch)
    result = (module._fetch_financial_statements_from_sec_companyfacts("AAPL", periods)
              if provider == "sec" else module._fetch_financial_statements_from_cn_hk_market("600519.SS", periods))
    assert result is None and calls == []


@pytest.mark.parametrize("market_cap", [-1, 0])
def test_finnhub_valuation_recovers_valid_market_cap_after_invalid_profile(monkeypatch, market_cap):
    from backend.dashboard import data_providers as module
    monkeypatch.setattr(module, "_finnhub_request", lambda path, *args, **kwargs:
                        {"marketCapitalization": market_cap} if path == "stock/profile2"
                        else {"metric": {"marketCapitalization": 10, "peTTM": 20}})
    result = module._fetch_valuation_from_finnhub("AAPL")
    assert result["market_cap"] == 10000000


@pytest.mark.parametrize("provider", ["sec", "cn_hk"])
@pytest.mark.parametrize("status", ["error", " Failed ", "unavailable"])
def test_dashboard_statement_adapters_reject_failed_status(monkeypatch, provider, status):
    from backend.dashboard import data_providers as module
    from backend.tools import sec, cn_hk_market
    payload = {"status": status, "periods": ["2025Q1"], "revenue": [999]}
    if provider == "sec":
        monkeypatch.setattr(sec, "get_sec_company_facts_quarterly", lambda *args, **kwargs: payload)
        result = module._fetch_financial_statements_from_sec_companyfacts("AAPL")
    else:
        monkeypatch.setattr(cn_hk_market, "fetch_cn_hk_financial_statements", lambda *args, **kwargs: payload)
        result = module._fetch_financial_statements_from_cn_hk_market("600519.SS")
    assert result is None


@pytest.mark.parametrize("status", ["error", " Failed ", "unavailable"])
def test_dashboard_cn_hk_valuation_rejects_failed_status(monkeypatch, status):
    from backend.dashboard import data_providers as module
    from backend.tools import cn_hk_market
    monkeypatch.setattr(cn_hk_market, "fetch_cn_hk_quote_metrics", lambda *args, **kwargs:
                        {"status": status, "trailing_pe": 999})
    assert module._fetch_valuation_from_cn_hk_market("600519.SS") is None


@pytest.mark.parametrize("status", ["error", " Failed ", "unavailable"])
def test_dashboard_finnhub_request_rejects_business_failure_status(monkeypatch, status):
    from backend.dashboard import data_providers as module
    from backend.tools import env, http
    monkeypatch.setattr(env, "FINNHUB_API_KEY", "test-key")
    monkeypatch.setattr(http, "_http_get", lambda *args, **kwargs:
                        SimpleNamespace(status_code=200, json=lambda: {"status": status, "metric": {"peTTM": 999}}))
    assert module._finnhub_request("stock/metric", {"symbol": "AAPL"}) is None


def test_reversed_annual_price_range_cannot_be_published(monkeypatch):
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda symbol:
                        SimpleNamespace(info={"fiftyTwoWeekHigh": 90, "fiftyTwoWeekLow": 100, "trailingPE": 20})))
    result = equity.fetch_valuation("AAPL")
    assert result["week52_high"] is None and result["week52_low"] is None
    assert result["trailing_pe"] == 20


@pytest.mark.parametrize("dividend_yield", [-0.1, True])
def test_valuation_dividend_yield_cannot_be_negative_or_boolean(monkeypatch, dividend_yield):
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda symbol:
                        SimpleNamespace(info={"dividendYield": dividend_yield, "trailingPE": 20})))
    result = equity.fetch_valuation("AAPL")
    assert result["dividend_yield"] is None


@pytest.mark.parametrize("field, value", [("marketCap", -1), ("marketCap", 0),
                                        ("fiftyTwoWeekHigh", -1), ("fiftyTwoWeekLow", 0)])
def test_valuation_market_cap_and_price_levels_require_positive_values(monkeypatch, field, value):
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda symbol:
                        SimpleNamespace(info={field: value, "trailingPE": 20})))
    result = equity.fetch_valuation("AAPL")
    key = {"marketCap": "market_cap", "fiftyTwoWeekHigh": "week52_high", "fiftyTwoWeekLow": "week52_low"}[field]
    assert result[key] is None
    assert result["trailing_pe"] == 20


@pytest.mark.parametrize("field", ["ticker", "symbol"])
def test_ohlcv_pipeline_excludes_daily_rows_for_other_instruments(monkeypatch, field):
    from backend.tools import price
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda symbol:
                        SimpleNamespace(history=lambda **kwargs: pd.DataFrame())))
    row = {"time": "2026-01-02", "open": 100, "high": 102, "low": 99, "close": 100}
    monkeypatch.setattr(price, "_fetch_with_stooq_history", lambda *args, **kwargs: None)
    monkeypatch.setattr(price, "get_stock_historical_data", lambda *args, **kwargs:
                        {"kline_data": [row, {**row, field: "MSFT", "close": 101}]})
    assert equity._load_ohlcv_frame("AAPL").iloc[0]["Close"] == 100


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_failed_ohlcv_rows_cannot_override_valid_observations(failure):
    row = {"time": "2026-01-02", "open": 100, "high": 102, "low": 99, "close": 100}
    frame = equity._build_ohlcv_frame_from_rows([row, {**row, "close": 101, **failure}])
    assert frame.iloc[0]["Close"] == 100


@pytest.mark.parametrize("status", ["error", " Failed ", "unavailable"])
def test_shared_history_status_failures_cannot_supply_ohlcv(monkeypatch, status):
    from backend.tools import price
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda symbol:
                        SimpleNamespace(history=lambda **kwargs: pd.DataFrame())))
    monkeypatch.setattr(price, "_fetch_with_stooq_history", lambda *args, **kwargs: None)
    monkeypatch.setattr(price, "get_stock_historical_data", lambda *args, **kwargs:
                        {"status": status, "kline_data": [{"time": "2026-01-02", "open": 100,
                          "high": 102, "low": 99, "close": 100}]})
    assert equity._load_ohlcv_frame("AAPL") is None


@pytest.mark.parametrize("status", ["error", " Failed ", "unavailable"])
def test_stooq_status_failures_do_not_mask_shared_history_fallback(monkeypatch, status):
    from backend.tools import price
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda symbol:
                        SimpleNamespace(history=lambda **kwargs: pd.DataFrame())))
    row = {"time": "2026-01-02", "open": 100, "high": 102, "low": 99, "close": 100}
    monkeypatch.setattr(price, "_fetch_with_stooq_history", lambda *args, **kwargs:
                        {"status": status, "kline_data": [row]})
    monkeypatch.setattr(price, "get_stock_historical_data", lambda *args, **kwargs:
                        {"kline_data": [{**row, "close": 101}]})
    assert equity._load_ohlcv_frame("AAPL").iloc[0]["Close"] == 101


@pytest.mark.parametrize("status", ["error", " Failed ", "unavailable"])
def test_failed_valuation_status_uses_the_next_provider(monkeypatch, status):
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda symbol:
                        SimpleNamespace(info={"status": status, "trailingPE": 100})))
    monkeypatch.setattr(equity, "_fetch_valuation_from_finnhub", lambda symbol: {"trailing_pe": 20})
    assert equity.fetch_valuation("AAPL")["trailing_pe"] == 20


@pytest.mark.parametrize("field", ["symbol", "ticker"])
def test_yfinance_valuation_rejects_another_instrument(monkeypatch, field):
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _symbol: SimpleNamespace(
        info={field: "MSFT", "trailingPE": 100.0},
    )))
    monkeypatch.setattr(equity, "_fetch_valuation_from_finnhub", lambda _symbol: {"trailing_pe": 20.0})
    assert equity.fetch_valuation("AAPL")["trailing_pe"] == 20.0


@pytest.mark.parametrize("marker", [{"success": False}, {"error": "unavailable"}])
def test_yfinance_failed_valuation_info_uses_fallback(monkeypatch, marker):
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _symbol: SimpleNamespace(
        info={**marker, "trailingPE": 100.0},
    )))
    monkeypatch.setattr(equity, "_fetch_valuation_from_finnhub", lambda _symbol: {"trailing_pe": 20.0})
    assert equity.fetch_valuation("AAPL")["trailing_pe"] == 20.0


@pytest.mark.parametrize("periods", [0, -1])
def test_empty_financial_statement_limit_stops_before_io(monkeypatch, periods):
    calls = []
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda symbol: calls.append(symbol)))
    monkeypatch.setattr(equity, "_fetch_financial_statements_from_sec_companyfacts",
                        lambda *args, **kwargs: {"periods": ["2025Q1"], "revenue": [100.0]})
    monkeypatch.setattr(equity, "_fetch_financial_statements_from_finnhub", lambda *args, **kwargs: None)
    assert equity.fetch_financial_statements("AAPL", periods=periods) is None
    assert calls == []


def test_financial_period_limit_selects_latest_across_unsorted_columns(monkeypatch):
    frame = pd.DataFrame([[10.0, 20.0]], index=["Total Revenue"],
                         columns=pd.to_datetime(["2024-03-31", "2025-03-31"]))
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _symbol: SimpleNamespace(
        quarterly_income_stmt=frame,
    )))
    result = equity.fetch_financial_statements("AAPL", periods=1)
    assert result["periods"] == ["2025Q1"]
    assert result["revenue"] == [20.0]


@pytest.mark.parametrize("invalid_time", [True, 1767225600, [], {"date": "2026-01-01"}])
def test_ohlcv_rows_skip_invalid_time_shapes(monkeypatch, invalid_time):
    valid = {"time": "2026-01-02", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}
    frame = equity._build_ohlcv_frame_from_rows([{**valid, "time": invalid_time}, valid])
    assert frame is not None
    assert len(frame) == 1
    assert frame.index[0] == pd.Timestamp("2026-01-02")


@pytest.mark.parametrize("changes", [{"close": 0.0}, {"open": -1.0}, {"high": 98.0}, {"low": 102.0}])
def test_ohlcv_frame_filters_invalid_price_geometry(changes):
    valid = {"time": "2026-01-02", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}
    frame = equity._build_ohlcv_frame_from_rows([{**valid, "time": "2026-01-01", **changes}, valid])
    assert frame is not None
    assert len(frame) == 1
    assert frame.iloc[0]["Close"] == 100.0


def test_ohlcv_negative_volume_is_not_a_trading_amount():
    frame = equity._build_ohlcv_frame_from_rows([{
        "time": "2026-01-02", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": -10.0,
    }])
    assert frame.iloc[0]["Volume"] == 0.0


def test_ohlcv_duplicate_timestamps_use_last_provider_observation():
    row = {"time": "2026-01-02", "open": 100.0, "high": 102.0, "low": 99.0, "close": 100.0}
    frame = equity._build_ohlcv_frame_from_rows([row, {**row, "close": 101.0}])
    assert len(frame) == 1
    assert frame.iloc[0]["Close"] == 101.0


def test_ohlcv_timezone_variants_share_one_sortable_observation():
    row = {"open": 100.0, "high": 102.0, "low": 99.0, "close": 100.0}
    frame = equity._build_ohlcv_frame_from_rows([
        {**row, "time": "2026-01-02T00:00:00"},
        {**row, "time": "2026-01-02T08:00:00+08:00", "close": 101.0},
    ])
    assert len(frame) == 1
    assert frame.iloc[0]["Close"] == 101.0


@pytest.mark.parametrize("marker", [{"success": False}, {"error": "unavailable"}])
def test_stooq_failed_history_does_not_mask_next_fallback(monkeypatch, marker):
    from backend.tools import price

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _symbol: SimpleNamespace(
        history=lambda **kwargs: pd.DataFrame(),
    )))
    row = {"time": "2026-01-02", "open": 100.0, "high": 102.0, "low": 99.0, "close": 100.0}
    monkeypatch.setattr(price, "_fetch_with_stooq_history", lambda *args, **kwargs: {**marker, "kline_data": [row]})
    monkeypatch.setattr(price, "get_stock_historical_data", lambda *args, **kwargs: {"kline_data": [{**row, "close": 101.0}]})
    assert equity._load_ohlcv_frame("AAPL").iloc[0]["Close"] == 101.0


@pytest.mark.parametrize("marker", [{"success": False}, {"error": "unavailable"}])
def test_failed_history_pipeline_cannot_supply_technical_data(monkeypatch, marker):
    from backend.tools import price

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _symbol: SimpleNamespace(
        history=lambda **kwargs: pd.DataFrame(),
    )))
    monkeypatch.setattr(price, "_fetch_with_stooq_history", lambda *args, **kwargs: None)
    monkeypatch.setattr(price, "get_stock_historical_data", lambda *args, **kwargs: {
        **marker, "kline_data": [{"time": "2026-01-02", "open": 100.0, "high": 102.0, "low": 99.0, "close": 100.0}],
    })
    assert equity._load_ohlcv_frame("AAPL") is None


@pytest.mark.parametrize("field", ["ticker", "symbol"])
def test_stooq_history_mismatch_uses_next_provider(monkeypatch, field):
    from backend.tools import price

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _symbol: SimpleNamespace(
        history=lambda **kwargs: pd.DataFrame(),
    )))
    row = {"time": "2026-01-02", "open": 100.0, "high": 102.0, "low": 99.0, "close": 100.0}
    monkeypatch.setattr(price, "_fetch_with_stooq_history", lambda *args, **kwargs: {field: "MSFT", "kline_data": [row]})
    monkeypatch.setattr(price, "get_stock_historical_data", lambda *args, **kwargs: {"kline_data": [{**row, "close": 101.0}]})
    assert equity._load_ohlcv_frame("AAPL").iloc[0]["Close"] == 101.0


@pytest.mark.parametrize("field", ["ticker", "symbol"])
def test_history_pipeline_mismatch_is_unavailable(monkeypatch, field):
    from backend.tools import price

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _symbol: SimpleNamespace(
        history=lambda **kwargs: pd.DataFrame(),
    )))
    monkeypatch.setattr(price, "_fetch_with_stooq_history", lambda *args, **kwargs: None)
    monkeypatch.setattr(price, "get_stock_historical_data", lambda *args, **kwargs: {
        field: "MSFT", "kline_data": [{"time": "2026-01-02", "open": 100.0, "high": 102.0, "low": 99.0, "close": 100.0}],
    })
    assert equity._load_ohlcv_frame("AAPL") is None


@pytest.mark.parametrize("value", [0.0, -10.0])
@pytest.mark.parametrize("as_frame", [False, True])
def test_analyst_targets_require_positive_prices(monkeypatch, value, as_frame):
    payload = {"low": value, "current": 100.0, "mean": value, "median": value, "high": 120.0}
    targets = pd.DataFrame([payload]) if as_frame else payload
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _symbol: SimpleNamespace(
        analyst_price_targets=targets,
    )))
    result = equity.fetch_analyst_targets("AAPL")
    assert result == {"low": None, "current": 100.0, "mean": None, "median": None, "high": 120.0}


@pytest.mark.parametrize("targets", [
    {"low": 120.0, "high": 100.0},
    {"low": 100.0, "mean": 90.0, "high": 120.0},
    {"low": 100.0, "median": 130.0, "high": 120.0},
])
def test_inconsistent_analyst_target_ranges_are_unavailable(monkeypatch, targets):
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _symbol: SimpleNamespace(
        analyst_price_targets=targets,
    )))
    assert equity.fetch_analyst_targets("AAPL") is None


@pytest.mark.parametrize("bucket", ["strongBuy", "buy", "hold", "sell", "strongSell"])
def test_recommendation_counts_cannot_be_negative(monkeypatch, bucket):
    row = {"strongBuy": 5, "buy": 5, "hold": 5, "sell": 5, "strongSell": 5}
    row[bucket] = -3
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _symbol: SimpleNamespace(
        recommendations_summary=pd.DataFrame([row]),
    )))
    result = equity.fetch_recommendations("AAPL")
    assert result is not None
    assert all(count >= 0 for count in result.values())
    assert sum(result.values()) == 20


@pytest.mark.parametrize("bucket", ["strongBuy", "buy", "hold", "sell", "strongSell"])
def test_fractional_recommendation_counts_do_not_become_integers(monkeypatch, bucket):
    row = {"strongBuy": 5.0, "buy": 5.0, "hold": 5.0, "sell": 5.0, "strongSell": 5.0}
    row[bucket] = 2.5
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _symbol: SimpleNamespace(
        recommendations_summary=pd.DataFrame([row]),
    )))
    result = equity.fetch_recommendations("AAPL")
    assert sum(result.values()) == 20


def test_shanghai_sh_alias_selects_cn_equity_providers():
    assert equity._infer_equity_market(" 600519.sh ") == "CN"
