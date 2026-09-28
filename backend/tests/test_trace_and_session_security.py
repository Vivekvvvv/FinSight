# -*- coding: utf-8 -*-
import importlib

import pytest
from fastapi.testclient import TestClient

from backend.api.schemas import ChatOptions, ChatRequest


def _load_main_module():
    import backend.api.main as main

    importlib.reload(main)
    return main


def test_session_id_normalization_rules():
    main = _load_main_module()

    assert main._resolve_thread_id("thread-001") == "public:anonymous:thread-001"
    assert main._resolve_thread_id("user1:thread-001") == "public:user1:thread-001"
    assert main._resolve_thread_id("tenant1:user1:thread-001") == "tenant1:user1:thread-001"


def test_session_id_rejects_invalid_format():
    main = _load_main_module()

    with pytest.raises(ValueError):
        main._resolve_thread_id("tenant:user:thread:extra")

    with pytest.raises(ValueError):
        main._resolve_thread_id("tenant:user:")

    with pytest.raises(ValueError):
        main._resolve_thread_id("tenant:user:bad/slash")


def test_trace_raw_override_priority(monkeypatch):
    main = _load_main_module()

    req = ChatRequest(query="hello")
    monkeypatch.setenv("TRACE_RAW_ENABLED", "false")
    assert main._resolve_trace_raw_enabled(req) is False

    req_on = ChatRequest(query="hello", options=ChatOptions(trace_raw_override="on"))
    assert main._resolve_trace_raw_enabled(req_on) is True

    req_off = ChatRequest(query="hello", options=ChatOptions(trace_raw_override="off"))
    monkeypatch.setenv("TRACE_RAW_ENABLED", "true")
    assert main._resolve_trace_raw_enabled(req_off) is False


def test_is_raw_trace_event_keeps_execution_progress_events():
    main = _load_main_module()

    assert main._is_raw_trace_event({"type": "pipeline_stage"}) is False
    assert main._is_raw_trace_event({"type": "plan_ready"}) is False
    assert main._is_raw_trace_event({"type": "decision_note"}) is False
    assert main._is_raw_trace_event({"type": "step_start"}) is False


def test_is_raw_trace_event_filters_verbose_events():
    main = _load_main_module()

    assert main._is_raw_trace_event({"type": "tool_start"}) is True
    assert main._is_raw_trace_event({"type": "llm_start"}) is True
    assert main._is_raw_trace_event({"type": "cache_hit"}) is True


def test_redact_sensitive_payload_masks_values():
    main = _load_main_module()

    payload = {
        "api_key": "sk-very-secret-12345678",
        "authorization": "Bearer abcdefghijklmnop",
        "nested": {"token": "tok_abcdefghijklmn", "normal": "safe"},
        "text": "authorization: bearer sk-secret-example-123456",
    }

    redacted = main._redact_sensitive_payload(payload)
    as_text = str(redacted).lower()

    assert "very-secret" not in as_text
    assert "abcdefghijklmnop" not in as_text
    assert "tok_abcdefghijklmn" not in as_text
    assert redacted["nested"]["normal"] == "safe"


def test_chat_endpoint_rejects_illegal_session_id():
    main = _load_main_module()
    with TestClient(main.app) as client:
        resp = client.post(
            "/chat/supervisor",
            json={"query": "分析影响", "session_id": "tenant:user:bad/slash"},
        )

    assert resp.status_code == 422
    detail = resp.json().get("detail") or ""
    assert "session_id" in str(detail)


def test_session_context_isolation_blocks_cross_session_reference(monkeypatch):
    main = _load_main_module()
    monkeypatch.setattr(main, "agent", None, raising=False)
    main._reference_contexts.clear()

    session_a = "tenant-a:user-a:thread-a"
    session_b = "tenant-a:user-a:thread-b"

    main._update_session_context(
        thread_id=session_a,
        original_query="苹果怎么样",
        response_markdown="AAPL 基本面改善",
        subject={"tickers": ["AAPL"]},
    )

    resolved_a = main._resolve_query_reference("它的估值如何", session_a)
    resolved_b = main._resolve_query_reference("它的估值如何", session_b)

    assert "AAPL" in resolved_a
    assert resolved_b == "它的估值如何"


def test_session_context_ttl_survives_wall_clock_jump(monkeypatch):
    """TTL 驱逐用 time.time() 测区间：系统时钟前跳（w32time 大步进/手动
    改时/VM 恢复快照）把 now-last_access 瞬间推过 ttl_seconds——所有
    活跃会话的 ContextManager 被一次清空，resolve_reference 指代链全断
    （"它"→解析不回 ticker，追问上下文静默丢失）；后跳则上下文永久驻留。
    区间计时必须用单调钟（同 23310e7/389d176 修复类）。"""
    main = _load_main_module()
    session_context_module = importlib.import_module("backend.api.session_context")
    wall = {"t": 1_000_000.0}
    monkeypatch.setattr(session_context_module.time, "time", lambda: wall["t"])
    monkeypatch.setattr(main, "agent", None, raising=False)
    main._reference_contexts.clear()
    main._reference_context_last_access.clear()

    main._update_session_context(
        thread_id="tenant-a:user-a:thread-a",
        original_query="苹果怎么样",
        response_markdown="AAPL 基本面改善",
        subject={"tickers": ["AAPL"]},
    )

    wall["t"] += 3600.0 * 10  # 时钟前跳 10h——远超 TTL 但真实经过 ~0s

    resolved = main._resolve_query_reference("它的估值如何", "tenant-a:user-a:thread-a")
    assert "AAPL" in resolved


def test_rag_collection_name_uses_session_key_shape():
    exec_node = importlib.import_module('backend.graph.nodes.execute_plan_stub')

    assert exec_node._collection_from_thread_id("tenant1:user1:thread-1") == "session:tenant1:user1:thread-1"
    assert exec_node._collection_from_thread_id("tenant 1:user/1:thread@1") == "session:tenant_1:user_1:thread_1"
    assert exec_node._collection_from_thread_id("just-thread") == "session:just-thread"
