# -*- coding: utf-8 -*-
"""RenderVars model + deterministic stub render-vars builder extracted from synthesize.py."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from backend.graph.nodes.compare_gate import should_render_compare
from backend.graph.executor import summarize_selection
from backend.graph.json_utils import json_dumps_safe
from backend.graph.state import GraphState
from backend.utils.strict_json import json_loads_strict


class RenderVars(BaseModel):
    """
    Template injection variables (Phase 4/5).

    NOTE: Keep this model permissive (extra=ignore) so we can evolve templates
    without breaking older model outputs.
    """

    model_config = ConfigDict(extra="ignore")

    # common-ish
    risks: str = ""
    conflict_disclosure: str = ""

    # news
    news_summary: str = ""
    impact_analysis: str = ""
    next_watch: str = ""

    # company
    conclusion: str = ""
    investment_summary: str = ""
    investment_thesis: str = ""
    company_overview: str = ""
    catalysts: str = ""
    valuation: str = ""
    price_snapshot: str = ""
    technical_snapshot: str = ""
    comparison_conclusion: str = ""
    comparison_metrics: str = ""

    # filing/doc
    summary: str = ""
    highlights: str = ""
    analysis: str = ""


def _stub_render_vars(state: GraphState) -> dict[str, str]:
    subject = state.get("subject") or {}
    subject_type = subject.get("subject_type") or "unknown"
    query = (state.get("query") or "").strip()
    operation = (state.get("operation") or {}).get("name") or "qa"
    output_mode = state.get("output_mode") or "brief"

    selection_payload = subject.get("selection_payload") if isinstance(subject, dict) else None
    selection_payload = selection_payload if isinstance(selection_payload, list) else []

    selection_summary = summarize_selection({"selection": selection_payload, "query": query})

    artifacts = state.get("artifacts") or {}
    step_results = artifacts.get("step_results") if isinstance(artifacts, dict) else None
    plan_ir = state.get("plan_ir") or {}
    steps = plan_ir.get("steps") if isinstance(plan_ir, dict) else None
    step_index = {s.get("id"): s for s in (steps or []) if isinstance(s, dict) and s.get("id")}

    def _get_tool_output(tool_name: str) -> Any:
        if not isinstance(step_results, dict) or not step_results:
            return None
        for step_id, item in step_results.items():
            if not isinstance(item, dict):
                continue
            output = item.get("output")
            if isinstance(output, dict) and output.get("skipped"):
                continue
            step = step_index.get(step_id) or {}
            if step.get("kind") == "tool" and step.get("name") == tool_name:
                return output
        return None

    def _get_agent_output(agent_name: str) -> dict[str, Any] | None:
        """Read a successful agent's output dict from step_results."""
        if not isinstance(step_results, dict) or not step_results:
            return None
        for step_id, item in step_results.items():
            if not isinstance(item, dict):
                continue
            output = item.get("output")
            if isinstance(output, dict) and output.get("skipped"):
                continue
            step = step_index.get(step_id) or {}
            if step.get("kind") == "agent" and step.get("name") == agent_name:
                return output if isinstance(output, dict) else None
        return None

    # --- Cross-agent conflict collection & arbitration ---
    # Comparable-claim matrix: pairs of agents whose outputs can logically conflict.
    # Each tuple: (agent_a, agent_b, comparable_topic)
    _COMPARABLE_PAIRS: list[tuple[str, str, str]] = [
        ("technical_agent", "fundamental_agent", "方向判断"),
        ("technical_agent", "news_agent", "价格动量 vs 事件冲击"),
        ("technical_agent", "price_agent", "技术信号 vs 实际走势"),
        ("fundamental_agent", "news_agent", "基本面 vs 事件影响"),
        ("fundamental_agent", "macro_agent", "个股基本面 vs 宏观环境"),
        ("news_agent", "macro_agent", "事件情绪 vs 宏观周期"),
        ("price_agent", "news_agent", "价格走势 vs 新闻情绪"),
        ("macro_agent", "technical_agent", "宏观趋势 vs 技术信号"),
    ]

    def _collect_conflict_disclosure() -> str:
        """
        Trigger formula:
          detect = deep_report || (success_agents >= 2 && comparable_claims >= 1)

        - deep_report: output_mode == 'investment_report'
        - success_agents: agents that returned non-skipped dict output
        - comparable_claims: number of comparable agent pairs with both sides successful

        Edge cases:
        - 0 successful agents  → skip entirely
        - 1 successful agent   → if deep_report, emit "冲突检测降级（证据不足）"
        - Single price query   → skip (handled by success_agents < 2)
        """
        all_agent_names = ("price_agent", "news_agent", "fundamental_agent", "technical_agent", "macro_agent")

        # 1) Count successful agents and collect their outputs
        success_outputs: dict[str, dict[str, Any]] = {}
        for aname in all_agent_names:
            a_out = _get_agent_output(aname)
            if isinstance(a_out, dict) and a_out.get("summary"):
                success_outputs[aname] = a_out
        success_count = len(success_outputs)

        # 2) Count comparable claims (pairs where both sides succeeded)
        comparable_claims_count = 0
        comparable_topics: list[str] = []
        for agent_a, agent_b, topic in _COMPARABLE_PAIRS:
            if agent_a in success_outputs and agent_b in success_outputs:
                comparable_claims_count += 1
                comparable_topics.append(topic)

        # 3) Determine if this is a deep report
        is_deep_report = output_mode == "investment_report"

        # 4) Apply trigger formula: detect = deep_report || (success >= 2 && comparable >= 1)
        should_detect = is_deep_report or (success_count >= 2 and comparable_claims_count >= 1)

        if not should_detect:
            return ""

        # 5) Edge case: deep report with only 1 agent → degraded mode
        if is_deep_report and success_count <= 1:
            return (
                "**冲突检测降级（证据不足）：**\n\n"
                f"仅 {success_count} 个智能体成功返回数据，"
                "无法执行跨维度交叉验证。建议：\n"
                "- 检查数据源连通性（API Key、网络）\n"
                "- 重试以获取更多智能体输出\n"
                "- 当前结论仅基于单一维度，可信度受限\n"
            )

        # 6) Collect actual conflict_flags and conflicting_claims from successful agents
        all_flags: list[str] = []
        all_claims: list[dict[str, Any]] = []
        for aname, a_out in success_outputs.items():
            flags = a_out.get("conflict_flags")
            if isinstance(flags, list):
                for f in flags:
                    if isinstance(f, str) and f.strip():
                        all_flags.append(f"[{aname.replace('_agent', '')}] {f.strip()}")
            claims = a_out.get("conflicting_claims")
            if isinstance(claims, list):
                for c in claims:
                    if isinstance(c, dict):
                        all_claims.append({**c, "_agent": aname})

        # 7) Build disclosure text
        lines: list[str] = []

        # Header with detection context
        detection_basis = "深度研报模式" if is_deep_report else f"{success_count} 个智能体成功 + {comparable_claims_count} 组可比命题"
        lines.append(f"**冲突检测（{detection_basis}）：**")
        lines.append("")

        if not all_claims:
            # No conflicts found — positive signal
            lines.append(f"✅ 已完成 {comparable_claims_count} 组跨维度交叉验证，未发现显著数据冲突。")
            if comparable_topics:
                lines.append(f"   验证维度：{', '.join(comparable_topics[:6])}")
            return "\n".join(lines)

        lines[0] = f"**跨智能体数据冲突（共 {len(all_claims)} 项，检测基础：{detection_basis}）：**"
        lines.append("")

        for idx, claim in enumerate(all_claims[:8], 1):
            agent_label = str(claim.get("_agent", "")).replace("_agent", "")
            topic = claim.get("claim", "未知")
            src_a = claim.get("source_a", "?")
            val_a = claim.get("value_a", "?")
            src_b = claim.get("source_b", "?")
            val_b = claim.get("value_b", "?")
            severity = claim.get("severity", "medium")
            resolved = claim.get("resolved", False)
            resolution = claim.get("resolution", "")

            severity_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(severity, "⚪")
            status = f"✅ {resolution}" if resolved and resolution else "❓ 待进一步验证"

            lines.append(f"{idx}. {severity_icon} **{topic}**（{agent_label}）")
            lines.append(f"   - {src_a}: {val_a}")
            lines.append(f"   - {src_b}: {val_b}")
            lines.append(f"   - 裁决: {status}")
            lines.append("")

        unresolved = [c for c in all_claims if not c.get("resolved", False)]
        if unresolved:
            lines.append(f"⚠️ {len(unresolved)} 项冲突未裁决，结论可信度需打折。建议关注后续数据更新。")

        return "\n".join(lines)

    def _fmt_price_snapshot() -> str:
        out = _get_tool_output("get_stock_price")
        if out is not None:
            if isinstance(out, (dict, list)):
                return f"- {json_dumps_safe(out, ensure_ascii=False)[:800]}"
            text = str(out).strip()
            return f"- {text}" if text else "- （价格数据为空）"
        # Fallback: use price_agent output when tool not scheduled directly
        agent_out = _get_agent_output("price_agent")
        if isinstance(agent_out, dict) and agent_out.get("summary"):
            return f"- {str(agent_out['summary']).strip()[:500]}"
        return "- （暂无价格数据；如需可启用 live tools）"

    def _fmt_technical_snapshot() -> str:
        out = _get_tool_output("get_technical_snapshot")
        if out is None:
            # Fallback: use technical_agent output when tool not scheduled directly
            agent_out = _get_agent_output("technical_agent")
            if isinstance(agent_out, dict) and agent_out.get("summary"):
                return f"- {str(agent_out['summary']).strip()[:600]}"
            return "- （暂无技术指标；如需可启用 live tools）"

        if isinstance(out, str):
            try:
                out = json_loads_strict(out)
            except Exception:
                out = {"raw": out}

        if not isinstance(out, dict):
            return f"- {str(out)[:800]}"

        if out.get("error"):
            return f"- 技术指标不可用：{out.get('error')}（points={out.get('points','N/A')}）"

        close = out.get("close")
        ma20 = out.get("ma20")
        ma50 = out.get("ma50")
        ma200 = out.get("ma200")
        rsi14 = out.get("rsi14")
        rsi_state = out.get("rsi_state")
        macd = out.get("macd")
        signal = out.get("macd_signal")
        momentum = out.get("momentum")
        trend = out.get("trend")
        as_of = out.get("as_of")

        lines = []
        if as_of:
            lines.append(f"- as_of: {as_of}")
        if close is not None:
            lines.append(f"- close: {close}")
        parts = []
        if ma20 is not None:
            parts.append(f"MA20 {ma20:.2f}" if isinstance(ma20, (int, float)) and not isinstance(ma20, bool) else f"MA20 {ma20}")
        if ma50 is not None:
            parts.append(f"MA50 {ma50:.2f}" if isinstance(ma50, (int, float)) and not isinstance(ma50, bool) else f"MA50 {ma50}")
        if ma200 is not None:
            parts.append(f"MA200 {ma200:.2f}" if isinstance(ma200, (int, float)) and not isinstance(ma200, bool) else f"MA200 {ma200}")
        if parts:
            lines.append("- " + " | ".join(parts))
        if rsi14 is not None:
            if isinstance(rsi14, (int, float)) and not isinstance(rsi14, bool):
                lines.append(f"- RSI(14): {rsi14:.2f} ({rsi_state})")
            else:
                lines.append(f"- RSI(14): {rsi14} ({rsi_state})")
        if macd is not None and signal is not None:
            if (
                isinstance(macd, (int, float))
                and not isinstance(macd, bool)
                and isinstance(signal, (int, float))
                and not isinstance(signal, bool)
            ):
                lines.append(f"- MACD: {macd:.4f} vs signal {signal:.4f} ({momentum})")
            else:
                lines.append(f"- MACD: {macd} vs signal {signal} ({momentum})")
        if trend:
            lines.append(f"- trend: {trend}")
        return "\n".join(lines) if lines else "- （技术指标为空）"

    def _fmt_company_news_summary() -> str:
        out = _get_tool_output("get_company_news")
        if out is None:
            return "- （暂无新闻数据）"

        if isinstance(out, str):
            try:
                out = json_loads_strict(out)
            except Exception:
                out = {"raw": out}

        if isinstance(out, dict):
            maybe = out.get("items") or out.get("news") or out.get("results")
            if isinstance(maybe, list):
                out = maybe

        items: list[dict[str, Any]] = []
        if isinstance(out, list):
            for item in out[:10]:
                if isinstance(item, dict):
                    items.append(item)

        if not items:
            return "- （未获取到相关新闻）"

        lines: list[str] = []
        for item in items[:6]:
            title = item.get("title") or item.get("headline") or "(untitled)"
            url = item.get("url")
            source = item.get("source")
            ts = item.get("published_date") or item.get("published_at") or item.get("datetime")
            meta = " / ".join([x for x in [source, ts] if isinstance(x, str) and x.strip()])
            if isinstance(url, str) and url.strip():
                lines.append(f"- [{title}]({url})" + (f"（{meta}）" if meta else ""))
            else:
                lines.append(f"- {title}" + (f"（{meta}）" if meta else ""))

        return "\n".join(lines) if lines else "- （未获取到相关新闻）"

    # Keep stub output useful and non-placeholder.
    base_risks = "- 注：以上仅供参考，不构成投资建议。"

    if subject_type in ("news_item", "news_set"):
        return RenderVars(
            news_summary=selection_summary,
            impact_analysis="\n".join(
                [
                    "- 结论：基于所选新闻做定性分析（非投资建议）。",
                    "- 影响路径：事件 → 市场预期/情绪 → 业绩预期 → 估值/价格。",
                    f"- 当前操作：`{operation}`；如需更深入，请点击“生成研报”。",
                ]
            ),
            next_watch="\n".join(
                [
                    "- 关注点：后续公告/财报指引、监管进展、竞争对手动态。",
                    "- 验证：价格反应是否与叙事一致（量价、成交量、波动）。",
                ]
            ),
            risks=base_risks,
        ).model_dump()

    if subject_type == "company":
        report_hint = "（研报模式）" if output_mode == "investment_report" else "（快评模式）"
        price_snapshot = _fmt_price_snapshot()
        technical_snapshot = _fmt_technical_snapshot()

        tickers = subject.get("tickers") if isinstance(subject, dict) else None
        tickers = tickers if isinstance(tickers, list) else []

        # --- Agent data extraction helpers (stub-mode enrichment) ---
        def _build_investment_summary_from_agents() -> str:
            """Brief bullet summary of each agent's key finding."""
            lines: list[str] = []
            price_out = _get_agent_output("price_agent")
            if isinstance(price_out, dict) and price_out.get("summary"):
                lines.append(f"- {str(price_out['summary']).strip()[:800]}")
            fund_out = _get_agent_output("fundamental_agent")
            if isinstance(fund_out, dict) and fund_out.get("summary"):
                lines.append(f"- {str(fund_out['summary']).strip()[:800]}")
            tech_out = _get_agent_output("technical_agent")
            if isinstance(tech_out, dict) and tech_out.get("summary"):
                lines.append(f"- {str(tech_out['summary']).strip()[:800]}")
            if not lines:
                lines = [
                    '- 研报为结构化交付物：会更长、更全面，但不等于\u201c必须跑全家桶\u201d。',
                    '- 如果缺少关键证据（财报/新闻/数据），会明确标注缺口。',
                ]
            return "\n".join(lines)

        def _build_investment_thesis() -> str:
            """
            Cross-reference ALL agent outputs to produce a high-value
            investment thesis: directional view, key drivers, and watch-points.
            """
            ticker_label = ", ".join(tickers) if tickers else "标的"
            sections: list[str] = []

            # --- 1. Aggregate signals ---
            bullish_factors: list[str] = []
            bearish_factors: list[str] = []
            neutral_notes: list[str] = []

            # Price agent
            price_out = _get_agent_output("price_agent")
            if isinstance(price_out, dict) and price_out.get("summary"):
                ps = str(price_out["summary"]).strip()
                if "up" in ps.lower() or "上涨" in ps:
                    bullish_factors.append("近期股价呈上行趋势")
                elif "down" in ps.lower() or "下跌" in ps:
                    bearish_factors.append("近期股价承压下行")

            # Technical agent
            tech_out = _get_agent_output("technical_agent")
            tech_trend = ""
            if isinstance(tech_out, dict) and tech_out.get("summary"):
                ts = str(tech_out["summary"]).strip().lower()
                if "overbought" in ts:
                    bearish_factors.append("RSI 显示超买，短期存在回调压力")
                    tech_trend = "超买"
                elif "oversold" in ts:
                    bullish_factors.append("RSI 显示超卖，技术面存在反弹机会")
                    tech_trend = "超卖"
                if "bullish" in ts:
                    bullish_factors.append("MACD 呈多头信号")
                    if not tech_trend:
                        tech_trend = "偏多"
                elif "bearish" in ts:
                    bearish_factors.append("MACD 呈空头信号")
                    if not tech_trend:
                        tech_trend = "偏空"
                if "sideways" in ts:
                    neutral_notes.append("技术面趋势偏横盘震荡")
                    if not tech_trend:
                        tech_trend = "震荡"

            # Fundamental agent
            fund_out = _get_agent_output("fundamental_agent")
            if isinstance(fund_out, dict):
                evidence = fund_out.get("evidence")
                if isinstance(evidence, list):
                    for ev in evidence:
                        if not isinstance(ev, dict):
                            continue
                        meta = ev.get("meta") if isinstance(ev.get("meta"), dict) else {}
                        yoy = meta.get("yoy")
                        text = str(ev.get("text") or "").lower()
                        if isinstance(yoy, (int, float)):
                            if "revenue" in text or "营收" in text:
                                if yoy > 0.05:
                                    bullish_factors.append(f"营收同比增长 {yoy:+.1%}，增长动能良好")
                                elif yoy < -0.05:
                                    bearish_factors.append(f"营收同比下降 {yoy:+.1%}，增长承压")
                            if "net income" in text or "净利润" in text:
                                if yoy > 0.1:
                                    bullish_factors.append(f"净利润同比增长 {yoy:+.1%}，盈利能力改善")
                                elif yoy < -0.1:
                                    bearish_factors.append(f"净利润同比下降 {yoy:+.1%}，盈利能力恶化")

            # Macro agent
            macro_out = _get_agent_output("macro_agent")
            if isinstance(macro_out, dict) and macro_out.get("summary"):
                ms = str(macro_out["summary"]).strip()
                if ms and len(ms) > 20:
                    neutral_notes.append(f"宏观环境：{ms[:600]}")

            # News agent
            news_out = _get_agent_output("news_agent")
            if isinstance(news_out, dict) and news_out.get("summary"):
                ns = str(news_out["summary"]).strip()
                if ns and len(ns) > 20:
                    neutral_notes.append(f"近期事件：{ns[:600]}")

            # --- 2. Determine directional view ---
            bull_count = len(bullish_factors)
            bear_count = len(bearish_factors)
            if bull_count >= bear_count + 2:
                direction = "偏多（Bullish）"
                direction_detail = "多数维度信号偏积极"
            elif bear_count >= bull_count + 2:
                direction = "偏空（Bearish）"
                direction_detail = "多数维度信号偏谨慎"
            elif bull_count > bear_count:
                direction = "中性偏多（Slightly Bullish）"
                direction_detail = "积极信号略占优，但需关注风险因素"
            elif bear_count > bull_count:
                direction = "中性偏空（Slightly Bearish）"
                direction_detail = "谨慎信号略占优，短期不宜激进"
            else:
                direction = "中性（Neutral）"
                direction_detail = "多空信号交织，建议观望或分批操作"

            sections.append(f"**{ticker_label} 综合研判：{direction}**")
            sections.append(f"")
            sections.append(f"{direction_detail}。以下为多维度交叉验证结论：")
            sections.append("")

            # --- 3. Key factors ---
            if bullish_factors:
                sections.append("**利多因素：**")
                for f in bullish_factors[:4]:
                    sections.append(f"- ✅ {f}")
                sections.append("")

            if bearish_factors:
                sections.append("**利空因素：**")
                for f in bearish_factors[:4]:
                    sections.append(f"- ⚠️ {f}")
                sections.append("")

            if neutral_notes:
                sections.append("**背景与参考：**")
                for n in neutral_notes[:3]:
                    sections.append(f"- {n}")
                sections.append("")

            # --- 4. Data quality note ---
            agent_names = ["fundamental_agent", "price_agent", "news_agent", "technical_agent", "macro_agent"]
            coverage: list[str] = []
            for aname in agent_names:
                a_out = _get_agent_output(aname)
                if isinstance(a_out, dict) and a_out.get("confidence"):
                    try:
                        conf = float(a_out["confidence"])
                        label = aname.replace("_agent", "")
                        coverage.append(f"{label} {conf:.0%}")
                    except (ValueError, TypeError):
                        pass
            if coverage:
                sections.append(f"**数据置信度：** {' | '.join(coverage)}")
                sections.append("")

            return "\n".join(sections)

        def _build_company_overview_from_agents() -> str:
            # Try get_company_info tool output first
            info_out = _get_tool_output("get_company_info")
            if isinstance(info_out, dict):
                name = info_out.get("name") or info_out.get("shortName") or ""
                sector = info_out.get("sector") or ""
                industry = info_out.get("industry") or ""
                mkt_cap = info_out.get("marketCap") or info_out.get("market_cap") or ""
                desc = info_out.get("longBusinessSummary") or info_out.get("description") or ""
                lines: list[str] = []
                if name:
                    header_parts = [name]
                    if sector:
                        header_parts.append(sector)
                    if industry:
                        header_parts.append(industry)
                    lines.append("- " + " | ".join(header_parts))
                if mkt_cap:
                    lines.append(f"- Market Cap: {mkt_cap}")
                if desc:
                    lines.append(f"- {str(desc).strip()[:500]}")
                if lines:
                    return "\n".join(lines)
            elif isinstance(info_out, str) and info_out.strip():
                # Tool returned a formatted string (e.g. "Company Profile (AAPL):\n...")
                text = info_out.strip()[:800]
                # Convert each line to bullet format if not already
                lines = []
                for ln in text.splitlines():
                    ln = ln.strip()
                    if not ln:
                        continue
                    if ln.startswith("- "):
                        lines.append(ln)
                    elif ln.startswith("Company Profile"):
                        continue  # skip header line
                    else:
                        lines.append(f"- {ln}")
                if lines:
                    return "\n".join(lines)
            # Fallback: use fundamental_agent summary
            fund_out = _get_agent_output("fundamental_agent")
            if isinstance(fund_out, dict) and fund_out.get("summary"):
                return f"- {str(fund_out['summary']).strip()[:1200]}"
            return "- 公司概况：暂无数据。"

        def _build_catalysts_from_agents() -> str:
            news_out = _get_agent_output("news_agent")
            if isinstance(news_out, dict) and news_out.get("summary"):
                return f"- {str(news_out['summary']).strip()[:1200]}"
            return "\n".join([
                "- 可能催化：财报、产品发布、政策变化、行业景气度变化。",
                "- 将基于新闻/财报证据进一步细化。",
            ])

        def _build_valuation_from_agents() -> str:
            facts_out = _get_tool_output("get_sec_company_facts_quarterly")
            if facts_out is not None:
                if isinstance(facts_out, str):
                    try:
                        facts_out = json_loads_strict(facts_out)
                    except Exception:
                        text = facts_out.strip()
                        if text:
                            return "\n".join(
                                f"- {line.strip()}"
                                for line in text.splitlines()
                                if line.strip()
                            )[:1200]

                if isinstance(facts_out, dict):
                    if facts_out.get("error"):
                        return f"- 财务事实暂不可用：{facts_out.get('error')}"
                    periods = facts_out.get("periods")
                    if isinstance(periods, list) and periods:
                        metric_labels = {
                            "revenue": "营收",
                            "gross_profit": "毛利",
                            "operating_income": "营业利润",
                            "net_income": "净利润",
                            "eps": "EPS",
                            "operating_cash_flow": "经营现金流",
                            "total_assets": "总资产",
                            "total_liabilities": "总负债",
                        }
                        lines: list[str] = []
                        for idx, period in enumerate(periods[:4]):
                            parts: list[str] = []
                            for key, label in metric_labels.items():
                                values = facts_out.get(key)
                                if not isinstance(values, list) or idx >= len(values):
                                    continue
                                value = values[idx]
                                if value is None:
                                    continue
                                if isinstance(value, (int, float)):
                                    if key == "eps":
                                        formatted = f"{value:.2f}"
                                    elif abs(value) >= 1_000_000_000:
                                        formatted = f"{value / 1_000_000_000:.1f}B"
                                    elif abs(value) >= 1_000_000:
                                        formatted = f"{value / 1_000_000:.1f}M"
                                    else:
                                        formatted = f"{value:g}"
                                else:
                                    formatted = str(value)
                                parts.append(f"{label} {formatted}")
                            if parts:
                                lines.append(f"- {period}：{'；'.join(parts[:5])}")
                        source = facts_out.get("source")
                        if source and lines:
                            lines.append(f"- 数据源：{source}")
                        if lines:
                            return "\n".join(lines)
                    rows = (
                        facts_out.get("items")
                        or facts_out.get("facts")
                        or facts_out.get("metrics")
                        or facts_out.get("data")
                    )
                    if isinstance(rows, list):
                        lines: list[str] = []
                        for row in rows[:8]:
                            if not isinstance(row, dict):
                                continue
                            label = row.get("label") or row.get("name") or row.get("metric") or row.get("concept")
                            value = row.get("value") or row.get("val") or row.get("amount")
                            period = row.get("period") or row.get("fy") or row.get("fp") or row.get("date") or row.get("end")
                            unit = row.get("unit") or row.get("unitRef") or ""
                            parts = [str(x).strip() for x in (label, value, unit) if str(x or "").strip()]
                            if parts:
                                suffix = f"（{period}）" if period else ""
                                lines.append(f"- {' '.join(parts)}{suffix}")
                        if lines:
                            return "\n".join(lines)
                    return f"- {json_dumps_safe(facts_out, ensure_ascii=False)[:1200]}"

            fund_out = _get_agent_output("fundamental_agent")
            if isinstance(fund_out, dict):
                # Prefer structured evidence for clean line items
                evidence = fund_out.get("evidence")
                if isinstance(evidence, list) and evidence:
                    lines: list[str] = []
                    for ev in evidence:
                        if not isinstance(ev, dict):
                            continue
                        text = str(ev.get("text") or "").strip()
                        if not text:
                            continue
                        meta = ev.get("meta") if isinstance(ev.get("meta"), dict) else {}
                        yoy = meta.get("yoy")
                        if isinstance(yoy, (int, float)):
                            text += f" (YoY {yoy:+.1%})"
                        lines.append(f"- {text}")
                    if lines:
                        return "\n".join(lines[:10])
                # Fallback to summary but filter out company header
                summary = str(fund_out.get("summary") or "").strip()
                if summary:
                    lines = []
                    for part in summary.split(". "):
                        part = part.strip()
                        if not part:
                            continue
                        # Skip company header parts (name | sector | industry)
                        if "|" in part and any(kw in part for kw in ("Technology", "Consumer", "Healthcare", "Financial")):
                            continue
                        lines.append(f"- {part}")
                    if lines:
                        return "\n".join(lines[:8])
            return "\n".join([
                "- 估值与财务：暂无数据。",
                "- 常见框架：增长 vs 估值倍数、盈利质量、现金流与风险溢价。",
            ])

        if operation == "fetch":
            trace = state.get("trace") if isinstance(state.get("trace"), dict) else {}
            executor_type = (trace.get("executor") or {}).get("type") if isinstance(trace, dict) else None

            news_summary = _fmt_company_news_summary()
            news_missing = any(x in news_summary for x in ("暂无", "未获取到"))
            impact_lines = [
                "- 如需我解读某条新闻对股价/基本面的影响：回复对应标题即可。",
                "- 若你想要“重大新闻”筛选：请指定维度（财报/监管/诉讼/并购/交付等）与时间范围。",
            ]
            if executor_type == "dry_run" and news_missing:
                impact_lines.append("- 注：当前未开启实时工具，无法拉取最新新闻；如需请开启 live tools。")

            return RenderVars(
                news_summary=news_summary,
                conclusion="\n".join(
                    [
                        "- 你想先看哪一条？我可以把事件→影响路径→需要验证的数据点讲清楚。",
                        "- 注：当前未开启实时工具，无法拉取最新新闻；如需请开启 live tools。" if executor_type == "dry_run" and news_missing else "",
                    ]
                ),
                impact_analysis="\n".join(impact_lines),
                next_watch="\n".join(
                    [
                        "- 关注：后续公告/财报指引、交付数据、监管与诉讼进展。",
                        "- 验证：价格反应/成交量/波动是否与叙事一致。",
                    ]
                ),
                risks=base_risks,
            ).model_dump()

        def _parse_comparison_table(text: str) -> dict[str, dict[str, str]]:
            if not text or "Performance Comparison" not in text:
                return {}
            rows: dict[str, dict[str, str]] = {}
            for line in str(text).splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith(("Ticker", "-", "Performance", "Notes")):
                    continue
                parts = stripped.split()
                if len(parts) < 4:
                    continue
                label = " ".join(parts[:-3]).strip()
                if not label:
                    continue
                current = parts[-3]
                ytd = parts[-2]
                one_year = parts[-1]
                rows[label] = {"current": current, "ytd": ytd, "1y": one_year}
            return rows

        def _parse_pct(value: str) -> float | None:
            if not isinstance(value, str):
                return None
            cleaned = value.strip()
            if not cleaned or cleaned.upper() == "N/A":
                return None
            cleaned = cleaned.replace("%", "")
            try:
                return float(cleaned)
            except Exception:
                return None

        if should_render_compare(state):
            metrics = _get_tool_output("get_performance_comparison")
            metrics_text = str(metrics).strip() if metrics is not None else ""
            metrics_missing = metrics is None or not metrics_text
            if metrics_missing:
                metrics_text = ""
            if isinstance(metrics, str) and (
                metrics_text.lower().startswith("get_performance_comparison failed")
                or metrics_text.lower().startswith("get_performance_comparison failed:")
            ):
                metrics_missing = True
                metrics_text = ""

            tickers_list = [str(t).strip().upper() for t in tickers if isinstance(t, str) and str(t).strip()]
            parsed = _parse_comparison_table(metrics_text)

            # Some planner variants may pass a mapping like {"Apple": "AAPL", "Microsoft": "MSFT"}.
            # The tool output then uses the *label* column (Apple/Microsoft) instead of the ticker.
            # Build a reverse lookup so we can match rows robustly.
            label_by_ticker: dict[str, str] = {}
            if isinstance(steps, list):
                for s in steps:
                    if not isinstance(s, dict):
                        continue
                    if s.get("kind") != "tool" or s.get("name") != "get_performance_comparison":
                        continue
                    inputs = s.get("inputs") if isinstance(s.get("inputs"), dict) else {}
                    mapping = inputs.get("tickers") if isinstance(inputs, dict) else None
                    if isinstance(mapping, dict):
                        for label, ticker in mapping.items():
                            if not isinstance(ticker, str):
                                continue
                            ticker_u = ticker.strip().upper()
                            if not ticker_u:
                                continue
                            label_str = label.strip() if isinstance(label, str) and label.strip() else ticker_u
                            label_by_ticker[ticker_u] = label_str
                    break

            def _find_row_for_ticker(ticker: str) -> dict[str, str]:
                if not ticker or not parsed:
                    return {}
                ticker_u = ticker.strip().upper()

                for key, row in parsed.items():
                    if isinstance(key, str) and key.strip().upper() == ticker_u:
                        return row

                label = label_by_ticker.get(ticker_u)
                if isinstance(label, str) and label.strip():
                    label_u = label.strip().upper()
                    for key, row in parsed.items():
                        if isinstance(key, str) and key.strip().upper() == label_u:
                            return row

                return {}

            conclusion_lines: list[str] = []
            metric_lines: list[str] = []
            better_ytd: str | None = None
            better_1y: str | None = None
            if parsed and tickers_list:
                # Prefer displaying the exact tickers from state, in order.
                pairs = []
                for t in tickers_list[:2]:
                    row = _find_row_for_ticker(t)
                    pairs.append((t, row))

                if len(pairs) == 2:
                    t1, r1 = pairs[0]
                    t2, r2 = pairs[1]
                    ytd1, ytd2 = _parse_pct(r1.get("ytd", "")), _parse_pct(r2.get("ytd", ""))
                    one1, one2 = _parse_pct(r1.get("1y", "")), _parse_pct(r2.get("1y", ""))
                    if ytd1 is not None and ytd2 is not None:
                        better_ytd = t1 if ytd1 > ytd2 else t2 if ytd2 > ytd1 else "平"
                        metric_lines.append(f"- YTD：{t1} {r1.get('ytd')} vs {t2} {r2.get('ytd')}")
                    if one1 is not None and one2 is not None:
                        better_1y = t1 if one1 > one2 else t2 if one2 > one1 else "平"
                        metric_lines.append(f"- 1Y：{t1} {r1.get('1y')} vs {t2} {r2.get('1y')}")

            # Add an explicit (non-advice) takeaway to answer "which is better" in this dimension.
            if metric_lines and (better_ytd is not None or better_1y is not None):
                non_tie: list[tuple[str, str]] = []
                if better_ytd and better_ytd != "平":
                    non_tie.append(("YTD", better_ytd))
                if better_1y and better_1y != "平":
                    non_tie.append(("1Y", better_1y))

                if len(non_tie) == 2 and non_tie[0][1] == non_tie[1][1]:
                    conclusion_lines.append(f"- 结论（历史回报维度）：{non_tie[0][1]} 相对更强。")
                elif non_tie:
                    conclusion_lines.append(
                        "- 结论（历史回报维度）："
                        + "；".join([f"{metric} 更强={ticker}" for metric, ticker in non_tie])
                        + "。"
                    )
                else:
                    if better_ytd == "平" and better_1y == "平":
                        conclusion_lines.append("- 结论（历史回报维度）：两者表现接近。")
            else:
                if metrics_missing:
                    conclusion_lines.append("- 结论（历史回报维度）：暂无可用的绩效对比数据。")
                else:
                    conclusion_lines.append("- 结论（历史回报维度）：已执行对比工具，但 YTD/1Y 数据不可用或不足。")

            if metric_lines and isinstance(metrics_text, str) and "fallback" in metrics_text.lower():
                metric_lines.append("- 数据源：used fallback price history（可能不是实时行情）。")

            if not metric_lines:
                metric_lines = ["- （暂无绩效对比数据）" if metrics_missing else "- （绩效对比数据不可用或格式异常）"]

            # Add a brief context line (no hard numbers) to help users answer "worth investing".
            if len(tickers_list) >= 2:
                conclusion_lines.append(
                    f"- 对比视角：{' vs '.join(tickers_list)} 各自的商业模式、竞争壁垒和增长驱动力需结合具体业务分析。"
                )
            conclusion_lines.append("- 更值得投资取决于：时间周期、风险偏好与估值/基本面假设。")

            return RenderVars(
                comparison_conclusion="\n".join(
                    [
                        f"- 对比对象：{' vs '.join(tickers_list) or 'N/A'}",
                        *conclusion_lines,
                    ]
                ),
                comparison_metrics="\n".join(metric_lines),
                risks=base_risks,
            ).model_dump()

        # --- Build conclusion from agent insights ---
        def _build_conclusion_from_agents() -> str:
            """
            Generate a substantive conclusion with actionable insights,
            not just a list of confidence percentages.
            """
            ticker_label = ", ".join(tickers) if tickers else "标的"
            lines: list[str] = []

            # 1) Overall signal summary
            tech_out = _get_agent_output("technical_agent")
            fund_out = _get_agent_output("fundamental_agent")
            price_out = _get_agent_output("price_agent")
            macro_out = _get_agent_output("macro_agent")

            # Technical takeaway
            if isinstance(tech_out, dict) and tech_out.get("summary"):
                ts = str(tech_out["summary"]).strip()
                ts_lower = ts.lower()
                if "overbought" in ts_lower:
                    lines.append(f"**技术面**：{ticker_label} RSI 进入超买区域，短期存在回调概率。建议关注支撑位和成交量变化，若缩量上涨则回调风险加大。")
                elif "oversold" in ts_lower:
                    lines.append(f"**技术面**：{ticker_label} RSI 处于超卖区域，存在技术性反弹可能。关注能否放量突破关键阻力位。")
                elif "sideways" in ts_lower:
                    lines.append(f"**技术面**：{ticker_label} 趋势偏震荡，缺乏明确方向。适合区间操作或等待突破信号。")
                elif "bullish" in ts_lower:
                    lines.append(f"**技术面**：{ticker_label} 技术指标偏多，MACD 呈多头排列。关注能否延续趋势。")
                elif "bearish" in ts_lower:
                    lines.append(f"**技术面**：{ticker_label} 技术指标偏空，注意防范进一步下行风险。")

            # Fundamental takeaway
            if isinstance(fund_out, dict):
                evidence = fund_out.get("evidence")
                if isinstance(evidence, list) and len(evidence) >= 2:
                    growth_signals: list[str] = []
                    for ev in evidence:
                        if not isinstance(ev, dict):
                            continue
                        meta = ev.get("meta") if isinstance(ev.get("meta"), dict) else {}
                        yoy = meta.get("yoy")
                        text = str(ev.get("text") or "")
                        if isinstance(yoy, (int, float)) and abs(yoy) > 0.03:
                            short_label = text.split(":")[0].strip()[:30] if ":" in text else text[:30]
                            growth_signals.append(f"{short_label} (YoY {yoy:+.1%})")
                    if growth_signals:
                        lines.append(f"**基本面**：关键财务指标 — {'; '.join(growth_signals[:3])}。{'整体增长态势良好。' if sum(1 for g in growth_signals if '+' in g) > len(growth_signals) / 2 else '部分指标承压，需关注趋势。'}")

            # Macro context
            if isinstance(macro_out, dict) and macro_out.get("summary"):
                ms = str(macro_out["summary"]).strip()
                if ms and len(ms) > 20:
                    lines.append(f"**宏观环境**：{ms[:600]}")

            # 2) Action items / watch points
            watch_items: list[str] = []
            watch_items.append("关注下一财报季的营收指引和利润率变化")
            if isinstance(tech_out, dict) and tech_out.get("summary"):
                ts_lower = str(tech_out["summary"]).lower()
                if "overbought" in ts_lower or "bearish" in ts_lower:
                    watch_items.append("复查回撤风险和关键技术位，降低结论确定性")
                elif "oversold" in ts_lower or "bullish" in ts_lower:
                    watch_items.append("复查成交量配合和反弹证据，避免仅凭单一技术信号下结论")
            watch_items.append("跟踪行业政策和竞争格局变化")

            if watch_items:
                lines.append("")
                lines.append("**后续关注：**")
                for w in watch_items[:4]:
                    lines.append(f"- {w}")

            if not lines:
                lines = [
                    f"- {report_hint} 查询：{query or 'N/A'}",
                    "- 当前数据不足以给出明确结论，建议补充更多信息源后重新分析。",
                ]
            return "\n".join(lines)

        # --- Build risks from agent outputs ---
        def _build_risks_from_agents() -> str:
            risk_lines: list[str] = []
            for aname in ("fundamental_agent", "technical_agent", "news_agent", "macro_agent"):
                a_out = _get_agent_output(aname)
                if not isinstance(a_out, dict):
                    continue
                agent_risks = a_out.get("risks")
                if isinstance(agent_risks, list):
                    for r in agent_risks:
                        r_text = str(r).strip()[:300]
                        if r_text and r_text not in risk_lines:
                            risk_lines.append(r_text)
            if risk_lines:
                return "\n".join([f"- {r}" for r in risk_lines[:6]])
            return base_risks

        return RenderVars(
            conclusion=_build_conclusion_from_agents(),
            price_snapshot=price_snapshot,
            technical_snapshot=technical_snapshot,
            investment_summary=_build_investment_summary_from_agents(),
            investment_thesis=_build_investment_thesis(),
            company_overview=_build_company_overview_from_agents(),
            catalysts=_build_catalysts_from_agents(),
            valuation=_build_valuation_from_agents(),
            risks=_build_risks_from_agents(),
            conflict_disclosure=_collect_conflict_disclosure(),
        ).model_dump()

    if subject_type in ("filing", "research_doc"):
        return RenderVars(
            summary=selection_summary,
            highlights="\n".join(
                [
                    "- 建议抽取：营收/利润/毛利率、指引、分部表现、一次性项目。",
                    "- 若为公告：关注口径变化、重大事项、潜在法律/监管风险。",
                ]
            ),
            analysis="\n".join(
                [
                    f"- 当前操作：`{operation}`；基于文档内容给出结构化解读与影响路径。",
                    "- 如需更深入章节，请点击“生成研报”。",
                ]
            ),
            risks=base_risks,
        ).model_dump()

    # unknown
    return RenderVars(
        conclusion="\n".join(
            [
                "- (internal) unexpected state: `unknown` subject reached Synthesize.",
                "- Clarify node should have intercepted this request before planning/execution.",
            ]
        ),
        risks=base_risks,
    ).model_dump()
