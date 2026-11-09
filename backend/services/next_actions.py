# -*- coding: utf-8 -*-
"""Next Actions 推荐引擎

基于规则生成用户下一步操作建议，不做交易建议。
"""
from __future__ import annotations

from typing import Any
from backend.tools._item import iter_dict_items

from backend.utils.quote import safe_float, safe_int


def _safe_priority(value: Any) -> int:
    """把历史数据中的空值或异常值安全归零。"""
    return safe_int(value, 0) or 0


def generate_next_actions(
    portfolio_summary: dict[str, Any] | None,
    watchlist_items: list[dict[str, Any]],
    reports_to_review: list[dict[str, Any]],
    alert_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """生成操作建议列表

    规则：
    1. 持仓亏损 >5% → 建议查看风险
    2. 报告过期 → 建议刷新
    3. 告警触发 → 建议查看
    4. 空 watchlist/portfolio → 建议添加
    5. 高优先级自选 → 建议关注

    返回 action 列表，每项包含：
    - id: 唯一标识
    - type: 操作类型
    - title: 标题
    - reason: 原因说明
    - severity: low/medium/high/critical
    - target_route: 跳转路径
    - related_symbol: 关联代码（可选）
    """
    actions: list[dict[str, Any]] = []
    watchlist_items = [{**w, "ticker": w["ticker"].strip().upper()} for w in iter_dict_items(watchlist_items)
                      if isinstance(w.get("ticker"), str) and w["ticker"].strip()
                      and not w.get("error") and w.get("success") is not False
                      and str(w.get("status") or "").strip().lower() not in {"error", "failed", "unavailable"}]
    reports_to_review = [r for r in iter_dict_items(reports_to_review)
                         if isinstance(r.get("report_id"), str) and r["report_id"].strip()
                         and not r.get("error") and r.get("success") is not False
                         and str(r.get("status") or "").strip().lower() not in {"error", "failed", "unavailable"}]
    alert_events = [r for r in iter_dict_items(alert_events)
                    if not r.get("error") and r.get("success") is not False
                    and str(r.get("status") or "").strip().lower() not in {"error", "failed", "unavailable"}]
    portfolio_summary = dict(portfolio_summary) if isinstance(portfolio_summary, dict) else None
    if portfolio_summary is not None:
        portfolio_summary["positions"] = [{**p, "ticker": p["ticker"].strip().upper()}
                                          for p in iter_dict_items(portfolio_summary.get("positions"))
                                          if isinstance(p.get("ticker"), str) and p["ticker"].strip()
                                          and not p.get("error") and p.get("success") is not False
                                          and str(p.get("status") or "").strip().lower() not in {"error", "failed", "unavailable"}]

    # 规则1：持仓亏损风险检查
    if portfolio_summary and portfolio_summary.get("positions"):
        for pos in portfolio_summary["positions"]:
            ticker = pos.get("ticker", "")
            unrealized_pnl = safe_float(pos.get("unrealized_pnl"))
            cost_basis = safe_float(pos.get("cost_basis"))
            if unrealized_pnl is not None and cost_basis and cost_basis > 0:
                pnl_pct = unrealized_pnl / cost_basis
                if safe_float(pnl_pct * 100) is None:
                    continue
                if pnl_pct < -0.05:  # 亏损超过 5%
                    severity = "high" if pnl_pct < -0.10 else "medium"
                    actions.append({
                        "id": f"risk_{ticker}",
                        "type": "risk_check",
                        "title": f"查看 {ticker} 风险",
                        "reason": f"持仓亏损 {pnl_pct * 100:.1f}%",
                        "severity": severity,
                        "target_route": f"/dashboard/{ticker}",
                        "related_symbol": ticker,
                    })

    # 规则2：报告过期提醒（最多取前 3 个）
    for rpt in reports_to_review[:3]:
        ticker = rpt.get("ticker", "")
        report_id = rpt.get("report_id", "")
        as_of = rpt.get("as_of", "")
        reasons = rpt.get("_review_reasons", [])
        reasons = [reasons] if isinstance(reasons, str) else reasons if isinstance(reasons, list) else []
        reason_text = "；".join(reason.strip() for reason in reasons if isinstance(reason, str) and reason.strip()) or "数据可能过期"
        actions.append({
            "id": f"refresh_{report_id}",
            "type": "refresh_report",
            "title": f"刷新 {ticker} 报告" if ticker else "刷新研究报告",
            "reason": reason_text,
            "severity": "medium",
            "target_route": f"/reports?report_id={report_id}" if report_id else "/reports",
            "related_symbol": ticker if ticker else None,
        })

    # 规则3：告警事件提醒（最多取前 2 个）
    for alert in alert_events[:2]:
        raw_ticker = alert.get("ticker")
        ticker = raw_ticker.strip().upper() if isinstance(raw_ticker, str) else ""
        title = alert.get("title")
        title = title.strip() if isinstance(title, str) else ""
        raw_severity = alert.get("severity")
        severity = raw_severity.strip().lower() if isinstance(raw_severity, str) else "medium"
        if severity not in {"low", "medium", "high", "critical"}:
            severity = "medium"
        actions.append({
            "id": f"alert_{alert.get('id', ticker)}",
            "type": "check_alert",
            "title": f"查看 {ticker} 提醒" if ticker else "查看提醒",
            "reason": title or "触发价格或新闻提醒",
            "severity": severity,
            "target_route": f"/dashboard/{ticker}" if ticker else "/alerts",
            "related_symbol": ticker if ticker else None,
        })

    # 规则4：空 watchlist → 建议添加
    if not watchlist_items:
        actions.append({
            "id": "add_watchlist",
            "type": "add_watchlist",
            "title": "添加自选标的",
            "reason": "建立自选清单，方便每日跟踪",
            "severity": "low",
            "target_route": "/watchlist",
            "related_symbol": None,
        })

    # 规则5：空 portfolio → 建议录入
    if not portfolio_summary or not portfolio_summary.get("positions"):
        actions.append({
            "id": "add_portfolio",
            "type": "add_portfolio",
            "title": "录入持仓组合",
            "reason": "录入持仓后可查看风险与盈亏估算",
            "severity": "low",
            "target_route": "/portfolio",
            "related_symbol": None,
        })

    # 规则6：高优先级自选提醒
    high_priority_watchlist = [w for w in watchlist_items if _safe_priority(w.get("priority")) >= 4]
    high_priority_watchlist.sort(key=lambda w: _safe_priority(w.get("priority")), reverse=True)
    unique_focus = {}
    for w in high_priority_watchlist:
        unique_focus.setdefault(w["ticker"], w)
    high_priority_watchlist = list(unique_focus.values())
    for w in high_priority_watchlist[:2]:
        ticker = w.get("ticker", "")
        raw_reason = w.get("watch_reason")
        reason = raw_reason.strip() if isinstance(raw_reason, str) else ""
        reason = reason or "高优先级标的"
        actions.append({
            "id": f"focus_{ticker}",
            "type": "focus_watchlist",
            "title": f"重点关注 {ticker}",
            "reason": reason,
            "severity": "medium",
            "target_route": f"/dashboard/{ticker}",
            "related_symbol": ticker,
        })

    # 规则7：研究状态队列
    for w in watchlist_items:
        ticker = w.get("ticker", "")
        status = str(w.get("research_status") or "").strip().lower()
        if not ticker or status not in {"new", "watching", "reviewing"}:
            continue
        title_map = {
            "new": f"为 {ticker} 建立初始研究档案",
            "watching": f"复查 {ticker} 的观察假设",
            "reviewing": f"继续推进 {ticker} 的研究复查",
        }
        actions.append({
            "id": f"research_status_{ticker}_{status}",
            "type": "research_review",
            "title": title_map[status],
            "reason": (w["watch_reason"].strip() if isinstance(w.get("watch_reason"), str) else "")
                      or "该标的仍处于研究流程中，需要补充证据或更新结论。",
            "severity": "medium" if status == "reviewing" else "low",
            "target_route": f"/dossier/{ticker}",
            "related_symbol": ticker,
        })

    # 按 severity 排序（critical > high > medium > low）
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    actions.sort(key=lambda a: severity_order.get(a.get("severity", "low"), 99))

    # 最多返回 10 条
    return actions[:10]
