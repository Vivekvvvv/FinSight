from datetime import UTC, datetime
from types import SimpleNamespace

from backend.tools import price_history_vendor_providers as hp


def test_stooq_fallback_later_valid_record_is_retained(monkeypatch):
    monkeypatch.setattr(hp, "search", lambda *a: "")
    for first in (None, "poison", {"close": 99, "error": "bad"}, {"symbol": "MSFT.us", "close": 99}):
        monkeypatch.setattr(hp, "_http_get", lambda *a, **kw: SimpleNamespace(
            status_code=200, json=lambda: {"symbols": [first, {"symbol": "AAPL.us", "close": 100}]}))
        assert hp._fallback_price_value("AAPL") == 100


def test_stooq_fallback_identity_must_match_requested_security(monkeypatch):
    monkeypatch.setattr(hp, "search", lambda *a: "")
    for marker in ({"symbol": "MSFT.us"}, {"ticker": "MSFT"}, {"symbol": {}}):
        monkeypatch.setattr(hp, "_http_get", lambda *a, **kw: SimpleNamespace(
            status_code=200, json=lambda: {"symbols": [{"close": 100, **marker}]}))
        assert hp._fallback_price_value("AAPL") is None


def test_stooq_fallback_failed_row_cannot_supply_price(monkeypatch):
    monkeypatch.setattr(hp, "search", lambda *a: "")
    for marker in ({"error": "bad"}, {"success": False}, {"status": " Failed "}):
        monkeypatch.setattr(hp, "_http_get", lambda *a, **kw: SimpleNamespace(
            status_code=200, json=lambda: {"symbols": [{"close": 100, **marker}]}))
        assert hp._fallback_price_value("AAPL") is None


def test_stooq_fallback_failed_envelope_cannot_supply_price(monkeypatch):
    monkeypatch.setattr(hp, "search", lambda *a: "")
    for marker in ({"error": "bad"}, {"success": False}, {"status": " Failed "}):
        monkeypatch.setattr(hp, "_http_get", lambda *a, **kw: SimpleNamespace(
            status_code=200, json=lambda: {"symbols": [{"close": 100}], **marker}))
        assert hp._fallback_price_value("AAPL") is None


def test_stooq_fallback_positive_quote_is_required(monkeypatch):
    monkeypatch.setattr(hp, "search", lambda *a: "index level 5900")
    for close in (-1, 0):
        monkeypatch.setattr(hp, "_http_get", lambda *a, **kw: SimpleNamespace(
            status_code=200, json=lambda: {"symbols": [{"close": close}]}))
        assert hp._fallback_price_value("^GSPC") == 5900


def test_stooq_empty_symbol_does_not_map_to_an_instrument():
    assert hp._map_to_stooq_symbol("") is None
    assert hp._map_to_stooq_symbol("   ") is None


def test_stooq_native_us_symbol_is_not_double_suffixed():
    assert hp._map_to_stooq_symbol("aapl.us") == "AAPL.us"


def test_stooq_beijing_stocks_do_not_map_to_us_market():
    assert hp._map_to_stooq_symbol("920001.BJ") is None


def test_stooq_whitespace_symbols_match_normalized_requests():
    assert hp._map_to_stooq_symbol(" aapl ") == "AAPL.us"
    assert hp._map_to_stooq_symbol(" ^ixic ") == "^ndq"


def test_stooq_impossible_ohlc_ranges_are_discarded(monkeypatch):
    for bad in (("2026-11-05", 100, 100, 99, 101, 10),
                ("2026-11-05", 100, 102, 101, 101, 10)):
        _csv_mock(monkeypatch, [bad, ("2026-11-06", 100, 102, 99, 101, 10)])
        assert len(hp._fetch_with_stooq_history("AAPL")["kline_data"]) == 1


def test_stooq_nonpositive_prices_are_discarded(monkeypatch):
    for field in range(1, 4):
        bad = ["2026-11-05", 100, 102, 99, 101, 10]
        bad[field] = 0
        _csv_mock(monkeypatch, [bad, ("2026-11-06", 100, 102, 99, 101, 10)])
        assert len(hp._fetch_with_stooq_history("AAPL")["kline_data"]) == 1


def test_stooq_negative_volume_is_unavailable(monkeypatch):
    _csv_mock(monkeypatch, [("2026-11-06", 100, 102, 99, 101, -10)])
    assert hp._fetch_with_stooq_history("AAPL")["kline_data"][0]["volume"] is None


def test_stooq_history_order_and_duplicates_preserve_latest_revision(monkeypatch):
    _csv_mock(monkeypatch, [("2026-11-06", 100, 102, 99, 101, 10),
                           ("2026-11-06", 100, 102, 99, 102, 10),
                           ("2026-11-05", 100, 102, 99, 100, 10)])
    rows = hp._fetch_with_stooq_history("AAPL")["kline_data"]
    assert [r["time"] for r in rows] == ["2026-11-05 00:00", "2026-11-06 00:00"]
    assert [r["close"] for r in rows] == [100, 102]


def test_stooq_valid_dates_are_required(monkeypatch):
    _csv_mock(monkeypatch, [(day, 100, 102, 99, 101, 10) for day in
                           ("2026-02-30", "not-a-date", "2026-11-06")])
    rows = hp._fetch_with_stooq_history("AAPL")["kline_data"]
    assert [r["time"] for r in rows] == ["2026-11-06 00:00"]


def test_stooq_minute_request_does_not_fetch_daily_bars(monkeypatch):
    calls = []
    _csv_mock(monkeypatch, [("2026-11-06", 100, 102, 99, 101, 10)])
    response = hp._http_get()
    monkeypatch.setattr(hp, "_http_get", lambda *a, **kw: calls.append(a) or response)
    assert hp._fetch_with_stooq_history("AAPL", interval="5m") is None
    assert calls == []


def test_yahoo_negative_volume_is_unavailable(monkeypatch):
    _csv_mock(monkeypatch, [("2026-11-06", 100, 102, 99, 101, -10)])
    assert hp._fetch_with_yahoo_scrape_historical("AAPL")["kline_data"][0]["volume"] is None


def test_yahoo_impossible_ohlc_ranges_are_discarded(monkeypatch):
    for bad in (("2026-11-05", 100, 100, 99, 101, 10),
                ("2026-11-05", 100, 102, 101, 101, 10)):
        _csv_mock(monkeypatch, [bad, ("2026-11-06", 100, 102, 99, 101, 10)])
        assert len(hp._fetch_with_yahoo_scrape_historical("AAPL")["kline_data"]) == 1


def test_yahoo_nonpositive_prices_are_discarded(monkeypatch):
    for field in range(1, 5):
        bad = ["2026-11-05", 100, 102, 99, 101, 10]
        bad[field] = 0
        _csv_mock(monkeypatch, [bad, ("2026-11-06", 100, 102, 99, 101, 10)])
        assert len(hp._fetch_with_yahoo_scrape_historical("AAPL")["kline_data"]) == 1


def test_yahoo_history_order_and_duplicates_preserve_latest_revision(monkeypatch):
    _csv_mock(monkeypatch, [("2026-11-06", 100, 102, 99, 101, 10),
                           ("2026-11-06", 100, 102, 99, 102, 10),
                           ("2026-11-05", 100, 102, 99, 100, 10)])
    rows = hp._fetch_with_yahoo_scrape_historical("AAPL")["kline_data"]
    assert [r["time"] for r in rows] == ["2026-11-05", "2026-11-06"]
    assert [r["close"] for r in rows] == [100, 102]


def test_yahoo_valid_dates_are_required(monkeypatch):
    _csv_mock(monkeypatch, [(day, 100, 102, 99, 101, 10) for day in
                           ("2026-02-30", "not-a-date", "2026-11-06")])
    rows = hp._fetch_with_yahoo_scrape_historical("AAPL")["kline_data"]
    assert [r["time"] for r in rows] == ["2026-11-06"]


def _csv_mock(monkeypatch, rows):
    header = "Date,Open,High,Low,Close,Volume\n"
    text = header + "\n".join(",".join(str(value) for value in row) for row in rows)
    monkeypatch.setattr(hp, "_http_get", lambda *a, **kw: SimpleNamespace(status_code=200, text=text))


def test_yahoo_short_csv_retains_real_single_day_history(monkeypatch):
    _csv_mock(monkeypatch, [("2026-11-06", 100, 102, 99, 101, 10)])
    result = hp._fetch_with_yahoo_scrape_historical("AAPL")
    assert result is not None
    assert result["kline_data"][0]["close"] == 101


def test_massive_impossible_ohlc_ranges_are_discarded(monkeypatch):
    prior = int(datetime(2026, 11, 5, tzinfo=UTC).timestamp() * 1000)
    for changes in ({"h": 100}, {"l": 101}):
        _mock(monkeypatch, "MASSIVE_API_KEY", {"status": "OK", "results": [
            _massive_row(t=prior, **changes), _massive_row()]})
        assert len(hp._fetch_with_massive_io("AAPL")["kline_data"]) == 1


def test_massive_nonpositive_prices_are_discarded(monkeypatch):
    prior = int(datetime(2026, 11, 5, tzinfo=UTC).timestamp() * 1000)
    for changes in ({"c": 0}, {"o": -1}, {"h": 0}, {"l": -1}):
        _mock(monkeypatch, "MASSIVE_API_KEY", {"status": "OK", "results": [
            _massive_row(t=prior, **changes), _massive_row()]})
        assert len(hp._fetch_with_massive_io("AAPL")["kline_data"]) == 1


def test_massive_negative_volume_is_unavailable(monkeypatch):
    _mock(monkeypatch, "MASSIVE_API_KEY", {"status": "OK", "results": [_massive_row(v=-1)]})
    assert hp._fetch_with_massive_io("AAPL")["kline_data"][0]["volume"] is None


def test_massive_history_order_and_duplicates_preserve_latest_revision(monkeypatch):
    prior = int(datetime(2026, 11, 5, tzinfo=UTC).timestamp() * 1000)
    _mock(monkeypatch, "MASSIVE_API_KEY", {"status": "OK", "results": [
        _massive_row(), _massive_row(c=102), _massive_row(t=prior, c=100)]})
    rows = hp._fetch_with_massive_io("AAPL")["kline_data"]
    assert [r["time"] for r in rows] == ["2026-11-05", "2026-11-06"]
    assert [r["close"] for r in rows] == [100, 102]


def test_massive_timestamp_overflow_does_not_discard_valid_history(monkeypatch):
    for timestamp in (1e308, -1e308):
        _mock(monkeypatch, "MASSIVE_API_KEY", {"status": "OK", "results": [
            _massive_row(t=timestamp), _massive_row()]})
        result = hp._fetch_with_massive_io("AAPL")
        assert result is not None
        assert [r["time"] for r in result["kline_data"]] == ["2026-11-06"]


def test_massive_row_identity_must_match_request(monkeypatch):
    rows = [_massive_row(symbol="MSFT"), _massive_row(ticker="MSFT"),
            _massive_row(symbol={}), _massive_row(symbol=" aapl ")]
    _mock(monkeypatch, "MASSIVE_API_KEY", {"status": "OK", "results": rows})
    assert len(hp._fetch_with_massive_io("AAPL")["kline_data"]) == 1


def test_massive_failed_rows_cannot_supply_history(monkeypatch):
    rows = [_massive_row(**marker) for marker in
            ({"error": "bad"}, {"success": False}, {"status": " Failed "})] + [_massive_row()]
    _mock(monkeypatch, "MASSIVE_API_KEY", {"status": "OK", "results": rows})
    assert len(hp._fetch_with_massive_io("AAPL")["kline_data"]) == 1


def test_massive_envelope_identity_must_match_request(monkeypatch):
    for marker in ({"ticker": "MSFT"}, {"symbol": "MSFT"}, {"ticker": {}}):
        _mock(monkeypatch, "MASSIVE_API_KEY", {"status": "OK", "results": [_massive_row()], **marker})
        assert hp._fetch_with_massive_io("AAPL") is None


def _massive_row(**changes):
    return {"t": int(datetime(2026, 11, 6, tzinfo=UTC).timestamp() * 1000),
            "o": 100, "h": 102, "l": 99, "c": 101, "v": 10, **changes}


def test_massive_failed_envelope_cannot_supply_history(monkeypatch):
    for marker in ({"error": "bad"}, {"success": False}):
        _mock(monkeypatch, "MASSIVE_API_KEY", {"status": "OK", "results": [_massive_row()], **marker})
        assert hp._fetch_with_massive_io("AAPL") is None


def test_marketstack_impossible_ohlc_ranges_are_discarded(monkeypatch):
    for changes in ({"high": 100}, {"low": 101}):
        _mock(monkeypatch, "MARKETSTACK_API_KEY", {"data": [_row(date="2026-11-05", **changes), _row()]})
        assert len(hp._fetch_with_marketstack("AAPL")["kline_data"]) == 1


def test_marketstack_nonpositive_prices_are_discarded(monkeypatch):
    for changes in ({"close": 0}, {"open": -1}, {"high": 0}, {"low": -1}):
        _mock(monkeypatch, "MARKETSTACK_API_KEY", {"data": [_row(date="2026-11-05", **changes), _row()]})
        assert len(hp._fetch_with_marketstack("AAPL")["kline_data"]) == 1


def test_marketstack_negative_volume_is_unavailable(monkeypatch):
    _mock(monkeypatch, "MARKETSTACK_API_KEY", {"data": [_row(volume=-1)]})
    assert hp._fetch_with_marketstack("AAPL")["kline_data"][0]["volume"] is None


def test_marketstack_history_order_and_duplicates_preserve_latest_revision(monkeypatch):
    _mock(monkeypatch, "MARKETSTACK_API_KEY", {"data": [_row(), _row(close=102),
          _row(date="2026-11-05", close=100)]})
    rows = hp._fetch_with_marketstack("AAPL")["kline_data"]
    assert [r["time"] for r in rows] == ["2026-11-05", "2026-11-06"]
    assert [r["close"] for r in rows] == [100, 102]


def test_marketstack_valid_dates_are_required(monkeypatch):
    rows = [_row(date=day) for day in ("2026-02-30", "not-a-date", {}, "2026-11-06")]
    _mock(monkeypatch, "MARKETSTACK_API_KEY", {"data": rows})
    assert [r["time"] for r in hp._fetch_with_marketstack("AAPL")["kline_data"]] == ["2026-11-06"]


def test_marketstack_stock_identity_must_match_request(monkeypatch):
    rows = [_row(symbol="MSFT"), _row(ticker="MSFT"), _row(symbol={}), _row(symbol=" aapl ")]
    _mock(monkeypatch, "MARKETSTACK_API_KEY", {"data": rows})
    assert len(hp._fetch_with_marketstack("AAPL")["kline_data"]) == 1


def test_marketstack_failed_rows_cannot_supply_history(monkeypatch):
    rows = [_row(**marker) for marker in
            ({"error": "bad"}, {"success": False}, {"status": " Failed "})] + [_row()]
    _mock(monkeypatch, "MARKETSTACK_API_KEY", {"data": rows})
    assert len(hp._fetch_with_marketstack("AAPL")["kline_data"]) == 1


def test_marketstack_failed_envelope_cannot_supply_history(monkeypatch):
    for marker in ({"success": False}, {"status": " Failed "}, {"status": "unavailable"}):
        _mock(monkeypatch, "MARKETSTACK_API_KEY", {"data": [_row()], **marker})
        assert hp._fetch_with_marketstack("AAPL") is None


def test_marketstack_https_protects_authenticated_request(monkeypatch):
    calls = []
    monkeypatch.setattr(hp, "MARKETSTACK_API_KEY", "test-key")
    monkeypatch.setattr(hp, "_http_get", lambda url, **kw: calls.append(url) or SimpleNamespace(
        status_code=200, json=lambda: {"data": [_row()]}))
    assert hp._fetch_with_marketstack("AAPL") is not None
    assert calls == ["https://api.marketstack.com/v1/eod"]


def test_twelve_impossible_ohlc_ranges_are_discarded(monkeypatch):
    for changes in ({"high": 100}, {"low": 101}):
        _mock(monkeypatch, "TWELVE_DATA_API_KEY", {"status": "ok", "values": [
            _row(datetime="2026-11-05", **changes), _row()]})
        assert len(hp._fetch_with_twelve_data("AAPL")["kline_data"]) == 1


def test_twelve_nonpositive_prices_are_discarded(monkeypatch):
    for changes in ({"close": 0}, {"open": -1}, {"high": 0}, {"low": -1}):
        _mock(monkeypatch, "TWELVE_DATA_API_KEY", {"status": "ok", "values": [
            _row(datetime="2026-11-05", **changes), _row()]})
        assert len(hp._fetch_with_twelve_data("AAPL")["kline_data"]) == 1


def test_twelve_negative_volume_is_unavailable(monkeypatch):
    _mock(monkeypatch, "TWELVE_DATA_API_KEY", {"status": "ok", "values": [_row(volume=-1)]})
    assert hp._fetch_with_twelve_data("AAPL")["kline_data"][0]["volume"] is None


def test_twelve_as_of_uses_latest_valid_observation(monkeypatch):
    for first in ("poison", _row(datetime="bad"), _row(datetime="2026-11-05")):
        _mock(monkeypatch, "TWELVE_DATA_API_KEY", {"status": "ok", "values": [first, _row()]})
        assert hp._fetch_with_twelve_data("AAPL")["as_of"] == "2026-11-06"


def test_twelve_history_order_and_duplicates_preserve_latest_revision(monkeypatch):
    rows = [_row(), _row(close=102), _row(datetime="2026-11-05", close=100)]
    _mock(monkeypatch, "TWELVE_DATA_API_KEY", {"status": "ok", "values": rows})
    bars = hp._fetch_with_twelve_data("AAPL")["kline_data"]
    assert [r["time"] for r in bars] == ["2026-11-05", "2026-11-06"]
    assert [r["close"] for r in bars] == [100, 102]


def test_twelve_valid_dates_are_required(monkeypatch):
    rows = [_row(datetime=day) for day in ("2026-02-30", "not-a-date", {}, "2026-11-06")]
    _mock(monkeypatch, "TWELVE_DATA_API_KEY", {"status": "ok", "values": rows})
    assert [r["time"] for r in hp._fetch_with_twelve_data("AAPL")["kline_data"]] == ["2026-11-06"]


def test_twelve_row_identity_must_match_request(monkeypatch):
    rows = [_row(symbol="MSFT"), _row(ticker="MSFT"), _row(symbol={}), _row(symbol=" aapl ")]
    _mock(monkeypatch, "TWELVE_DATA_API_KEY", {"status": "ok", "values": rows})
    assert len(hp._fetch_with_twelve_data("AAPL")["kline_data"]) == 1


def test_twelve_failed_rows_cannot_supply_history(monkeypatch):
    rows = [_row(**marker) for marker in
            ({"error": "bad"}, {"success": False}, {"status": " Failed "})] + [_row()]
    _mock(monkeypatch, "TWELVE_DATA_API_KEY", {"status": "ok", "values": rows})
    assert len(hp._fetch_with_twelve_data("AAPL")["kline_data"]) == 1


def test_twelve_metadata_identity_must_match_request(monkeypatch):
    for meta in ({"symbol": "MSFT"}, {"ticker": "MSFT"}, {"symbol": {}}):
        _mock(monkeypatch, "TWELVE_DATA_API_KEY", {"status": "ok", "meta": meta, "values": [_row()]})
        assert hp._fetch_with_twelve_data("AAPL") is None


def test_twelve_failed_envelope_cannot_supply_history(monkeypatch):
    for marker in ({"error": "bad"}, {"success": False}):
        _mock(monkeypatch, "TWELVE_DATA_API_KEY", {"status": "ok", "values": [_row()], **marker})
        assert hp._fetch_with_twelve_data("AAPL") is None


def test_tiingo_impossible_ohlc_ranges_are_discarded(monkeypatch):
    for changes in ({"high": 100}, {"low": 101}):
        _mock(monkeypatch, "TIINGO_API_KEY", [_row(date="2026-11-05", **changes), _row()])
        assert len(hp._fetch_with_tiingo("AAPL")["kline_data"]) == 1


def test_tiingo_nonpositive_prices_are_discarded(monkeypatch):
    for changes in ({"close": 0}, {"open": -1}, {"high": 0}, {"low": -1}):
        _mock(monkeypatch, "TIINGO_API_KEY", [_row(date="2026-11-05", **changes), _row()])
        assert len(hp._fetch_with_tiingo("AAPL")["kline_data"]) == 1


def test_tiingo_negative_volume_is_unavailable(monkeypatch):
    _mock(monkeypatch, "TIINGO_API_KEY", [_row(volume=-1)])
    assert hp._fetch_with_tiingo("AAPL")["kline_data"][0]["volume"] is None


def test_tiingo_history_order_and_duplicates_preserve_latest_revision(monkeypatch):
    _mock(monkeypatch, "TIINGO_API_KEY", [_row(), _row(close=102), _row(date="2026-11-05", close=100)])
    rows = hp._fetch_with_tiingo("AAPL")["kline_data"]
    assert [r["time"] for r in rows] == ["2026-11-05", "2026-11-06"]
    assert [r["close"] for r in rows] == [100, 102]


def test_tiingo_valid_dates_are_required(monkeypatch):
    _mock(monkeypatch, "TIINGO_API_KEY", [_row(date=day) for day in
          ("2026-02-30", "not-a-date", {}, "2026-11-06T00:00:00Z")])
    assert [r["time"] for r in hp._fetch_with_tiingo("AAPL")["kline_data"]] == ["2026-11-06"]


def test_tiingo_stock_identity_must_match_request(monkeypatch):
    _mock(monkeypatch, "TIINGO_API_KEY", [_row(symbol="MSFT"), _row(ticker="MSFT"),
                                        _row(symbol={}), _row(symbol=" aapl ")])
    assert len(hp._fetch_with_tiingo("AAPL")["kline_data"]) == 1


def test_tiingo_failed_rows_cannot_supply_history(monkeypatch):
    _mock(monkeypatch, "TIINGO_API_KEY", [_row(**marker) for marker in
          ({"error": "bad"}, {"success": False}, {"status": " Failed "})] + [_row()])
    assert len(hp._fetch_with_tiingo("AAPL")["kline_data"]) == 1


def test_iex_impossible_ohlc_ranges_are_discarded(monkeypatch):
    for changes in ({"high": 100}, {"low": 101}):
        _mock(monkeypatch, "IEX_CLOUD_API_KEY", [_row(date="2026-11-05", **changes), _row()])
        assert len(hp._fetch_with_iex_cloud("AAPL")["kline_data"]) == 1


def test_iex_nonpositive_reported_prices_are_discarded(monkeypatch):
    for changes in ({"close": 0}, {"open": -1}, {"high": 0}, {"low": -1}):
        _mock(monkeypatch, "IEX_CLOUD_API_KEY", [_row(date="2026-11-05", **changes), _row()])
        assert len(hp._fetch_with_iex_cloud("AAPL")["kline_data"]) == 1


def test_iex_negative_volume_is_unavailable(monkeypatch):
    _mock(monkeypatch, "IEX_CLOUD_API_KEY", [_row(volume=-1)])
    assert hp._fetch_with_iex_cloud("AAPL")["kline_data"][0]["volume"] is None


def test_iex_history_order_and_duplicates_preserve_latest_revision(monkeypatch):
    _mock(monkeypatch, "IEX_CLOUD_API_KEY", [_row(), _row(close=102), _row(date="2026-11-05", close=100)])
    rows = hp._fetch_with_iex_cloud("AAPL")["kline_data"]
    assert [r["time"] for r in rows] == ["2026-11-05", "2026-11-06"]
    assert [r["close"] for r in rows] == [100, 102]


def test_iex_valid_dates_are_required(monkeypatch):
    _mock(monkeypatch, "IEX_CLOUD_API_KEY", [_row(date=day) for day in
          ("2026-02-30", "not-a-date", {}, "2026-11-06")])
    assert [r["time"] for r in hp._fetch_with_iex_cloud("AAPL")["kline_data"]] == ["2026-11-06"]


def test_iex_stock_identity_must_match_request(monkeypatch):
    _mock(monkeypatch, "IEX_CLOUD_API_KEY", [_row(symbol="MSFT"), _row(ticker="MSFT"),
                                           _row(symbol={}), _row(symbol=" aapl ")])
    assert len(hp._fetch_with_iex_cloud("AAPL")["kline_data"]) == 1


def _row(**changes):
    return {"date": "2026-11-06", "datetime": "2026-11-06", "open": 100,
            "high": 102, "low": 99, "close": 101, "volume": 10, **changes}


def _mock(monkeypatch, key, payload):
    monkeypatch.setattr(hp, key, "test-key")
    monkeypatch.setattr(hp, "_http_get", lambda *a, **kw: SimpleNamespace(
        status_code=200, json=lambda: payload))


def test_iex_failed_rows_cannot_supply_history(monkeypatch):
    _mock(monkeypatch, "IEX_CLOUD_API_KEY", [_row(**marker) for marker in
          ({"error": "bad"}, {"success": False}, {"status": " Failed "})] + [_row()])
    assert len(hp._fetch_with_iex_cloud("AAPL")["kline_data"]) == 1
