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


import pytest


@pytest.fixture(autouse=True)
def _eastmoney_full_market_offline(monkeypatch):
    """本文件测的是 CN/HK fallback 链（eastmoney_quote / 静态池 / 冷却）。

    screen_stocks 现在优先走 cn_screener 的东财全市场源（调用时 import 真实
    模块，不受本文件顶部的 sys.modules 假注入控制）；不固定置为 None 的话，
    境内环境会真连东财返回真数据，直接短路掉 fallback 链的全部断言，且
    测试结果随网络/文件组合顺序漂移。"""
    import backend.tools.cn_screener as _cn_screener

    monkeypatch.setattr(_cn_screener, "eastmoney_screen_stocks", lambda **kwargs: None)


@pytest.fixture(autouse=True)
def _nasdaq_public_market_offline(monkeypatch):
    monkeypatch.setattr(screener, "nasdaq_screen_stocks", lambda **_kwargs: None)


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

    def _fail_yfinance(*_args, **_kwargs):
        raise AssertionError("US no-key screener should not wait on yfinance")

    monkeypatch.setattr(screener, "_yfinance_screen_stocks", _fail_yfinance)

    result = screener.screen_stocks(market="US", limit=10)

    assert result["success"] is True
    assert {item["symbol"] for item in result["items"]} >= {"AAPL", "MSFT"}
    assert result["source"] == "static_market_demo"


def test_screener_prefers_nasdaq_public_market_without_fmp_key(monkeypatch):
    monkeypatch.setattr(screener, "FMP_API_KEY", "")
    expected = {
        "success": True,
        "market": "US",
        "items": [{"symbol": f"REAL{index:03d}"} for index in range(120)],
        "count": 120,
        "source": "nasdaq_public_screener",
    }
    monkeypatch.setattr(screener, "nasdaq_screen_stocks", lambda **_kwargs: expected)

    result = screener.screen_stocks(market="US", limit=120)

    assert result is expected
    assert result["count"] == 120


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
    assert "免费行情源" in result["capability_note"]


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


def test_screener_cn_uses_tencent_quote_when_available(monkeypatch):
    monkeypatch.setattr(screener, "FMP_API_KEY", "")
    monkeypatch.setattr(
        screener,
        "fetch_cn_hk_quote_metrics",
        lambda symbol, **_kwargs: {
            "symbol": symbol,
            "name": symbol,
            "last_price": 10,
            "market_cap": 1000,
            "source": "tencent_quote",
        },
    )

    result = screener.screen_stocks(market="CN", limit=10)

    assert result["success"] is True
    assert result["source"] == "tencent_quote"
    assert result["warning"] is None


def test_screener_cn_static_pool_fills_first_page_when_live_source_is_slow(monkeypatch):
    monkeypatch.setattr(screener, "FMP_API_KEY", "")
    monkeypatch.setattr(screener, "_CN_HK_LIVE_UNAVAILABLE_UNTIL", {"CN": 0.0, "HK": 0.0})
    monkeypatch.setattr(screener, "fetch_cn_hk_quote_metrics", lambda *_args, **_kwargs: None)

    result = screener.screen_stocks(market="CN", limit=10)

    assert result["success"] is True
    assert result["market"] == "CN"
    assert result["source"] == "static_market_demo"
    assert result["count"] == 10
    assert len({item["symbol"] for item in result["items"]}) == 10
    assert screener._CN_HK_LIVE_UNAVAILABLE_UNTIL["CN"] > 0


def test_screener_hk_static_pool_fills_first_page_when_live_source_is_slow(monkeypatch):
    monkeypatch.setattr(screener, "FMP_API_KEY", "")
    monkeypatch.setattr(screener, "_CN_HK_LIVE_UNAVAILABLE_UNTIL", {"CN": 0.0, "HK": 0.0})
    monkeypatch.setattr(screener, "fetch_cn_hk_quote_metrics", lambda *_args, **_kwargs: None)

    result = screener.screen_stocks(market="HK", limit=10)

    assert result["success"] is True
    assert result["market"] == "HK"
    assert result["source"] == "static_market_demo"
    assert result["count"] == 10
    assert len({item["symbol"] for item in result["items"]}) == 10


@pytest.mark.parametrize(
    ("market", "expected_symbol"),
    [
        ("US", "ADBE"),
        ("CN", "601919.SS"),
        ("HK", "1928.HK"),
    ],
)
def test_static_fallback_pools_cover_at_least_thirty_named_symbols(market, expected_symbol):
    items = screener._static_fallback_items(market, {})

    assert len(items) >= 30
    assert len({item["symbol"] for item in items}) == len(items)
    assert expected_symbol in {item["symbol"] for item in items}
    assert all(item.get("name") and item["name"] != item["symbol"] for item in items)


def test_screener_cn_skips_live_source_during_cooldown(monkeypatch):
    monkeypatch.setattr(screener, "FMP_API_KEY", "")
    monkeypatch.setattr(screener, "_CN_HK_LIVE_UNAVAILABLE_UNTIL", {"CN": 999999999.0, "HK": 0.0})

    def _fail_quote(*_args, **_kwargs):
        raise AssertionError("CN live source should be skipped while cooldown is active")

    monkeypatch.setattr(screener, "fetch_cn_hk_quote_metrics", _fail_quote)

    result = screener.screen_stocks(market="CN", limit=10)

    assert result["success"] is True
    assert result["source"] == "static_market_demo"
    assert result["count"] == 10


def test_screener_fallback_result_keeps_items_and_results_alias(monkeypatch):
    monkeypatch.setattr(screener, "FMP_API_KEY", "")
    monkeypatch.setattr(screener.yf, "Ticker", lambda _symbol: _FakeTicker())

    result = screener._yfinance_popular_stocks("US", {}, 1, "marketCap", "desc")

    assert "items" in result
    assert "results" in result
    assert result["items"] == result["results"]
    assert result["items"][0]["country"] == "US"
