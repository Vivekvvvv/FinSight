from __future__ import annotations

import pandas as pd
import pytest

from backend.dashboard import data_fetchers


@pytest.mark.parametrize("field", ["shares", "value"])
@pytest.mark.parametrize("number", [None, True, {}, "bad", float("inf"), float("nan"), "12.5"])
def test_holding_shares_and_values_are_finite_numbers(monkeypatch, field, number):
    from backend.tools import fmp
    rows = [{"symbol": "AAPL", "shares": 10, "value": 100, field: number}]
    monkeypatch.setattr(fmp, "get_etf_holdings", lambda symbol, limit: rows)
    result = data_fetchers.fetch_holdings("SPY", "etf")
    assert result[0][field] == (12.5 if number == "12.5" else 0)
    assert not isinstance(result[0][field], bool)


@pytest.mark.parametrize("weight", [-1, 101, "-10", "101"])
def test_holdings_and_constituents_cannot_publish_out_of_range_percentages(monkeypatch, weight):
    from backend.tools import fmp
    rows = [{"symbol": "AAPL", "weight": weight}, {"symbol": "MSFT", "weight": 100}]
    monkeypatch.setattr(fmp, "get_index_constituents", lambda symbol: rows)
    monkeypatch.setattr(fmp, "get_etf_holdings", lambda symbol, limit: rows)
    for result in (data_fetchers.fetch_top_constituents("SPX", "index"), data_fetchers.fetch_holdings("SPY", "etf")):
        assert [row["weight"] for row in result] == [0, 100]


@pytest.mark.parametrize("weight", [None, True, {}, [], "bad", float("inf"), float("nan"), "12.5"])
def test_holdings_and_constituents_publish_only_finite_numeric_weights(monkeypatch, weight):
    from backend.tools import fmp
    rows = [{"symbol": "AAPL", "weight": weight}]
    monkeypatch.setattr(fmp, "get_index_constituents", lambda symbol: rows)
    monkeypatch.setattr(fmp, "get_etf_holdings", lambda symbol, limit: rows)
    expected = 12.5 if weight == "12.5" else 0
    for result in (data_fetchers.fetch_top_constituents("SPX", "index"), data_fetchers.fetch_holdings("SPY", "etf")):
        assert result[0]["weight"] == expected
        assert not isinstance(result[0]["weight"], bool)


@pytest.mark.parametrize("name", [None, True, 123, {}, [], "  "])
def test_holding_and_constituent_names_are_text_with_symbol_fallback(monkeypatch, name):
    from backend.tools import fmp
    rows = [{"symbol": " aapl ", "name": name}, {"symbol": "MSFT", "name": " Microsoft "}]
    monkeypatch.setattr(fmp, "get_index_constituents", lambda symbol: rows)
    monkeypatch.setattr(fmp, "get_etf_holdings", lambda symbol, limit: rows)
    for result in (data_fetchers.fetch_top_constituents("SPX", "index"), data_fetchers.fetch_holdings("SPY", "etf")):
        assert [row["name"] for row in result] == ["AAPL", "Microsoft"]


@pytest.mark.parametrize("identity", [{"ticker": "MSFT"}, {"symbol": "MSFT"}, {"ticker": {}}])
def test_segment_mix_excludes_explicit_other_instrument_revenue(monkeypatch, identity):
    from backend.tools import fmp
    good = {"segment": "Cloud", "revenue": 100, "percentage": 50, "symbol": " aapl "}
    monkeypatch.setattr(fmp, "get_revenue_product_segmentation", lambda symbol: [
        {**good, **identity, "segment": "Wrong"}, good])
    assert data_fetchers.fetch_segment_mix("AAPL") == [{"name": "Cloud", "value": 100, "weight": 0.5}]


@pytest.mark.parametrize("field", ["ticker", "symbol"])
def test_chart_row_instrument_must_match_requested_symbol(monkeypatch, field):
    good = {"Open": 100, "High": 120, "Low": 90, "Close": 100, field: " aapl "}
    frame = pd.DataFrame([good, {**good, "Close": 110, field: "MSFT"}],
                         index=pd.to_datetime(["2026-01-01", "2026-01-01"]), dtype=object)
    monkeypatch.setattr(data_fetchers, "_load_ohlcv_frame", lambda *args, **kwargs: frame)
    result = data_fetchers.fetch_market_chart("AAPL")
    assert len(result) == 1 and result[0]["close"] == 100


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_failed_chart_rows_cannot_override_valid_observations(monkeypatch, failure):
    good = {"Open": 100, "High": 120, "Low": 90, "Close": 100}
    frame = pd.DataFrame([good, {**good, "Close": 110, **failure}],
                         index=pd.to_datetime(["2026-01-01", "2026-01-01"]), dtype=object)
    monkeypatch.setattr(data_fetchers, "_load_ohlcv_frame", lambda *args, **kwargs: frame)
    result = data_fetchers.fetch_market_chart("AAPL")
    assert len(result) == 1
    assert result[0]["close"] == 100


def test_market_chart_sorts_and_deduplicates_provider_times(monkeypatch):
    rows = [{"Open": 100, "High": 120, "Low": 90, "Close": close} for close in (110, 100, 115)]
    frame = pd.DataFrame(rows, index=pd.to_datetime(["2026-01-02", "2026-01-01", "2026-01-02"]))
    monkeypatch.setattr(data_fetchers, "_load_ohlcv_frame", lambda *args, **kwargs: frame)
    result = data_fetchers.fetch_market_chart("AAPL")
    assert [row["close"] for row in result] == [100, 115]
    assert result[0]["time"] < result[1]["time"]
    assert len(frame) == 3


def test_chart_with_no_usable_rows_is_unavailable_instead_of_cacheable_empty(monkeypatch):
    for frame in (pd.DataFrame([{"Open": 0, "High": 1, "Low": 0, "Close": 1}],
                               index=pd.to_datetime(["2026-01-01"])),
                  pd.DataFrame([{"Open": 100, "High": 110, "Low": 90, "Close": 100}],
                               index=["not-a-time"])):
        monkeypatch.setattr(data_fetchers, "_load_ohlcv_frame", lambda *args, **kwargs: frame)
        assert data_fetchers.fetch_market_chart("AAPL") is None


@pytest.mark.parametrize("volume", [-1, -100, True, float("inf")])
def test_market_chart_invalid_volumes_cannot_be_published_as_negative_or_boolean(monkeypatch, volume):
    frame = pd.DataFrame([{"Open": 100, "High": 110, "Low": 90, "Close": 105, "Volume": volume}],
                         index=pd.to_datetime(["2026-01-01"]))
    monkeypatch.setattr(data_fetchers, "_load_ohlcv_frame", lambda *args, **kwargs: frame)
    result = data_fetchers.fetch_market_chart("AAPL")
    assert result[0]["volume"] == 0
    assert result[0]["close"] == 105


@pytest.mark.parametrize("bad", [{"High": 99}, {"Low": 106}, {"High": 90, "Low": 110}])
def test_market_chart_ohlc_ranges_must_contain_open_and_close(monkeypatch, bad):
    good = {"Open": 100, "High": 110, "Low": 90, "Close": 105}
    frame = pd.DataFrame([{**good, **bad}, good], index=pd.to_datetime(["2026-01-01", "2026-01-02"]))
    monkeypatch.setattr(data_fetchers, "_load_ohlcv_frame", lambda *args, **kwargs: frame)
    result = data_fetchers.fetch_market_chart("AAPL")
    assert len(result) == 1
    assert result[0]["low"] == 90


@pytest.mark.parametrize("field, invalid", [("Open", 0), ("Close", -1), ("High", None),
                                           ("Low", float("inf")), ("Close", True)])
def test_market_chart_discards_unusable_price_rows_before_publishing(monkeypatch, field, invalid):
    good = {"Open": 100, "High": 110, "Low": 90, "Close": 105, "Volume": 10}
    bad = {**good, field: invalid}
    frame = pd.DataFrame([bad, good], index=pd.to_datetime(["2026-01-01", "2026-01-02"]))
    monkeypatch.setattr(data_fetchers, "_load_ohlcv_frame", lambda *args, **kwargs: frame)
    result = data_fetchers.fetch_market_chart("AAPL")
    assert len(result) == 1
    assert result[0]["close"] == 105
    assert result[0]["time"] == int(pd.Timestamp("2026-01-02", tz="UTC").timestamp())


def test_revenue_trend_is_chronological_even_when_provider_periods_are_unsorted(monkeypatch):
    import yfinance
    dates = pd.to_datetime(["2025-06-30", "2025-03-31", "2025-09-30"])
    financials = pd.DataFrame([[200, 100, 300]], index=["Total Revenue"], columns=dates)
    monkeypatch.setattr(yfinance, "Ticker", lambda symbol: type("Ticker", (), {"quarterly_income_stmt": financials})())
    result = data_fetchers.fetch_revenue_trend("AAPL")
    assert [row["period"] for row in result] == ["2025 Q1", "2025 Q2", "2025 Q3"]
    assert [row["value"] for row in result] == [100, 200, 300]


def test_sector_and_segment_names_are_text_and_normalized(monkeypatch):
    from backend.tools import fmp
    monkeypatch.setattr(fmp, "get_revenue_product_segmentation", lambda symbol:
                        [{"segment": {"bad": True}, "revenue": 1, "percentage": 1},
                         {"segment": " Cloud ", "revenue": 100, "percentage": 50}])
    monkeypatch.setattr(fmp, "get_etf_sector_weights", lambda symbol:
                        [{"sector": None, "weight": 50}, {"sector": " Technology ", "weight": 50}])
    assert [row["name"] for row in data_fetchers.fetch_segment_mix("AAPL")] == ["Cloud"]
    assert [row["name"] for row in data_fetchers.fetch_sector_weights("SPY", "etf")] == ["Technology"]


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_failed_segments_and_sectors_cannot_be_published_as_valid_exposures(monkeypatch, failure):
    from backend.tools import fmp
    monkeypatch.setattr(fmp, "get_revenue_product_segmentation", lambda symbol:
                        [{"segment": "Bad", "revenue": 100, "percentage": 50, **failure},
                         {"segment": "Cloud", "revenue": 100, "percentage": 50}])
    monkeypatch.setattr(fmp, "get_etf_sector_weights", lambda symbol:
                        [{"sector": "Bad", "weight": 50, **failure}, {"sector": "Technology", "weight": 50}])
    assert [row["name"] for row in data_fetchers.fetch_segment_mix("AAPL")] == ["Cloud"]
    assert [row["name"] for row in data_fetchers.fetch_sector_weights("SPY", "etf")] == ["Technology"]


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_failed_constituent_and_holding_rows_cannot_displace_valid_data(monkeypatch, failure):
    from backend.tools import fmp
    rows = [{"symbol": "BAD", **failure}, {"symbol": "AAPL", "weight": 10}]
    monkeypatch.setattr(fmp, "get_index_constituents", lambda symbol: rows)
    monkeypatch.setattr(fmp, "get_etf_holdings", lambda symbol, limit: rows)
    assert [row["symbol"] for row in data_fetchers.fetch_top_constituents("SPX", "index", limit=1)] == ["AAPL"]
    assert [row["symbol"] for row in data_fetchers.fetch_holdings("SPY", "etf", limit=1)] == ["AAPL"]


@pytest.mark.parametrize("symbol", [None, "", "  ", True, [], 123])
def test_invalid_holding_ids_cannot_displace_valid_symbols(monkeypatch, symbol):
    from backend.tools import fmp
    monkeypatch.setattr(fmp, "get_etf_holdings", lambda ticker, limit:
                        [{"symbol": symbol}, {"symbol": " aapl ", "name": "Apple", "weight": 10, "shares": 20, "value": 100}])
    result = data_fetchers.fetch_holdings("SPY", "etf", limit=1)
    assert result == [{"symbol": "AAPL", "name": "Apple", "weight": 10, "shares": 20, "value": 100}]


@pytest.mark.parametrize("symbol", [None, "", "  ", True, [], 123])
def test_invalid_constituent_ids_cannot_displace_valid_symbols(monkeypatch, symbol):
    from backend.tools import fmp
    monkeypatch.setattr(fmp, "get_index_constituents", lambda ticker:
                        [{"symbol": symbol}, {"symbol": " aapl ", "name": "Apple", "weight": 10}])
    result = data_fetchers.fetch_top_constituents("SPX", "index", limit=1)
    assert result == [{"symbol": "AAPL", "name": "Apple", "weight": 10}]


def test_nonpositive_holdings_limits_stop_before_upstream_fetches(monkeypatch):
    from backend.tools import fmp
    calls = []
    def fetch(*args, **kwargs):
        calls.append(args)
        return [{"symbol": "AAPL"}]
    monkeypatch.setattr(fmp, "get_etf_holdings", fetch)
    monkeypatch.setattr(fmp, "get_index_constituents", fetch)
    for limit in (0, -1):
        assert data_fetchers.fetch_holdings("SPY", "etf", limit=limit) == []
        assert data_fetchers.fetch_top_constituents("SPX", "index", limit=limit) == []
    assert calls == []


def test_etf_holdings_filter_malformed_rows_before_applying_limit(monkeypatch):
    from backend.tools import fmp
    monkeypatch.setattr(fmp, "get_etf_holdings", lambda symbol, limit:
                        [None, "bad", {"symbol": "AAPL", "name": "Apple", "weight": 10, "shares": 20, "value": 100}])
    result = data_fetchers.fetch_holdings("SPY", "etf", limit=1)
    assert result == [{"symbol": "AAPL", "name": "Apple", "weight": 10, "shares": 20, "value": 100}]


def test_index_constituents_filter_malformed_rows_before_applying_limit(monkeypatch):
    from backend.tools import fmp
    monkeypatch.setattr(fmp, "get_index_constituents", lambda symbol:
                        [None, "bad", {"symbol": "AAPL", "name": "Apple", "weight": 10}])
    result = data_fetchers.fetch_top_constituents("SPX", "index", limit=1)
    assert result == [{"symbol": "AAPL", "name": "Apple", "weight": 10}]


@pytest.mark.parametrize("weight", [None, "bad", -1, 101, True, float("inf")])
def test_sector_weights_exclude_unavailable_and_invalid_percentages(monkeypatch, weight):
    from backend.tools import fmp
    monkeypatch.setattr(fmp, "get_etf_sector_weights", lambda symbol:
                        [{"sector": "Bad", "weight": weight}, {"sector": "Technology", "weight": 50}])
    assert data_fetchers.fetch_sector_weights("SPY", "etf") == [{"name": "Technology", "weight": 0.5}]


def test_sector_weights_preserve_valid_entries_beside_malformed_rows(monkeypatch):
    from backend.tools import fmp
    monkeypatch.setattr(fmp, "get_etf_sector_weights", lambda symbol:
                        [None, "bad", {"sector": "Technology", "weight": 50}])
    assert data_fetchers.fetch_sector_weights("SPY", "etf") == [{"name": "Technology", "weight": 0.5}]


@pytest.mark.parametrize("revenue, percentage", [(None, 50), ("bad", 50), (-1, 50), (float("inf"), 50),
                                               (100, None), (100, "bad"), (100, -1), (100, 101), (100, True)])
def test_segment_mix_numeric_fields_cannot_break_or_corrupt_valid_results(monkeypatch, revenue, percentage):
    from backend.tools import fmp
    monkeypatch.setattr(fmp, "get_revenue_product_segmentation", lambda symbol:
                        [{"segment": "Bad", "revenue": revenue, "percentage": percentage},
                         {"segment": "Cloud", "revenue": 100, "percentage": 50}])
    result = data_fetchers.fetch_segment_mix("AAPL")
    assert result == [{"name": "Cloud", "value": 100.0, "weight": 0.5}]


def test_segment_mix_preserves_valid_rows_beside_malformed_entries(monkeypatch):
    from backend.tools import fmp
    monkeypatch.setattr(fmp, "get_revenue_product_segmentation", lambda symbol:
                        [None, "bad", {"segment": "Cloud", "revenue": 100, "percentage": 50}])
    assert data_fetchers.fetch_segment_mix("AAPL") == [{"name": "Cloud", "value": 100, "weight": 0.5}]
