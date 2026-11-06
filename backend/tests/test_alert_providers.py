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
