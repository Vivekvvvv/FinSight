import json
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
    assert "RuntimeError" in caplog.text


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
