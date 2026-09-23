# -*- coding: utf-8 -*-
"""
Conditional interrupt node for human-in-the-loop confirmation.

Uses LangGraph ``interrupt()`` when current run requires user confirmation.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from langgraph.types import interrupt

from backend.graph.confirmation_policy import normalize_confirmation_mode, should_require_confirmation
from backend.graph.state import GraphState

logger = logging.getLogger(__name__)

_DEFAULT_CONFIRMATION_OPTIONS = ["确认执行", "调整参数", "取消"]
_QUERY_ADJUSTMENT_MARKER = "[User adjustment]"
_INTENT_CONFIRM = "confirm_execute"
_INTENT_ADJUST = "adjust_parameters"
_INTENT_CANCEL = "cancel_execution"

# 意图关键词的否定标记：裸子串会把 "我不确认" 判成 confirm 放行执行、
# 把 "请不要取消"/"don't cancel" 判成 cancel 误杀——必须看紧邻前方。
_CJK_NEGATION_MARKERS = ("不", "别", "勿", "没", "未")
_EN_NEGATION_MARKERS = ("not", "n't", "never", "cannot", "cant", "dis")


def _has_intent_keyword(text: str, keywords: tuple[str, ...], *, english: bool) -> bool:
    """关键词出现且紧邻前方没有否定标记。

    CJK 取前 2 字窗口（"不确认"/"别取消"/"先不取消" 均覆盖；
    "没问题，确认" 的 "没" 距 "确认" 3 字不误伤）。
    英文取前 6 字符窗口（"don't cancel"/"cannot confirm"/"disapprove"）。
    """
    window = 6 if english else 2
    markers = _EN_NEGATION_MARKERS if english else _CJK_NEGATION_MARKERS
    for keyword in keywords:
        start = 0
        while True:
            idx = text.find(keyword, start)
            if idx < 0:
                break
            prefix = text[max(0, idx - window):idx]
            if not any(marker in prefix for marker in markers):
                return True
            start = idx + len(keyword)
    return False


def _resolve_gate_reason(
    *,
    require_confirmation: Any,
    confirmation_mode: str,
    output_mode: Any,
) -> tuple[str, str]:
    output_mode_text = str(output_mode or "").strip().lower()
    if require_confirmation is True:
        return (
            "explicit_required",
            "Current request explicitly requires a confirmation before execution.",
        )
    if confirmation_mode == "required":
        return (
            "mode_required",
            "Current confirmation policy is required, so execution needs a confirmation.",
        )
    if output_mode_text == "investment_report":
        return (
            "investment_report_auto_required",
            "Investment report mode requires a pre-execution confirmation by default.",
        )
    return (
        "policy_required",
        "Current policy requires a confirmation before execution.",
    )


def _build_option_metadata(options: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    option_effects: dict[str, str] = {}
    option_intents: dict[str, str] = {}
    if not options:
        return option_effects, option_intents

    # Positional defaults for canonical 3-option flow.
    option_intents[options[0]] = _INTENT_CONFIRM
    option_effects[options[0]] = "Continue now with the current execution plan."

    if len(options) >= 2:
        option_intents[options[1]] = _INTENT_ADJUST
        option_effects[options[1]] = "Adjust parameters before continuing."

    if len(options) >= 3:
        option_intents[options[2]] = _INTENT_CANCEL
        option_effects[options[2]] = "Cancel this execution and stop the workflow."

    for option in options[3:]:
        option_intents[option] = "custom"
        option_effects[option] = "Continue based on this option."
    return option_effects, option_intents


def _normalize_user_response(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("instruction", "text", "value", "response", "option"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return str(value or "").strip()


def _strip_adjustment_prefix(text: str) -> str:
    if not text:
        return ""
    patterns = [
        r"^\s*调整参数\s*[:：]\s*",
        r"^\s*adjust(?:\s+parameters?)?\s*[:：]\s*",
    ]
    for pattern in patterns:
        updated = re.sub(pattern, "", text, flags=re.IGNORECASE)
        if updated != text:
            return updated.strip()
    return text.strip()


def _parse_confirmation_response(
    response: Any,
    *,
    option_intents: dict[str, str],
) -> tuple[str, str | None]:
    text = _normalize_user_response(response)
    if not text:
        return _INTENT_CONFIRM, None

    if text in option_intents:
        intent = str(option_intents.get(text) or "").strip() or _INTENT_CONFIRM
        if intent == _INTENT_ADJUST:
            return intent, None
        return intent, None

    lowered = text.lower()
    if _has_intent_keyword(lowered, ("cancel", "abort", "stop"), english=True):
        return _INTENT_CANCEL, None
    if _has_intent_keyword(text, ("取消", "终止", "停止"), english=False):
        return _INTENT_CANCEL, None

    if _has_intent_keyword(lowered, ("confirm", "continue", "approve"), english=True):
        return _INTENT_CONFIRM, None
    if _has_intent_keyword(text, ("确认", "继续"), english=False):
        return _INTENT_CONFIRM, None

    instruction = _strip_adjustment_prefix(text)
    if instruction:
        return _INTENT_ADJUST, instruction
    return _INTENT_CONFIRM, None


def _merge_query_with_adjustment(query: Any, instruction: str | None) -> str | None:
    base = str(query or "").strip()
    patch = str(instruction or "").strip()
    if not patch:
        return None
    addition = f"{_QUERY_ADJUSTMENT_MARKER} {patch}"
    if addition in base:
        return base or addition
    if not base:
        return addition
    return f"{base}\n\n{addition}"


def confirmation_gate(state: GraphState) -> dict[str, Any]:
    """Conditionally interrupt the graph to ask for user confirmation."""
    require = state.get("require_confirmation")
    output_mode = state.get("output_mode", "chat")
    confirmation_mode = normalize_confirmation_mode(state.get("confirmation_mode"), default="auto")

    should_confirm = should_require_confirmation(
        require_confirmation=require,
        confirmation_mode=confirmation_mode,
        output_mode=output_mode,
    )
    if not should_confirm:
        # Explicitly reset transient confirmation fields to avoid stale state
        # after a previous interrupted run.
        return {
            "confirmation_intent": _INTENT_CONFIRM,
            "confirmation_instruction": None,
            "confirmation_mode": confirmation_mode,
        }

    plan_ir = state.get("plan_ir") or {}
    options = state.get("confirmation_options") or _DEFAULT_CONFIRMATION_OPTIONS
    gate_reason_code, gate_reason = _resolve_gate_reason(
        require_confirmation=require,
        confirmation_mode=confirmation_mode,
        output_mode=output_mode,
    )
    option_effects, option_intents = _build_option_metadata(options)

    logger.info("[confirmation_gate] interrupt for confirmation")

    user_response = interrupt(
        {
            "prompt": "执行计划确认",
            "options": options,
            "plan_summary": plan_ir.get("rationale", ""),
            "required_agents": plan_ir.get("required_agents", []),
            "gate_reason_code": gate_reason_code,
            "gate_reason": gate_reason,
            "option_effects": option_effects,
            "option_intents": option_intents,
            "output_mode": output_mode,
            "confirmation_mode": confirmation_mode,
        }
    )

    intent, instruction = _parse_confirmation_response(
        user_response,
        option_intents=option_intents,
    )
    # If user only clicked an "adjust" option without actual instructions,
    # continue with the current plan to avoid redundant re-planning.
    if intent == _INTENT_ADJUST and not instruction:
        intent = _INTENT_CONFIRM

    updates: dict[str, Any] = {
        "user_confirmation": user_response,
        "require_confirmation": False,
        "confirmation_mode": confirmation_mode,
        "confirmation_intent": intent,
        "confirmation_instruction": instruction,
    }
    if intent == _INTENT_ADJUST:
        merged_query = _merge_query_with_adjustment(state.get("query"), instruction)
        if merged_query:
            updates["query"] = merged_query

    logger.info("[confirmation_gate] resumed")
    return updates


__all__ = ["confirmation_gate"]
