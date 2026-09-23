# -*- coding: utf-8 -*-
import asyncio
import importlib


def _run(coro):
    return asyncio.run(coro)


async def _collect_events(generator):
    items = []
    async for item in generator:
        if isinstance(item, dict) and item.get("type") == "keep-alive":
            continue
        items.append(item)
    return items


def test_run_graph_pipeline_emits_quality_blocked_and_skips_index(monkeypatch, caplog):
    execution_service = importlib.import_module("backend.services.execution_service")
    runner_module = importlib.import_module("backend.graph.runner")
    report_builder_module = importlib.import_module("backend.graph.report_builder")
    graph_store_module = importlib.import_module("backend.graph.store")

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
        return {
            "thread_id": thread_id,
            "query": query,
            "output_mode": output_mode or "investment_report",
            "subject": {"subject_type": "company", "tickers": ["AAPL"]},
            "trace": {},
            "artifacts": {"draft_markdown": "blocked markdown"},
        }

    monkeypatch.setattr(runner_module, "run_graph_traced", _fake_run_graph_traced)
    monkeypatch.setattr(
        report_builder_module,
        "build_report_payload",
        lambda **kwargs: {
            "report_id": "rpt-block-1",
            "ticker": "AAPL",
            "title": "blocked report",
            "summary": "blocked",
            "generated_at": "2026-02-20T00:00:00Z",
            "citations": [],
            "meta": {},
            "report_quality": {
                "state": "block",
                "reasons": [
                    {
                        "code": "EVIDENCE_COVERAGE_BELOW_MIN",
                        "severity": "block",
                        "metric": "coverage",
                        "actual": 0.2,
                        "threshold": 0.8,
                        "message": "coverage too low",
                    }
                ],
            },
        },
    )

    indexed: list[dict] = []
    updated_context: list[dict] = []
    secret = "PRIVATE postgres://execution:secret@db/chat-turn"

    def _fail_record_chat_turn(**_kwargs):
        raise RuntimeError(secret)

    memory_secret = "PRIVATE postgres://execution:secret@db/memory"

    def _fail_memory_snapshot(**_kwargs):
        raise RuntimeError(memory_secret)

    monkeypatch.setattr(graph_store_module, "persist_memory_snapshot", _fail_memory_snapshot)

    async def _fake_get_graph_runner():
        return object()

    deps = execution_service.ExecutionDeps(
        get_graph_runner=_fake_get_graph_runner,
        schedule_report_index=lambda **kwargs: indexed.append(kwargs),
        update_session_context=lambda **kwargs: updated_context.append(kwargs),
        record_chat_turn=_fail_record_chat_turn,
        redact_sensitive_payload=lambda payload: payload,
        is_raw_trace_event=lambda payload: False,
        contract_info=lambda: {"chat_response": "chat.response.v1"},
        sse_event_schema_version="chat.sse.v1",
    )

    events = _run(
        _collect_events(
            execution_service.run_graph_pipeline(
                deps=deps,
                query="生成 AAPL 投资报告",
                thread_id="tenant:user:thread",
                output_mode="investment_report",
                source="execute_test",
            )
        )
    )

    # soft-block: report exists so it IS indexed with quality metadata
    assert indexed, "soft-blocked reports should be indexed (report content preserved)"
    assert updated_context, "chat context should still be updated for conversation continuity"

    blocked_events = [event for event in events if isinstance(event, dict) and event.get("type") == "quality_blocked"]
    assert blocked_events, "SSE stream should emit quality_blocked"
    # soft-blocked: publishable=True because content is preserved
    assert blocked_events[0].get("publishable") is True
    assert "EVIDENCE_COVERAGE_BELOW_MIN" in (blocked_events[0].get("blocked_reason_codes") or [])
    assert blocked_events[0].get("blocked_report_available") is True
    assert blocked_events[0].get("allow_continue_when_blocked") is True
    assert blocked_events[0].get("soft_blocked") is True

    done_events = [event for event in events if isinstance(event, dict) and event.get("type") == "done"]
    assert done_events, "pipeline should still emit done"
    done = done_events[0]
    # soft-block: quality_blocked=False at done level, content preserved
    assert done.get("quality_blocked") is False, "soft-blocked should not flag quality_blocked in done"
    assert done.get("publishable") is True
    assert done.get("soft_blocked") is True
    assert done.get("response") != "", "soft-blocked should preserve markdown response"
    assert isinstance(done.get("report"), dict), "soft-blocked should preserve report"
    assert isinstance(done.get("blocked_report"), dict)
    assert done.get("allow_continue_when_blocked") is True
    assert secret not in caplog.text
    assert memory_secret not in caplog.text
    assert "[execution_service] record chat turn failed" in caplog.text
    assert "[execution_service] persist memory snapshot failed" in caplog.text


def test_resume_graph_pipeline_emits_quality_blocked_and_skips_index(monkeypatch, caplog):
    execution_service = importlib.import_module("backend.services.execution_service")
    report_builder_module = importlib.import_module("backend.graph.report_builder")
    graph_store_module = importlib.import_module("backend.graph.store")

    class _Runner:
        async def resume(self, *, thread_id: str, resume_value):
            yield {
                "event": "on_chain_end",
                "data": {
                    "output": {
                        "thread_id": thread_id,
                        "query": "resume query",
                        "output_mode": "investment_report",
                        "subject": {"subject_type": "company", "tickers": ["AAPL"]},
                        "trace": {},
                        "artifacts": {"draft_markdown": "resume blocked markdown"},
                    }
                },
            }

    monkeypatch.setattr(
        report_builder_module,
        "build_report_payload",
        lambda **kwargs: {
            "report_id": "rpt-block-resume-1",
            "ticker": "AAPL",
            "title": "blocked report resume",
            "summary": "blocked",
            "generated_at": "2026-02-20T00:00:00Z",
            "citations": [],
            "meta": {},
            "report_quality": {
                "state": "block",
                "reasons": [
                    {
                        "code": "GROUNDING_RATE_BELOW_MIN",
                        "severity": "block",
                        "metric": "grounding_rate",
                        "actual": 0.21,
                        "threshold": 0.6,
                        "message": "grounding too low",
                    }
                ],
            },
        },
    )

    indexed: list[dict] = []
    updated_context: list[dict] = []
    secret = "PRIVATE postgres://execution:secret@db/resume-chat"

    def _fail_record_chat_turn(**_kwargs):
        raise RuntimeError(secret)

    memory_secret = "PRIVATE postgres://execution:secret@db/resume-memory"

    def _fail_memory_snapshot(**_kwargs):
        raise RuntimeError(memory_secret)

    monkeypatch.setattr(graph_store_module, "persist_memory_snapshot", _fail_memory_snapshot)

    async def _fake_get_graph_runner():
        return _Runner()

    deps = execution_service.ExecutionDeps(
        get_graph_runner=_fake_get_graph_runner,
        schedule_report_index=lambda **kwargs: indexed.append(kwargs),
        update_session_context=lambda **kwargs: updated_context.append(kwargs),
        record_chat_turn=_fail_record_chat_turn,
        redact_sensitive_payload=lambda payload: payload,
        is_raw_trace_event=lambda payload: False,
        contract_info=lambda: {"chat_response": "chat.response.v1"},
        sse_event_schema_version="chat.sse.v1",
    )

    events = _run(
        _collect_events(
            execution_service.resume_graph_pipeline(
                deps=deps,
                thread_id="tenant:user:thread",
                resume_value="确认执行",
                source="resume_test",
            )
        )
    )

    # soft-block: report exists so it IS indexed
    assert indexed, "soft-blocked reports should be indexed (report content preserved)"
    blocked_events = [event for event in events if isinstance(event, dict) and event.get("type") == "quality_blocked"]
    assert blocked_events, "SSE stream should emit quality_blocked"
    # soft-blocked: publishable=True because content is preserved
    assert blocked_events[0].get("publishable") is True
    assert "GROUNDING_RATE_BELOW_MIN" in (blocked_events[0].get("blocked_reason_codes") or [])
    assert blocked_events[0].get("blocked_report_available") is True
    assert blocked_events[0].get("allow_continue_when_blocked") is True
    assert blocked_events[0].get("soft_blocked") is True

    done_events = [event for event in events if isinstance(event, dict) and event.get("type") == "done"]
    assert done_events, "resume pipeline should still emit done"
    done = done_events[0]
    # soft-block: quality_blocked=False at done level, content preserved
    assert done.get("quality_blocked") is False, "soft-blocked should not flag quality_blocked in done"
    assert done.get("publishable") is True
    assert done.get("soft_blocked") is True
    assert done.get("response") != "", "soft-blocked should preserve markdown response"
    assert isinstance(done.get("report"), dict), "soft-blocked should preserve report"
    assert isinstance(done.get("blocked_report"), dict)
    assert done.get("allow_continue_when_blocked") is True
    assert secret not in caplog.text
    assert memory_secret not in caplog.text
    assert "[resume_pipeline] record chat turn failed" in caplog.text
    assert "[resume_pipeline] persist memory snapshot failed" in caplog.text


def test_resume_graph_pipeline_unhandled_error_is_redacted(caplog):
    execution_service = importlib.import_module("backend.services.execution_service")
    secret = "PRIVATE postgres://execution:secret@db/resume"

    class _FailingRunner:
        async def resume(self, *, thread_id: str, resume_value):
            raise RuntimeError(secret)
            yield

    async def _fake_get_graph_runner():
        return _FailingRunner()

    deps = execution_service.ExecutionDeps(
        get_graph_runner=_fake_get_graph_runner,
        schedule_report_index=lambda **_kwargs: None,
        update_session_context=lambda **_kwargs: None,
        record_chat_turn=None,
        redact_sensitive_payload=lambda payload: payload,
        is_raw_trace_event=lambda _payload: False,
        contract_info=lambda: {},
        sse_event_schema_version="chat.sse.v1",
    )

    events = _run(
        _collect_events(
            execution_service.resume_graph_pipeline(
                deps=deps,
                thread_id="tenant:user:thread",
                resume_value="confirm",
            )
        )
    )

    error_events = [event for event in events if event.get("type") == "error"]
    assert len(error_events) == 1
    assert error_events[0]["schema_version"] == "chat.sse.v1"
    assert error_events[0]["message"] == "Resume execution failed"
    assert secret not in str(events)
    assert secret not in caplog.text
    assert "[resume_pipeline] unhandled" in caplog.text


def test_resume_report_build_error_log_is_redacted(monkeypatch, caplog):
    execution_service = importlib.import_module("backend.services.execution_service")
    report_builder_module = importlib.import_module("backend.graph.report_builder")
    secret = "PRIVATE postgres://execution:secret@db/report"

    class _Runner:
        async def resume(self, *, thread_id: str, resume_value):
            yield {
                "event": "on_chain_end",
                "data": {
                    "output": {
                        "thread_id": thread_id,
                        "query": "resume query",
                        "artifacts": {"draft_markdown": "draft"},
                    }
                },
            }

    async def _fake_get_graph_runner():
        return _Runner()

    def _fail_report(**_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(report_builder_module, "build_report_payload", _fail_report)
    deps = execution_service.ExecutionDeps(
        get_graph_runner=_fake_get_graph_runner,
        schedule_report_index=lambda **_kwargs: None,
        update_session_context=lambda **_kwargs: None,
        record_chat_turn=None,
        redact_sensitive_payload=lambda payload: payload,
        is_raw_trace_event=lambda _payload: False,
        contract_info=lambda: {},
        sse_event_schema_version="chat.sse.v1",
    )

    events = _run(
        _collect_events(
            execution_service.resume_graph_pipeline(
                deps=deps,
                thread_id="tenant:user:thread",
                resume_value="confirm",
            )
        )
    )

    assert any(event.get("type") == "done" for event in events)
    assert secret not in str(events)
    assert secret not in caplog.text
    assert "[resume_pipeline] report build failed" in caplog.text


def test_run_graph_timeout_does_not_log_query(monkeypatch, caplog):
    execution_service = importlib.import_module("backend.services.execution_service")
    runner_module = importlib.import_module("backend.graph.runner")
    secret = "PRIVATE timeout query token"

    async def _slow_run_graph(*_args, **_kwargs):
        await asyncio.sleep(0.05)
        return {}

    async def _fake_get_graph_runner():
        return object()

    monkeypatch.setattr(runner_module, "run_graph_traced", _slow_run_graph)
    monkeypatch.setattr(execution_service, "_execution_timeout_seconds", lambda _mode: 0.001)
    deps = execution_service.ExecutionDeps(
        get_graph_runner=_fake_get_graph_runner,
        schedule_report_index=lambda **_kwargs: None,
        update_session_context=lambda **_kwargs: None,
        record_chat_turn=None,
        redact_sensitive_payload=lambda payload: payload,
        is_raw_trace_event=lambda _payload: False,
        contract_info=lambda: {},
        sse_event_schema_version="chat.sse.v1",
    )

    events = _run(
        _collect_events(
            execution_service.run_graph_pipeline(
                deps=deps,
                query=secret,
                thread_id="tenant:user:thread",
            )
        )
    )

    assert any(event.get("type") == "error" for event in events)
    assert secret not in caplog.text
    assert "[execution_service] graph timeout" in caplog.text
    assert "query_chars=" not in caplog.text


def _hang_deps(execution_service):
    async def _hang_get_graph_runner():
        await asyncio.sleep(3600)
        return object()

    return execution_service.ExecutionDeps(
        get_graph_runner=_hang_get_graph_runner,
        schedule_report_index=lambda **_kwargs: None,
        update_session_context=lambda **_kwargs: None,
        record_chat_turn=None,
        redact_sensitive_payload=lambda payload: payload,
        is_raw_trace_event=lambda _payload: False,
        contract_info=lambda: {},
        sse_event_schema_version="chat.sse.v1",
    )


def test_r96_trace_events_do_not_cross_sessions(monkeypatch):
    """TraceEmitter 是进程级单例：两个并发 run 各自 add_listener，
    监听器在发射方上下文同步执行——A 的 agent_start（metadata 带 A 的
    query）会同步投递到 B 的 SSE 队列并盖章 B 的 session_id，前端
    Console 显示别家会话的查询文本（跨会话泄漏）。监听器必须按
    发射方 run 的 thread_id 过滤。"""
    import asyncio

    from backend.orchestration.trace_emitter import get_trace_emitter

    execution_service = importlib.import_module("backend.services.execution_service")
    runner_module = importlib.import_module("backend.graph.runner")

    async def _main():
        started = asyncio.Event()
        release = asyncio.Event()
        a_emitted = asyncio.Event()

        async def _fake_run_graph_traced(_runner, *, thread_id, query, **_kw):
            if thread_id == "sess-A":
                started.set()
                # 在 run 中段发射（后续仍挂 release）——call_soon_threadsafe 的
                # put_nowait 有机会先于 _END 落队，保证自身事件可达。
                get_trace_emitter().emit_agent_start("NewsAgent", query="QUERY_OF_sess-A")
                await release.wait()
                a_emitted.set()
            else:
                await started.wait()
                get_trace_emitter().emit_agent_start("MacroAgent", query="QUERY_OF_sess-B")
                release.set()
                await a_emitted.wait()
            return {"artifacts": {"draft_markdown": ""}, "trace": {}}

        monkeypatch.setattr(runner_module, "run_graph_traced", _fake_run_graph_traced)

        async def _fake_get_graph_runner():
            return object()

        deps = execution_service.ExecutionDeps(
            get_graph_runner=_fake_get_graph_runner,
            schedule_report_index=lambda **_kw: None,
            update_session_context=lambda **_kw: None,
            record_chat_turn=None,
            redact_sensitive_payload=lambda payload: payload,
            is_raw_trace_event=lambda _payload: False,  # 全放行，只考验会话隔离
            contract_info=lambda: {},
            sse_event_schema_version="chat.sse.v1",
        )

        events_a, events_b = await asyncio.gather(
            _collect_events(
                execution_service.run_graph_pipeline(
                    deps=deps, query="q-a", thread_id="sess-A"
                )
            ),
            _collect_events(
                execution_service.run_graph_pipeline(
                    deps=deps, query="q-b", thread_id="sess-B"
                )
            ),
        )
        return events_a, events_b

    events_a, events_b = _run(_main())

    a_agent = [e.get("query") for e in events_a if e.get("type") == "agent_start"]
    b_agent = [e.get("query") for e in events_b if e.get("type") == "agent_start"]
    # buggy: A 的队列里混进 QUERY_OF_sess-B（盖 A 的章），反之亦然
    assert a_agent == ["QUERY_OF_sess-A"], f"session A leaked/foreign events: {a_agent}"
    assert b_agent == ["QUERY_OF_sess-B"], f"session B leaked/foreign events: {b_agent}"


def test_run_graph_pipeline_aclose_does_not_leak_cancelled_error():
    """客户端中途断开 → 消费者 aclose() → finally 取消并 await producer。
    asyncio.CancelledError 是 BaseException，`except Exception` 捕不到，
    会把 CancelledError 抛给 aclose() 的调用方。"""
    execution_service = importlib.import_module("backend.services.execution_service")
    deps = _hang_deps(execution_service)

    async def _consume_then_close():
        agen = execution_service.run_graph_pipeline(
            deps=deps, query="q", thread_id="tenant:user:thread"
        )
        first = await agen.__anext__()  # langgraph_start 事件
        assert isinstance(first, dict)
        # producer 仍挂在 get_graph_runner；aclose 走 finally 的取消路径
        await agen.aclose()

    _run(_consume_then_close())  # buggy: asyncio.CancelledError 泄漏


def test_resume_graph_pipeline_aclose_does_not_leak_cancelled_error():
    """resume 路径同样存在 finally cancel+await 的死代码缺陷。"""
    execution_service = importlib.import_module("backend.services.execution_service")
    deps = _hang_deps(execution_service)

    async def _consume_then_close():
        agen = execution_service.resume_graph_pipeline(
            deps=deps, thread_id="tenant:user:thread", resume_value="confirm"
        )
        first = await agen.__anext__()  # resume_start 事件
        assert isinstance(first, dict)
        await agen.aclose()

    _run(_consume_then_close())  # buggy: asyncio.CancelledError 泄漏
