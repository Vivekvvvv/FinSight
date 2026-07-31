# -*- coding: utf-8 -*-

import asyncio
import logging


def _run(coro):
    return asyncio.run(coro)


def test_normalize_agent_output_repairs_invalid_shapes():
    import backend.graph.adapters.agent_adapter as adapter

    out = adapter._normalize_agent_output(
        step_name="news_agent",
        output={
            "summary": "  news ok  ",
            "confidence": "0.95",
            "evidence": "bad-shape",
            "data_sources": "bad-shape",
            "risks": "bad-shape",
            "trace": "bad-shape",
        },
        query="q",
        ticker="MSFT",
    )

    assert out.get("agent_name") == "news_agent"
    assert out.get("summary") == "news ok"
    assert 0.0 <= float(out.get("confidence", 0)) <= 1.0
    assert isinstance(out.get("evidence"), list)
    assert isinstance(out.get("data_sources"), list)
    assert isinstance(out.get("risks"), list)
    assert isinstance(out.get("trace"), list)


def test_normalize_agent_output_returns_fallback_on_empty_summary():
    import backend.graph.adapters.agent_adapter as adapter

    out = adapter._normalize_agent_output(
        step_name="price_agent",
        output={
            "summary": "   ",
            "confidence": 0.9,
            "evidence": [],
            "data_sources": ["x"],
        },
        query="price check",
        ticker="AAPL",
    )

    assert out.get("agent_name") == "price_agent"
    assert out.get("fallback_used") is True
    assert float(out.get("confidence", 1)) <= 0.2
    assert "降级" in str(out.get("summary") or "")


def test_build_agent_invokers_unknown_agent_returns_fallback():
    import backend.graph.adapters.agent_adapter as adapter

    invokers = adapter.build_agent_invokers(
        allowed_agents=["unknown_agent"],
        state={"query": "q", "subject": {"tickers": ["AAPL"]}},
    )

    assert "unknown_agent" in invokers
    out = _run(invokers["unknown_agent"]({"query": "q", "ticker": "AAPL"}))
    assert out.get("agent_name") == "unknown_agent"
    assert out.get("fallback_used") is True
    assert out.get("summary")


def test_build_agent_invoker_retries_and_fallbacks_on_runtime_error(monkeypatch):
    import backend.graph.adapters.agent_adapter as adapter

    monkeypatch.setenv("LANGGRAPH_AGENT_INVOKER_RETRY_ATTEMPTS", "2")
    monkeypatch.setenv("LANGGRAPH_AGENT_INVOKER_TIMEOUT_SECONDS", "2")

    class _BadAgent:
        async def research(self, query: str, ticker: str):
            raise RuntimeError("agent boom")

    async def _invoke_bad(inputs: dict):
        query = str(inputs.get("query") or "")
        ticker = str(inputs.get("ticker") or "N/A")
        last_error = "unknown"
        for attempt in range(1, 3):
            try:
                return await asyncio.wait_for(_BadAgent().research(query, ticker), timeout=2)
            except Exception as exc:
                last_error = f"{exc.__class__.__name__}: {exc}"
                if attempt < 2:
                    continue
        return adapter._build_agent_fallback_output(
            step_name="fundamental_agent",
            query=query,
            ticker=ticker,
            error=last_error,
        )

    out = _run(_invoke_bad({"query": "fundamental", "ticker": "AAPL"}))
    assert out.get("agent_name") == "fundamental_agent"
    assert out.get("fallback_used") is True
    assert "RuntimeError" in "\n".join(out.get("risks") or [])


def test_agent_invoker_redacts_runtime_error_from_events_fallback_and_logs(monkeypatch, caplog):
    import backend.agents.news_agent as news_agent_module
    import backend.graph.adapters.agent_adapter as adapter

    sentinel = "PRIVATE_AGENT_PROVIDER_TOKEN"
    events = []

    class _FailingNewsAgent:
        def __init__(self, *_args):
            pass

        async def research(self, **_kwargs):
            raise RuntimeError(sentinel)

    async def _capture_event(event):
        events.append(event)

    monkeypatch.setenv("LANGGRAPH_AGENT_INVOKER_RETRY_ATTEMPTS", "2")
    monkeypatch.setattr(news_agent_module, "NewsAgent", _FailingNewsAgent)
    monkeypatch.setattr(adapter, "emit_event", _capture_event)
    caplog.set_level(logging.INFO, logger=adapter.__name__)

    invokers = adapter.build_agent_invokers(
        allowed_agents=["news_agent"],
        state={"query": "news", "subject": {"tickers": ["AAPL"]}},
    )
    out = _run(invokers["news_agent"]({"query": "news", "ticker": "AAPL"}))

    serialized = str({"events": events, "output": out})
    assert sentinel not in serialized
    assert sentinel not in caplog.text
    assert "RuntimeError" in serialized
    assert out["fallback_used"] is True
