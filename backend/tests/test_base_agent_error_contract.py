import json
from types import SimpleNamespace

import pytest

import backend.agents.base_agent as base_agent_module
from backend.agents.base_agent import BaseFinancialAgent


class _TraceRecorder:
    def __init__(self):
        self.llm_end = []
        self.tool_end = []

    def emit_llm_start(self, **_kwargs):
        return None

    def emit_llm_end(self, **kwargs):
        self.llm_end.append(kwargs)

    def emit_tool_start(self, *_args, **_kwargs):
        return None

    def emit_tool_end(self, *args, **kwargs):
        self.tool_end.append((args, kwargs))


@pytest.mark.asyncio
async def test_llm_analyze_redacts_provider_error(monkeypatch, caplog):
    secret = "PRIVATE_LLM_ERROR_SENTINEL"
    trace = _TraceRecorder()

    async def allow_token(**_kwargs):
        return True

    async def fail_invoke(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(base_agent_module, "get_trace_emitter", lambda: trace)
    monkeypatch.setattr("backend.services.rate_limiter.acquire_llm_token", allow_token)
    monkeypatch.setattr("backend.services.llm_retry.ainvoke_with_rate_limit_retry", fail_invoke)
    agent = BaseFinancialAgent(llm=SimpleNamespace(model_name="test"), cache=None)

    result = await agent._llm_analyze("summary", role="analyst", focus="risk")

    assert result is None
    assert trace.llm_end[-1]["error"] == "RuntimeError"
    assert secret not in caplog.text
    assert secret not in str(trace.llm_end)


@pytest.mark.asyncio
async def test_identify_gaps_redacts_provider_error(monkeypatch):
    secret = "PRIVATE_GAP_ERROR_SENTINEL"
    trace = _TraceRecorder()

    async def allow_token(**_kwargs):
        return True

    async def fail_invoke(*_args, **_kwargs):
        raise ValueError(secret)

    monkeypatch.setattr(base_agent_module, "get_trace_emitter", lambda: trace)
    monkeypatch.setattr("backend.services.rate_limiter.acquire_llm_token", allow_token)
    monkeypatch.setattr("backend.services.llm_retry.ainvoke_with_rate_limit_retry", fail_invoke)
    agent = BaseFinancialAgent(llm=SimpleNamespace(model_name="test"), cache=None)

    result = await agent._identify_gaps("summary")

    assert result == []
    assert trace.llm_end[-1]["error"] == "ValueError"
    assert secret not in str(trace.llm_end)


@pytest.mark.asyncio
async def test_identify_gaps_sanitizes_structured_llm_fields(monkeypatch):
    trace = _TraceRecorder()

    async def allow_token(**_kwargs):
        return True

    async def return_gaps(*_args, **_kwargs):
        return SimpleNamespace(
            content=(
                '{"complete":NaN}\n'
                '{"tool":"search","query":"AAPL filing","confidence":NaN}'
            )
        )

    monkeypatch.setattr(base_agent_module, "get_trace_emitter", lambda: trace)
    monkeypatch.setattr("backend.services.rate_limiter.acquire_llm_token", allow_token)
    monkeypatch.setattr(
        "backend.services.llm_retry.ainvoke_with_rate_limit_retry",
        return_gaps,
    )
    agent = BaseFinancialAgent(llm=SimpleNamespace(model_name="test"), cache=None)

    result = await agent._identify_gaps("summary")

    assert result == [{"tool": "search", "query": "AAPL filing"}]


@pytest.mark.asyncio
async def test_targeted_search_redacts_tool_error(monkeypatch, caplog):
    secret = "PRIVATE_TOOL_ERROR_SENTINEL"
    trace = _TraceRecorder()

    def fail_search(_query):
        raise RuntimeError(secret)

    monkeypatch.setattr(base_agent_module, "get_trace_emitter", lambda: trace)
    agent = BaseFinancialAgent(llm=None, cache=None)
    monkeypatch.setattr(
        agent,
        "_get_tool_registry",
        lambda: {"search": {"func": fail_search, "call_with": "query"}},
    )

    result = await agent._targeted_search(["missing filing"], "AAPL")

    assert result is None
    assert trace.tool_end[-1][1]["error"] == "RuntimeError"
    assert secret not in caplog.text
    assert secret not in str(trace.tool_end)


@pytest.mark.asyncio
async def test_update_summary_redacts_provider_error(monkeypatch):
    secret = "PRIVATE_SUMMARY_PASSWORD=provider-secret"
    trace = _TraceRecorder()

    async def allow_token(**_kwargs):
        return True

    async def fail_invoke(*_args, **_kwargs):
        raise ConnectionError(secret)

    monkeypatch.setattr(base_agent_module, "get_trace_emitter", lambda: trace)
    monkeypatch.setattr("backend.services.rate_limiter.acquire_llm_token", allow_token)
    monkeypatch.setattr("backend.services.llm_retry.ainvoke_with_rate_limit_retry", fail_invoke)
    agent = BaseFinancialAgent(llm=SimpleNamespace(model_name="test"), cache=None)

    result = await agent._update_summary("original", "new data")

    assert result == "original"
    assert trace.llm_end[-1]["error"] == "ConnectionError"
    assert secret not in str(trace.llm_end)


@pytest.mark.asyncio
async def test_analyze_stream_redacts_search_error(monkeypatch):
    secret = "PRIVATE_SEARCH_ERROR_SENTINEL"
    agent = BaseFinancialAgent(llm=None, cache=None)

    async def fail_search(_query, _ticker):
        raise RuntimeError(secret)

    monkeypatch.setattr(agent, "_initial_search", fail_search)

    events = [json.loads(item) async for item in agent.analyze_stream("query", "AAPL")]

    assert events[-1] == {"type": "error", "agent": "base", "message": "Search failed"}
    assert secret not in str(events)
