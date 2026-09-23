# -*- coding: utf-8 -*-
"""DashboardDataService 缓存键必须包含影响结果的参数。

bug：get_market_chart 用 "market_chart:{period}:{interval}" 参数化键（约定），
但 get_snapshot/get_news/get_sector_weights/get_top_constituents/get_holdings
把 asset_type/limit 丢在键外——同 symbol 不同参数的请求命中彼此缓存，
调用方拿到错误参数的数据（limit=50 的请求吃到 limit=5 的缓存项、
etf 的行业权重串到 stock 查询）。
"""
from __future__ import annotations

from backend.dashboard import data_service


class _FakeCache:
    """与 dashboard_cache 同接口的内存实现。"""

    TTL_CHARTS = TTL_SNAPSHOT = TTL_NEWS = TTL_MACRO = 0
    TTL_SEGMENT_MIX = TTL_SECTOR_WEIGHTS = TTL_CONSTITUENTS = 0
    TTL_HOLDINGS = TTL_VALUATION = TTL_FINANCIALS = TTL_TECHNICALS = 0
    TTL_EARNINGS = TTL_ANALYST = 0

    def __init__(self):
        self.store = {}

    def get(self, symbol, key):
        return self.store.get((symbol, key))

    def set(self, symbol, key, data, ttl=None):
        self.store[(symbol, key)] = data


def _svc():
    svc = data_service.DashboardDataService()
    svc.cache = _FakeCache()
    return svc


def test_get_news_cache_key_includes_limit(monkeypatch):
    svc = _svc()
    calls = []

    def fake_fetch(symbol, limit):
        calls.append(limit)
        return {"items": list(range(limit))}

    monkeypatch.setattr(data_service, "fetch_news", fake_fetch)

    svc.get_news("AAPL", limit=5)
    out = svc.get_news("AAPL", limit=50)

    assert calls == [5, 50]  # limit=50 必须重新拉取，不得命中 limit=5 缓存
    assert len(out["items"]) == 50


def test_get_snapshot_cache_key_includes_asset_type(monkeypatch):
    svc = _svc()
    calls = []

    def fake_fetch(symbol, asset_type):
        calls.append(asset_type)
        return {"resolved": asset_type}

    monkeypatch.setattr(data_service, "fetch_snapshot", fake_fetch)

    svc.get_snapshot("SPY", "etf")
    out = svc.get_snapshot("SPY", "stock")

    assert calls == ["etf", "stock"]
    assert out["resolved"] == "stock"


def test_get_sector_weights_cache_key_includes_asset_type(monkeypatch):
    svc = _svc()
    calls = []

    def fake_fetch(symbol, asset_type):
        calls.append(asset_type)
        return [{"kind": asset_type}]

    monkeypatch.setattr(data_service, "fetch_sector_weights", fake_fetch)

    svc.get_sector_weights("SPY", "etf")
    out = svc.get_sector_weights("SPY", "stock")

    assert calls == ["etf", "stock"]
    assert out[0]["kind"] == "stock"


def test_get_top_constituents_cache_key_includes_params(monkeypatch):
    svc = _svc()
    calls = []

    def fake_fetch(symbol, asset_type, limit):
        calls.append((asset_type, limit))
        return [{"n": limit, "t": asset_type}]

    monkeypatch.setattr(data_service, "fetch_top_constituents", fake_fetch)

    svc.get_top_constituents("SPY", "etf", 10)
    out = svc.get_top_constituents("SPY", "etf", 25)

    assert calls == [("etf", 10), ("etf", 25)]
    assert out[0]["n"] == 25


def test_get_holdings_cache_key_includes_params(monkeypatch):
    svc = _svc()
    calls = []

    def fake_fetch(symbol, asset_type, limit):
        calls.append((asset_type, limit))
        return [{"n": limit}]

    monkeypatch.setattr(data_service, "fetch_holdings", fake_fetch)

    svc.get_holdings("SPY", "etf", 50)
    out = svc.get_holdings("SPY", "etf", 100)

    assert calls == [("etf", 50), ("etf", 100)]
    assert out[0]["n"] == 100


def test_same_params_still_hit_cache(monkeypatch):
    """同参数仍应命中缓存——修复只加参数维度，不破坏命中。"""
    svc = _svc()
    calls = []

    def fake_fetch(symbol, limit):
        calls.append(limit)
        return {"items": [limit]}

    monkeypatch.setattr(data_service, "fetch_news", fake_fetch)

    svc.get_news("AAPL", limit=20)
    out = svc.get_news("AAPL", limit=20)

    assert calls == [20]
    assert out["items"] == [20]
