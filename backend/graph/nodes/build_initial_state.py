# -*- coding: utf-8 -*-
from __future__ import annotations

from langchain_core.messages import HumanMessage

from backend.contracts import GRAPH_STATE_SCHEMA_VERSION, TRACE_SCHEMA_VERSION
from backend.graph.confirmation_policy import parse_confirmation_mode
from backend.graph.store import load_memory_context
from backend.graph.state import GraphState
from backend.personas import get_persona


def _resolve_persona_id(state: GraphState) -> str | None:
    """Read persona_id from (in order of precedence):
       1) explicit state.persona_id (e.g. set by other nodes / tests)
       2) ui_context.persona_id   (the canonical entry from chat_router)

    Returns the trimmed string, or None when absent / blank.
    """
    explicit = state.get("persona_id")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    ui_ctx = state.get("ui_context") or {}
    if isinstance(ui_ctx, dict):
        candidate = ui_ctx.get("persona_id")
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def build_initial_state(state: GraphState) -> dict:
    """
    Ensure required fields exist and append the user message.

    The runner should provide at least: thread_id, query, ui_context (optional).
    """
    query = (state.get("query") or "").strip()
    updates: dict = {}

    trace = state.get("trace") or {}
    trace.setdefault("schema_version", TRACE_SCHEMA_VERSION)
    trace.setdefault("routing_chain", ["langgraph"])
    updates["trace"] = trace
    updates["schema_version"] = GRAPH_STATE_SCHEMA_VERSION

    thread_id = str(state.get("thread_id") or "").strip() or "default"
    if not state.get("thread_id"):
        updates["thread_id"] = thread_id

    memory_context = load_memory_context(thread_id=thread_id)
    if memory_context:
        updates["memory_context"] = memory_context

    confirmation_mode = parse_confirmation_mode(state.get("confirmation_mode"))
    if confirmation_mode is not None:
        updates["confirmation_mode"] = confirmation_mode

    # --- Persona resolution ----------------------------------------------------
    # Always populate persona_id + persona_config so downstream nodes (policy_gate,
    # synthesize, report_builder) can rely on their presence. Missing / unknown
    # ids gracefully fall back to "neutral" (= current behavior).
    persona = get_persona(_resolve_persona_id(state))
    updates["persona_id"] = persona.id
    updates["persona_config"] = persona.model_dump()
    trace.setdefault("persona", {"id": persona.id, "display_name": persona.display_name_zh})

    if query:
        updates["messages"] = [HumanMessage(content=query)]
    else:
        # No-op; Clarify node may interrupt with a prompt.
        updates["messages"] = []

    return updates
