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
    watched_tickers = set(t.upper() for t in watchlist_tickers + portfolio_tickers if t)

    candidates: list[tuple[int, dict[str, Any]]] = []  # (priority_score, report)

    for report in all_reports:
        score = 0
        reasons: list[str] = []

        # 规则1: review_status = 'watch' → +50
        if report.get("review_status") == "watch":
            score += 50
            reasons.append("手动标记关注")

        # 规则2: freshness_status != 'live' → +30
        freshness = report.get("freshness_status")
        if freshness and freshness != "live":
            score += 30
            reasons.append(f"数据状态: {freshness}")

        # 规则3: quality_state 问题 → +40 (block) / +20 (warn)
        quality_state = report.get("quality_state")
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
        ticker = str(report.get("ticker") or "").upper()
        if as_of_str and ticker in watched_tickers:
            try:
                as_of_dt = datetime.fromisoformat(as_of_str.replace("Z", "+00:00"))
                # naive as_of（如纯日期串 "2025-12-31"）与 aware stale_threshold 比较会抛 TypeError，补齐 UTC 时区。
                if as_of_dt.tzinfo is None:
                    as_of_dt = as_of_dt.replace(tzinfo=timezone.utc)
                if as_of_dt < stale_threshold:
                    days_old = (now - as_of_dt).days
                    score += 25
                    reasons.append(f"数据超过 {days_old} 天")
            except (ValueError, AttributeError, TypeError):
                pass

        # 只返回有评分的报告
        if score > 0:
            report["_review_reasons"] = reasons
            report["_review_score"] = score
            candidates.append((score, report))

    # 按评分降序排序
    candidates.sort(key=lambda x: x[0], reverse=True)

    return [report for _, report in candidates[:limit]]
