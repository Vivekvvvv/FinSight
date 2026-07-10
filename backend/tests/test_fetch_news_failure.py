# -*- coding: utf-8 -*-
"""R51 回归：fetch_news 在 news 管道故障时返回 None，而非空 payload 伪装成功。

此前两个来源都抛异常时仍返回 {"market":[], "impact":[], ...}，router 只把
None 当失败，导致真实故障被当成"高置信度无新闻"、缓存 TTL_NEWS 时长且
不标 fallback。区分"两源都失败"（→None）与"两源都返回空"（→真无新闻 payload）。
"""
from __future__ import annotations


def test_fetch_news_returns_none_when_both_sources_fail(monkeypatch):
    import backend.tools.news as news_mod
    from backend.dashboard import data_service

    def _boom(*args, **kwargs):
        raise RuntimeError("news source down")

    monkeypatch.setattr(news_mod, "get_company_news", _boom)
    monkeypatch.setattr(news_mod, "get_market_news_headlines", _boom)

    assert data_service.fetch_news("AAPL") is None


def test_fetch_news_returns_payload_when_both_sources_empty(monkeypatch):
    # 两源成功但返回空 = 真无新闻，必须返回 payload（非 None），否则误判为故障。
    import backend.tools.news as news_mod
    from backend.dashboard import data_service

    monkeypatch.setattr(news_mod, "get_company_news", lambda *a, **k: [])
    monkeypatch.setattr(news_mod, "get_market_news_headlines", lambda *a, **k: [])

    result = data_service.fetch_news("AAPL")
    assert result is not None
    assert result["market"] == []
    assert result["impact"] == []


def test_fetch_news_returns_payload_when_one_source_ok(monkeypatch):
    # 一源失败一源成功 → 部分降级，仍返回 payload，不算彻底故障。
    import backend.tools.news as news_mod
    from backend.dashboard import data_service

    def _boom(*args, **kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr(news_mod, "get_company_news", _boom)
    monkeypatch.setattr(news_mod, "get_market_news_headlines", lambda *a, **k: [])

    assert data_service.fetch_news("AAPL") is not None
