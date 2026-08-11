"""Session-context helpers extracted from api/main.py.

Keeps session/reference-context bookkeeping and its in-process state out
of the FastAPI entrypoint so api.main stays focused on app wiring.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from threading import Lock
from typing import Any, Dict, List, Optional
from uuid import uuid4

from backend.api.schemas import ChatRequest
from backend.api.security_config import env_int as _env_int
from backend.contracts import contract_manifest
from backend.conversation.context import ContextManager
from backend.orchestration.tools_bridge import get_global_orchestrator
from backend.services.report_index import get_report_index_store

logger = logging.getLogger("backend.api.main")

_reference_contexts: Dict[str, ContextManager] = {}
_reference_context_last_access: Dict[str, float] = {}
_reference_lock = Lock()
_SESSION_PART_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_ESSENTIAL_SSE_TYPES = {
    "token",
    "done",
    "error",
    # Execution visibility essentials (kept even when trace_raw is OFF)
    "plan_ready",
    "pipeline_stage",
    "step_start",
    "step_done",
    "step_error",
    "agent_start",
    "agent_done",
    "agent_error",
    "decision_note",
}


def _normalize_session_key(session_id: Optional[str]) -> str:
    raw = (session_id or "").strip()
    if not raw:
        return f"public:anonymous:{uuid4()}"

    parts = raw.split(":")
    if len(parts) == 1:
        parts = ["public", "anonymous", parts[0]]
    elif len(parts) == 2:
        parts = ["public", parts[0], parts[1]]
    elif len(parts) != 3:
        raise ValueError("session_id format invalid, expected tenant:user:thread")

    normalized: list[str] = []
    for idx, part in enumerate(parts):
        text = (part or "").strip()
        if not text:
            raise ValueError("session_id contains empty segment")
        if not _SESSION_PART_PATTERN.fullmatch(text):
            raise ValueError(f"session_id segment[{idx}] contains illegal chars")
        normalized.append(text)
    return ":".join(normalized)


def _build_trace_digest(state: dict[str, Any] | None) -> dict[str, Any]:
    payload = state if isinstance(state, dict) else {}
    trace = payload.get("trace") if isinstance(payload.get("trace"), dict) else {}
    spans = trace.get("spans") if isinstance(trace.get("spans"), list) else []
    first_nodes: list[str] = []
    for span in spans[:10]:
        if not isinstance(span, dict):
            continue
        node = span.get("node")
        if isinstance(node, str) and node:
            first_nodes.append(node)
    return {
        "output_mode": payload.get("output_mode"),
        "subject": payload.get("subject"),
        "span_count": len(spans),
        "first_nodes": first_nodes,
    }


def _index_report_async(*, session_id: str, report: dict[str, Any], state: dict[str, Any] | None) -> None:
    try:
        store = get_report_index_store()
        store.upsert_report(
            session_id=session_id,
            report=report,
            trace_digest=_build_trace_digest(state),
        )
    except Exception as exc:
        logger.error("report index async upsert failed")


def _schedule_report_index(*, session_id: str, report: dict[str, Any], state: dict[str, Any] | None) -> None:
    if not (isinstance(report, dict) and report.get("report_id")):
        return
    try:
        import asyncio as _asyncio

        _asyncio.get_running_loop().run_in_executor(
            None,
            lambda: _index_report_async(session_id=session_id, report=report, state=state),
        )
    except Exception as exc:
        logger.error("schedule async report indexing failed")


def _is_raw_trace_event(payload: dict[str, Any]) -> bool:
    event_type = str(payload.get("type") or "").strip().lower()
    if not event_type:
        return True
    return event_type not in _ESSENTIAL_SSE_TYPES


def _resolve_thread_id(session_id: Optional[str]) -> str:
    return _normalize_session_key(session_id)


def _cleanup_session_contexts(now_ts: Optional[float] = None) -> None:
    now = now_ts if now_ts is not None else time.time()
    ttl_minutes = max(1, _env_int("SESSION_CONTEXT_TTL_MINUTES", 240))
    ttl_seconds = ttl_minutes * 60
    max_threads = max(16, _env_int("SESSION_CONTEXT_MAX_THREADS", 1000))

    expired = [
        sid
        for sid, last_access in list(_reference_context_last_access.items())
        if now - float(last_access) >= ttl_seconds
    ]
    for sid in expired:
        _reference_contexts.pop(sid, None)
        _reference_context_last_access.pop(sid, None)

    current_size = len(_reference_contexts)
    if current_size <= max_threads:
        return

    overflow = current_size - max_threads
    oldest_first = sorted(
        _reference_context_last_access.items(),
        key=lambda item: item[1],
    )
    for sid, _ in oldest_first[:overflow]:
        _reference_contexts.pop(sid, None)
        _reference_context_last_access.pop(sid, None)


def _get_session_context(session_id: str) -> ContextManager:
    with _reference_lock:
        now = time.time()
        _cleanup_session_contexts(now)
        manager = _reference_contexts.get(session_id)
        if manager is None:
            manager = ContextManager(max_turns=20)
            _reference_contexts[session_id] = manager
        _reference_context_last_access[session_id] = now
        return manager


def _resolve_query_reference(query: str, thread_id: str) -> str:
    try:
        return _get_session_context(thread_id).resolve_reference(query)
    except Exception:
        return query


def _update_session_context(
    *,
    thread_id: str,
    original_query: str,
    response_markdown: str,
    subject: Optional[Dict[str, Any]] = None,
    skip_context: bool = False,
) -> None:
    if not thread_id:
        return
    # 指令型操作（�?alert_set）不应污染对话上下文
    if skip_context:
        return
    try:
        tickers = []
        if isinstance(subject, dict):
            tickers = [str(t).strip().upper() for t in (subject.get("tickers") or []) if str(t).strip()]
        metadata: Dict[str, Any] = {}
        if tickers:
            metadata["tickers"] = tickers
        _get_session_context(thread_id).add_turn(
            query=original_query,
            intent="chat",
            response=response_markdown or "",
            metadata=metadata,
        )
    except Exception as exc:
        logger.error("failed to update session context")


def _build_ui_context(request: ChatRequest) -> Dict[str, Any]:
    ui_context: Dict[str, Any] = {}
    if not request.context:
        return ui_context
    if request.context.active_symbol:
        ui_context["active_symbol"] = request.context.active_symbol
    if request.context.view:
        ui_context["view"] = request.context.view

    selections: List[Dict[str, Any]] = []
    if request.context.selection:
        selections.append(request.context.selection.model_dump())
    if getattr(request.context, "selections", None):
        selections.extend([s.model_dump() for s in (request.context.selections or []) if s])
    if selections:
        ui_context["selections"] = selections
    if request.context.user_email:
        ui_context["user_email"] = request.context.user_email
    if getattr(request.context, "persona_id", None):
        ui_context["persona_id"] = request.context.persona_id
    return ui_context


def _contract_info() -> Dict[str, str]:
    return contract_manifest()


def _get_orchestrator_safe():
    try:
        return get_global_orchestrator()
    except Exception as exc:
        logger.error("failed to initialize orchestrator")
        return None
