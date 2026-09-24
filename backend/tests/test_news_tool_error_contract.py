from __future__ import annotations

import types

from backend.tools import news


def test_get_news_sentiment_redacts_fetch_exception(monkeypatch):
    sentinel = "PRIVATE_NEWS_SENTIMENT_PROVIDER_DETAIL"

    def _fail_get(*_args, **_kwargs):
        raise RuntimeError(sentinel)

    monkeypatch.setattr(news, "ALPHA_VANTAGE_API_KEY", "configured")
    monkeypatch.setattr(news, "_http_get", _fail_get)

    result = news.get_news_sentiment("AAPL")

    assert result == "News Sentiment: fetch failed"
    assert sentinel not in result


def test_get_news_sentiment_skips_poison_feed_items(monkeypatch):
    """R107 回归：feed 中一条畸形记录不得毁掉整批结果。

    旧实现里 time_published=None → None[:8] TypeError、ticker_sentiment=None →
    迭代 None TypeError、ticker=None → None.upper() AttributeError、非 dict
    条目 → .get AttributeError——全部落进函数级 except，整个情绪结果变成
    'fetch failed'（与 R60 一个 NaN 桶毁掉整组分析师评级同缺陷类）。
    坏记录应被跳过，好记录照常返回。"""
    payload = {
        "feed": [
            {
                "title": "Alpha beats expectations",
                "source": "Reuters",
                "time_published": "20260924T120000",
                "url": "https://example.com/a",
                "ticker_sentiment": [
                    {
                        "ticker": "AAPL",
                        "ticker_sentiment_score": "0.5",
                        "ticker_sentiment_label": "Bullish",
                    }
                ],
            },
            None,  # 非 dict 条目
            {"title": None, "time_published": None, "ticker_sentiment": None},
            {"title": "poison-ts", "ticker_sentiment": [{"ticker": None}, "junk"]},
            "garbage-string",
            {
                "title": "Beta rises",
                "source": "Bloomberg",
                "time_published": "20260924T130000",
                "url": "https://example.com/b",
                "ticker_sentiment": [
                    {
                        "ticker": "AAPL",
                        "ticker_sentiment_score": "0.3",
                        "ticker_sentiment_label": "Somewhat-Bullish",
                    }
                ],
            },
        ]
    }

    class _Resp:
        def json(self):
            return payload

    monkeypatch.setattr(news, "ALPHA_VANTAGE_API_KEY", "configured")
    monkeypatch.setattr(news, "_http_get", lambda *a, **k: _Resp())

    result = news.get_news_sentiment("AAPL")

    assert "fetch failed" not in result
    assert "Alpha beats expectations" in result
    assert "Beta rises" in result


def test_get_company_news_skips_poison_av_feed_items(monkeypatch):
    """R108 回归：Alpha Vantage 分支单条毒记录不得毁掉整批已收集结果。

    article.get('time_published','') 对 present-None 不生效 → None[:8]
    TypeError；feed 里混入非 dict 条目 → .get AttributeError——两者都落进
    方法级 except，已收集的 items 被整体丢弃并回退到搜索兜底（同 R107
    缺陷类）。坏记录应被跳过，好记录照常返回。"""
    payload = {
        "feed": [
            {
                "title": "Alpha beats expectations",
                "source": "Reuters",
                "time_published": "20260924T120000",
                "summary": "solid earnings beat",
                "url": "https://example.com/a",
            },
            None,  # 非 dict 条目
            {"title": "poison", "time_published": None, "summary": "x"},
            {
                "title": "Beta rises sharply",
                "source": "Bloomberg",
                "time_published": "20260924T130000",
                "summary": "strong guidance",
                "url": "https://example.com/b",
            },
        ]
    }

    class _Resp:
        def json(self):
            return payload

    class _EmptyTicker:
        def __init__(self, _symbol):
            self.news = []

    search_called = []

    monkeypatch.setattr(news, "ALPHA_VANTAGE_API_KEY", "configured")
    monkeypatch.setattr(news, "finnhub_client", None)
    monkeypatch.setattr(news, "yf", types.SimpleNamespace(Ticker=_EmptyTicker))
    monkeypatch.setattr(news, "_http_get", lambda *a, **k: _Resp())
    monkeypatch.setattr(
        news, "search", lambda *a, **k: search_called.append(True) or ""
    )

    items = news.get_company_news("AAPL")

    assert not search_called, "毒记录不得把整批结果逼进搜索兜底"
    titles = [str(it.get("title")) for it in items]
    assert any("Alpha beats" in t for t in titles)
    assert any("Beta rises" in t for t in titles)
