from __future__ import annotations

import types
from datetime import UTC, datetime

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


def test_get_company_news_skips_non_dict_feed_items(monkeypatch):
    """R109 回归：yfinance/Finnhub 分支混入非 dict 条目不得毁掉整批。

    article.get(...) 对字符串/None 条目抛 AttributeError，落进方法级
    except 后该分支已收集的 items 全丢（与 R107/R108 同缺陷类）。"""
    search_called = []
    monkeypatch.setattr(
        news, "search", lambda *a, **k: search_called.append(True) or ""
    )
    monkeypatch.setattr(news, "ALPHA_VANTAGE_API_KEY", "")

    class _EmptyResp:
        def json(self):
            return {"feed": []}

    monkeypatch.setattr(news, "_http_get", lambda *a, **k: _EmptyResp())

    # ── 方法1: yfinance ────────────────────────────────────────────
    class _TickerWithPoisonNews:
        def __init__(self, _symbol):
            self.news = [
                {
                    "title": "Gamma beats estimates",
                    "summary": "record quarter guidance",
                    "publisher": "Reuters",
                    "providerPublishTime": 1758700000,
                    "link": "https://example.com/g",
                },
                "junk-entry",
                None,
            ]

    monkeypatch.setattr(news, "yf", types.SimpleNamespace(Ticker=_TickerWithPoisonNews))
    monkeypatch.setattr(news, "finnhub_client", None)

    items = news.get_company_news("AAPL")
    assert not search_called, "yfinance 分支毒记录不得毁批"
    assert any("Gamma beats" in str(it.get("title")) for it in items)

    # ── 方法2: Finnhub ────────────────────────────────────────────
    class _EmptyTicker:
        def __init__(self, _symbol):
            self.news = []

    monkeypatch.setattr(news, "yf", types.SimpleNamespace(Ticker=_EmptyTicker))
    monkeypatch.setattr(
        news,
        "finnhub_client",
        types.SimpleNamespace(
            company_news=lambda *a, **k: [
                {
                    "headline": "Delta raises outlook",
                    "summary": "management lifts guidance",
                    "source": "Finnhub",
                    "datetime": 1758700000,
                    "url": "https://example.com/d",
                },
                42,
                None,
            ]
        ),
    )

    items = news.get_company_news("AAPL")
    assert not search_called, "Finnhub 分支毒记录不得毁批"
    assert any("Delta raises" in str(it.get("title")) for it in items)


def test_fetch_finnhub_market_news_skips_poison_items(monkeypatch):
    """R110 回归：finnhub general_news 混入非 dict 条目不得让异常逃逸函数。

    该解析循环在 try 之外——item.get 对字符串/None 条目抛 AttributeError
    会直接传播给 get_market_news_headlines（无外层 try 包裹），整个
    市场要闻工具崩溃而非走下一兜底（同 R107 缺陷类，但此处异常逃逸）。
    且 items 为非 list 真值时 for 循环同样崩。"""
    from backend.tools import news_search_tools

    monkeypatch.setattr(
        news_search_tools,
        "finnhub_client",
        types.SimpleNamespace(
            general_news=lambda _category: [
                {
                    "headline": "Markets rally on data",
                    "summary": "stocks climb broadly",
                    "source": "Finnhub",
                    "datetime": int(datetime.now(UTC).timestamp()),
                    "url": "https://example.com/m",
                },
                "junk-entry",
                None,
                42,
            ]
        ),
    )

    lines, ok = news_search_tools._fetch_finnhub_market_news(limit=5, max_age_hours=48)

    assert ok, "含毒条目的 feed 不应整体失败"
    assert any("Markets rally" in line for line in lines)


def test_index_and_market_news_skip_non_dict_feed_items(monkeypatch):
    """R111 回归：指数/市场要闻分支的非 dict 条目按条跳过。

    get_company_news 指数路径的 alert_scheduler 循环（news.py:194）、
    index-yf 循环（news.py:226）、get_market_news_headlines 的
    alert_scheduler 循环（news.py:761）——a.get 对非 dict 条目抛
    AttributeError，已收集内容被弃或整条工具崩（同 R107-R110）。"""
    import backend.services.alert_scheduler as alert_scheduler

    search_called = []
    monkeypatch.setattr(
        news, "search", lambda *a, **k: search_called.append(True) or ""
    )
    monkeypatch.setattr(news, "ALPHA_VANTAGE_API_KEY", "")
    monkeypatch.setattr(news, "finnhub_client", None)
    monkeypatch.setattr(news, "_fetch_rss_headlines", lambda *a, **k: ([], False))
    monkeypatch.setattr(news, "_fetch_finnhub_market_news", lambda *a, **k: ([], False))

    class _EmptyResp:
        def json(self):
            return {"feed": []}

    monkeypatch.setattr(news, "_http_get", lambda *a, **k: _EmptyResp())

    class _EmptyTicker:
        def __init__(self, _symbol):
            self.news = []

    # ── 指数 alert_scheduler 循环 + index-yf 循环 ──────────────────
    monkeypatch.setattr(
        alert_scheduler,
        "fetch_news_articles",
        lambda _t: [
            {
                "title": "S&P hits record high",
                "summary": "broad rally across sectors",
                "source": "Reuters",
                "published_at": "2026-09-24T10:00:00",
                "url": "https://example.com/sp",
            },
            None,
            "junk",
        ],
    )

    items = news.get_company_news("^GSPC")
    assert any("record high" in str(it.get("title")) for it in items), (
        "alert_scheduler 循环的毒条目不得毁批"
    )

    # alert_scheduler 空 → 走 index-yf 循环（含毒条目）
    monkeypatch.setattr(alert_scheduler, "fetch_news_articles", lambda _t: [])

    class _IndexTicker:
        def __init__(self, _symbol):
            self.news = [
                {
                    "title": "Nasdaq climbs on tech",
                    "summary": "tech leads market gains",
                    "publisher": "Reuters",
                    "providerPublishTime": 1758700000,
                    "link": "https://example.com/n",
                },
                42,
            ]

    monkeypatch.setattr(news, "yf", types.SimpleNamespace(Ticker=_IndexTicker))
    items = news.get_company_news("^GSPC")
    assert any("Nasdaq climbs" in str(it.get("title")) for it in items), (
        "index-yf 循环的毒条目不得毁批"
    )
    assert not search_called, "毒条目不得把指数新闻逼进搜索兜底"

    # ── 市场要闻 alert_scheduler 循环 ─────────────────────────────
    monkeypatch.setattr(news, "yf", types.SimpleNamespace(Ticker=_EmptyTicker))
    monkeypatch.setattr(
        alert_scheduler,
        "fetch_news_articles",
        lambda _t: [
            {
                "title": "Global markets steady",
                "summary": "investors await data",
                "source": "Reuters",
                "published_at": "2026-09-24T09:00:00",
                "url": "https://example.com/gm",
            },
            "garbage",
        ],
    )

    result = news.get_market_news_headlines(limit=5)
    assert "Global markets steady" in result, "市场要闻循环的毒条目不得毁批"


def test_fetch_finnhub_market_news_coerces_non_string_fields(monkeypatch):
    """R123：dict 条目内的非 str 毒值过不了格式层——headline=123/{...} 的
    条目过了 isinstance 守卫后，_format_headline_line 的 (title or "").strip()
    AttributeError 逃逸出 per-item 解析循环，整个 get_market_news_headlines
    崩（同 R107-R110 缺陷类，毒值比毒记录深一层）。归 str 后合法条目照常输出。"""
    from backend.tools import news_search_tools

    monkeypatch.setattr(
        news_search_tools,
        "finnhub_client",
        types.SimpleNamespace(
            general_news=lambda _category: [
                {
                    "headline": 12345,
                    "summary": {"nested": "dict"},
                    "source": ["not-a-string"],
                    "datetime": int(datetime.now(UTC).timestamp()),
                    "url": "https://example.com/poison-values",
                },
                {
                    "headline": "Legit market headline for testing",
                    "summary": "valid summary here",
                    "source": "Finnhub",
                    "datetime": int(datetime.now(UTC).timestamp()),
                    "url": "https://example.com/legit",
                },
            ]
        ),
    )

    lines, ok = news_search_tools._fetch_finnhub_market_news(limit=5, max_age_hours=48)
    assert ok, "毒值条目不得让市场要闻工具整体失败"
    assert any("Legit market headline" in line for line in lines)
