# -*- coding: utf-8 -*-
"""_extract_datetime_from_url：8 位紧凑日期没有边界保护——长数字 ID 内部
的 8 位片段被当成日期（注释写明"requiring separators nearby"但正则没实现）。

如 `?id=1202509234`（10 位数字 ID）→ 误提取 2025-09-23 → 搜索新闻条目被标上
假日期，且可能伪造"近 N 天"新鲜度通过 recent 过滤。
"""
from __future__ import annotations

from datetime import datetime

from backend.tools.news_rss_tools import _extract_datetime_from_url


def test_long_digit_id_not_a_date():
    # 10 位数字 ID 内部的 "20250923" 不是日期
    assert _extract_datetime_from_url("https://x.com/a?id=1202509234") is None
    # 9 位前缀 ID 同理
    assert _extract_datetime_from_url("https://x.com/item/120250923") is None
    # 尾部还带数字 → 仍是 ID 的一部分
    assert _extract_datetime_from_url("https://x.com/p/202509231") is None


def test_standalone_8digit_still_matches():
    # 独立的 8 位段视为日期（保持原意）
    assert _extract_datetime_from_url("https://x.com/id=20250923") == datetime(2025, 9, 23)


def test_separated_date_still_matches():
    assert _extract_datetime_from_url("https://x.com/2025/09/23/story") == datetime(2025, 9, 23)
    assert _extract_datetime_from_url("https://x.com/news-2025-09-23-a") == datetime(2025, 9, 23)


def test_no_date_returns_none():
    assert _extract_datetime_from_url("https://x.com/article/latest") is None
    assert _extract_datetime_from_url("") is None
