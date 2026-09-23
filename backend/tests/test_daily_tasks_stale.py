# -*- coding: utf-8 -*-
"""daily_tasks._days_since 对 naive generated_at 必须按本机时区归一。

bug：report_index.generated_at 可为 naive 本地时间（report_generator.py、
report/ir.py、report/validator.py 用 datetime.now().isoformat() 写入——
task_router.py:83 与 reports_to_review.py:89 的修复注释已确认此存储惯例）。
_days_since 直接 aware_now - naive_dt 抛 TypeError，被 except 吞成 None，
调用方落入 "近期研报" 分支——9 天前的过期研报被判成"查看最新"，
"重新分析"任务永不生成。修复与另两处一致：naive 先 astimezone(utc)。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.services.daily_tasks import _days_since, generate_daily_tasks


def test_days_since_naive_local_generated_at_returns_days():
    old_naive_local = (datetime.now() - timedelta(days=9)).isoformat()
    assert _days_since(old_naive_local) is not None
    assert _days_since(old_naive_local) >= 8


def test_days_since_aware_generated_at_unchanged():
    old_aware = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    assert _days_since(old_aware) == 5


def test_days_since_unparseable_returns_none():
    assert _days_since("not-a-date") is None
    assert _days_since(None) is None


def test_stale_report_with_naive_generated_at_yields_reanalyze_task():
    """端到端：naive 过期研报应产出 reanalyze 而非 review 任务。"""
    old_naive_local = (datetime.now() - timedelta(days=9)).isoformat()
    tasks = generate_daily_tasks(
        watchlist=["AAPL"],
        reports=[{"ticker": "AAPL", "generated_at": old_naive_local, "report_id": "r1"}],
    )
    cats = [t["category"] for t in tasks]
    assert "reanalyze" in cats
    assert "review" not in cats
