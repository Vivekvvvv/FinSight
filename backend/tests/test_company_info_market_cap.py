# -*- coding: utf-8 -*-
"""R73：get_company_info yfinance 分支 `info.get('marketCap', 0)` —— .get
默认值只在键缺失时生效；yfinance 对 ETF/指数/加密/小盘标的常返回
{'marketCap': None}（键存在、值为 None），`f"{None:,.0f}"` 抛
TypeError，整个 yfinance 分支被 except 吞掉 → 明明拿到 longName
却退化到 Finnhub/AlphaVantage/web 搜索。与 361/380 行
safe_float(...) or 0.0 同型修复。"""
from __future__ import annotations

import backend.tools.financial as fin


class _FakeTicker:
    def __init__(self, info):
        self.info = info


def _patch_fallthrough(monkeypatch):
    """封死 Finnhub/AV/web 兜底路径——走到即说明 yfinance 分支死了。"""
    monkeypatch.setattr(fin, "finnhub_client", None)

    def _boom(*_a, **_k):
        raise AssertionError("AlphaVantage path must not be reached")

    monkeypatch.setattr(fin, "_http_get", _boom)
    monkeypatch.setattr(fin, "search", lambda *_a, **_k: "WEB_SEARCH_FALLBACK")


def test_market_cap_none_keeps_yfinance_path(monkeypatch):
    """marketCap=None 不该杀死 yfinance 分支——修前 TypeError → web 兜底。"""
    monkeypatch.setattr(fin.yf, "Ticker", lambda _t: _FakeTicker({
        "longName": "SPDR S&P 500 ETF",
        "marketCap": None,
        "sector": None,
        "industry": None,
        "website": "https://example.com",
        "longBusinessSummary": "",
    }))
    _patch_fallthrough(monkeypatch)
    out = fin.get_company_info("SPY")
    assert "Company Profile" in out
    assert "SPDR S&P 500 ETF" in out
    assert out != "WEB_SEARCH_FALLBACK"


def test_market_cap_non_numeric_does_not_crash(monkeypatch):
    """marketCap 为畸形字符串也不该崩——safe_float 归一为 $0。"""
    monkeypatch.setattr(fin.yf, "Ticker", lambda _t: _FakeTicker({
        "longName": "Weird Corp",
        "marketCap": "N/A",
        "sector": "Industrials",
        "industry": "Misc",
        "website": "",
        "longBusinessSummary": "",
    }))
    _patch_fallthrough(monkeypatch)
    out = fin.get_company_info("WCO")
    assert "Weird Corp" in out
    assert "Market Cap: $0" in out


def test_market_cap_present_formats_value(monkeypatch):
    """正常 marketCap 仍格式化进简介——回归保护。"""
    monkeypatch.setattr(fin.yf, "Ticker", lambda _t: _FakeTicker({
        "longName": "Apple Inc.",
        "marketCap": 3_000_000_000_000,
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "website": "https://apple.com",
        "longBusinessSummary": "Makes stuff",
    }))
    _patch_fallthrough(monkeypatch)
    out = fin.get_company_info("AAPL")
    assert "Market Cap: $3,000,000,000,000" in out
