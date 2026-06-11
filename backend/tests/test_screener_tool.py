# -*- coding: utf-8 -*-
from __future__ import annotations

from backend.tools import screener


class _DummyResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_screen_stocks_uses_fallback_without_api_key(monkeypatch):
    monkeypatch.setattr(screener, "FMP_API_KEY", "")

    def _fake_fallback(market, filters, limit, sort_by, sort_order):
        return {
            "success": True,
            "market": market,
            "items": [{"symbol": "AAPL"}],
            "results": [{"symbol": "AAPL"}],
            "count": 1,
            "source": "test_fallback",
            "sort": {"by": sort_by, "order": sort_order},
            "filters": filters,
        }

    monkeypatch.setattr(screener, "_yfinance_screen_stocks", _fake_fallback)

    result = screener.screen_stocks(market="US", filters={}, limit=10, page=1)

    assert result["success"] is True
    assert result["source"] == "test_fallback"
    assert result["items"][0]["symbol"] == "AAPL"


def test_yfinance_empty_result_uses_static_popular_fallback(monkeypatch):
    class _BrokenTicker:
        @property
        def fast_info(self):
            raise RuntimeError("network unavailable")

    monkeypatch.setattr(screener.yf, "Ticker", lambda _symbol: _BrokenTicker())

    result = screener._yfinance_popular_stocks("US", {}, 3, "marketCap", "desc")

    assert result["success"] is True
    assert result["count"] == 3
    assert result["items"]
    assert result["source"] == "yfinance_popular"
    assert result["items"][0]["symbol"] in {"AAPL", "MSFT", "NVDA", "GOOGL"}


def test_screen_stocks_parses_items(monkeypatch):
    monkeypatch.setattr(screener, "FMP_API_KEY", "demo-key")

    def _fake_get(_url: str, params: dict, timeout: int):
        assert params["sort"] == "marketCap"
        assert params["order"] == "desc"
        return _DummyResponse(
            200,
            [
                {
                    "symbol": "AAPL",
                    "companyName": "Apple Inc.",
                    "sector": "Technology",
                    "industry": "Consumer Electronics",
                    "country": "US",
                    "exchangeShortName": "NASDAQ",
                    "price": 180.12,
                    "marketCap": 1000,
                    "volume": 250,
                    "beta": 1.2,
                    "lastAnnualDividend": 0.5,
                    "changesPercentage": 1.1,
                }
            ],
        )

    monkeypatch.setattr(screener, "_http_get", _fake_get)

    result = screener.screen_stocks(market="US", filters={"sector": "Technology"}, limit=20, page=2)

    assert result["success"] is True
    assert result["market"] == "US"
    assert result["page"] == 2
    assert result["count"] == 1
    assert result["items"][0]["symbol"] == "AAPL"
    assert result["items"][0]["price"] == 180.12


def test_screen_stocks_applies_cn_market_filter(monkeypatch):
    monkeypatch.setattr(screener, "FMP_API_KEY", "demo-key")

    captured = {}

    def _fake_get(_url: str, params: dict, timeout: int):
        captured.update(params)
        return _DummyResponse(200, [])

    monkeypatch.setattr(screener, "_http_get", _fake_get)

    result = screener.screen_stocks(market="CN", filters={}, limit=10, page=1)

    assert result["success"] is True
    assert captured.get("country") == "CN"
    assert captured.get("offset") == 0
    assert "coverage is limited" in str(result.get("capability_note") or "")
