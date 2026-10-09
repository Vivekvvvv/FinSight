# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from backend.graph.nodes.compare_gate import should_render_compare, is_compare_operation
from backend.graph.event_bus import emit_event
from backend.graph.failure import append_failure, build_runtime, utc_now_iso
from backend.graph.json_utils import json_dumps_safe
from backend.graph.state import GraphState
from backend.services.llm_retry import ainvoke_with_rate_limit_retry, is_rate_limit_error
from backend.utils.env_config import env_float
from backend.utils.strict_json import json_loads_strict

logger = logging.getLogger(__name__)

from backend.graph.nodes.hallucination_guards import (
    _normalize_for_match,
    _claim_supported_by_evidence,
    _scrub_unverified_future_claims,
    _apply_verifier_redactions,
    _contains_claim_after_redaction,
    _compute_unresolved_unsupported_claims,
    _FUTURE_EVENT_VERBS,
    _FUTURE_DATE_PHRASE,
    _HALLUCINATION_EVENT_PATTERNS,
    _HALLUCINATION_SAFE_PLACEHOLDER,
)

from backend.graph.nodes.synthesize_brief import _extract_brief_headline, _synthesize_morning_brief_data
from backend.graph.nodes.synthesize_format import (
    _coerce_payload_to_strings,
    _extract_json_object,
    _format_conversation_history_for_synth,
    _format_memory_context_for_synth,
    _format_persona_lens,
    _format_risks,
    _sanitize_llm_section,
    _section_limits,
)

from backend.graph.nodes.synthesize_render_vars import (
    RenderVars,
    _stub_render_vars,
)

from backend.graph.nodes.synthesize_verifier import (
    _env_bool,
    _env_str,
    _run_deep_report_verifier,
)


async def _generate_narrative_draft(
    state: GraphState,
    render_vars: dict[str, str],
    trace: dict[str, Any],
) -> tuple[str, dict[str, Any] | None]:
    """
    Call LLM to produce a complete markdown research report (narrative mode).

    Returns:
    - markdown string on success (or empty string on failure)
    - optional verifier result payload
    """
    try:
        from backend.llm_config import create_llm

        _synth_temp = env_float(
            "LANGGRAPH_SYNTHESIZE_TEMPERATURE", 0.3, minimum=0.0, maximum=2.0
        )
        llm = create_llm(temperature=_synth_temp)
        llm_factory = lambda: create_llm(temperature=_synth_temp)  # noqa: E731
    except Exception as exc:
        logger.warning("[Synthesize/narrative] LLM init failed")
        return "", None

    artifacts = state.get("artifacts") or {}
    step_results = artifacts.get("step_results") if isinstance(artifacts, dict) else None
    evidence_pool = artifacts.get("evidence_pool") if isinstance(artifacts, dict) else None
    query = (state.get("query") or "").strip()
    subject = state.get("subject") or {}
    tickers = subject.get("tickers") if isinstance(subject, dict) else []
    tickers = tickers if isinstance(tickers, list) else []
    ticker_label = ", ".join(str(t) for t in tickers) if tickers else "标的"

    # -- Collect agent summaries and evidence for the prompt context --
    agent_sections: list[str] = []
    if isinstance(step_results, dict):
        plan_ir = state.get("plan_ir") or {}
        steps = plan_ir.get("steps") if isinstance(plan_ir, dict) else None
        step_index = {s.get("id"): s for s in (steps or []) if isinstance(s, dict) and s.get("id")}

        for step_id, item in step_results.items():
            if not isinstance(item, dict):
                continue
            output = item.get("output")
            if isinstance(output, dict) and output.get("skipped"):
                continue
            step_meta = step_index.get(step_id) or {}
            agent_name = step_meta.get("name") or step_id
            kind = step_meta.get("kind") or "unknown"

            section_lines = [f"### {agent_name} ({kind})"]
            if isinstance(output, dict):
                summary = output.get("summary")
                if summary:
                    section_lines.append(f"摘要: {str(summary).strip()[:2000]}")
                evidence = output.get("evidence")
                if isinstance(evidence, list):
                    for ev in evidence[:15]:
                        if isinstance(ev, dict):
                            ev_text = str(ev.get("text") or "").strip()
                            if ev_text:
                                section_lines.append(f"- {ev_text[:400]}")
                        elif isinstance(ev, str) and ev.strip():
                            section_lines.append(f"- {ev.strip()[:400]}")
                risks = output.get("risks")
                if isinstance(risks, list):
                    for r in risks[:6]:
                        section_lines.append(f"- [风险] {str(r).strip()[:300]}")
            elif output is not None:
                section_lines.append(str(output).strip()[:1500])

            agent_sections.append("\n".join(section_lines))

    # -- Collect cross-agent conflict information for narrative context --
    # Apply same trigger formula: deep_report || (success >= 2 && comparable >= 1)
    _NARRATIVE_COMPARABLE_PAIRS = [
        ("technical_agent", "fundamental_agent"),
        ("technical_agent", "news_agent"),
        ("technical_agent", "price_agent"),
        ("fundamental_agent", "news_agent"),
        ("fundamental_agent", "macro_agent"),
        ("news_agent", "macro_agent"),
        ("price_agent", "news_agent"),
        ("macro_agent", "technical_agent"),
    ]
    narrative_success_agents: set[str] = set()
    if isinstance(step_results, dict):
        for step_id, item in step_results.items():
            if not isinstance(item, dict):
                continue
            output = item.get("output")
            if not isinstance(output, dict) or output.get("skipped"):
                continue
            a_name = (step_index.get(step_id) or {}).get("name") or ""
            if a_name and isinstance(output.get("summary"), str) and output["summary"].strip():
                narrative_success_agents.add(a_name)

    narrative_comparable_count = sum(
        1 for a, b in _NARRATIVE_COMPARABLE_PAIRS
        if a in narrative_success_agents and b in narrative_success_agents
    )
    output_mode_raw = state.get("output_mode") or ""
    is_narrative_deep = output_mode_raw == "investment_report"
    should_collect_conflicts = is_narrative_deep or (
        len(narrative_success_agents) >= 2 and narrative_comparable_count >= 1
    )

    conflict_context_lines: list[str] = []
    if should_collect_conflicts and isinstance(step_results, dict):
        for step_id, item in step_results.items():
            if not isinstance(item, dict):
                continue
            output = item.get("output")
            if not isinstance(output, dict):
                continue
            a_name = (step_index.get(step_id) or {}).get("name") or step_id
            flags = output.get("conflict_flags")
            claims = output.get("conflicting_claims")
            if isinstance(flags, list):
                for f in flags:
                    if isinstance(f, str) and f.strip():
                        conflict_context_lines.append(f"- [{a_name}] {f.strip()}")
            if isinstance(claims, list):
                for c in claims:
                    if isinstance(c, dict):
                        claim_text = c.get("claim", "")
                        src_a = c.get("source_a", "?")
                        val_a = c.get("value_a", "?")
                        src_b = c.get("source_b", "?")
                        val_b = c.get("value_b", "?")
                        resolved = c.get("resolved", False)
                        resolution = c.get("resolution", "")
                        status = f"已裁决: {resolution}" if resolved else "未裁决"
                        conflict_context_lines.append(
                            f"- [{a_name}] {claim_text}: {src_a}={val_a} vs {src_b}={val_b} ({status})"
                        )
        # Edge case: deep report with ≤1 agent → add degraded notice to prompt
        if is_narrative_deep and len(narrative_success_agents) <= 1:
            conflict_context_lines.insert(
                0, f"- [系统] 冲突检测降级：仅 {len(narrative_success_agents)} 个智能体成功，无法交叉验证"
            )
    conflict_context = "\n".join(conflict_context_lines) if conflict_context_lines else ""

    evidence_text = ""
    if isinstance(evidence_pool, list) and evidence_pool:
        ev_lines: list[str] = []
        for ev in evidence_pool[:20]:
            if isinstance(ev, dict):
                text = str(ev.get("text") or "").strip()
                source = str(ev.get("source") or "").strip()
                if text:
                    ev_lines.append(f"- [{source}] {text[:400]}" if source else f"- {text[:400]}")
            elif isinstance(ev, str) and ev.strip():
                ev_lines.append(f"- {ev.strip()[:400]}")
        if ev_lines:
            evidence_text = "\n".join(ev_lines)

    conversation_history = _format_conversation_history_for_synth(state)
    memory_context_block = _format_memory_context_for_synth(state)
    persona_lens_block = _format_persona_lens(state)
    current_date = utc_now_iso()[:10]
    narrative_grounding_text = "\n".join(
        part for part in [evidence_text, conflict_context, "\n".join(agent_sections)] if part
    )

    prompt = f"""<role>FinSight 叙事报告引擎 — 资深卖方分析师视角，将多智能体分析结果合成为专业级投资研究报告</role>

{persona_lens_block}<task>
基于以下多个分析智能体的输出，撰写一份完整、深度的中文 Markdown 投资研究报告。
查询: {query}
标的: {ticker_label}
</task>

<time_anchor>
当前日期: {current_date}
你的知识可能过时。涉及日期/发布/并购/监管等事件时，仅可使用本提示中明确提供的证据内容。
</time_anchor>

{conversation_history}{memory_context_block}<agent_outputs>
{chr(10).join(agent_sections) if agent_sections else "(无智能体输出)"}
</agent_outputs>

{"<evidence_pool>" + chr(10) + evidence_text + chr(10) + "</evidence_pool>" if evidence_text else ""}

{"<cross_agent_conflicts>" + chr(10) + conflict_context + chr(10) + "</cross_agent_conflicts>" if conflict_context else ""}

<report_structure>
严格按以下结构撰写，使用 Markdown 标题。每个章节必须包含实质性分析段落，禁止仅列出数据点：

## 投资论点
2-3 段话。第一段给出核心判断（偏多/偏空/中性），附置信度和关键驱动因素。第二段阐述投资逻辑链条：事件 → 基本面影响 → 估值变化 → 价格预期。如有分歧信号，需明确说明矛盾点和权衡逻辑。

## 基本面分析
3-4 段话。必须涵盖：
- 盈利能力：营收规模、增速（YoY/QoQ）、利润率趋势
- 财务健康：杠杆率、现金流状况、资本配置
- 增长质量：增长驱动来源（量价/新业务/并购）、可持续性评估
- 与同业或历史水平的对比。每个论点引用具体数字。

## 技术面分析
2-3 段话。必须涵盖：
- 趋势判断：均线系统（MA20/MA50/MA200）排列与价格位置
- 动量指标：RSI 区间判断、MACD 信号方向
- 关键价位：支撑位与阻力位，以及触及后的操作含义
- 技术面与基本面信号的一致性/背离分析

## 催化剂与风险
分别列出催化剂和风险，各 2-4 条。每条必须包含：
1. 事件描述（具体事件/日期/来源）
2. 影响路径（事件 → 预期/情绪 → 业绩预期 → 估值/价格）
3. 概率和影响程度评估

## 结论
2 段话。第一段综合研判，给出明确的操作建议框架（观望/逢低关注/逢高减仓等，附前提条件）。第二段列出 3-5 个关键观察指标和触发条件变更信号。
</report_structure>

<constraints>
1) 总长度 4000-6000 字符。这是严格要求，不可少于 4000 字符。
2) 每句话必须有数据支撑或逻辑推导，禁止空洞套话和模板化表述。
3) 跨智能体交叉引用：技术面与基本面信号对比、新闻事件与价格走势关联、宏观环境对个股的传导路径。
4) **冲突处理（关键）**：如 <cross_agent_conflicts> 中存在未裁决冲突，必须在相关章节中：(a) 明确说明冲突点和双方数据来源；(b) 给出裁决依据（优先采信哪方、为什么）；(c) 标注剩余不确定性。已裁决冲突也需简要提及裁决结论。
5) 有证据来源时标注引用编号 [1][2]。
6) 数据不足时明确标注"[数据缺失]"，不编造数字。
7) 直接输出 Markdown，禁止 JSON 包装、代码块包裹或开场白。
8) 末尾附一行免责声明："*以上内容仅供参考，不构成投资建议。*"
9) 禁止出现"补充分析"、"核心发现"等附录性标题，所有内容必须融入上述五大章节中。
10) **可选可视化**：当你认为可视化有助于读者理解时，可在正文中插入图表标签（每篇报告最多 2 个）：
    - LLM 概览数据：`<chart type="bar" title="标题">{{"labels":["A","B"],"values":[10,20]}}</chart>`
    - 引用前端已有数据：`<chart_ref type="bar" source="peers" fields="trailing_pe" title="PE对比"/>`
    - 支持类型: bar / line / pie / scatter / gauge。规则: 不替代文字分析，仅做辅助展示。
11) **严格闭卷原则（高优先级）**：你唯一可用的信息来源仅限本提示中的 <agent_outputs>、<evidence_pool>、<cross_agent_conflicts>。
12) 禁止引用任何未在上述标签中出现的具体事实（尤其是产品发布时间、并购、监管进展、公司战略计划、竞争对手具体动态）。
13) 如需提及行业背景，仅允许使用泛化表述（如"行业竞争加剧"），禁止输出具体日期+事件断言。
14) 违反闭卷原则视为编造数据，与编造财务数字同级错误。
</constraints>"""

    retry_attempts = 0

    def _on_retry(attempt: int, _exc: BaseException) -> None:
        nonlocal retry_attempts
        retry_attempts = max(retry_attempts, int(attempt))

    try:
        await emit_event(
            {
                "type": "thinking",
                "stage": "llm_call_start",
                "message": "synthesize_narrative",
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
                "message": "synthesize_narrative",
                "timestamp": utc_now_iso(),
            }
        )
        content = resp.content if hasattr(resp, "content") else str(resp)
        draft = str(content).strip()

        # Strip accidental code-fence wrapping
        draft = re.sub(r"^```(?:markdown|md)?\s*", "", draft, flags=re.IGNORECASE)
        draft = re.sub(r"\s*```$", "", draft)
        draft = draft.strip()
        draft = _scrub_unverified_future_claims(draft, narrative_grounding_text)

        verifier_result = await _run_deep_report_verifier(
            state=state,
            generated_text=draft,
            grounding_text=narrative_grounding_text,
        )
        unsupported_claims = (
            verifier_result.get("unsupported_claims")
            if isinstance(verifier_result, dict)
            else []
        )
        if isinstance(unsupported_claims, list) and unsupported_claims:
            draft = _apply_verifier_redactions(draft, unsupported_claims)
        unresolved_claims = (
            _compute_unresolved_unsupported_claims(draft, unsupported_claims)
            if isinstance(unsupported_claims, list)
            else []
        )
        if isinstance(verifier_result, dict):
            verifier_result["unresolved_unsupported_claims"] = unresolved_claims

        if len(draft) < 500:
            logger.warning("[Synthesize/narrative] LLM output too short; discarding")
            return "", verifier_result

        logger.info("[Synthesize/narrative] generated narrative draft")
        return draft, verifier_result

    except Exception as exc:
        retryable = is_rate_limit_error(exc)
        logger.warning("[Synthesize/narrative] LLM call failed; using template fallback")
        append_failure(
            trace,
            node="synthesize",
            stage="narrative_llm_call",
            error=type(exc).__name__,
            fallback="template_draft",
            retryable=retryable,
            retry_attempts=retry_attempts,
        )
        await emit_event(
            {
                "type": "thinking",
                "stage": "llm_call_error",
                "message": "synthesize_narrative failed; fallback to template",
                "timestamp": utc_now_iso(),
            }
        )
        return "", None


async def synthesize(state: GraphState) -> dict:
    """
    Phase 4.4 Synthesize node.

    Modes:
    - LANGGRAPH_SYNTHESIZE_MODE=stub (default): deterministic render_vars
    - LANGGRAPH_SYNTHESIZE_MODE=llm: LLM fills render_vars JSON; validate; fallback to stub
    - LANGGRAPH_SYNTHESIZE_MODE=narrative: LLM writes full markdown report; render_vars kept for cards
    """
    mode = _env_str("LANGGRAPH_SYNTHESIZE_MODE", "stub").lower()
    trace = state.get("trace") or {}
    synth_started_at = time.perf_counter()

    await emit_event(
        {
            "type": "pipeline_stage",
            "stage": "synthesizing",
            "status": "start",
            "message": "Synthesize started",
            "timestamp": utc_now_iso(),
        }
    )

    async def _emit_synth_stage_done(*, status: str, message: str, error: str | None = None) -> None:
        payload: dict[str, Any] = {
            "type": "pipeline_stage",
            "stage": "synthesizing",
            "status": status,
            "message": message,
            "duration_ms": int((time.perf_counter() - synth_started_at) * 1000),
            "timestamp": utc_now_iso(),
        }
        if error:
            payload["error"] = str(error)[:300]
        await emit_event(payload)

    # ── Morning brief: deterministic structured synthesis (ADR-P1-001, zero LLM) ──
    _op_raw = state.get("operation") or {}
    _op_name = _op_raw.get("name") if isinstance(_op_raw, dict) else None
    if _op_name == "morning_brief":
        brief_result = _synthesize_morning_brief_data(state)
        trace.update({
            "synthesize_runtime": {
                **build_runtime(mode="morning_brief_deterministic", fallback=False),
                "keys": ["brief_data", "draft_markdown"],
            }
        })
        merged_artifacts = {
            **(state.get("artifacts") or {}),
            "brief_data": brief_result["brief_data"],
            "draft_markdown": brief_result["draft_markdown"],
            "render_vars": {},
        }
        await _emit_synth_stage_done(status="done", message="Morning brief synthesized (deterministic)")
        return {"artifacts": merged_artifacts, "trace": trace}

    # ── Emit decision_note when compare intent has no evidence ──
    # should_render_compare() now requires BOTH operation=compare AND valid
    # tool evidence.  When evidence is absent, the downstream _stub_render_vars
    # / LLM path will naturally degrade to multi-asset QA.  We emit a note
    # here so the frontend can surface the reason once, before mode branching.
    if is_compare_operation(state) and not should_render_compare(state):
        await emit_event(
            {
                "type": "decision_note",
                "scope": "synthesize",
                "title": "Compare evidence missing — degraded to QA",
                "reason": "operation=compare but get_performance_comparison returned no valid data",
                "code": "compare_evidence_missing",
                "impact": "Using standard multi-asset QA template instead of comparison template",
                "timestamp": utc_now_iso(),
            }
        )

    # ── narrative mode: LLM writes full markdown report; render_vars kept for cards ──
    if mode == "narrative":
        logger.info("[Synthesize] Running in NARRATIVE mode — LLM writes full report draft")
        render_vars = _stub_render_vars(state)

        draft_markdown, verifier_result = await _generate_narrative_draft(state, render_vars, trace)
        verifier_claims = (
            verifier_result.get("unsupported_claims")
            if isinstance(verifier_result, dict)
            else []
        )
        unresolved_verifier_claims = (
            verifier_result.get("unresolved_unsupported_claims")
            if isinstance(verifier_result, dict)
            else []
        )
        synth_runtime: dict[str, Any] = {
            **build_runtime(mode="narrative", fallback=not bool(draft_markdown)),
            "keys": sorted(render_vars.keys()),
        }
        # Persona observability — record which persona shaped this synthesis
        _persona_id = state.get("persona_id")
        if _persona_id:
            synth_runtime["persona_id"] = str(_persona_id)
            synth_runtime["persona_lens_applied"] = bool(persona_lens_block)
        if isinstance(verifier_result, dict):
            synth_runtime["verifier_enabled"] = bool(verifier_result.get("enabled"))
            synth_runtime["verifier_checked"] = bool(verifier_result.get("checked"))
            synth_runtime["verifier_unsupported_count"] = (
                len(verifier_claims) if isinstance(verifier_claims, list) else 0
            )
            synth_runtime["verifier_unresolved_unsupported_count"] = (
                len(unresolved_verifier_claims) if isinstance(unresolved_verifier_claims, list) else 0
            )

        trace.update({"synthesize_runtime": synth_runtime})
        artifacts = {**(state.get("artifacts") or {}), "render_vars": render_vars}
        if draft_markdown:
            artifacts["draft_markdown"] = draft_markdown
        if isinstance(verifier_result, dict):
            artifacts["verifier_result"] = verifier_result
        if isinstance(verifier_claims, list) and verifier_claims:
            await emit_event(
                {
                    "type": "decision_note",
                    "scope": "verifier",
                    "title": "Deep report verifier redactions",
                    "reason": "Detected unsupported factual claims and redacted them.",
                    "impact": f"unsupported_claims={len(verifier_claims)}",
                    "timestamp": utc_now_iso(),
                }
            )
        await _emit_synth_stage_done(status="done", message="Synthesize completed")
        return {"artifacts": artifacts, "trace": trace}

    # ── stub mode (default): deterministic render_vars ──
    if mode != "llm":
        logger.info("[Synthesize] Running in STUB mode (set LANGGRAPH_SYNTHESIZE_MODE=llm for LLM synthesis)")
        render_vars = _stub_render_vars(state)
        trace.update(
            {
                "synthesize_runtime": {
                    **build_runtime(mode="stub", fallback=False),
                    "keys": sorted(render_vars.keys()),
                }
            }
        )
        await _emit_synth_stage_done(status="done", message="Synthesize completed in stub mode")
        return {"artifacts": {**(state.get("artifacts") or {}), "render_vars": render_vars}, "trace": trace}

    # ── llm mode: LLM fills render_vars JSON ──
    try:
        from backend.llm_config import create_llm

        _synth_temp = env_float(
            "LANGGRAPH_SYNTHESIZE_TEMPERATURE", 0.2, minimum=0.0, maximum=2.0
        )
        llm = create_llm(temperature=_synth_temp)
        llm_factory = lambda: create_llm(temperature=_synth_temp)  # noqa: E731
    except Exception as exc:
        render_vars = _stub_render_vars(state)
        append_failure(
            trace,
            node="synthesize",
            stage="llm_init",
            error=type(exc).__name__,
            fallback="synthesize_stub",
            retryable=False,
        )
        trace.update(
            {
                "synthesize_runtime": build_runtime(
                    mode="llm",
                    fallback=True,
                    reason=f"llm_unavailable: {type(exc).__name__}",
                    retry_attempts=0,
                )
            }
        )
        await _emit_synth_stage_done(
            status="error",
            message="Synthesize LLM unavailable, fallback emitted",
            error=type(exc).__name__,
        )
        return {"artifacts": {**(state.get("artifacts") or {}), "render_vars": render_vars}, "trace": trace}

    subject = state.get("subject") or {}
    operation = state.get("operation") or {}
    output_mode = state.get("output_mode") or "brief"
    artifacts = state.get("artifacts") or {}
    evidence_pool = artifacts.get("evidence_pool") if isinstance(artifacts, dict) else None
    rag_context = artifacts.get("rag_context") if isinstance(artifacts, dict) else None
    step_results = artifacts.get("step_results") if isinstance(artifacts, dict) else None

    # Build separated evidence sections for structured prompt
    evidence_pool_list = evidence_pool if isinstance(evidence_pool, list) else []
    rag_context_list = rag_context if isinstance(rag_context, list) else []

    inputs = {
        "query": state.get("query") or "",
        "subject": subject,
        "operation": operation,
        "output_mode": output_mode,
        "step_results": step_results if isinstance(step_results, dict) else {},
    }

    # Format evidence sections with XML tags
    realtime_section = ""
    if evidence_pool_list:
        realtime_section = "<realtime_evidence>\n" + json_dumps_safe(evidence_pool_list[:20], ensure_ascii=False, indent=2) + "\n</realtime_evidence>\n"

    historical_section = ""
    if rag_context_list:
        historical_section = "<historical_knowledge>\n" + json_dumps_safe(rag_context_list[:20], ensure_ascii=False, indent=2) + "\n</historical_knowledge>\n"

    evidence_rules = ""
    if realtime_section or historical_section:
        evidence_rules = """<evidence_priority_rules>
1. 实时数据与历史数据冲突时，以实时数据为准
2. 引用历史数据时必须标注数据时间（如"根据 2025 Q3 财报..."）
3. 无法确认时效性的数据需注明"截至某日期"
</evidence_priority_rules>
"""

    synth_conversation_history = _format_conversation_history_for_synth(state)
    synth_memory_context = _format_memory_context_for_synth(state)
    current_date = utc_now_iso()[:10]
    llm_grounding_text = "\n".join(
        part for part in [
            json_dumps_safe(evidence_pool_list[:20], ensure_ascii=False),
            json_dumps_safe(rag_context_list[:20], ensure_ascii=False),
            json_dumps_safe(step_results if isinstance(step_results, dict) else {}, ensure_ascii=False),
        ] if part
    )

    prompt = f"""<role>FinSight 报告合成引擎 — 将原始数据转化为高质量中文分析内容</role>

<task>
根据输入数据填充报告模板变量。仅返回 JSON 对象，禁止 markdown 或注释。
所有文本值必须为简体中文。
</task>

<time_anchor>
当前日期: {current_date}
你的知识可能过时。涉及日期/发布/并购/监管等事件时，仅可使用本提示中明确提供的证据内容。
</time_anchor>

{synth_conversation_history}{synth_memory_context}<inputs>
{json_dumps_safe(inputs, ensure_ascii=False, indent=2)}
</inputs>

{realtime_section}{historical_section}{evidence_rules}<output_format>
返回 JSON 对象，键为以下模板变量的子集：
news_summary, impact_analysis, next_watch, risks,
conclusion, investment_summary, company_overview, catalysts, valuation,
price_snapshot, technical_snapshot,
comparison_conclusion, comparison_metrics,
summary, highlights, analysis.
</output_format>

<field_quality_guidelines>
每个字段的质量要求：
- company_overview: 2-3 句话概括公司主营、市场地位、核心竞争力
- catalysts: 列出 3-5 个近期催化剂，每条含事件+潜在影响
- valuation: 包含关键估值指标（PE/PB/PS）及与历史/同业对比
- risks: 3-5 条风险要点，区分系统性风险和个股风险
- conclusion: 综合各维度给出明确的方向性判断，附条件和置信度
- news_summary: 提炼核心新闻事件，侧重影响而非事件本身
- investment_summary: 一段话浓缩投资核心逻辑（多/空/中性 + 理由）
- investment_thesis: 投资主线需包含判断、依据、触发条件、证伪条件与执行建议
</field_quality_guidelines>

<constraints>
1) 严格闭卷：仅可使用 <realtime_evidence>、<historical_knowledge>、<inputs.step_results> 中已出现的信息。
2) 禁止引用任何未在上述标签中出现的具体事实（尤其是产品发布时间、并购、监管进展、公司战略计划、竞争对手具体动态）。
3) 如需提及行业背景，仅允许泛化表述，禁止输出具体日期+事件断言。
4) 数据不足时明确标注"[数据缺失]"或"数据有限"，禁止补写训练知识中的细节。
5) 禁止输出原始工具数据、搜索日志、trace 信息。
6) 免责声明最多在 risks 字段末尾出现 1 次，其他字段禁止重复。
7) 每个字段控制在 6 条要点以内，追求信息密度而非长度。
8) 禁止使用"待实现"、"暂无数据"等占位短语；无数据时输出"[数据缺失]"。
9) 输出必须为合法 JSON 对象。
10) 禁止开场白、寒暄。直接输出 JSON。
</constraints>
"""

    retry_attempts = 0

    def _on_retry(attempt: int, _exc: BaseException) -> None:
        nonlocal retry_attempts
        retry_attempts = max(retry_attempts, int(attempt))

    try:
        await emit_event(
            {
                "type": "thinking",
                "stage": "llm_call_start",
                "message": "synthesize",
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
                "message": "synthesize",
                "timestamp": utc_now_iso(),
            }
        )
        content = resp.content if hasattr(resp, "content") else str(resp)
        payload = json_loads_strict(_extract_json_object(str(content)))
        if not isinstance(payload, dict):
            raise ValueError("render_vars payload must be a JSON object")

        payload = _coerce_payload_to_strings(payload)
        llm_render_vars = RenderVars.model_validate(payload).model_dump()
        # Merge with deterministic stub defaults so omitted keys never fall back
        # to template placeholders. Some keys are "data sections" that must stay
        # evidence-driven; keep the stub version to avoid hallucinated metrics.
        stub_render_vars = _stub_render_vars(state)
        base_risks = str(stub_render_vars.get("risks") or "- 注：以上仅供参考，不构成投资建议。").strip()
        protected_keys = {"news_summary", "comparison_metrics", "price_snapshot", "technical_snapshot"}
        render_vars: dict[str, str] = {}
        for key, stub_value in stub_render_vars.items():
            if key in protected_keys:
                render_vars[key] = stub_value
                continue
            candidate = llm_render_vars.get(key)
            if key == "risks":
                formatted_risks = _format_risks(candidate, base_risks=base_risks)
                render_vars[key] = _scrub_unverified_future_claims(formatted_risks, llm_grounding_text)
                continue
            if key in (
                "comparison_conclusion",
                "conclusion",
                "impact_analysis",
                "next_watch",
                "investment_summary",
                "investment_thesis",
                "company_overview",
                "catalysts",
                "valuation",
                "summary",
                "highlights",
                "analysis",
            ):
                if isinstance(candidate, str) and candidate.strip():
                    candidate = _scrub_unverified_future_claims(candidate, llm_grounding_text)
                    max_lines, max_chars = _section_limits(output_mode, key)
                    sanitized = _sanitize_llm_section(candidate, max_lines=max_lines, max_chars=max_chars)
                    render_vars[key] = sanitized if sanitized else stub_value
                else:
                    render_vars[key] = stub_value
                continue

            if isinstance(candidate, str) and candidate.strip():
                candidate = _scrub_unverified_future_claims(candidate, llm_grounding_text)
                render_vars[key] = candidate
            else:
                render_vars[key] = stub_value
        for key, candidate in llm_render_vars.items():
            if key not in render_vars:
                render_vars[key] = candidate
        if any("待实现" in str(v) for v in render_vars.values()):
            raise ValueError("render_vars contains placeholder tokens")

        verifier_result = await _run_deep_report_verifier(
            state=state,
            generated_text="\n".join(
                [
                    section
                    for section in (
                        str(render_vars.get("summary") or ""),
                        str(render_vars.get("highlights") or ""),
                        str(render_vars.get("analysis") or ""),
                        str(render_vars.get("investment_summary") or ""),
                        str(render_vars.get("investment_thesis") or ""),
                        str(render_vars.get("valuation") or ""),
                        str(render_vars.get("conclusion") or ""),
                        str(render_vars.get("impact_analysis") or ""),
                        str(render_vars.get("next_watch") or ""),
                        str(render_vars.get("risks") or ""),
                    )
                    if section.strip()
                ]
            ),
            grounding_text=llm_grounding_text,
        )
        verifier_claims = (
            verifier_result.get("unsupported_claims")
            if isinstance(verifier_result, dict)
            else []
        )
        if isinstance(verifier_claims, list) and verifier_claims:
            redact_keys = (
                "summary",
                "highlights",
                "analysis",
                "investment_summary",
                "investment_thesis",
                "valuation",
                "conclusion",
                "impact_analysis",
                "next_watch",
                "risks",
            )
            for key in redact_keys:
                value = render_vars.get(key)
                if isinstance(value, str) and value.strip():
                    render_vars[key] = _apply_verifier_redactions(value, verifier_claims)
        verifier_text_after_redaction = "\n".join(
            [
                str(render_vars.get("summary") or ""),
                str(render_vars.get("highlights") or ""),
                str(render_vars.get("analysis") or ""),
                str(render_vars.get("investment_summary") or ""),
                str(render_vars.get("investment_thesis") or ""),
                str(render_vars.get("valuation") or ""),
                str(render_vars.get("conclusion") or ""),
                str(render_vars.get("impact_analysis") or ""),
                str(render_vars.get("next_watch") or ""),
                str(render_vars.get("risks") or ""),
            ]
        )
        unresolved_verifier_claims = (
            _compute_unresolved_unsupported_claims(verifier_text_after_redaction, verifier_claims)
            if isinstance(verifier_claims, list)
            else []
        )
        if isinstance(verifier_result, dict):
            verifier_result["unresolved_unsupported_claims"] = unresolved_verifier_claims

        synth_runtime: dict[str, Any] = {
            **build_runtime(mode="llm", fallback=False, retry_attempts=retry_attempts),
            "keys": sorted(render_vars.keys()),
        }
        if isinstance(verifier_result, dict):
            synth_runtime["verifier_enabled"] = bool(verifier_result.get("enabled"))
            synth_runtime["verifier_checked"] = bool(verifier_result.get("checked"))
            synth_runtime["verifier_unsupported_count"] = (
                len(verifier_claims) if isinstance(verifier_claims, list) else 0
            )
            synth_runtime["verifier_unresolved_unsupported_count"] = (
                len(unresolved_verifier_claims) if isinstance(unresolved_verifier_claims, list) else 0
            )

        trace.update({"synthesize_runtime": synth_runtime})
        merged_artifacts = {**(state.get("artifacts") or {}), "render_vars": render_vars}
        if isinstance(verifier_result, dict):
            merged_artifacts["verifier_result"] = verifier_result
        if isinstance(verifier_claims, list) and verifier_claims:
            await emit_event(
                {
                    "type": "decision_note",
                    "scope": "verifier",
                    "title": "Verifier unsupported claims",
                    "reason": "Unsupported factual claims were identified in synthesis output.",
                    "impact": f"unsupported_claims={len(verifier_claims)}",
                    "timestamp": utc_now_iso(),
                }
            )
        await _emit_synth_stage_done(status="done", message="Synthesize completed")
        return {"artifacts": merged_artifacts, "trace": trace}
    except Exception as exc:
        retryable = is_rate_limit_error(exc)
        logger.warning("[Synthesize] LLM call failed; falling back to stub")
        append_failure(
            trace,
            node="synthesize",
            stage="llm_call",
            error=type(exc).__name__,
            fallback="synthesize_stub",
            retryable=retryable,
            retry_attempts=retry_attempts,
        )
        await emit_event(
            {
                "type": "thinking",
                "stage": "llm_call_error",
                "message": "synthesize failed; fallback to stub",
                "timestamp": utc_now_iso(),
            }
        )
        render_vars = _stub_render_vars(state)
        trace.update(
            {
                "synthesize_runtime": build_runtime(
                    mode="llm",
                    fallback=True,
                    reason="llm_output_invalid",
                    retry_attempts=retry_attempts,
                )
            }
        )
        await _emit_synth_stage_done(
            status="error",
            message="Synthesize failed, fallback to stub",
            error=type(exc).__name__,
        )
        return {"artifacts": {**(state.get("artifacts") or {}), "render_vars": render_vars}, "trace": trace}

__all__ = ["synthesize", "RenderVars"]
