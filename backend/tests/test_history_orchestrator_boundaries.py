from datetime import UTC, datetime
from types import SimpleNamespace

import pandas as pd

from backend.tools import price_history_providers as hp


def test_download_source_metadata_identifies_the_data_provider(monkeypatch):
    _isolate(monkeypatch)
    monkeypatch.setattr(hp.yf, "Ticker", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("offline")))
    frame = pd.DataFrame([{"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 10}],
                         index=pd.to_datetime(["2026-11-06"]))
    monkeypatch.setattr(hp.yf, "download", lambda *a, **kw: frame)
    assert hp.get_stock_historical_data("AAPL")["source"] == "yfinance"


def test_download_requested_interval_is_forwarded_to_yfinance(monkeypatch):
    _isolate(monkeypatch)
    monkeypatch.setattr(hp.yf, "Ticker", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("offline")))
    frame = pd.DataFrame([{"Open": 100, "High": 102, "Low": 99, "Close": 101, "Volume": 10}],
                         index=pd.to_datetime(["2026-11-06T10:00:00"]))
    calls = []
    monkeypatch.setattr(hp.yf, "download", lambda *a, **kw: calls.append(kw) or frame)
    result = hp.get_stock_historical_data("AAPL", interval="1h")
    assert result["kline_data"][0]["close"] == 101
    assert calls[0]["interval"] == "1h"


def test_finnhub_impossible_ohlc_ranges_are_discarded(monkeypatch):
    ts = int(datetime(2026, 11, 6, tzinfo=UTC).timestamp())
    for field, invalid in (("h", 100), ("l", 101)):
        payload = _candles(t=[ts - 86400, ts], o=[100, 100], h=[102, 102],
                           l=[99, 99], c=[101, 101], v=[10, 10])
        payload[field][0] = invalid
        _finnhub(monkeypatch, payload)
        assert [r["time"] for r in hp.get_stock_historical_data("AAPL")["kline_data"]] == ["2026-11-06"]


def test_finnhub_nonpositive_prices_are_discarded(monkeypatch):
    ts = int(datetime(2026, 11, 6, tzinfo=UTC).timestamp())
    for field in ("o", "h", "l", "c"):
        payload = _candles(t=[ts - 86400, ts], o=[100, 100], h=[102, 102],
                           l=[99, 99], c=[101, 101], v=[10, 10])
        payload[field][0] = 0
        _finnhub(monkeypatch, payload)
        assert [r["time"] for r in hp.get_stock_historical_data("AAPL")["kline_data"]] == ["2026-11-06"]


def test_finnhub_negative_volume_is_unavailable(monkeypatch):
    _finnhub(monkeypatch, _candles(v=[-10]))
    assert hp.get_stock_historical_data("AAPL")["kline_data"][0]["volume"] is None


def test_finnhub_history_order_and_duplicates_preserve_latest_revision(monkeypatch):
    ts = int(datetime(2026, 11, 6, tzinfo=UTC).timestamp())
    _finnhub(monkeypatch, _candles(t=[ts, ts, ts - 86400], o=[100, 100, 100],
                                 h=[102, 102, 102], l=[99, 99, 99], c=[101, 102, 100], v=[10, 10, 10]))
    rows = hp.get_stock_historical_data("AAPL")["kline_data"]
    assert [r["time"] for r in rows] == ["2026-11-05", "2026-11-06"]
    assert [r["close"] for r in rows] == [100, 102]


def test_finnhub_invalid_timestamps_do_not_discard_valid_history(monkeypatch):
    ts = int(datetime(2026, 11, 6, tzinfo=UTC).timestamp())
    for invalid in (1e308, -1e308, None, "bad"):
        _finnhub(monkeypatch, _candles(t=[invalid, ts], o=[100, 100], h=[102, 102],
                                     l=[99, 99], c=[101, 101], v=[10, 10]))
        result = hp.get_stock_historical_data("AAPL")
        assert "kline_data" in result
        assert [r["time"] for r in result["kline_data"]] == ["2026-11-06"]


def test_finnhub_missing_volumes_do_not_discard_price_observations(monkeypatch):
    ts = int(datetime(2026, 11, 5, tzinfo=UTC).timestamp())
    for volumes in ([10], None):
        payload = _candles(t=[ts, ts + 86400], o=[100, 100], h=[102, 102], l=[99, 99], c=[101, 101])
        if volumes is None:
            del payload["v"]
        else:
            payload["v"] = volumes
        _finnhub(monkeypatch, payload)
        result = hp.get_stock_historical_data("AAPL")
        assert "kline_data" in result
        assert [r["volume"] for r in result["kline_data"]] == ([10, None] if volumes else [None, None])


def test_finnhub_daily_metadata_matches_returned_resolution(monkeypatch):
    _finnhub(monkeypatch, _candles())
    result = hp.get_stock_historical_data("AAPL", interval="1h")
    assert result["interval"] == "1d"
    assert result["source"] == "finnhub"


def test_finnhub_identity_must_match_request(monkeypatch):
    for marker in ({"ticker": "MSFT"}, {"symbol": "MSFT"}, {"ticker": {}}):
        _finnhub(monkeypatch, _candles(**marker))
        assert "error" in hp.get_stock_historical_data("AAPL")


def _candles(**changes):
    return {"s": "ok", "t": [int(datetime(2026, 11, 6, tzinfo=UTC).timestamp())],
            "o": [100], "h": [102], "l": [99], "c": [101], "v": [10], **changes}


def _finnhub(monkeypatch, payload):
    _isolate(monkeypatch)
    monkeypatch.setattr(hp, "FINNHUB_API_KEY", "test-key")
    monkeypatch.setattr(hp, "finnhub_client", SimpleNamespace(stock_candles=lambda *a: payload))


def test_finnhub_failed_envelope_cannot_supply_history(monkeypatch):
    for marker in ({"error": "bad"}, {"success": False}, {"status": " Failed "}):
        _finnhub(monkeypatch, _candles(**marker))
        assert "error" in hp.get_stock_historical_data("AAPL")


def test_alpha_limit_counts_valid_rows_instead_of_failed_newer_rows(monkeypatch):
    _alpha(monkeypatch, {"Time Series (Daily)": {"2026-11-06": None, "2026-11-05": _day()}})
    result = hp.get_stock_historical_data("AAPL", period="1d")
    assert "kline_data" in result
    assert [r["time"] for r in result["kline_data"]] == ["2026-11-05"]
    _alpha(monkeypatch, {"Time Series (Daily)": {"2026-11-05": _day(), "2026-11-06": _day()}})
    assert [r["time"] for r in hp.get_stock_historical_data("AAPL", period="1d")["kline_data"]] == ["2026-11-06"]


def test_alpha_negative_volume_is_unavailable(monkeypatch):
    _alpha(monkeypatch, {"Time Series (Daily)": {"2026-11-06": _day(**{"5. volume": "-10"})}})
    assert hp.get_stock_historical_data("AAPL")["kline_data"][0]["volume"] is None


def test_alpha_impossible_ohlc_ranges_are_discarded(monkeypatch):
    for changes in ({"2. high": "100"}, {"3. low": "101"}):
        _alpha(monkeypatch, {"Time Series (Daily)": {"2026-11-05": _day(**changes), "2026-11-06": _day()}})
        assert [r["time"] for r in hp.get_stock_historical_data("AAPL")["kline_data"]] == ["2026-11-06"]


def test_alpha_nonpositive_prices_are_discarded(monkeypatch):
    for field in ("1. open", "2. high", "3. low", "4. close"):
        _alpha(monkeypatch, {"Time Series (Daily)": {"2026-11-05": _day(**{field: "0"}), "2026-11-06": _day()}})
        assert [r["time"] for r in hp.get_stock_historical_data("AAPL")["kline_data"]] == ["2026-11-06"]


def test_alpha_empty_filtered_series_continues_to_next_source(monkeypatch):
    _alpha(monkeypatch, {"Time Series (Daily)": {"2026-11-06": None}})
    monkeypatch.setattr(hp, "IEX_CLOUD_API_KEY", "test-key")
    expected = {"source": "fixture", "kline_data": [{"time": "2026-11-06", "close": 101}]}
    monkeypatch.setattr(hp, "_fetch_with_yahoo_scrape_historical", lambda *a: expected)
    assert hp.get_stock_historical_data("AAPL") == expected


def test_alpha_daily_metadata_does_not_label_daily_bars_as_hourly(monkeypatch):
    _alpha(monkeypatch, {"Time Series (Daily)": {"2026-11-06": _day()}})
    result = hp.get_stock_historical_data("AAPL", interval="1h")
    assert result["interval"] == "1d"
    assert result["source"] == "alpha_vantage"


def test_alpha_valid_dates_are_required(monkeypatch):
    _alpha(monkeypatch, {"Time Series (Daily)": {day: _day() for day in ("2026-02-30", "bad", "2026-11-06")}})
    assert [r["time"] for r in hp.get_stock_historical_data("AAPL")["kline_data"]] == ["2026-11-06"]


def test_alpha_incomplete_rows_do_not_discard_valid_history(monkeypatch):
    for field in ("1. open", "2. high", "3. low", "4. close"):
        bad = _day()
        del bad[field]
        _alpha(monkeypatch, {"Time Series (Daily)": {"2026-11-05": bad, "2026-11-06": _day()}})
        result = hp.get_stock_historical_data("AAPL")
        assert "kline_data" in result
        assert [r["time"] for r in result["kline_data"]] == ["2026-11-06"]


def test_alpha_failed_rows_cannot_supply_history(monkeypatch):
    for marker in ({"error": "bad"}, {"success": False}, {"status": " Failed "}):
        _alpha(monkeypatch, {"Time Series (Daily)": {"2026-11-05": _day(**marker), "2026-11-06": _day()}})
        rows = hp.get_stock_historical_data("AAPL")["kline_data"]
        assert [r["time"] for r in rows] == ["2026-11-06"]


def test_alpha_metadata_identity_must_match_request(monkeypatch):
    for symbol in ("MSFT", {}):
        _alpha(monkeypatch, {"Meta Data": {"2. Symbol": symbol}, "Time Series (Daily)": {"2026-11-06": _day()}})
        assert "error" in hp.get_stock_historical_data("AAPL")


def _isolate(monkeypatch):
    monkeypatch.setattr(hp.yf, "Ticker", lambda *a, **kw: SimpleNamespace(history=lambda **kw: pd.DataFrame()))
    monkeypatch.setattr(hp.yf, "download", lambda *a, **kw: pd.DataFrame())
    monkeypatch.setattr(hp.time, "sleep", lambda *a: None)
    for key in ("ALPHA_VANTAGE_API_KEY", "FINNHUB_API_KEY", "IEX_CLOUD_API_KEY",
                "TIINGO_API_KEY", "TWELVE_DATA_API_KEY", "MARKETSTACK_API_KEY", "MASSIVE_API_KEY"):
        monkeypatch.setattr(hp, key, "")
    monkeypatch.setattr(hp, "finnhub_client", None)
    for name in ("_fetch_with_yahoo_scrape_historical", "_fetch_with_iex_cloud",
                 "_fetch_with_tiingo", "_fetch_with_twelve_data", "_fetch_with_marketstack",
                 "_fetch_with_massive_io", "_fetch_with_stooq_history"):
        monkeypatch.setattr(hp, name, lambda *a, **kw: None)


def _day(**changes):
    return {"1. open": "100", "2. high": "102", "3. low": "99",
            "4. close": "101", "5. volume": "10", **changes}


def _alpha(monkeypatch, payload):
    _isolate(monkeypatch)
    monkeypatch.setattr(hp, "ALPHA_VANTAGE_API_KEY", "test-key")
    monkeypatch.setattr(hp, "_http_get", lambda *a, **kw: SimpleNamespace(json=lambda: payload))


def test_alpha_failed_envelope_cannot_supply_history(monkeypatch):
    for marker in ({"error": "bad"}, {"success": False}, {"status": " Failed "}):
        _alpha(monkeypatch, {"Time Series (Daily)": {"2026-11-06": _day()}, **marker})
        assert "error" in hp.get_stock_historical_data("AAPL")
