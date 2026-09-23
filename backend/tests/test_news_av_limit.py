# -*- coding: utf-8 -*-
"""get_company_news 的 Alpha Vantage 兜底必须把调用方 limit 透传给 API 请求。

bug：AV 分支 params 写死 'limit': 5——调用方传 limit=10 时该路径最多返回 5 条，
同文件 get_news_sentiment 已正确透传 'limit': limit，证明此处是遗漏而非设计。
"""
from __future__ import annotations

from backend.tools import news


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _patch_upstream_misses(monkeypatch):
    """让 yfinance / finnhub 两路先落空，走到 Alpha Vantage 分支。"""

    class _EmptyTicker:
        news = []

    monkeypatch.setattr(news.yf, "Ticker", lambda _t: _EmptyTicker())
    monkeypatch.setattr(news, "finnhub_client", None)


def test_av_path_requests_and_returns_caller_limit(monkeypatch):
    _patch_upstream_misses(monkeypatch)
    captured = {}

    def _fake_get(url, params=None, timeout=None):
        captured.update(params or {})
        want = int(captured["limit"])
        feed = [
            {
                "title": f"Apple headline number {i} beats analyst expectations",
                "source": "Reuters",
                "time_published": "20260920T1200",
                "summary": "Apple results coverage summary text.",
                "url": f"https://example.com/{i}",
            }
            for i in range(12)
        ][:want]
        return _Resp({"feed": feed})

    monkeypatch.setattr(news, "_http_get", _fake_get)

    items = news.get_company_news("AAPL", limit=10)

    assert captured.get("limit") == 10
    assert len(items) == 10
