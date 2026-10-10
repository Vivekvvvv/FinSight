# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from langchain_core.messages import HumanMessage

from backend.graph.failure import append_failure, build_runtime, utc_now_iso
from backend.graph.capability_registry import REPORT_AGENT_CANDIDATES
from backend.graph.plan_ir import PlanIR
from backend.graph.planner_prompt import build_planner_prompt
from backend.graph.event_bus import emit_event
from backend.graph.state import GraphState
from backend.graph.nodes.planner_stub import planner_stub
from backend.services.llm_retry import ainvoke_with_rate_limit_retry, is_rate_limit_error
from backend.utils.env_config import env_float
from backend.utils.strict_json import json_loads_strict

from backend.graph.nodes.planner_json import (
    _build_json_retry_prompt,
    _build_parse_error_info,
    _extract_error_snippet,
    _extract_json_object,
    _load_json_with_repair,
    _public_parse_error_info,
    _reject_json_constant,
    _repair_json_text,
)

from backend.graph.nodes.planner_emit import _emit_pipeline_stage, _emit_plan_ready
from backend.graph.nodes.planner_policy import (
    _build_budget_assertions,
    _enforce_policy,
    _env_bool,
    _env_int,
    _env_str,
    _estimate_step_cost_latency,
    _flag,
    _is_dashboard_forced_report,
    _is_dashboard_source,
    _is_deep_hint,
    _record_planner_ab_metrics,
    _resolve_planner_variant,
    get_planner_ab_metrics,
)

logger = logging.getLogger(__name__)


async def planner(state: GraphState) -> dict:
    """
    Planner node.

    Modes:
    - LANGGRAPH_PLANNER_MODE=stub (default): deterministic plan (no network)
    - LANGGRAPH_PLANNER_MODE=llm: ask LLM for PlanIR JSON; validate + enforce policy; fallback to stub
    """
    mode = _env_str("LANGGRAPH_PLANNER_MODE", "stub").lower()
    trace = state.get("trace") or {}
    planner_variant = _resolve_planner_variant(state)
    planner_started_at = time.perf_counter()

    await _emit_pipeline_stage(
        stage="planning",
        status="start",
        message="Planner started",
    )

    if mode != "llm":
        trace.update({"planner_runtime": {**build_runtime(mode="stub", fallback=False), "variant": planner_variant}})
        out = {**planner_stub(state), "trace": trace}
        steps = len(((out.get("plan_ir") or {}).get("steps") or []))
        _record_planner_ab_metrics(variant=planner_variant, fallback=False, retry_attempts=0, steps=steps)
        await _emit_plan_ready(
            state=state,
            plan_dict=(out.get("plan_ir") or {}),
            fallback=False,
        )
        await _emit_pipeline_stage(
            stage="planning",
            status="done",
            message="Planner completed",
            duration_ms=int((time.perf_counter() - planner_started_at) * 1000),
        )
        return out

    try:
        from backend.llm_config import create_llm

        _planner_temp = env_float(
            "LANGGRAPH_PLANNER_TEMPERATURE", 0.2, minimum=0.0, maximum=2.0
        )
        llm = create_llm(temperature=_planner_temp)
        llm_factory = lambda: create_llm(temperature=_planner_temp)  # noqa: E731
    except Exception as exc:
        error_code = "planner_llm_init_error"
        logger.error("[Planner] LLM initialization failed")
        append_failure(
            trace,
            node="planner",
            stage="llm_init",
            error=error_code,
            fallback="planner_stub",
            retryable=False,
        )
        trace.update(
            {
                "planner_runtime": build_runtime(
                    mode="llm",
                    fallback=True,
                    reason=error_code,
                    retry_attempts=0,
                )
                | {"variant": planner_variant}
            }
        )
        out = {**planner_stub(state), "trace": trace}
        steps = len(((out.get("plan_ir") or {}).get("steps") or []))
        _record_planner_ab_metrics(variant=planner_variant, fallback=True, retry_attempts=0, steps=steps)
        await _emit_plan_ready(
            state=state,
            plan_dict=(out.get("plan_ir") or {}),
            fallback=True,
            fallback_reason=f"llm_unavailable:{exc.__class__.__name__}",
        )
        await _emit_pipeline_stage(
            stage="planning",
            status="done",
            message="Planner fallback completed",
            duration_ms=int((time.perf_counter() - planner_started_at) * 1000),
        )
        return out

    prompt = build_planner_prompt(state, variant=planner_variant)
    retry_attempts = 0
    last_output_preview = ""
    parse_error_info: dict[str, Any] | None = None

    def _on_retry(attempt: int, _exc: BaseException) -> None:
        nonlocal retry_attempts
        retry_attempts = max(retry_attempts, int(attempt))

    try:
        await emit_event(
            {
                "type": "thinking",
                "stage": "llm_call_start",
                "message": "planner",
                "timestamp": utc_now_iso(),
            }
        )
        resp = await ainvoke_with_rate_limit_retry(
            llm,
            [HumanMessage(content=prompt)],
            llm_factory=llm_factory,
            acquire_token=True,
            on_retry=_on_retry,
        )
        await emit_event(
            {
                "type": "thinking",
                "stage": "llm_call_done",
                "message": "planner",
                "timestamp": utc_now_iso(),
            }
        )
        content = resp.content if hasattr(resp, "content") else str(resp)
        raw_text = str(content)
        last_output_preview = raw_text[:1200]
        parse_meta: dict[str, Any] = {}
        try:
            json_text = _extract_json_object(raw_text)
            payload, parse_meta = _load_json_with_repair(json_text)
        except Exception as first_parse_exc:
            parse_error_info = _build_parse_error_info(raw_text, first_parse_exc)
            logger.warning("[Planner] invalid JSON from first LLM output")
            await emit_event(
                {
                    "type": "thinking",
                    "stage": "llm_output_invalid_json",
                    "message": f"planner_json_invalid: {parse_error_info.get('error')}",
                    "timestamp": utc_now_iso(),
                }
            )
            await emit_event(
                {
                    "type": "thinking",
                    "stage": "llm_call_retry_start",
                    "message": "planner_json_repair",
                    "timestamp": utc_now_iso(),
                }
            )
            repair_prompt = _build_json_retry_prompt(
                base_prompt=prompt,
                parse_error=parse_error_info,
                invalid_output=raw_text,
            )
            retry_resp = await ainvoke_with_rate_limit_retry(
                llm,
                [HumanMessage(content=repair_prompt)],
                llm_factory=llm_factory,
                acquire_token=True,
                on_retry=_on_retry,
            )
            await emit_event(
                {
                    "type": "thinking",
                    "stage": "llm_call_retry_done",
                    "message": "planner_json_repair",
                    "timestamp": utc_now_iso(),
                }
            )
            retry_content = retry_resp.content if hasattr(retry_resp, "content") else str(retry_resp)
            retry_text = str(retry_content)
            last_output_preview = retry_text[:1200]
            try:
                retry_json_text = _extract_json_object(retry_text)
                payload, parse_meta = _load_json_with_repair(retry_json_text)
                parse_meta["json_retry_used"] = True
                parse_meta["first_parse_error"] = {
                    "error": parse_error_info.get("error"),
                    "line": parse_error_info.get("line"),
                    "column": parse_error_info.get("column"),
                    "snippet": parse_error_info.get("snippet"),
                }
            except Exception as second_parse_exc:
                second_error_info = _build_parse_error_info(retry_text, second_parse_exc)
                parse_error_info = {
                    "json_retry_used": True,
                    "first_attempt": parse_error_info,
                    "second_attempt": second_error_info,
                }
                logger.warning("[Planner] invalid JSON after retry")
                raise
        if not isinstance(payload, dict):
            raise ValueError("PlanIR payload must be a JSON object")
        payload, budget_assertions = _enforce_policy(payload, state)
        plan = PlanIR.model_validate(payload)
        trace.update(
            {
                "planner_runtime": {
                    **build_runtime(mode="llm", fallback=False, retry_attempts=retry_attempts),
                    "variant": planner_variant,
                    "steps": len(plan.steps),
                    "budget_assertions": budget_assertions,
                    "json_parse": parse_meta,
                }
            }
        )
        _record_planner_ab_metrics(
            variant=planner_variant,
            fallback=False,
            retry_attempts=retry_attempts,
            steps=len(plan.steps),
        )
        plan_dict = plan.model_dump()
        await _emit_plan_ready(
            state=state,
            plan_dict=plan_dict,
            fallback=False,
        )
        await _emit_pipeline_stage(
            stage="planning",
            status="done",
            message="Planner completed",
            duration_ms=int((time.perf_counter() - planner_started_at) * 1000),
        )
        return {"plan_ir": plan_dict, "trace": trace}
    except Exception as exc:
        retryable = is_rate_limit_error(exc)
        error_code = "planner_llm_call_error"
        public_parse_error = _public_parse_error_info(parse_error_info)
        logger.error("[Planner] LLM planning failed")
        append_failure(
            trace,
            node="planner",
            stage="llm_call",
            error=error_code,
            fallback="planner_stub",
            retryable=retryable,
            retry_attempts=retry_attempts,
            metadata={
                "json_parse_error": public_parse_error,
                "last_output_preview": "[redacted]" if last_output_preview else "",
            },
        )
        await emit_event(
            {
                "type": "thinking",
                "stage": "llm_call_error",
                "message": error_code,
                "timestamp": utc_now_iso(),
            }
        )
        trace.update(
            {
                "planner_runtime": build_runtime(
                    mode="llm",
                    fallback=True,
                    reason=error_code,
                    retry_attempts=retry_attempts,
                )
                | {
                    "variant": planner_variant,
                    "json_parse_error": public_parse_error,
                }
            }
        )
        out = {**planner_stub(state), "trace": trace}
        steps = len(((out.get("plan_ir") or {}).get("steps") or []))
        _record_planner_ab_metrics(
            variant=planner_variant,
            fallback=True,
            retry_attempts=retry_attempts,
            steps=steps,
        )
        await _emit_plan_ready(
            state=state,
            plan_dict=(out.get("plan_ir") or {}),
            fallback=True,
            fallback_reason=error_code,
        )
        await _emit_pipeline_stage(
            stage="planning",
            status="error",
            message="Planner failed, fallback plan emitted",
            duration_ms=int((time.perf_counter() - planner_started_at) * 1000),
            error=error_code,
        )
        return out
