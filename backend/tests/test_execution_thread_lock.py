# -*- coding: utf-8 -*-
import asyncio
import importlib

from backend.services.execution_helpers import _get_thread_run_lock


def _make_deps(execution_service):
    async def _get_graph_runner():
        return object()

    return execution_service.ExecutionDeps(
        get_graph_runner=_get_graph_runner,
        schedule_report_index=lambda **_kwargs: None,
        update_session_context=lambda **_kwargs: None,
        record_chat_turn=None,
        redact_sensitive_payload=lambda payload: payload,
        is_raw_trace_event=lambda _payload: False,
        contract_info=lambda: {},
        sse_event_schema_version="chat.sse.v1",
    )


async def _collect(generator):
    return [
        item
        async for item in generator
        if not (isinstance(item, dict) and item.get("type") == "keep-alive")
    ]


def _patch_pipeline(monkeypatch, fake_run_graph_traced):
    runner_module = importlib.import_module("backend.graph.runner")
    report_builder_module = importlib.import_module("backend.graph.report_builder")
    graph_store_module = importlib.import_module("backend.graph.store")
    monkeypatch.setattr(runner_module, "run_graph_traced", fake_run_graph_traced)
    monkeypatch.setattr(
        report_builder_module,
        "build_report_payload",
        lambda **_kwargs: {
            "report_id": "rpt-thread-lock",
            "ticker": "AAPL",
            "title": "thread lock",
            "summary": "thread lock",
            "generated_at": "2026-02-20T00:00:00Z",
            "citations": [],
            "meta": {},
            "report_quality": {"state": "pass", "reasons": []},
        },
    )
    monkeypatch.setattr(graph_store_module, "persist_memory_snapshot", lambda **_kwargs: None)


def test_thread_run_lock_is_per_thread_and_per_loop():
    async def _same_loop():
        return (
            _get_thread_run_lock("thread-a"),
            _get_thread_run_lock("thread-a"),
            _get_thread_run_lock("thread-b"),
        )

    first, second, other = asyncio.run(_same_loop())
    assert first is second
    assert first is not other
    # 换 event loop 后必须重建（asyncio.Lock 绑定 loop），不能复用旧锁。
    assert asyncio.run(_same_loop())[0] is not first


def test_same_thread_runs_are_serialized(monkeypatch):
    execution_service = importlib.import_module("backend.services.execution_service")
    first_started = asyncio.Event()
    release = asyncio.Event()
    running = 0
    max_running = 0

    async def _fake_run_graph_traced(
        _runner,
        *,
        thread_id: str,
        query: str,
        ui_context=None,
        output_mode=None,
        strict_selection=None,
        confirmation_mode=None,
    ):
        nonlocal running, max_running
        running += 1
        max_running = max(max_running, running)
        first_started.set()
        await release.wait()
        running -= 1
        return {
            "thread_id": thread_id,
            "query": query,
            "output_mode": output_mode or "investment_report",
            "subject": {"subject_type": "company", "tickers": ["AAPL"]},
            "trace": {},
            "artifacts": {"draft_markdown": "thread lock markdown"},
        }

    _patch_pipeline(monkeypatch, _fake_run_graph_traced)

    async def _scenario():
        deps = _make_deps(execution_service)
        first = asyncio.create_task(
            _collect(execution_service.run_graph_pipeline(
                deps=deps, query="first", thread_id="same-thread", output_mode="investment_report",
            ))
        )
        await asyncio.wait_for(first_started.wait(), timeout=2)
        second = asyncio.create_task(
            _collect(execution_service.run_graph_pipeline(
                deps=deps, query="second", thread_id="same-thread", output_mode="investment_report",
            ))
        )
        await asyncio.sleep(0.1)
        assert max_running == 1, "同一 thread_id 的第二个 run 不应与第一个并行进入图执行"
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second), timeout=5)
        assert max_running == 1

    asyncio.run(_scenario())
