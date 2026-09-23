# -*- coding: utf-8 -*-
"""Conversation ContextManager Tests"""
from __future__ import annotations

from backend.conversation.context import ContextManager


def test_extract_selection_index_ascii_digits():
    """clarification 待选时用户回 '1'/'第1个'/'第 2 个' 应解析为序号。
    r\"...\\s...\\b...\" 原始字符串里的双反斜杠让正则去匹配字面
    backslash+'s'/'b'，永远命中不了正常输入——数字分支整体失效，
    只有中文数字（第\"一\"）走 cn_map 兜底。"""
    cm = ContextManager()
    assert cm._extract_selection_index("选第1个") == 0
    assert cm._extract_selection_index("第 2 个") == 1
    assert cm._extract_selection_index("2") == 1
    assert cm._extract_selection_index("第1") == 0


def test_extract_selection_index_chinese_numerals_still_work():
    """中文数字分支（cn_map）不应被修复破坏。"""
    cm = ContextManager()
    assert cm._extract_selection_index("第二个") == 1
    assert cm._extract_selection_index("三") == 2
    assert cm._extract_selection_index("没有序号") is None
