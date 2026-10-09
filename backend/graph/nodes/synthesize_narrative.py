# -*- coding: utf-8 -*-
"""Narrative-mode LLM report drafter extracted from synthesize.py."""
from __future__ import annotations

import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage

from backend.graph.event_bus import emit_event
from backend.graph.failure import append_failure, utc_now_iso
from backend.graph.state import GraphState
from backend.services.llm_retry import ainvoke_with_rate_limit_retry, is_rate_limit_error
from backend.utils.env_config import env_float

logger = logging.getLogger(__name__)

from backend.graph.nodes.hallucination_guards import (
    _apply_verifier_redactions,
    _compute_unresolved_unsupported_claims,
    _scrub_unverified_future_claims,
)
from backend.graph.nodes.synthesize_format import (
    _format_conversation_history_for_synth,
    _format_memory_context_for_synth,
    _format_persona_lens,
)
from backend.graph.nodes.synthesize_verifier import _run_deep_report_verifier


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
