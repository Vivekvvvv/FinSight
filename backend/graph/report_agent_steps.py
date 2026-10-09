# -*- coding: utf-8 -*-
"""Agent-step status/summary helpers extracted from report_builder.py."""
from __future__ import annotations

from typing import Any

from backend.graph.report_text_tools import (
    _env_int,
    _safe_str,
    _sanitize_deep_search_summary,
    _to_json_compatible,
)
from backend.graph.report_citations import (
    _safe_confidence,
)

_AGENT_TITLE_MAP: dict[str, str] = {
    "price_agent": "价格分析",
    "news_agent": "新闻分析",
    "technical_agent": "技术分析",
    "fundamental_agent": "基本面分析",
    "macro_agent": "宏观分析",
    "deep_search_agent": "深度搜索",
}


def _agent_status_from_steps(
    *,
    allowed_agents: list[str],
    plan_steps: list[dict[str, Any]],
    step_results: dict[str, Any],
    errors: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    status: dict[str, dict[str, Any]] = {}
    steps_by_agent: dict[str, str] = {}
    for step in plan_steps:
        if not isinstance(step, dict):
            continue
        if step.get("kind") != "agent":
            continue
        name = step.get("name")
        step_id = step.get("id")
        if isinstance(name, str) and isinstance(step_id, str) and name.strip() and step_id.strip():
            steps_by_agent[name.strip()] = step_id.strip()

    errors_by_step: dict[str, str] = {}
    for err in errors:
        if not isinstance(err, dict):
            continue
        sid = err.get("step_id")
        msg = err.get("error")
        if isinstance(sid, str) and sid and isinstance(msg, str) and msg:
            errors_by_step[sid] = msg

    for agent_name in allowed_agents:
        step_id = steps_by_agent.get(agent_name)
        if not step_id:
            status[agent_name] = {"status": "not_run", "confidence": 0.0}
            continue

        if step_id in errors_by_step:
            status[agent_name] = {"status": "error", "confidence": 0.0, "error": errors_by_step[step_id]}
            continue

        raw = step_results.get(step_id) if isinstance(step_results, dict) else None
        output = raw.get("output") if isinstance(raw, dict) else None
        if isinstance(output, dict) and output.get("skipped") is True:
            reason = _safe_str(output.get("reason") or "skipped") or "skipped"
            skipped_payload: dict[str, Any] = {
                "status": "not_run",
                "confidence": 0.0,
                "skipped_reason": reason,
                "escalation_not_needed": reason == "escalation_not_needed",
            }
            evidence_quality = output.get("evidence_quality")
            if isinstance(evidence_quality, dict):
                skipped_payload["evidence_quality"] = evidence_quality
            status[agent_name] = skipped_payload
            continue

        confidence = output.get("confidence") if isinstance(output, dict) else None
        conf = _safe_confidence(confidence, default=0.6)

        success_payload: dict[str, Any] = {"status": "success", "confidence": max(0.0, min(1.0, conf))}
        if isinstance(output, dict):
            evidence_quality = output.get("evidence_quality")
            if isinstance(evidence_quality, dict):
                success_payload["evidence_quality"] = evidence_quality
            data_sources = output.get("data_sources")
            if isinstance(data_sources, list):
                success_payload["data_sources"] = [str(x) for x in data_sources if str(x).strip()][:8]
            # P0-3d: structured fallback diagnostics
            if output.get("fallback_used"):
                success_payload["status"] = "fallback"
                success_payload["fallback_reason"] = output.get("fallback_reason")
                success_payload["retryable"] = bool(output.get("retryable", False))
                success_payload["error_stage"] = output.get("error_stage")
            # Conflict tracking
            conflict_flags = output.get("conflict_flags")
            if isinstance(conflict_flags, list) and conflict_flags:
                success_payload["conflict_flags"] = [str(f) for f in conflict_flags[:10]]
                success_payload["has_conflicts"] = True
        status[agent_name] = success_payload

    return status


def _agent_summaries_from_steps(
    *,
    allowed_agents: list[str],
    plan_steps: list[dict[str, Any]],
    step_results: dict[str, Any],
    errors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    steps_by_agent: dict[str, str] = {}
    for step in plan_steps:
        if not isinstance(step, dict):
            continue
        if step.get("kind") != "agent":
            continue
        name = step.get("name")
        step_id = step.get("id")
        if isinstance(name, str) and isinstance(step_id, str) and name.strip() and step_id.strip():
            steps_by_agent[name.strip()] = step_id.strip()

    errors_by_step: dict[str, str] = {}
    for err in errors:
        if not isinstance(err, dict):
            continue
        sid = err.get("step_id")
        msg = err.get("error")
        if isinstance(sid, str) and sid and isinstance(msg, str) and msg:
            errors_by_step[sid] = msg

    summaries: list[dict[str, Any]] = []
    order = 1
    for agent_name in allowed_agents:
        step_id = steps_by_agent.get(agent_name)
        title = _AGENT_TITLE_MAP.get(agent_name, agent_name)
        if not step_id:
            summaries.append(
                {
                    "title": title,
                    "order": order,
                    "agent_name": agent_name,
                    "status": "not_run",
                    "summary": "未运行（本轮未触发或无匹配意图）",
                    "confidence": 0.0,
                    "data_sources": [],
                    "raw_output": {},
                    "evidence_full": [],
                    "trace_full": [],
                }
            )
            order += 1
            continue

        if step_id in errors_by_step:
            summaries.append(
                {
                    "title": title,
                    "order": order,
                    "agent_name": agent_name,
                    "status": "error",
                    "error": True,
                    "error_message": errors_by_step[step_id],
                    "summary": f"⚠️ 执行失败：{errors_by_step[step_id]}",
                    "confidence": 0.0,
                    "data_sources": [],
                    "raw_output": {"error": errors_by_step[step_id], "step_id": step_id},
                    "evidence_full": [],
                    "trace_full": [],
                }
            )
            order += 1
            continue

        raw = step_results.get(step_id) if isinstance(step_results, dict) else None
        output = raw.get("output") if isinstance(raw, dict) else None
        if isinstance(output, dict) and output.get("skipped") is True:
            reason = _safe_str(output.get("reason") or "skipped") or "skipped"
            summary_text = "Not run."
            if reason == "dry_run":
                summary_text = "Not run (dry_run)."
            elif reason == "escalation_not_needed":
                summary_text = "Not run (escalation not needed)."
            elif reason:
                summary_text = f"Not run ({reason})."
            summaries.append(
                {
                    "title": title,
                    "order": order,
                    "agent_name": agent_name,
                    "status": "not_run",
                    "summary": summary_text,
                    "confidence": 0.0,
                    "data_sources": [],
                    "skipped_reason": reason,
                    "escalation_not_needed": reason == "escalation_not_needed",
                    "raw_output": _to_json_compatible(output),
                    "evidence_full": [],
                    "trace_full": _to_json_compatible(output.get("trace")) if isinstance(output.get("trace"), list) else [],
                }
            )
            order += 1
            continue

        summary_max_chars = max(4000, _env_int("REPORT_AGENT_SUMMARY_MAX_CHARS", 12000))
        summary = _safe_str(output.get("summary") if isinstance(output, dict) else "")[:summary_max_chars]
        summary = _sanitize_deep_search_summary(summary, agent_name)
        confidence = output.get("confidence") if isinstance(output, dict) else None
        confidence_value = _safe_confidence(confidence, default=0.6)
        data_sources = output.get("data_sources") if isinstance(output, dict) else None
        if not isinstance(data_sources, list):
            data_sources = []
        raw_output = _to_json_compatible(output if isinstance(output, dict) else {"output": output})
        evidence_full = []
        if isinstance(output, dict) and isinstance(output.get("evidence"), list):
            evidence_full = _to_json_compatible(output.get("evidence"))
        trace_full = []
        if isinstance(output, dict) and isinstance(output.get("trace"), list):
            trace_full = _to_json_compatible(output.get("trace"))

        summaries.append(
            {
                "title": title,
                "order": order,
                "agent_name": agent_name,
                "status": "success",
                "summary": summary or "（无输出）",
                "confidence": max(0.0, min(1.0, confidence_value)),
                "data_sources": [str(x) for x in data_sources if str(x).strip()][:8],
                "evidence_quality": (output.get("evidence_quality") if isinstance(output, dict) and isinstance(output.get("evidence_quality"), dict) else {}),
                "raw_output": raw_output,
                "evidence_full": evidence_full if isinstance(evidence_full, list) else [],
                "trace_full": trace_full if isinstance(trace_full, list) else [],
            }
        )
        order += 1

    return summaries
