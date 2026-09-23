# -*- coding: utf-8 -*-
"""R68：screener_providers 两处过滤块与 us_screener(R66)/cn_screener(R67) 同型
缺陷——字段缺失的行在数值约束下被放行：
- _yfinance_popular_stocks：fast_info 拉取失败 → price=None 通过 "price>100"
- _alpha_vantage_screen_stocks：API 畸形值 → price=None 通过 "price>100"
有阈值时缺失字段应判不通过。

有意不动的两个宽松副本（语义边界说明）：
- _passes_screener_filters：CN/HK 实时行 volume 结构性 None（上游不取该字段），
  严格化会让任何 volumeMoreThan 必然丢光实时行——那是"字段未采集"的另一种缺陷，
  修法是给 fetch_cn_hk_quote_metrics 补字段，不是改过滤语义；
- _static_fallback_items：静态池（含 _ensure_static_fallback_coverage 合成项）
  price/market_cap/volume 全量非空，缺值路径不可达。"""
from __future__ import annotations

import backend.tools.screener_providers as sp


class _FakeTicker:
    def __init__(self, info):
        self.fast_info = info


def _run_yfinance(monkeypatch, infos, filters):
    """走 _yfinance_popular_stocks 主路径，禁用 AV/CN-HK 旁路与静态兜底。"""
    monkeypatch.setattr(sp, "_alpha_vantage_screen_stocks", lambda *a, **k: None)
    monkeypatch.setattr(sp, "_POPULAR_TICKERS", {"US": list(infos)})
    monkeypatch.setattr(sp.yf, "Ticker", lambda symbol: _FakeTicker(infos[symbol]))
    monkeypatch.setattr(sp, "_static_fallback_items", lambda *a, **k: [])
    return sp._yfinance_popular_stocks("US", filters, 10, "marketCap", "desc")


def test_yfinance_missing_price_fails_price_filter(monkeypatch):
    """fast_info.last_price 缺失（限流/停牌）的行不满足 "price>100"。"""
    result = _run_yfinance(
        monkeypatch,
        {
            "NOPX": {"last_price": None, "market_cap": 2e9, "last_volume": 1e6, "previous_close": None},
            "OKPX": {"last_price": 150.0, "market_cap": 1e9, "last_volume": 1e6, "previous_close": 140.0},
        },
        {"priceMoreThan": "100"},
    )
    assert [item["symbol"] for item in result["items"]] == ["OKPX"]


def test_yfinance_missing_market_cap_fails_cap_filter(monkeypatch):
    result = _run_yfinance(
        monkeypatch,
        {
            "NOCAP": {"last_price": 50.0, "market_cap": None, "last_volume": 1e6, "previous_close": None},
            "OKCAP": {"last_price": 50.0, "market_cap": 6e9, "last_volume": 1e6, "previous_close": None},
        },
        {"marketCapMoreThan": "1000000000"},
    )
    assert [item["symbol"] for item in result["items"]] == ["OKCAP"]


def test_yfinance_missing_volume_fails_volume_filter(monkeypatch):
    result = _run_yfinance(
        monkeypatch,
        {
            "NOVOL": {"last_price": 50.0, "market_cap": 6e9, "last_volume": None, "previous_close": None},
            "OKVOL": {"last_price": 50.0, "market_cap": 6e9, "last_volume": 9e6, "previous_close": None},
        },
        {"volumeMoreThan": "1000"},
    )
    assert [item["symbol"] for item in result["items"]] == ["OKVOL"]


def test_yfinance_no_threshold_keeps_missing_fields(monkeypatch):
    """无阈值约束时缺字段行保留——无约束语义不变。"""
    result = _run_yfinance(
        monkeypatch,
        {
            "NOPX": {"last_price": None, "market_cap": None, "last_volume": None, "previous_close": None},
            "OKPX": {"last_price": 150.0, "market_cap": 1e9, "last_volume": 1e6, "previous_close": None},
        },
        {},
    )
    assert {item["symbol"] for item in result["items"]} == {"NOPX", "OKPX"}


class _FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_alpha_vantage_missing_price_fails_price_filter(monkeypatch):
    """AV 榜单行 price 畸形（""→None）不满足 "price>100"。"""
    monkeypatch.setattr(sp, "ALPHA_VANTAGE_API_KEY", "test-key")
    payload = {
        "top_gainers": [
            {"ticker": "NOPX", "price": "", "volume": "1000", "change_percentage": "1%"},
            {"ticker": "OKPX", "price": "150.0", "volume": "1000", "change_percentage": "1%"},
        ],
        "top_losers": [],
        "most_actively_traded": [],
    }
    monkeypatch.setattr(sp, "_ALPHA_TOP_MOVERS_CACHE", {})
    monkeypatch.setattr(sp, "_http_get", lambda *a, **k: _FakeResponse(payload))
    result = sp._alpha_vantage_screen_stocks(
        market="US", filters={"priceMoreThan": "100"}, limit=10,
        sort_by="price", sort_order="desc",
    )
    assert result is not None
    assert [item["symbol"] for item in result["items"]] == ["OKPX"]


def test_alpha_vantage_missing_volume_fails_volume_filter(monkeypatch):
    monkeypatch.setattr(sp, "ALPHA_VANTAGE_API_KEY", "test-key")
    payload = {
        "most_actively_traded": [
            {"ticker": "NOVOL", "price": "50.0", "volume": "", "change_percentage": "1%"},
            {"ticker": "OKVOL", "price": "50.0", "volume": "9000000", "change_percentage": "1%"},
        ],
        "top_gainers": [],
        "top_losers": [],
    }
    monkeypatch.setattr(sp, "_ALPHA_TOP_MOVERS_CACHE", {})
    monkeypatch.setattr(sp, "_http_get", lambda *a, **k: _FakeResponse(payload))
    result = sp._alpha_vantage_screen_stocks(
        market="US", filters={"volumeMoreThan": "1000"}, limit=10,
        sort_by="volume", sort_order="desc",
    )
    assert result is not None
    assert [item["symbol"] for item in result["items"]] == ["OKVOL"]
