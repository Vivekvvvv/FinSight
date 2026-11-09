from __future__ import annotations


import pytest

from backend.dashboard.data_service import fetch_news
from backend.dashboard.news_ranking import _to_news_item, _ts_seconds


def test_empty_news_limit_stops_before_fetching_external_sources(monkeypatch):
    import backend.tools.news as news
    calls = []
    def fetch(*args):
        calls.append(args)
        return [{"title": "update"}]
    monkeypatch.setattr(news, "get_company_news", fetch)
    monkeypatch.setattr(news, "get_market_news_headlines", fetch)
    for limit in (0, -1):
        result = fetch_news("AAPL", limit=limit)
        assert result["market"] == result["impact"] == result["market_raw"] == result["impact_raw"] == []
    assert calls == []


def test_future_news_timestamp_does_not_receive_maximum_recency():
    from datetime import datetime, timedelta, timezone
    from backend.dashboard.news_ranking import _calculate_time_decay
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert _calculate_time_decay(future) == 0.5


@pytest.mark.parametrize("failure", [{"error": "bad"}, {"success": False}, {"status": " Failed "}])
def test_failed_news_rows_cannot_appear_as_ranked_articles(monkeypatch, failure):
    import backend.tools.news as news
    monkeypatch.setattr(news, "get_company_news", lambda *args:
                        [{"title": "Bad earnings", **failure}, {"title": "Valid update"}])
    monkeypatch.setattr(news, "get_market_news_headlines", lambda *args: [])
    result = fetch_news("AAPL")
    assert [item["title"] for item in result["impact"]] == ["Valid update"]


def test_short_real_news_headlines_are_preserved_without_separator_lines():
    from backend.dashboard.news_ranking import _parse_news_text
    rows = _parse_news_text("1. CPI drops\n2. 央行降息\n---")
    assert [row["title"] for row in rows] == ["CPI drops", "央行降息"]


def test_news_text_fields_ignore_structures_and_use_valid_aliases():
    item = _to_news_item({"title": "AAPL update", "url": ["bad"], "link": "https://example.test/story",
                          "source": {"wrong": True}, "publisher": "Reuters",
                          "summary": {"earnings": True}, "snippet": "Schedule updated"})
    assert item["url"] == "https://example.test/story"
    assert item["source"] == "Reuters"
    assert item["summary"] == "Schedule updated"


def test_impact_keywords_cannot_match_inside_unrelated_words():
    from backend.dashboard.news_ranking import _estimate_asset_relevance, _estimate_impact_score
    assert _estimate_impact_score("Corporate cuts announced", "") == 0.45
    assert _estimate_asset_relevance("AAPL", "market", "Corporate cuts announced", "") == 0.4
    assert _estimate_impact_score("Rate cuts announced", "") >= 0.6


def test_news_ranking_considers_candidates_before_applying_result_limit(monkeypatch):
    import backend.tools.news as news
    import backend.dashboard.news_ranking as ranking

    monkeypatch.setattr(news, "get_company_news", lambda *args: [
        {"title": "Local market update", "source": "Unknown"},
        {"title": "Apple earnings guidance", "source": "Reuters"},
    ])
    monkeypatch.setattr(news, "get_market_news_headlines", lambda *args: [])
    monkeypatch.setattr(ranking, "_calculate_time_decay", lambda *args, **kwargs: 1.0)

    result = fetch_news("AAPL", limit=1)

    assert [item["title"] for item in result["impact"]] == ["Apple earnings guidance"]
    assert len(result["impact_raw"]) == 1


@pytest.mark.parametrize("source", ["SecurityWeek", "Second Nexus", "Financial Timesheet", "notreuters"])
def test_source_substrings_do_not_inherit_publisher_reliability(source):
    from backend.dashboard.news_ranking import _resolve_source_reliability

    assert _resolve_source_reliability(source) == 0.65


@pytest.mark.parametrize("source, score", [("Thomson Reuters", 0.95), ("SEC Filings", 0.86), ("Yahoo Finance", 0.72)])
def test_recognized_publisher_names_keep_reliability(source, score):
    from backend.dashboard.news_ranking import _resolve_source_reliability

    assert _resolve_source_reliability(source) == score


@pytest.mark.parametrize("hours, expected", [(0, 1.0), (36, 0.5), (72, 0.25)])
def test_news_recency_uses_the_advertised_half_life(monkeypatch, hours, expected):
    from datetime import datetime, timedelta, timezone
    import backend.dashboard.news_ranking as module

    fixed = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)

    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(module, "datetime", FixedClock)

    assert module._calculate_time_decay((fixed - timedelta(hours=hours)).isoformat(), half_life_hours=36) == pytest.approx(expected)


@pytest.mark.parametrize("symbol, title", [("AAPL", "Pineapple harvest grows"), ("C", "Electric cars rise"), ("BRK-B", "BRKBETA updates")])
def test_asset_substrings_do_not_boost_unrelated_news(symbol, title):
    from backend.dashboard.news_ranking import _estimate_asset_relevance

    assert _estimate_asset_relevance(symbol, "impact", title, "") == 0.35


def test_actual_ticker_and_company_mentions_keep_relevance_boost():
    from backend.dashboard.news_ranking import _estimate_asset_relevance

    assert _estimate_asset_relevance("AAPL", "impact", "$AAPL Apple results", "") > 0.35


@pytest.mark.parametrize("item", [{"title": True}, {"headline": {"value": "bad"}}, False, 7, []])
def test_invalid_news_titles_are_not_stringified_into_articles(item):
    assert _to_news_item(item)["title"] == ""


def test_news_filtering_precedes_the_result_limit(monkeypatch):
    import backend.tools.news as news

    monkeypatch.setattr(news, "get_company_news", lambda *args: [
        {"title": True}, {"headline": {}}, None,
        {"title": {}, "headline": "Valid headline"},
    ])
    monkeypatch.setattr(news, "get_market_news_headlines", lambda *args: [])

    result = fetch_news("AAPL", limit=2)

    assert [item["title"] for item in result["impact"]] == ["Valid headline"]


def test_all_unusable_news_rows_return_failure(monkeypatch):
    import backend.tools.news as news

    monkeypatch.setattr(news, "get_company_news", lambda *args: [{"title": True}, None])
    monkeypatch.setattr(news, "get_market_news_headlines", lambda *args: [])

    assert fetch_news("AAPL") is None


@pytest.mark.parametrize("with_url", [False, True])
def test_duplicate_news_does_not_displace_distinct_results(monkeypatch, with_url):
    import backend.tools.news as news

    first = {"title": "Same news", "source": "Reuters", "url": "https://example.com/one" if with_url else ""}
    second = {**first, "title": "same NEWS", "source": "reuters"}
    distinct = {"title": "Distinct news", "source": "Reuters", "url": "https://example.com/two"}
    monkeypatch.setattr(news, "get_company_news", lambda *args: [first, second, distinct])
    monkeypatch.setattr(news, "get_market_news_headlines", lambda *args: [])

    result = fetch_news("AAPL", limit=2)

    assert len(result["impact"]) == 2
    assert {item["title"] for item in result["impact"]} == {"Same news", "Distinct news"}
    assert len(result["impact_raw"]) == 2


def test_news_timestamp_helpers_reject_booleans():
    assert _ts_seconds(True) is None
    assert _ts_seconds(False) is None
    assert _to_news_item({"title": "bad ts", "ts": True})["ts"] == ""


def test_fetch_news_returns_ranking_meta_v2(monkeypatch):
    def _fake_company_news(symbol: str, limit: int = 20):
        return [
            {
                "title": f"{symbol} raises guidance after earnings beat",
                "summary": "Earnings and guidance update",
                "source": "Reuters",
                "ts": "2026-02-08T10:00:00+00:00",
                "url": "https://example.com/impact-1",
            },
            {
                "title": f"{symbol} supply chain outlook stable",
                "summary": "Operational note",
                "source": "Yahoo Finance",
                "ts": "2026-02-08T09:00:00+00:00",
                "url": "https://example.com/impact-2",
            },
        ]

    def _fake_market_news(limit: int = 20):
        return [
            {
                "title": "US market opens mixed ahead of CPI",
                "summary": "Macro focus on inflation",
                "source": "Bloomberg",
                "ts": "2026-02-08T08:00:00+00:00",
                "url": "https://example.com/market-1",
            },
            {
                "title": "Rates outlook remains uncertain",
                "summary": "Fed watchers split",
                "source": "MarketWatch",
                "ts": "2026-02-08T07:00:00+00:00",
                "url": "https://example.com/market-2",
            },
        ]

    monkeypatch.setattr("backend.tools.news.get_company_news", _fake_company_news)
    monkeypatch.setattr("backend.tools.news.get_market_news_headlines", _fake_market_news)

    payload = fetch_news("AAPL", limit=20)

    ranking_meta = payload.get("ranking_meta") or {}
    assert ranking_meta.get("version") == "v2"
    assert "weights" in ranking_meta
    assert "half_life_hours" in ranking_meta

    impact = payload.get("impact") or []
    market = payload.get("market") or []
    assert impact and market

    first_item = impact[0]
    assert "asset_relevance" in first_item
    assert "source_penalty" in first_item
    assert "ranking_reason" in first_item
    assert isinstance(first_item.get("ranking_factors"), dict)


def test_ranked_news_has_stable_descending_order(monkeypatch):
    def _fake_company_news(symbol: str, limit: int = 20):
        return [
            {
                "title": "Update A",
                "summary": "guidance and earnings",
                "source": "Reuters",
                "ts": "2026-02-08T10:00:00+00:00",
                "url": "https://example.com/a",
            },
            {
                "title": "Update B",
                "summary": "guidance and earnings",
                "source": "Reuters",
                "ts": "2026-02-08T10:00:00+00:00",
                "url": "https://example.com/b",
            },
        ]

    def _fake_market_news(limit: int = 20):
        return []

    monkeypatch.setattr("backend.tools.news.get_company_news", _fake_company_news)
    monkeypatch.setattr("backend.tools.news.get_market_news_headlines", _fake_market_news)

    payload = fetch_news("AAPL", limit=20)
    ranked = payload.get("impact") or []

    assert len(ranked) == 2
    assert float(ranked[0].get("ranking_score") or 0.0) >= float(ranked[1].get("ranking_score") or 0.0)
    # score ties should have deterministic order by title
    assert [item.get("title") for item in ranked] == sorted([item.get("title") for item in ranked])


def test_fetch_news_returns_none_when_sources_fail(monkeypatch):
    """R51 契约：两个来源都抛异常 = 管道故障，返回 None 让 router 走
    news_unavailable 降级；不得返回空 payload 伪装成"确实没新闻"。
    （旧断言锁定的正是被修掉的 bug：故障返回空 payload、被缓存 5 分钟。）"""
    def _raise_company_news(symbol: str, limit: int = 20):
        raise RuntimeError("company source down")

    def _raise_market_news(limit: int = 20):
        raise RuntimeError("market source down")

    monkeypatch.setattr("backend.tools.news.get_company_news", _raise_company_news)
    monkeypatch.setattr("backend.tools.news.get_market_news_headlines", _raise_market_news)

    assert fetch_news("AAPL", limit=20) is None
