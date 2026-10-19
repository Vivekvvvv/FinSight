import json
import logging
from unittest.mock import MagicMock

import pytest

from backend.agents.news_agent import NewsAgent
from backend.services.circuit_breaker import CircuitBreaker


@pytest.mark.asyncio
async def test_news_stream_redacts_finnhub_error(caplog):
    secret = "PRIVATE_FINNHUB_STREAM_ERROR_SENTINEL"
    cache = MagicMock()
    cache.get.return_value = None
    tools = MagicMock()
    tools._fetch_with_finnhub_news.side_effect = RuntimeError(secret)
    agent = NewsAgent(None, cache, tools, CircuitBreaker())

    events = []
    async for raw_event in agent.analyze_stream("news", "AAPL"):
        event = json.loads(raw_event)
        events.append(event)
        if event.get("source") == "finnhub" and event.get("status") == "error":
            break

    failure = events[-1]
    assert failure["message"] == "source_unavailable"
    assert secret not in str(events)
    assert secret not in caplog.text
    assert "[NewsAgent] Finnhub stream fetch failed" in caplog.text


@pytest.mark.asyncio
async def test_news_stream_redacts_tavily_error(caplog):
    """Tavily 流式分支原本是唯一零日志的 except：源挂了只吐一个 error 帧，
    报告正文里也没有"数据源不可用"痕迹，用户把 0 条新闻当成"确实没有新闻"
    （项目规则 2、finsight-silent-success-forbidden）。
    """
    secret = "PRIVATE_TAVILY_STREAM_ERROR_SENTINEL"
    cache = MagicMock()
    cache.get.return_value = None
    tools = MagicMock()
    tools._fetch_with_finnhub_news.return_value = []
    tools._search_company_news.side_effect = RuntimeError(secret)
    agent = NewsAgent(None, cache, tools, CircuitBreaker())

    events = []
    async for raw_event in agent.analyze_stream("news", "AAPL"):
        event = json.loads(raw_event)
        events.append(event)
        if event.get("source") == "tavily" and event.get("status") == "error":
            break

    assert events[-1]["status"] == "error"
    assert secret not in str(events)
    assert secret not in caplog.text
    assert "[NewsAgent] Tavily stream fetch failed" in caplog.text


def test_event_calendar_failure_is_not_a_measured_empty_calendar(caplog):
    """日历源挂掉时 _load_event_calendar 回退成 {}，和"未来 30 天确实没有
    事件"在结构上同形：summary 照旧写 earnings=0，_format_output 还会把新闻
    证据的 confidence 顶到 0.8。一次取数故障必须留下 fallback_reason
    （项目规则 2、finsight-silent-success-forbidden）。
    """
    secret = "PRIVATE_EVENT_CALENDAR_SENTINEL"
    tools = MagicMock()
    tools.get_event_calendar.side_effect = RuntimeError(secret)
    agent = NewsAgent(None, MagicMock(), tools, CircuitBreaker())
    agent._last_event_calendar = {}
    agent._last_reliability_summary = {}

    with caplog.at_level(logging.WARNING):
        agent._last_event_calendar = agent._load_event_calendar("AAPL")
        output = agent._format_output(
            "Recent news includes: something happened.",
            [{"headline": "something happened", "source": "finnhub"}],
        )

    assert agent._last_event_calendar == {}
    assert output.fallback_reason == "event_calendar_unavailable"
    assert output.fallback_used is True
    assert "[NewsAgent] event calendar load failed" in caplog.text
    assert secret not in caplog.text


def test_successful_empty_event_calendar_stays_a_real_empty_calendar():
    """真·空日历（源可用、确实没有事件）不能被降级标记污染。"""
    tools = MagicMock()
    tools.get_event_calendar.return_value = {"earnings_events": []}
    agent = NewsAgent(None, MagicMock(), tools, CircuitBreaker())
    agent._last_reliability_summary = {}

    agent._last_event_calendar = agent._load_event_calendar("AAPL")
    output = agent._format_output(
        "Recent news includes: something happened.",
        [{"headline": "something happened", "source": "finnhub"}],
    )

    assert agent._last_event_calendar_failed is False
    assert output.fallback_reason is None


def test_news_reliability_rejects_non_finite_tool_score():
    tools = MagicMock()
    tools.score_news_source_reliability.return_value = {
        "reliability_score": float("nan"),
        "reliability_tier": "high",
    }
    agent = NewsAgent(None, MagicMock(), tools, CircuitBreaker())

    result = agent._score_reliability_for_item(
        {"source": "example", "url": "https://example.invalid"}
    )

    assert result["reliability_score"] == 0.55


def test_news_reliability_summary_skips_legacy_non_finite_score():
    agent = NewsAgent(None, MagicMock(), MagicMock(), CircuitBreaker())

    result = agent._summarize_reliability(
        [
            {"source_reliability": {"reliability_score": float("inf")}},
            {"source_reliability": {"reliability_score": 0.8}},
        ]
    )

    assert result["count"] == 1
    assert result["avg_reliability"] == 0.8
