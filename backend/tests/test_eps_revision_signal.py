# -*- coding: utf-8 -*-
"""R69：_infer_revision_signal 读 "downLast7Days"（大写 D），而 yfinance
eps_revisions 真实列名是 "downLast7days"（base.py docstring：
upLast7days/upLast30days/downLast7days/downLast30days 全小写 days）——
row.get("downLast7Days") 永远 None → down_7 恒 0，近7日下调被静默忽略，
revision_signal 系统性偏正（fundamental_agent 把它渲染进报告并按
"negative" 分支处理）。"""
from __future__ import annotations

from backend.tools.financial import _infer_revision_signal


def test_down_last_7days_counted():
    """仅 downLast7days 有大量下调时应判 negative——旧代码读错键名得 neutral。"""
    rows = [{"upLast7days": 0, "upLast30days": 0, "downLast7days": 9, "downLast30days": 0}]
    assert _infer_revision_signal(rows) == "negative"


def test_down_last_7days_offsets_up_counts():
    """up=6 与 down7=6 应抵消为 neutral——旧代码忽略 down7 → 误判 positive。"""
    rows = [{"upLast7days": 3, "upLast30days": 3, "downLast7days": 6, "downLast30days": 0}]
    assert _infer_revision_signal(rows) == "neutral"


def test_all_four_fields_still_counted():
    """四字段齐算的正/负边界回归保护。"""
    assert _infer_revision_signal(
        [{"upLast7days": 4, "upLast30days": 4, "downLast7days": 1, "downLast30days": 1}]
    ) == "positive"  # score=6
    assert _infer_revision_signal(
        [{"upLast7days": 0, "upLast30days": 0, "downLast7days": 2, "downLast30days": 4}]
    ) == "negative"  # score=-6
    assert _infer_revision_signal(
        [{"upLast7days": 2, "upLast30days": 2, "downLast7days": 1, "downLast30days": 1}]
    ) == "neutral"  # score=2
    assert _infer_revision_signal([]) == "unknown"
