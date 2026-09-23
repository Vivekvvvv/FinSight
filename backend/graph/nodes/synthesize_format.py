# -*- coding: utf-8 -*-
"""Formatting and section helpers extracted from synthesize.py (round 17)."""

from __future__ import annotations

import os
import re
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from backend.graph.json_utils import json_dumps_safe
from backend.graph.state import GraphState
from backend.utils.strict_json import json_loads_strict



# Maximum messages to include in synthesize prompt context
_MAX_SYNTH_HISTORY_MESSAGES = 8


def _format_persona_lens(state: GraphState) -> str:
    """Build the <persona_lens> prompt block for narrative synthesis.

    Reads `state.persona_config` (set by build_initial_state). When persona is
    neutral / lens is empty, returns "" so the prompt remains identical to
    pre-Persona behavior (full backward compatibility).

    Honesty-first: the injected block explicitly tells the LLM that data
    truth must override stylistic consistency.
    """
    persona = state.get("persona_config") or {}
    if not isinstance(persona, dict):
        return ""
    lens = str(persona.get("synthesis_lens") or "").strip()
    if not lens:
        return ""

    name_zh = str(persona.get("display_name_zh") or "").strip() or "中立分析师"
    emoji = str(persona.get("emoji") or "").strip()
    risk_tolerance = str(persona.get("risk_tolerance") or "medium")

    header = f"{emoji} {name_zh}".strip()

    return (
        "<persona_lens>\n"
        f"你正在以 **{header}** 的视角合成研究结论。\n"
        f"风险偏好基线: {risk_tolerance}\n\n"
        "视角准则：\n"
        f"{lens}\n\n"
        "⚠️ 关键约束：\n"
        "- 诚实优先级 > 风格一致性。若证据明显与该视角偏好矛盾，必须如实指出，不得为风格强行裁剪。\n"
        "- 仍须遵守原有的<constraints>（闭卷原则、数据缺失标注、不构成投资建议等）。\n"
        f"- 在结论末尾用一行标明：「以 {header} 视角」。\n"
        "</persona_lens>\n\n"
    )


def _format_conversation_history_for_synth(state: GraphState) -> str:
    """
    Extract recent conversation history from state messages for synthesize context.
    Shorter than planner's version — only includes enough for pronoun resolution.
    """
    messages = state.get("messages") or []
    if not messages:
        return ""

    current_query = (state.get("query") or "").strip()
    history_msgs = []

    for idx, msg in enumerate(messages):
        if isinstance(msg, HumanMessage):
            content = msg.content.strip() if isinstance(msg.content, str) else str(msg.content).strip()
            # Skip the current query——必须用 enumerate 的位置 idx；旧代码
            # messages.index(msg) 对重复提问（两条内容相同的 HumanMessage）
            # 永远返回第一条的下标，最后那条（当前 query）会误判"后面还有
            # 同名消息"而不被跳过，query 被重复塞进 <conversation_history>。
            if content == current_query and not any(
                isinstance(m, HumanMessage) and
                (m.content.strip() if isinstance(m.content, str) else str(m.content).strip()) == current_query
                for m in messages[idx + 1:]
                if isinstance(m, HumanMessage)
            ):
                continue
            history_msgs.append(f"[user]: {content}")
        elif isinstance(msg, AIMessage):
            content = msg.content.strip() if isinstance(msg.content, str) else str(msg.content).strip()
            if content and len(content) > 200:
                content = content[:200] + "..."
            if content:
                history_msgs.append(f"[assistant]: {content}")

    if not history_msgs:
        return ""

    recent = history_msgs[-_MAX_SYNTH_HISTORY_MESSAGES:]
    return (
        "<conversation_history>\n"
        + "\n".join(recent)
        + "\n</conversation_history>\n"
    )


def _format_memory_context_for_synth(state: GraphState) -> str:
    memory_context = state.get("memory_context")
    if not isinstance(memory_context, dict) or not memory_context:
        return ""

    payload: dict[str, Any] = {}
    for key in ("user_id", "risk_tolerance", "investment_style", "watchlist", "last_focus", "recent_focuses"):
        value = memory_context.get(key)
        if value is None:
            continue
        payload[key] = value

    if not payload:
        return ""

    return (
        "<memory_context>\n"
        + json_dumps_safe(payload, ensure_ascii=False, indent=2)
        + "\n</memory_context>\n"
    )


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except Exception:
        return default


def _extract_json_object(text: str) -> str:
    if not text:
        raise ValueError("empty model output")

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no json object found")
    return cleaned[start : end + 1]


_DISALLOWED_SNIPPET_MARKERS = (
    "Search Results",
    "Performance Comparison",
    "get_",
    " output",
    "Notes:",
    "====",
    "```",
    "<inputs>",
    "</inputs>",
    "<output_format>",
    "</output_format>",
)
_DISCLAIMER_PHRASES = ("不构成投资建议", "仅供参考", "历史不代表未来", "非投资建议")


def _normalize_llm_section_line(line: str) -> str:
    cleaned = str(line or "").strip()
    if not cleaned:
        return ""

    if cleaned.startswith("- "):
        cleaned = cleaned[2:].strip()

    if cleaned.startswith("{") and cleaned.endswith("}"):
        try:
            obj = json_loads_strict(cleaned)
        except Exception:
            obj = None
        if isinstance(obj, dict):
            event = str(obj.get("event") or "").strip()
            impact = str(obj.get("impact") or "").strip()
            if event and impact:
                return f"{event}：{impact}"

            risk = str(obj.get("risk") or "").strip()
            detail = str(obj.get("detail") or "").strip()
            if risk and detail:
                return f"{risk}：{detail}"

            title = str(obj.get("title") or obj.get("name") or "").strip()
            desc = str(obj.get("summary") or obj.get("reason") or obj.get("value") or "").strip()
            if title and desc:
                return f"{title}：{desc}"

            pairs: list[str] = []
            for key, value in obj.items():
                key_text = str(key).strip()
                value_text = str(value).strip()
                if not key_text or not value_text:
                    continue
                if any(phrase in value_text for phrase in _DISCLAIMER_PHRASES):
                    continue
                pairs.append(f"{key_text}: {value_text}")
                if len(pairs) >= 3:
                    break
            if pairs:
                return "；".join(pairs)

    return cleaned


def _sanitize_llm_section(text: str, *, max_lines: int = 8, max_chars: int = 900) -> str:
    if not isinstance(text, str):
        return ""
    cleaned_lines: list[str] = []
    for raw in text.splitlines():
        line = _normalize_llm_section_line(raw)
        if not line:
            continue
        if any(marker in line for marker in _DISALLOWED_SNIPPET_MARKERS):
            continue
        if any(phrase in line for phrase in _DISCLAIMER_PHRASES):
            continue
        cleaned_lines.append(line)
        if len(cleaned_lines) >= max_lines:
            break
    if not cleaned_lines:
        return ""
    normalized = "\n".join([l if l.startswith("-") else f"- {l}" for l in cleaned_lines]).strip()
    if len(normalized) > max_chars:
        normalized = normalized[:max_chars].rstrip()
    return normalized


def _is_deep_research_run(state: GraphState) -> bool:
    """判断是否需要运行深度核查 Verifier。

    修复：原来只有 analysis_depth==deep_research 时才触发，导致普通
    investment_report 模式完全跳过二次 LLM 事实核查，幻觉漏网。
    新策略：所有 investment_report 模式均触发；deep_research 深度时
    进一步可扩展核查强度（预留 flag）。
    """
    output_mode = str(state.get("output_mode") or "").strip().lower()
    return output_mode == "investment_report"


def _section_limits(output_mode: str, key: str) -> tuple[int, int]:
    if output_mode == "investment_report" and key in {
        "investment_thesis",
        "investment_summary",
        "company_overview",
        "catalysts",
        "valuation",
        "conclusion",
        "impact_analysis",
        "next_watch",
        "analysis",
        "highlights",
        "summary",
        "comparison_conclusion",
    }:
        max_lines = max(10, _env_int("LANGGRAPH_SYNTHESIZE_LONGFORM_MAX_LINES", 18))
        max_chars = max(1200, _env_int("LANGGRAPH_SYNTHESIZE_LONGFORM_MAX_CHARS", 3200))
        return max_lines, max_chars
    return 8, 900


def _coerce_payload_to_strings(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Best-effort coercion so RenderVars validation doesn't fail when the LLM returns
    lists/dicts for string fields (e.g. risks: ["...", "..."]).
    """
    if not isinstance(payload, dict):
        return {}

    coerced: dict[str, Any] = {}
    for key, value in payload.items():
        if value is None:
            coerced[key] = ""
            continue

        if isinstance(value, str):
            coerced[key] = value
            continue

        if isinstance(value, list):
            lines: list[str] = []
            for item in value[:20]:
                if item is None:
                    continue
                if isinstance(item, str):
                    line = item.strip()
                else:
                    try:
                        line = json_dumps_safe(item, ensure_ascii=False)
                    except Exception:
                        line = str(item)
                if line:
                    lines.append(line)
            coerced[key] = "\n".join(lines)
            continue

        if isinstance(value, dict):
            try:
                coerced[key] = json_dumps_safe(value, ensure_ascii=False)
            except Exception:
                coerced[key] = str(value)
            continue

        coerced[key] = str(value)

    return coerced


def _format_risks(candidate: Any, *, base_risks: str) -> str:
    base = base_risks.strip() if isinstance(base_risks, str) and base_risks.strip() else "- 注：以上仅供参考，不构成投资建议。"

    if candidate is None:
        return base

    raw_text = candidate.strip() if isinstance(candidate, str) else str(candidate).strip()

    parsed: dict[str, Any] | None = None
    if isinstance(candidate, dict):
        parsed = candidate
    elif isinstance(candidate, str) and raw_text.startswith("{") and raw_text.endswith("}"):
        try:
            obj = json_loads_strict(raw_text)
            if isinstance(obj, dict):
                parsed = obj
        except Exception:
            parsed = None

    if isinstance(parsed, dict):
        lines: list[str] = []
        for k, v in parsed.items():
            if v is None:
                continue
            key = str(k).strip()
            if not key:
                continue
            key_lower = key.lower()
            if "disclaimer" in key_lower or "免责声明" in key:
                continue

            if isinstance(v, str):
                value = v.strip()
            else:
                try:
                    value = json_dumps_safe(v, ensure_ascii=False)
                except Exception:
                    value = str(v)
                value = value.strip()

            if not value:
                continue
            if any(phrase in value for phrase in _DISCLAIMER_PHRASES):
                continue

            # Prefer `AAPL: ...` style when keys look like tickers or named buckets.
            if key_lower in ("risk", "risks"):
                lines.append(f"- {value}")
            else:
                lines.append(f"- {key}：{value}")
            if len(lines) >= 6:
                break

        return "\n".join([*lines, base]).strip() if lines else base

    sanitized = _sanitize_llm_section(raw_text, max_lines=6)
    return "\n".join([sanitized, base]).strip() if sanitized else base
