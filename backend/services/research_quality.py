# -*- coding: utf-8 -*-
"""Research Quality Calibration Service - 研究库健康度校准"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Literal

from backend.services.report_index import get_report_index_store
from backend.services import timeline_service

IssueType = Literal[
    "stale_report",
    "low_citation",
    "blocked_report",
    "warn_report",
    "unreviewed_report",
    "challenged_conclusion",
    "research_hygiene",
    "library_freshness",
]
Severity = Literal["low", "medium", "high", "critical"]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_safe(iso_str: str | None) -> datetime | None:
    """安全解析 ISO 时间字符串"""
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except Exception:
        return None


def _calculate_health_score(summary: dict[str, Any]) -> int:
    """计算健康分数（0-100）"""
    score = 100

    # stale reports 扣分：每个 -5，最多 -25
    stale_count = summary.get("stale_reports", 0)
    score -= min(stale_count * 5, 25)

    # low quality 扣分：每个 -5，最多 -20
    low_quality_count = summary.get("low_quality_reports", 0)
    score -= min(low_quality_count * 5, 20)

    # blocked 扣分：每个 -15
    blocked_count = summary.get("blocked_reports", 0)
    score -= blocked_count * 15

    # warn 扣分：每个 -8
    warn_count = summary.get("warn_reports", 0)
    score -= warn_count * 8

    # challenged conclusions 扣分：每个 -10，最多 -30
    challenged_count = summary.get("challenged_conclusions", 0)
    score -= min(challenged_count * 10, 30)

    # reviewed_rate 低于 50% 扣 10（空库不扣分）
    total_reports = summary.get("total_reports", 0)
    reviewed_rate = summary.get("reviewed_rate", 1.0)
    if total_reports > 0 and reviewed_rate < 0.5:
        score -= 10

    return max(0, min(100, score))


def _collect_stale_reports(
    reports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """识别过期报告"""
    issues = []

    for rpt in reports:
        freshness_status = rpt.get("freshness_status")
        if freshness_status not in ("live", None):
            severity = "high" if freshness_status == "stale" else "medium"

            issue = {
                "id": f"stale-report:{rpt['report_id']}",
                "issue_type": "stale_report",
                "severity": severity,
                "title": f"{rpt.get('ticker', '未知')} 报告已过期",
                "reason": f"报告数据 freshness_status={freshness_status}，建议刷新后复查。",
                "target_route": f"/reports?highlight={rpt['report_id']}",
                "related_symbol": rpt.get("ticker"),
                "related_report_id": rpt["report_id"],
            }
            issues.append(issue)

    return issues


def _collect_low_citation_reports(
    reports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """识别低引用质量报告"""
    issues = []

    for rpt in reports:
        citation_quality = rpt.get("citation_quality")
        if citation_quality == "low":
            issue = {
                "id": f"low-citation:{rpt['report_id']}",
                "issue_type": "low_citation",
                "severity": "medium",
                "title": f"{rpt.get('ticker', '未知')} 报告引用质量低",
                "reason": "报告引用数量不足或引用质量低，建议补充证据来源。",
                "target_route": f"/reports?highlight={rpt['report_id']}",
                "related_symbol": rpt.get("ticker"),
                "related_report_id": rpt["report_id"],
            }
            issues.append(issue)

    return issues


def _collect_quality_issues(
    reports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """识别质量问题报告"""
    issues = []

    for rpt in reports:
        quality_state = rpt.get("quality_state")

        if quality_state == "block":
            issue = {
                "id": f"blocked-report:{rpt['report_id']}",
                "issue_type": "blocked_report",
                "severity": "critical",
                "title": f"{rpt.get('ticker', '未知')} 报告质量阻断",
                "reason": "报告未通过质量检查，存在严重问题，必须修复后才能使用。",
                "target_route": f"/reports?highlight={rpt['report_id']}",
                "related_symbol": rpt.get("ticker"),
                "related_report_id": rpt["report_id"],
            }
            issues.append(issue)

        elif quality_state == "warn":
            issue = {
                "id": f"warn-report:{rpt['report_id']}",
                "issue_type": "warn_report",
                "severity": "high",
                "title": f"{rpt.get('ticker', '未知')} 报告质量警告",
                "reason": "报告存在质量问题，建议复查后使用。",
                "target_route": f"/reports?highlight={rpt['report_id']}",
                "related_symbol": rpt.get("ticker"),
                "related_report_id": rpt["report_id"],
            }
            issues.append(issue)

    return issues


def _collect_unreviewed_reports(
    reports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """识别未复查报告"""
    issues = []
    now = _now_utc()

    for rpt in reports:
        review_status = rpt.get("review_status")
        generated_at = _parse_iso_safe(rpt.get("generated_at"))

        if review_status == "new" and generated_at:
            hours_old = (now - generated_at).total_seconds() / 3600
            if hours_old > 24:
                issue = {
                    "id": f"unreviewed:{rpt['report_id']}",
                    "issue_type": "unreviewed_report",
                    "severity": "low",
                    "title": f"{rpt.get('ticker', '未知')} 报告未复查",
                    "reason": f"报告生成已超过 {int(hours_old)} 小时，尚未标记为已复查。",
                    "target_route": f"/reports?highlight={rpt['report_id']}",
                    "related_symbol": rpt.get("ticker"),
                    "related_report_id": rpt["report_id"],
                }
                issues.append(issue)

    return issues


def _collect_challenged_conclusions(
    reports: list[dict[str, Any]],
    session_id: str,
    user_id: str,
) -> list[dict[str, Any]]:
    """识别被新证据挑战的旧结论"""
    issues = []

    # 按 symbol 分组
    reports_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for rpt in reports:
        ticker = rpt.get("ticker")
        if ticker:
            if ticker not in reports_by_symbol:
                reports_by_symbol[ticker] = []
            reports_by_symbol[ticker].append(rpt)

    # 对每个 symbol，检查最近 7 天的 timeline 事件
    from_date = (_now_utc() - timedelta(days=7)).isoformat()

    for symbol, symbol_reports in reports_by_symbol.items():
        try:
            events = timeline_service.get_timeline(
                symbol=symbol,
                session_id=session_id,
                user_id=user_id,
                from_date=from_date,
                limit=20,
            )

            # 找 high/critical severity 事件
            high_severity_events = [
                e for e in events if e.get("severity") in ("high", "critical")
            ]

            if not high_severity_events:
                continue

            # 找该 symbol 的旧报告（早于最新 high severity 事件）
            for event in high_severity_events:
                event_time = _parse_iso_safe(event.get("occurred_at"))
                if not event_time:
                    continue

                for rpt in symbol_reports:
                    rpt_time = _parse_iso_safe(rpt.get("generated_at"))
                    if rpt_time and rpt_time < event_time:
                        issue = {
                            "id": f"challenged:{rpt['report_id']}",
                            "issue_type": "challenged_conclusion",
                            "severity": "high",
                            "title": f"{symbol} 旧报告可能被新证据挑战",
                            "reason": f"报告生成于 {rpt_time.strftime('%m-%d')}，但 {event_time.strftime('%m-%d')} 出现了 {event.get('severity')} 级别事件：{event.get('title', '未知事件')}。建议复查结论。",
                            "target_route": f"/reports?highlight={rpt['report_id']}",
                            "related_symbol": symbol,
                            "related_report_id": rpt["report_id"],
                        }
                        issues.append(issue)
                        break  # 每个报告只报一次

        except Exception:
            # timeline 查询失败不影响其他逻辑
            continue

    return issues


def _collect_hygiene_issues(
    summary: dict[str, Any],
) -> list[dict[str, Any]]:
    """识别研究卫生问题"""
    issues = []

    total = summary.get("total_reports", 0)
    if total == 0:
        return issues

    # reviewed_rate 低于 50%
    reviewed_rate = summary.get("reviewed_rate", 0)
    if reviewed_rate < 0.5:
        issue = {
            "id": "hygiene:low-reviewed-rate",
            "issue_type": "research_hygiene",
            "severity": "medium",
            "title": "研究复查率偏低",
            "reason": f"当前复查率 {int(reviewed_rate * 100)}%，建议定期复查已生成报告。",
            "target_route": "/reports",
            "related_symbol": None,
            "related_report_id": None,
        }
        issues.append(issue)

    # stale_reports 占比超过 30%
    stale_count = summary.get("stale_reports", 0)
    stale_ratio = stale_count / total if total > 0 else 0
    if stale_ratio > 0.3:
        issue = {
            "id": "hygiene:high-stale-ratio",
            "issue_type": "library_freshness",
            "severity": "high",
            "title": "研究库时效性不足",
            "reason": f"当前 {stale_count}/{total} 份报告数据过期（{int(stale_ratio * 100)}%），建议批量刷新。",
            "target_route": "/reports",
            "related_symbol": None,
            "related_report_id": None,
        }
        issues.append(issue)

    return issues


def get_research_quality(
    *,
    session_id: str,
    user_id: str,
    symbol: str | None = None,
) -> dict[str, Any]:
    """
    获取研究库健康度

    Args:
        session_id: 会话 ID
        user_id: 用户 ID
        symbol: 可选，只看某个标的的质量

    Returns:
        研究质量报告
    """
    store = get_report_index_store()

    # 获取报告（包括 blocked 的，因为要统计质量问题）
    reports = store.list_reports(
        session_id=session_id,
        ticker=symbol,
        limit=500,
        include_blocked=True,
    )

    # 统计摘要
    total_reports = len(reports)

    stale_reports = len([r for r in reports if r.get("freshness_status") == "stale"])
    aging_reports = len([r for r in reports if r.get("freshness_status") == "aging"])

    low_quality_reports = len([r for r in reports if r.get("citation_quality") == "low"])

    blocked_reports = len([r for r in reports if r.get("quality_state") == "block"])
    warn_reports = len([r for r in reports if r.get("quality_state") == "warn"])

    watch_reports = len([r for r in reports if r.get("review_status") == "watch"])

    reviewed_count = len([r for r in reports if r.get("review_status") in ("reviewed", "watch", "archived")])
    reviewed_rate = reviewed_count / total_reports if total_reports > 0 else 0

    summary = {
        "total_reports": total_reports,
        "stale_reports": stale_reports + aging_reports,  # stale + aging 都算过期
        "low_quality_reports": low_quality_reports,
        "blocked_reports": blocked_reports,
        "warn_reports": warn_reports,
        "watch_reports": watch_reports,
        "reviewed_rate": round(reviewed_rate, 2),
        "challenged_conclusions": 0,  # 先设为 0，后面收集后更新
    }

    # 收集问题
    all_issues: list[dict[str, Any]] = []

    all_issues.extend(_collect_stale_reports(reports))
    all_issues.extend(_collect_low_citation_reports(reports))
    all_issues.extend(_collect_quality_issues(reports))
    all_issues.extend(_collect_unreviewed_reports(reports))

    challenged_issues = _collect_challenged_conclusions(reports, session_id, user_id)
    all_issues.extend(challenged_issues)
    summary["challenged_conclusions"] = len(challenged_issues)

    all_issues.extend(_collect_hygiene_issues(summary))

    # 计算健康分数
    summary["health_score"] = _calculate_health_score(summary)

    # 按 severity 排序
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    all_issues.sort(key=lambda x: severity_order.get(x["severity"], 99))

    # 限制 top_issues 数量
    top_issues = all_issues[:10]

    return {
        "success": True,
        "as_of": _now_utc().isoformat(),
        "summary": summary,
        "top_issues": top_issues,
        "next_actions": [],  # 暂不实现
    }
