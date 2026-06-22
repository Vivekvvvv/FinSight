from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types


class _FakeFastInfo:
    last_price = 195.5
    market_cap = 3_000_000_000_000
    last_volume = 50_000_000


class _FakeTicker:
    fast_info = _FakeFastInfo()


_ORIGINAL_MODULES = {
    "backend.tools.env": sys.modules.get("backend.tools.env"),
    "backend.tools.http": sys.modules.get("backend.tools.http"),
}

sys.modules.setdefault("yfinance", types.SimpleNamespace(Ticker=lambda _symbol: _FakeTicker()))
sys.modules.setdefault(
    "backend.tools.env",
    types.SimpleNamespace(
        ALPHA_VANTAGE_API_KEY="",
        FMP_API_KEY="",
        FINNHUB_API_KEY="",
        MASSIVE_API_KEY="",
        IEX_CLOUD_API_KEY="",
        TIINGO_API_KEY="",
        TWELVE_DATA_API_KEY="",
        MARKETSTACK_API_KEY="",
        TAVILY_API_KEY="",
        EXA_API_KEY="",
        OPENFIGI_API_KEY="",
        EODHD_API_KEY="",
        FRED_API_KEY="",
        finnhub_client=None,
    ),
)
sys.modules.setdefault(
    "backend.tools.http",
    types.SimpleNamespace(
        _http_get=lambda *args, **kwargs: None,
        _http_post=lambda *args, **kwargs: None,
    ),
)

_SCREENER_PATH = Path(__file__).resolve().parents[1] / "tools" / "screener.py"
_SPEC = importlib.util.spec_from_file_location("screener_under_test", _SCREENER_PATH)
assert _SPEC and _SPEC.loader
screener = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(screener)

for _module_name, _module in _ORIGINAL_MODULES.items():
    if _module is None:
        sys.modules.pop(_module_name, None)
    else:
        sys.modules[_module_name] = _module


def _fake_us_fallback(market, filters, limit, sort_by, sort_order):
    return {
        "success": True,
        "market": market,
        "items": [
            {
                "symbol": "AAPL",
                "name": "Apple",
                "price": 195.5,
                "market_cap": 3_000_000_000_000,
            }
        ][:limit],
        "count": 1,
        "source": "test_fallback",
        "sort": {"by": sort_by, "order": sort_order},
        "filters": filters or {},
    }


def test_screener_uses_fallback_without_fmp_key(monkeypatch):
    monkeypatch.setattr(screener, "FMP_API_KEY", "")
    monkeypatch.setattr(screener, "_yfinance_screen_stocks", _fake_us_fallback)

    result = screener.screen_stocks(market="US", limit=10)

    assert result["success"] is True
    assert result["items"][0]["symbol"] == "AAPL"
    assert result["source"] == "test_fallback"


def test_screener_invalid_sort_falls_back(monkeypatch):
    monkeypatch.setattr(screener, "FMP_API_KEY", "")
    monkeypatch.setattr(screener, "_yfinance_screen_stocks", _fake_us_fallback)

    result = screener.screen_stocks(market="US", sort_by="bad", sort_order="bad")

    assert result["sort"] == {"by": "marketCap", "order": "desc"}


def test_screener_cn_without_key_uses_yfinance_popular(monkeypatch):
    monkeypatch.setattr(screener, "FMP_API_KEY", "")
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

    result = screener.screen_stocks(market="CN", limit=10)

    assert result["success"] is True
    assert result["market"] == "CN"
    assert result["items"]
    assert result["items"][0]["country"] == "CN"
    assert result["warning"] is None
    assert result["source"] == "eastmoney_quote"
    assert "Eastmoney" in result["capability_note"]


def test_screener_hk_without_key_uses_yfinance_popular(monkeypatch):
    monkeypatch.setattr(screener, "FMP_API_KEY", "")
    monkeypatch.setattr(
        screener,
        "fetch_cn_hk_quote_metrics",
        lambda symbol, **_kwargs: {
            "symbol": symbol,
            "name": symbol,
            "last_price": 20,
            "market_cap": 2000,
        },
    )

    result = screener.screen_stocks(market="HK", limit=10)

    assert result["success"] is True
    assert result["market"] == "HK"
    assert result["items"]
    assert result["items"][0]["country"] == "HK"
    assert result["warning"] is None
    assert result["source"] == "eastmoney_quote"


def test_screener_fallback_result_keeps_items_and_results_alias(monkeypatch):
    monkeypatch.setattr(screener, "FMP_API_KEY", "")
    monkeypatch.setattr(screener.yf, "Ticker", lambda _symbol: _FakeTicker())

    result = screener._yfinance_popular_stocks("US", {}, 1, "marketCap", "desc")

    assert "items" in result
    assert "results" in result
    assert result["items"] == result["results"]
    assert result["items"][0]["country"] == "US"
