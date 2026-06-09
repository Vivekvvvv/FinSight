# -*- coding: utf-8 -*-
"""What Changed Service - 识别最重要的变化"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Literal

from backend.services import timeline_service, research_notes
from backend.services.report_index import get_report_index_store
from backend.services.memory import MemoryService

ChangeType = Literal["price", "news", "risk", "report", "alert", "evidence", "portfolio", "note"]
Severity = Literal["low", "medium", "high", "critical"]

# 全局 memory service 实例
_memory_service = MemoryService()


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


def _hours_ago(dt: datetime | None) -> float:
    """计算距离现在多少小时"""
    if not dt:
        return float("inf")
    return (_now_utc() - dt).total_seconds() / 3600


def _score_severity(severity: str) -> int:
    """Severity 评分"""
    mapping = {
        "critical": 50,
        "high": 35,
        "medium": 20,
        "low": 10,
    }
    return mapping.get(str(severity).lower(), 0)


def _score_recency(hours: float) -> int:
    """时间新鲜度评分"""
    if hours <= 24:
        return 15
    if hours <= 72:
        return 8
    return 0


def _collect_timeline_changes(
    session_id: str,
    user_id: str,
    symbol: str | None,
    watchlist_symbols: list[str],
    portfolio_symbols: list[str],
) -> list[dict[str, Any]]:
    """从 Timeline 事件中提取变化"""
    changes = []

    # 获取最近 72 小时的事件
    from_date = (_now_utc() - timedelta(hours=72)).isoformat()

    # 如果指定 symbol，只看这个标的
    symbols_to_check = [symbol] if symbol else (watchlist_symbols + portfolio_symbols)

    for sym in symbols_to_check[:10]:  # 最多检查 10 个标的
        events = timeline_service.get_timeline(
            symbol=sym,
            session_id=session_id,
            user_id=user_id,
            from_date=from_date,
            limit=20,
        )

        for event in events:
            severity = event.get("severity", "low")
            if severity not in ("high", "critical"):
                continue  # 只关注高严重度事件

            occurred_at = _parse_iso_safe(event.get("occurred_at"))
            hours = _hours_ago(occurred_at)

            score = _score_severity(severity) + _score_recency(hours)

            # 持仓标的加权
            if sym in portfolio_symbols:
                score += 20

            # Watchlist 优先级加权（待实现）
            if sym in watchlist_symbols:
                score += 10

            change = {
                "id": f"timeline_{event['id']}",
                "symbol": sym,
                "change_type": event.get("event_type", "evidence"),
                "title": event.get("title", "未命名事件"),
                "severity": severity,
                "reason": event.get("summary", ""),
                "target_route": event.get("target_route", f"/timeline/{sym}"),
                "evidence": event.get("evidence"),
                "score": score,
                "occurred_at": event.get("occurred_at"),
            }
            changes.append(change)

    return changes


def _collect_report_changes(
    session_id: str,
    watchlist_symbols: list[str],
    portfolio_symbols: list[str],
) -> list[dict[str, Any]]:
    """从报告质量和时效中提取变化"""
    changes = []
    store = get_report_index_store()

    # 获取所有报告（包括 blocked 的，因为质量问题本身就是变化）
    reports = store.list_reports(session_id=session_id, limit=100, include_blocked=True)

    for rpt in reports:
        ticker = rpt.get("ticker")
        if not ticker:
            continue

        # 只关注 watchlist/portfolio 相关报告
        if ticker not in watchlist_symbols and ticker not in portfolio_symbols:
            continue

        score = 0
        reasons = []

        # 规则 1: 质量状态恶化
        quality_state = rpt.get("quality_state", "pass")
        if quality_state == "block":
            score += 40
            reasons.append("质量状态为 blocked")
        elif quality_state == "warn":
            score += 25
            reasons.append("质量状态为 warning")

        # 规则 2: 引用质量低
        citation_quality = rpt.get("citation_quality")
        if citation_quality == "low":
            score += 20
            reasons.append("引用质量低")

        # 规则 3: 数据时效性
        freshness_status = rpt.get("freshness_status")
        if freshness_status == "stale":
            score += 25
            reasons.append("数据已过期")
        elif freshness_status == "aging":
            score += 15
            reasons.append("数据正在老化")

        # 规则 4: review_status
        review_status = rpt.get("review_status")
        if review_status == "watch":
            score += 15
            reasons.append("标记为需复查")

        # 持仓标的加权
        if ticker in portfolio_symbols:
            score += 20

        if score >= 20:  # 阈值：至少 20 分才算变化
            severity = "critical" if score >= 50 else "high" if score >= 35 else "medium"

            change = {
                "id": f"report_{rpt['report_id']}",
                "symbol": ticker,
                "change_type": "report",
                "title": f"{ticker} 报告需要复查",
                "severity": severity,
                "reason": "、".join(reasons) + "。",
                "target_route": f"/reports?highlight={rpt['report_id']}",
                "evidence": {
                    "quality_state": quality_state,
                    "freshness_status": freshness_status,
                    "citation_quality": citation_quality,
                },
                "score": score,
                "report_id": rpt["report_id"],
            }
            changes.append(change)

    return changes


def _collect_note_changes(
    session_id: str,
    user_id: str,
    watchlist_symbols: list[str],
    portfolio_symbols: list[str],
) -> list[dict[str, Any]]:
    """从研究笔记中提取变化"""
    changes = []

    # 获取最近 24 小时的笔记
    from_date = (_now_utc() - timedelta(hours=24)).isoformat()

    for sym in (watchlist_symbols + portfolio_symbols)[:10]:
        events = timeline_service.get_timeline(
            symbol=sym,
            session_id=session_id,
            user_id=user_id,
            event_type="note",
            from_date=from_date,
            limit=5,
        )

        for event in events:
            occurred_at = _parse_iso_safe(event.get("occurred_at"))
            hours = _hours_ago(occurred_at)

            if hours > 24:
                continue

            score = 20 + _score_recency(hours)

            if sym in portfolio_symbols:
                score += 20

            change = {
                "id": f"note_{event['related_note_id']}",
                "symbol": sym,
                "change_type": "note",
                "title": f"{sym} 新增研究笔记",
                "severity": "medium",
                "reason": f"你在 {event.get('title', '未命名笔记')} 中记录了新假设，建议复查证据。",
                "target_route": f"/notes?ticker={sym}",
                "evidence": None,
                "score": score,
                "occurred_at": event.get("occurred_at"),
            }
            changes.append(change)

    return changes


def _deduplicate_changes(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """去重：同一 change_type + symbol 只保留最高分"""
    seen: dict[str, dict[str, Any]] = {}

    for change in changes:
        key = f"{change['change_type']}:{change.get('symbol', 'global')}"

        if key not in seen or change["score"] > seen[key]["score"]:
            seen[key] = change

    return list(seen.values())


def get_what_changed(
    *,
    session_id: str,
    user_id: str,
    symbol: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    获取最重要的变化列表

    Args:
        session_id: 会话 ID
        user_id: 用户 ID
        symbol: 可选，只看某个标的的变化
        limit: 返回数量上限，默认 5

    Returns:
        按重要性排序的变化列表
    """
    # 获取 watchlist 和 portfolio
    watchlist = _memory_service.list_watchlist_items(user_id)
    watchlist_symbols = [item["ticker"] for item in watchlist if item.get("ticker")]

    # TODO: 获取 portfolio symbols（需要 portfolio_store 支持）
    portfolio_symbols: list[str] = []

    # 收集候选变化
    all_changes: list[dict[str, Any]] = []

    # 1. Timeline 事件变化
    all_changes.extend(
        _collect_timeline_changes(
            session_id, user_id, symbol, watchlist_symbols, portfolio_symbols
        )
    )

    # 2. 报告质量变化
    if not symbol:  # 报告变化是全局的
        all_changes.extend(
            _collect_report_changes(session_id, watchlist_symbols, portfolio_symbols)
        )

    # 3. 研究笔记变化
    all_changes.extend(
        _collect_note_changes(session_id, user_id, watchlist_symbols, portfolio_symbols)
    )

    # 去重
    deduplicated = _deduplicate_changes(all_changes)

    # 按 score 倒序排序
    deduplicated.sort(key=lambda x: x["score"], reverse=True)

    # 限制数量
    top_changes = deduplicated[:limit]

    # 清理内部字段
    for change in top_changes:
        change.pop("score", None)

    return top_changes
