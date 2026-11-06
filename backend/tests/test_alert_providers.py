"""Regression tests for alert quote provider identity and fallback behavior."""
from types import SimpleNamespace
import sys

import pytest

from backend.services import alert_providers as providers
from backend.services.alert_scheduler import PriceChangeScheduler


def _mock_response(monkeypatch, payload):
    response = SimpleNamespace(status_code=200, json=lambda: payload)
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=lambda *_args, **_kwargs: response))


@pytest.mark.parametrize("symbol", ["TSLA", None, ""])
def test_yahoo_quote_rejects_unidentified_or_unrelated_quote(monkeypatch, symbol):
    _mock_response(monkeypatch, {"quoteResponse": {"result": [{
        "symbol": symbol, "regularMarketPrice": 120.0, "regularMarketPreviousClose": 100.0,
    }]}})

    assert providers._fetch_with_yahoo_quote("AAPL") is None


def test_yahoo_quote_selects_matching_symbol_instead_of_first_result(monkeypatch):
    _mock_response(monkeypatch, {"quoteResponse": {"result": [
        {"symbol": "TSLA", "regularMarketPrice": 300.0, "regularMarketPreviousClose": 250.0},
        {"symbol": " aapl ", "regularMarketPrice": 105.0, "regularMarketPreviousClose": 100.0},
    ]}})

    snapshot = providers._fetch_with_yahoo_quote("AAPL")

    assert snapshot is not None
    assert snapshot.ticker == "AAPL"
    assert snapshot.price == 105.0
    assert snapshot.change_percent == pytest.approx(5.0)


def test_yahoo_quote_mismatch_cannot_trigger_price_alert(monkeypatch):
    _mock_response(monkeypatch, {"quoteResponse": {"result": [{
        "symbol": "TSLA", "regularMarketPrice": 120.0, "regularMarketPreviousClose": 100.0,
    }]}})
    attempts = []
    sends = []
    subscription_service = SimpleNamespace(
        get_subscriptions=lambda **_kwargs: [{
            "email": "alice@example.invalid", "ticker": "AAPL", "alert_types": ["price_change"],
            "alert_mode": "price_target", "price_target": 110.0, "direction": "above",
        }],
        is_valid_email=lambda _email: True,
        record_alert_attempt=lambda *args, **kwargs: attempts.append((args, kwargs)),
        set_price_target_fired=lambda *args: attempts.append(args),
        record_alert_event=lambda *args, **kwargs: attempts.append((args, kwargs)),
    )
    scheduler = PriceChangeScheduler(
        subscription_service,
        SimpleNamespace(send_stock_alert=lambda **kwargs: sends.append(kwargs) or True),
        providers._fetch_with_yahoo_quote,
    )

    assert scheduler.run_once() == []
    assert sends == []
    assert attempts == []
    assert scheduler.last_price_unavailable == 1


@pytest.mark.parametrize("symbol", ["TSLA", None, ""])
def test_yahoo_chart_rejects_unidentified_or_unrelated_result(monkeypatch, symbol):
    _mock_response(monkeypatch, {"chart": {"result": [{
        "meta": {"symbol": symbol}, "indicators": {"quote": [{"close": [100.0, 120.0]}]},
    }]}})

    assert providers._fetch_with_yahoo_chart("AAPL") is None


def test_yahoo_chart_accepts_normalized_matching_symbol(monkeypatch):
    _mock_response(monkeypatch, {"chart": {"result": [{
        "meta": {"symbol": " aapl "}, "indicators": {"quote": [{"close": [100.0, 105.0]}]},
    }]}})

    snapshot = providers._fetch_with_yahoo_chart("AAPL")

    assert snapshot is not None
    assert snapshot.ticker == "AAPL"
    assert snapshot.price == 105.0
    assert snapshot.change_percent == pytest.approx(5.0)


@pytest.mark.parametrize("symbol", ["TSLA.US", None, ""])
def test_stooq_rejects_unidentified_or_unrelated_quote(monkeypatch, symbol):
    _mock_response(monkeypatch, {"symbols": [{"symbol": symbol, "close": 120.0}]})

    assert providers._fetch_with_stooq("AAPL") is None


def test_stooq_accepts_normalized_matching_symbol(monkeypatch):
    _mock_response(monkeypatch, {"symbols": [{"symbol": " aapl.US ", "close": 105.0}]})

    snapshot = providers._fetch_with_stooq("AAPL")

    assert snapshot is not None
    assert snapshot.ticker == "AAPL"
    assert snapshot.price == 105.0


@pytest.mark.parametrize("days_since_quote", [1, 2, 3])
def test_stooq_uses_previous_trading_close_for_older_quote(monkeypatch, days_since_quote):
    from datetime import datetime, timedelta, timezone

    quote_date = datetime.now(timezone.utc).date() - timedelta(days=days_since_quote)
    quote_response = SimpleNamespace(status_code=200, json=lambda: {"symbols": [{
        "symbol": "AAPL.US", "date": quote_date.isoformat(), "close": 105.0,
    }]})
    history_response = SimpleNamespace(
        status_code=200,
        text=f"Date,Close\n{quote_date - timedelta(days=1)},100.0\n{quote_date},105.0\n",
    )
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(
        get=lambda url, **_kwargs: history_response if "/q/d/l/" in url else quote_response,
    ))

    snapshot = providers._fetch_with_stooq("AAPL")

    assert snapshot is not None
    assert snapshot.change_percent == pytest.approx(5.0)


def _mock_fetchers(monkeypatch, snapshots):
    monkeypatch.setattr(providers, "_PRICE_CACHE", {})
    calls = []
    for name, snapshot in zip((
        "_fetch_with_stooq", "_fetch_with_yfinance", "_fetch_with_yahoo_quote", "_fetch_with_yahoo_chart",
    ), snapshots):
        def fetch(_ticker, result=snapshot, provider_name=name):
            calls.append(provider_name)
            return result
        monkeypatch.setattr(providers, name, fetch)
    return calls


def test_snapshot_fallback_prefers_complete_quote_after_price_only_result(monkeypatch):
    partial = providers.PriceSnapshot("AAPL", 105.0, None)
    complete = providers.PriceSnapshot("AAPL", 105.0, 5.0)
    calls = _mock_fetchers(monkeypatch, [partial, complete, None, None])

    snapshot = providers.fetch_price_snapshot("AAPL")

    assert snapshot == complete
    assert calls == ["_fetch_with_stooq", "_fetch_with_yfinance"]
    assert providers._get_cached_snapshot("AAPL") == complete


def test_snapshot_fallback_keeps_price_only_quote_when_later_sources_fail(monkeypatch):
    partial = providers.PriceSnapshot("AAPL", 105.0, None)
    calls = _mock_fetchers(monkeypatch, [partial, None, None, None])

    snapshot = providers.fetch_price_snapshot("AAPL")

    assert snapshot == partial
    assert len(calls) == 4
    assert providers._get_cached_snapshot("AAPL") == partial


@pytest.mark.parametrize("cached_ticker", ["TSLA", "", None])
def test_mismatched_cached_quote_is_evicted_before_source_fallback(monkeypatch, cached_ticker):
    complete = providers.PriceSnapshot("AAPL", 105.0, 5.0)
    calls = _mock_fetchers(monkeypatch, [complete, None, None, None])
    providers._PRICE_CACHE["AAPL"] = (
        providers.PriceSnapshot(cached_ticker, 300.0, 10.0), providers.time.time(),
    )

    snapshot = providers.fetch_price_snapshot("AAPL")

    assert snapshot == complete
    assert calls == ["_fetch_with_stooq"]
    assert providers._get_cached_snapshot("AAPL") == complete


def test_matching_cached_ticker_accepts_case_and_spaces_without_fetch(monkeypatch):
    calls = _mock_fetchers(monkeypatch, [None, None, None, None])
    snapshot = providers.PriceSnapshot(" aapl ", 105.0, 5.0)
    providers._PRICE_CACHE["AAPL"] = (snapshot, providers.time.time())

    assert providers.fetch_price_snapshot("AAPL") == snapshot
    assert calls == []
