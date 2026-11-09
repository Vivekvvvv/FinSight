# -*- coding: utf-8 -*-
"""Reports To Review 规则引擎

识别需要用户复查的报告：
1. review_status = 'watch'
2. freshness_status != 'live'
3. quality_state = 'warn' | 'block'
4. as_of 超过 N 天且 ticker 在 watchlist/portfolio 中
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from backend.services.report_index import get_report_index_store
from backend.tools._item import iter_dict_items


def get_reports_to_review(
    session_id: str,
    watchlist_tickers: list[str],
    portfolio_tickers: list[str],
    *,
    stale_days: int = 7,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """返回待复查报告列表

    规则：
    1. review_status = 'watch' → 高优先级
    2. freshness_status != 'live' → 数据过期
    3. quality_state in ('warn', 'block') → 质量问题
    4. as_of 超过 stale_days 天 且 ticker 在 watchlist/portfolio → 需刷新

    返回按优先级排序的报告列表
    """
    if limit <= 0:
        return []
    store = get_report_index_store()

    # 获取所有报告（限制 100 条避免过载）
    all_reports = store.list_reports(
        session_id=session_id,
        limit=100,
        include_blocked=True,
    )

    if not all_reports:
        return []

    # 计算时间阈值
    now = datetime.now(timezone.utc)
    stale_threshold = now - timedelta(days=stale_days)

    # 关注的 tickers 集合
    watched_tickers = {t.strip().upper() for t in watchlist_tickers + portfolio_tickers if isinstance(t, str) and t.strip()}

    candidates: list[tuple[int, dict[str, Any]]] = []  # (priority_score, report)

    for report in iter_dict_items(all_reports):
        if (report.get("error") or report.get("success") is False
            or str(report.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            continue
        if not isinstance(report.get("report_id"), str) or not report["report_id"].strip():
            continue
        score = 0
        reasons: list[str] = []

        # 规则1: review_status = 'watch' → +50
        if str(report.get("review_status") or "").strip().lower() == "watch":
            score += 50
            reasons.append("手动标记关注")

        # 规则2: freshness_status != 'live' → +30
        freshness = str(report.get("freshness_status") or "").strip().lower()
        if freshness and freshness != "live":
            score += 30
            reasons.append(f"数据状态: {freshness}")

        # 规则3: quality_state 问题 → +40 (block) / +20 (warn)
        quality_state = str(report.get("quality_state") or "").strip().lower()
        if quality_state == "block":
            score += 40
            reasons.append("质检未通过")
        elif quality_state == "warn":
            score += 20
            reasons.append("质检警告")

        # 规则4: as_of 超过阈值 且 ticker 在关注列表 → +25
        as_of_str = report.get("as_of") or report.get("generated_at")
        # ticker 列可空（宏观/组合级报告 upsert 时显式写 None），get 默认值只对
        # 缺键生效——None.upper() 会让整个待复查接口 500
        ticker = str(report.get("ticker") or "").strip().upper()
        if ticker in watched_tickers:
            try:
                as_of_dt = datetime.fromisoformat(as_of_str.replace("Z", "+00:00"))
                # naive 值按本机时区归一：generated_at 由 ir.py/validator.py 以
                # datetime.now().isoformat()（本地时间）写入，replace(tzinfo=utc)
                # 会把它错当 UTC 后移 +8h，让临界陈旧报告漏判（与 task_router 修复一致）。
                if as_of_dt.tzinfo is None:
                    as_of_dt = as_of_dt.astimezone(timezone.utc)
                if as_of_dt > now:
                    score += 25
                    reasons.append("数据时间在未来，建议刷新")
                elif as_of_dt < stale_threshold:
                    days_old = (now - as_of_dt).days
                    score += 25
                    reasons.append(f"数据超过 {days_old} 天")
            except (ValueError, AttributeError, TypeError):
                score += 25
                reasons.append("数据时间不可用，建议刷新")

        # 只返回有评分的报告
        if score > 0:
            report = dict(report)
            report["_review_reasons"] = reasons
            report["_review_score"] = score
            candidates.append((score, report))

    # 按评分降序排序
    candidates.sort(key=lambda x: x[0], reverse=True)

    return [report for _, report in candidates[:limit]]
