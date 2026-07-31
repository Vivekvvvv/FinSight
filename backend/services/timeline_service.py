# -*- coding: utf-8 -*-
"""Evidence Timeline Service

聚合多个来源的事件，提供统一时间线视图，用于研究过程复盘。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from backend.services import research_notes
from backend.services.report_index import get_report_index_store
from backend.utils.quote import safe_int


EventType = Literal["report", "alert", "note", "risk", "evidence", "watchlist"]


def _parse_iso_or_none(value: Any) -> Optional[datetime]:
    """解析 ISO 时间字符串为 datetime，失败返回 None"""
    if not value:
        return None
    try:
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return None
    except (ValueError, AttributeError):
        return None


def _format_iso(dt: datetime) -> str:
    """格式化 datetime 为 ISO 字符串"""
    return dt.isoformat()


def _collect_report_events(
    symbol: str,
    session_id: str,
    from_dt: Optional[datetime],
    to_dt: Optional[datetime],
) -> list[dict[str, Any]]:
    """从报告索引收集事件"""
    store = get_report_index_store()

    # 获取该 ticker 的所有报告
    reports = store.list_reports(
        session_id=session_id,
        ticker=symbol,
        sort_by="generated_at_desc",
        limit=100,
    )

    events = []
    for report in reports:
        occurred_at = _parse_iso_or_none(report.get("generated_at"))
        if not occurred_at:
            continue

        # 时间范围过滤
        if from_dt and occurred_at < from_dt:
            continue
        if to_dt and occurred_at > to_dt:
            continue

        # 判断严重度
        quality_state = report.get("quality_state")
        confidence = report.get("confidence_score")

        severity = "low"
        if quality_state == "block":
            severity = "critical"
        elif quality_state == "warn":
            severity = "high"
        elif confidence and confidence >= 0.8:
            severity = "medium"

        events.append({
            "id": f"report_{report['report_id']}",
            "symbol": symbol,
            "event_type": "report",
            "title": f"生成报告：{report.get('title', '未命名报告')}",
            "summary": report.get("summary", "")[:200],
            "occurred_at": _format_iso(occurred_at),
            "severity": severity,
            "source": "report_index",
            "target_route": f"/reports?report_id={report['report_id']}",
            "related_report_id": report["report_id"],
            "evidence": {
                "confidence": confidence,
                "citation_count": safe_int(report.get("citation_count"), 0) or 0,
                "freshness_status": report.get("freshness_status"),
                "quality_state": quality_state,
            },
        })

    return events


def _collect_note_events(
    symbol: str,
    session_id: str,
    user_id: str,
    from_dt: Optional[datetime],
    to_dt: Optional[datetime],
) -> list[dict[str, Any]]:
    """从研究笔记收集事件"""
    notes = research_notes.list_notes(
        session_id=session_id,
        user_id=user_id,
        ticker=symbol,
        limit=100,
    )

    events = []
    for note in notes:
        # 使用 updated_at 作为事件时间
        occurred_at = _parse_iso_or_none(note.get("updated_at"))
        if not occurred_at:
            continue

        # 时间范围过滤
        if from_dt and occurred_at < from_dt:
            continue
        if to_dt and occurred_at > to_dt:
            continue

        # 笔记事件通常是中等重要性
        severity = "medium"

        # 如果标签中包含"风险"、"警告"等关键词，提升严重度
        tags = note.get("tags", [])
        if any(keyword in " ".join(tags).lower() for keyword in ["风险", "警告", "问题", "风控"]):
            severity = "high"

        events.append({
            "id": f"note_{note['note_id']}",
            "symbol": symbol,
            "event_type": "note",
            "title": f"研究笔记：{note.get('title', '未命名笔记')}",
            "summary": note.get("content", "")[:200],
            "occurred_at": _format_iso(occurred_at),
            "severity": severity,
            "source": "research_notes",
            "target_route": f"/notes?note_id={note['note_id']}",
            "related_note_id": note["note_id"],
        })

    return events


def get_timeline(
    symbol: str,
    session_id: str,
    user_id: str,
    event_type: Optional[EventType] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """获取指定标的的事件时间线

    Args:
        symbol: 股票代码
        session_id: 会话 ID
        user_id: 用户 ID
        event_type: 事件类型过滤（可选）
        from_date: 开始日期（ISO 格式，可选）
        to_date: 结束日期（ISO 格式，可选）
        limit: 返回数量限制

    Returns:
        事件列表，按 occurred_at 倒序排序
    """
    # 解析时间范围
    from_dt = _parse_iso_or_none(from_date)
    to_dt = _parse_iso_or_none(to_date)

    # 收集所有事件
    all_events: list[dict[str, Any]] = []

    # 根据 event_type 决定收集哪些来源
    if event_type is None or event_type == "report":
        all_events.extend(_collect_report_events(symbol, session_id, from_dt, to_dt))

    if event_type is None or event_type == "note":
        all_events.extend(_collect_note_events(symbol, session_id, user_id, from_dt, to_dt))

    # TODO: 未来添加更多来源
    # if event_type is None or event_type == "alert":
    #     all_events.extend(_collect_alert_events(symbol, ...))
    # if event_type is None or event_type == "risk":
    #     all_events.extend(_collect_risk_events(symbol, ...))

    # 按 occurred_at 倒序排序
    all_events.sort(key=lambda e: e.get("occurred_at", ""), reverse=True)

    # 应用 limit
    return all_events[:limit]
