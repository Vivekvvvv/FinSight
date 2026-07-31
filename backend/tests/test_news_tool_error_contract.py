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
