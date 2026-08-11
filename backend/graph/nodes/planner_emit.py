"""Planner step-summary and pipeline-event helpers extracted from planner.py."""

import time
from typing import Any

from backend.graph.capability_registry import REPORT_AGENT_CANDIDATES
from backend.graph.event_bus import emit_event
from backend.graph.failure import utc_now_iso
from backend.graph.state import GraphState


def _dedupe_agent_names(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in items:
        name = str(raw or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    return ordered


def _extract_selected_agents(plan_dict: dict[str, Any]) -> list[str]:
    steps = plan_dict.get("steps")
    if not isinstance(steps, list):
        return []
    names: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        if str(step.get("kind") or "") != "agent":
            continue
        name = str(step.get("name") or "").strip()
        if name:
            names.append(name)
    return _dedupe_agent_names(names)


def _candidate_agents_for_plan(state: GraphState) -> list[str]:
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    allowed = policy.get("allowed_agents") if isinstance(policy, dict) else None
    if isinstance(allowed, list):
        candidates = [str(item or "").strip() for item in allowed]
        deduped = _dedupe_agent_names(candidates)
        if deduped:
            return deduped
    return list(REPORT_AGENT_CANDIDATES)


def _build_plan_steps_summary(plan_dict: dict[str, Any]) -> list[dict[str, Any]]:
    raw_steps = plan_dict.get("steps")
    if not isinstance(raw_steps, list):
        return []
    summary: list[dict[str, Any]] = []
    for step in raw_steps[:24]:
        if not isinstance(step, dict):
            continue
        summary.append(
            {
                "id": str(step.get("id") or "").strip() or "unknown",
                "kind": str(step.get("kind") or "").strip() or "unknown",
                "name": str(step.get("name") or "").strip() or "unknown",
                "parallel_group": (
                    str(step.get("parallel_group") or "").strip()
                    if step.get("parallel_group") is not None
                    else None
                ),
                "optional": bool(step.get("optional")),
            }
        )
    return summary


def _build_planner_reasoning_brief(
    *,
    state: GraphState,
    selected_agents: list[str],
    skipped_agents: list[str],
    plan_steps_count: int,
    fallback: bool,
    fallback_reason: str | None = None,
) -> str:
    output_mode = str(state.get("output_mode") or "brief").strip() or "brief"
    ui_context = state.get("ui_context") if isinstance(state.get("ui_context"), dict) else {}
    source = str((ui_context or {}).get("source") or "").strip() or "unknown"
    selected_preview = ", ".join(selected_agents[:5]) if selected_agents else "none"
    skipped_preview = ", ".join(skipped_agents[:5]) if skipped_agents else "none"
    if fallback:
        reason = str(fallback_reason or "planner_fallback").strip()
        return (
            f"Planner fallback mode ({reason}); output_mode={output_mode}; source={source}; "
            f"selected={selected_preview}; skipped={skipped_preview}; steps={plan_steps_count}."
        )
    return (
        f"Planner completed; output_mode={output_mode}; source={source}; "
        f"selected={selected_preview}; skipped={skipped_preview}; steps={plan_steps_count}."
    )


async def _emit_pipeline_stage(
    *,
    stage: str,
    status: str,
    message: str,
    duration_ms: int | None = None,
    error: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "type": "pipeline_stage",
        "stage": stage,
        "status": status,
        "message": message,
        "timestamp": utc_now_iso(),
    }
    if isinstance(duration_ms, int) and duration_ms >= 0:
        payload["duration_ms"] = duration_ms
    if error:
        payload["error"] = str(error)[:300]
    await emit_event(payload)


async def _emit_plan_ready(
    *,
    state: GraphState,
    plan_dict: dict[str, Any],
    fallback: bool,
    fallback_reason: str | None = None,
) -> None:
    selected_agents = _extract_selected_agents(plan_dict)
    candidate_agents = _candidate_agents_for_plan(state)
    selected_set = set(selected_agents)
    skipped_agents = [name for name in candidate_agents if name not in selected_set]
    reasoning_brief = _build_planner_reasoning_brief(
        state=state,
        selected_agents=selected_agents,
        skipped_agents=skipped_agents,
        plan_steps_count=len(plan_dict.get("steps") or []),
        fallback=fallback,
        fallback_reason=fallback_reason,
    )
    plan_steps = _build_plan_steps_summary(plan_dict)
    has_parallel = any(step.get("parallel_group") for step in plan_steps)
    await emit_event(
        {
            "type": "plan_ready",
            "plan_steps": plan_steps,
            "plan_steps_count": len(plan_steps),
            "agents": selected_agents,
            "selected_agents": selected_agents,
            "skipped_agents": skipped_agents,
            "has_parallel": has_parallel,
            "reasoning_brief": reasoning_brief,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    )
    await emit_event(
        {
            "type": "decision_note",
            "scope": "planner",
            "title": "Planner selection summary",
            "reason": reasoning_brief,
            "impact": (
                f"selected_agents={len(selected_agents)}; skipped_agents={len(skipped_agents)}; "
                f"parallel={'yes' if has_parallel else 'no'}"
            ),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    )
