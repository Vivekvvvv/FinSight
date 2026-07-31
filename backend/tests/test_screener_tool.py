# -*- coding: utf-8 -*-
from __future__ import annotations

from backend.tools import screener

import pytest


@pytest.fixture(autouse=True)
def _eastmoney_full_market_offline(monkeypatch):
    """本文件测 US 静态池与 CN 逐票行情 fallback。screen_stocks 现在优先走
    东财全市场源（cn_screener），境内会真连网络短路掉次级 fallback 的断言，
    且结果随文件组合顺序漂移；固定为不可用，让断言确定性覆盖 fallback 链。"""
    import backend.tools.cn_screener as _cn_screener

    monkeypatch.setattr(_cn_screener, "eastmoney_screen_stocks", lambda **kwargs: None)


class _DummyResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_screen_stocks_uses_fallback_without_api_key(monkeypatch):
    monkeypatch.setattr(screener, "FMP_API_KEY", "")

    def _fail_yfinance(*_args, **_kwargs):
        raise AssertionError("US no-key screener should not wait on yfinance")

    monkeypatch.setattr(screener, "_yfinance_screen_stocks", _fail_yfinance)

    result = screener.screen_stocks(market="US", filters={}, limit=10, page=1)

    assert result["success"] is True
    assert result["source"] == "static_market_demo"
    assert result["count"] == 10
    assert {item["symbol"] for item in result["items"]} >= {"AAPL", "MSFT"}


def test_screen_stocks_static_fallback_fills_first_page(monkeypatch):
    monkeypatch.setattr(screener, "FMP_API_KEY", "")

    result = screener.screen_stocks(market="US", filters={}, limit=20, page=1)

    assert result["success"] is True
    assert result["source"] == "static_market_demo"
    assert result["count"] == 20
    assert len({item["symbol"] for item in result["items"]}) == 20


def test_yfinance_empty_result_uses_static_popular_fallback(monkeypatch):
    monkeypatch.setattr(screener, "ALPHA_VANTAGE_API_KEY", "")

    class _BrokenTicker:
        @property
        def fast_info(self):
            raise RuntimeError("network unavailable")

    monkeypatch.setattr(screener.yf, "Ticker", lambda _symbol: _BrokenTicker())

    result = screener._yfinance_popular_stocks("US", {}, 3, "marketCap", "desc")

    assert result["success"] is True
    assert result["count"] == 3
    assert result["items"]
    assert result["source"] == "static_market_demo"
    assert result["items"][0]["symbol"] in {"AAPL", "MSFT", "NVDA", "GOOGL"}


def test_yfinance_fallback_error_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE http://proxy-user:secret@proxy.local"
    calls = {"count": 0}

    def _fail_then_empty(_market, _filters):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError(secret)
        return []

    monkeypatch.setattr(screener, "_alpha_vantage_screen_stocks", lambda *_args: None)
    monkeypatch.setattr(screener, "_static_fallback_items", _fail_then_empty)
    monkeypatch.setattr(screener.yf, "Ticker", lambda _symbol: (_ for _ in ()).throw(RuntimeError("offline")))

    result = screener._yfinance_popular_stocks("US", {}, 3, "marketCap", "desc")

    assert result["success"] is False
    assert result["error"] == "yfinance_fallback_failed"
    assert secret not in str(result)
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_screen_stocks_parses_items(monkeypatch):
    monkeypatch.setattr(screener, "FMP_API_KEY", "demo-key")

    def _fake_get(_url: str, params: dict, timeout: int):
        assert _url.endswith("/stable/company-screener")
        assert params["apikey"] == "demo-key"
        assert params["limit"] == 20
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
    assert result["source"] == "fmp_company_screener"
    assert result["count"] == 0


def test_screen_stocks_fmp_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE https://api-key@fmp.example.com"
    fallback = {
        "success": True,
        "market": "US",
        "items": [{"symbol": "AAPL"}],
        "results": [{"symbol": "AAPL"}],
        "count": 1,
        "source": "static_market_demo",
    }

    def _fail_get(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(screener, "FMP_API_KEY", "test-key")
    monkeypatch.setattr(screener, "_FMP_SCREENER_UNAVAILABLE_UNTIL", 0.0)
    monkeypatch.setattr(screener, "_http_get", _fail_get)
    monkeypatch.setattr(screener, "_yfinance_screen_stocks", lambda *_args: fallback)

    result = screener.screen_stocks(market="US", filters={}, limit=10, page=1)

    assert result["source"] == "static_market_demo"
    assert secret not in str(result)
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_screen_stocks_applies_cn_market_filter(monkeypatch):
    monkeypatch.setattr(screener, "FMP_API_KEY", "demo-key")
    monkeypatch.setattr(
        screener,
        "fetch_cn_hk_quote_metrics",
        lambda symbol, **_kwargs: {
            "symbol": symbol,
            "name": symbol,
            "last_price": 10,
            "market_cap": 1000,
        },
    )

    def _fail_get(*_args, **_kwargs):
        raise AssertionError("CN/HK screener should use Eastmoney path before FMP")

    monkeypatch.setattr(screener, "_http_get", _fail_get)

    result = screener.screen_stocks(market="CN", filters={}, limit=10, page=1)

    assert result["success"] is True
    assert result["source"] == "eastmoney_quote"
    assert "免费行情源" in str(result.get("capability_note") or "")


def test_screen_stocks_paid_fmp_status_falls_back_with_clear_note(monkeypatch):
    monkeypatch.setattr(screener, "FMP_API_KEY", "free-key")
    monkeypatch.setattr(screener, "_FMP_SCREENER_UNAVAILABLE_UNTIL", 0.0)
    monkeypatch.setattr(screener, "_FMP_SCREENER_UNAVAILABLE_STATUS", None)

    def _fake_get(_url: str, params: dict, timeout: int):
        return _DummyResponse(402, {"error": "payment required"})

    monkeypatch.setattr(screener, "_http_get", _fake_get)
    monkeypatch.setattr(
        screener,
        "_yfinance_screen_stocks",
        lambda market, filters, limit, sort_by, sort_order: {
            "success": True,
            "market": market,
            "items": [{"symbol": "AAPL"}],
            "results": [{"symbol": "AAPL"}],
            "count": 1,
            "source": "alpha_vantage_top_movers",
            "warning": None,
            "capability_note": "Using Alpha Vantage free top movers.",
        },
    )

    result = screener.screen_stocks(market="US", filters={}, limit=10, page=1)

    assert result["success"] is True
    assert result["source"] == "alpha_vantage_top_movers"
    assert result["warning"] == "fmp_screener_unavailable"
    assert "HTTP 402" in str(result["capability_note"])


def test_screen_stocks_skips_fmp_during_paid_status_cooldown(monkeypatch):
    monkeypatch.setattr(screener, "FMP_API_KEY", "free-key")
    monkeypatch.setattr(screener, "_FMP_SCREENER_UNAVAILABLE_UNTIL", 999999999.0)
    monkeypatch.setattr(screener, "_FMP_SCREENER_UNAVAILABLE_STATUS", 402)

    def _fail_get(*_args, **_kwargs):
        raise AssertionError("FMP should be skipped while paid-status cooldown is active")

    monkeypatch.setattr(screener, "_http_get", _fail_get)
    monkeypatch.setattr(
        screener,
        "_yfinance_screen_stocks",
        lambda market, filters, limit, sort_by, sort_order: {
            "success": True,
            "market": market,
            "items": [{"symbol": "AAPL"}],
            "results": [{"symbol": "AAPL"}],
            "count": 1,
            "source": "alpha_vantage_top_movers",
            "warning": None,
            "capability_note": "Using Alpha Vantage free top movers.",
        },
    )

    result = screener.screen_stocks(market="US", filters={}, limit=10, page=1)

    assert result["success"] is True
    assert result["warning"] == "fmp_screener_unavailable"
    assert "HTTP 402" in str(result["capability_note"])
