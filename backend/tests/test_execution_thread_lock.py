# -*- coding: utf-8 -*-
import asyncio
import importlib

import httpx
import pytest
from fastapi import FastAPI

from backend.api.chat_router import ChatRouterDeps, create_chat_router
from backend.security.auth import Principal, get_current_user
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


def _make_chat_app():
    async def _get_graph_runner():
        return object()

    async def _get_user():
        return Principal("alice", auth_type="dev")

    app = FastAPI()
    app.dependency_overrides[get_current_user] = _get_user
    app.include_router(create_chat_router(ChatRouterDeps(
        get_graph_runner=_get_graph_runner,
        resolve_thread_id=lambda session_id: session_id,
        build_ui_context=lambda _request: {},
        resolve_query_reference=lambda query, _thread_id: query,
        schedule_report_index=lambda **_kwargs: None,
        update_session_context=lambda **_kwargs: None,
        contract_info=lambda: {},
        resolve_trace_raw_enabled=lambda _request: False,
        is_raw_trace_event=lambda _event: False,
        redact_sensitive_payload=lambda payload: payload,
        get_session_context=lambda _thread_id: None,
        chat_history_store=None,
        chat_response_schema_version="chat.response.v1",
        sse_event_schema_version="chat.sse.v1",
    )))
    return app


@pytest.mark.parametrize("same_thread", [True, False])
@pytest.mark.parametrize("first_endpoint,second_endpoint", [
    ("/chat/supervisor", "/chat/supervisor"),
    ("/chat/supervisor", "/chat/supervisor/stream"),
    ("/chat/supervisor/stream", "/chat/supervisor"),
])
def test_chat_requests_preserve_checkpoint_updates(
    monkeypatch, same_thread, first_endpoint, second_endpoint,
):
    """用同一事件循环上的真实 HTTP 请求验证会话串行和跨会话并行。"""
    execution_helpers = importlib.import_module("backend.services.execution_helpers")
    checkpoints = {}
    first_started = asyncio.Event()
    second_reached = asyncio.Event()
    release = asyncio.Event()
    active = 0
    max_active = 0

    async def _run_graph(_runner, *, thread_id, query, **_kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        history = list(checkpoints.get(thread_id, []))
        (first_started if query == "first" else second_reached).set()
        try:
            await release.wait()
            checkpoints[thread_id] = [*history, query]
            return {
                "thread_id": thread_id,
                "subject": {"subject_type": "company", "tickers": ["AAPL"]},
                "artifacts": {"draft_markdown": query},
            }
        finally:
            active -= 1

    _patch_pipeline(monkeypatch, _run_graph)
    app = _make_chat_app()

    async def _scenario():
        first_thread = "public:alice:first"
        second_thread = first_thread if same_thread else "public:alice:second"
        lock = _get_thread_run_lock(first_thread)

        class _ObservedLock:
            async def __aenter__(self):
                if lock.locked():
                    # 第二个请求等待锁时通知测试，避免靠 sleep 猜测进度。
                    second_reached.set()
                await lock.acquire()
                return self

            async def __aexit__(self, *_args):
                lock.release()

        monkeypatch.setitem(execution_helpers._thread_run_locks, first_thread, _ObservedLock())
        tasks = []
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            def post(endpoint, query, session_id):
                return client.post(endpoint, json={
                    "query": query, "session_id": session_id,
                    "options": {"output_mode": "brief"},
                })

            tasks.append(asyncio.create_task(post(first_endpoint, "first", first_thread)))
            try:
                await asyncio.wait_for(first_started.wait(), timeout=2)
                tasks.append(asyncio.create_task(post(second_endpoint, "second", second_thread)))
                await asyncio.wait_for(second_reached.wait(), timeout=2)
                assert max_active == (1 if same_thread else 2)
            finally:
                release.set()
                responses = await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)

        assert len(responses) == 2
        assert all(response.status_code == 200 for response in responses)
        if same_thread:
            assert checkpoints[first_thread] == ["first", "second"]
        else:
            assert checkpoints == {first_thread: ["first"], second_thread: ["second"]}

    asyncio.run(_scenario())


def test_sync_chat_execution_failure_releases_thread_lock(monkeypatch):
    async def _run_graph(_runner, *, query, **_kwargs):
        if query == "fail":
            raise RuntimeError("graph failed")
        return {"artifacts": {"draft_markdown": "ok"}}

    _patch_pipeline(monkeypatch, _run_graph)
    app = _make_chat_app()

    async def _scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            failure = await client.post("/chat/supervisor", json={
                "query": "fail", "session_id": "public:alice:failure",
            })
            assert failure.status_code == 500
            success = await asyncio.wait_for(client.post("/chat/supervisor", json={
                "query": "retry", "session_id": "public:alice:failure",
            }), timeout=2)
            assert success.status_code == 200
            assert success.json()["response"] == "ok"

    asyncio.run(_scenario())


def test_sync_chat_timeout_cancels_graph_and_releases_thread_lock(monkeypatch):
    router_module = importlib.import_module("backend.api.chat_router")
    monkeypatch.setattr(router_module, "_execution_timeout_seconds", lambda _mode: 0.02, raising=False)
    cancelled = asyncio.Event()

    async def _run_graph(_runner, *, query, **_kwargs):
        if query == "stall":
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
        return {"artifacts": {"draft_markdown": "ok"}}

    _patch_pipeline(monkeypatch, _run_graph)
    app = _make_chat_app()

    async def _scenario():
        thread_id = "public:alice:timeout"
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            response = await asyncio.wait_for(client.post("/chat/supervisor", json={
                "query": "stall", "session_id": thread_id,
            }), timeout=1)

            assert response.status_code == 504
            assert "timed out" in response.json()["detail"].lower()
            assert cancelled.is_set(), "超时必须取消图执行"
            assert not _get_thread_run_lock(thread_id).locked(), "超时后必须释放会话锁"

            retry = await asyncio.wait_for(client.post("/chat/supervisor", json={
                "query": "retry", "session_id": thread_id,
            }), timeout=1)
            assert retry.status_code == 200
            assert retry.json()["response"] == "ok"

    asyncio.run(_scenario())


@pytest.mark.parametrize("output_mode,expected_status", [
    (None, 504), ("brief", 504), ("chat", 504), ("investment_report", 200),
])
def test_sync_chat_timeout_uses_requested_output_mode(monkeypatch, output_mode, expected_status):
    router_module = importlib.import_module("backend.api.chat_router")
    monkeypatch.setattr(
        router_module, "_execution_timeout_seconds",
        lambda mode: 0.2 if mode == "investment_report" else 0.02,
        raising=False,
    )
    monkeypatch.setattr(router_module, "enforce_feature", lambda *_args: None)

    async def _run_graph(_runner, **_kwargs):
        await asyncio.sleep(0.06)
        return {"artifacts": {"draft_markdown": "ok"}}

    _patch_pipeline(monkeypatch, _run_graph)
    app = _make_chat_app()

    async def _scenario():
        request = {"query": "slow", "session_id": "public:alice:mode-timeout"}
        if output_mode is not None:
            request["options"] = {"output_mode": output_mode}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test",
        ) as client:
            response = await asyncio.wait_for(
                client.post("/chat/supervisor", json=request), timeout=1,
            )

        assert response.status_code == expected_status
        if expected_status == 200:
            assert response.json()["response"] == "ok"

    asyncio.run(_scenario())
