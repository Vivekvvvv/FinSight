from __future__ import annotations

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
