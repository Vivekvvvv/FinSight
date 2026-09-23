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


def test_market_hint_cjk_single_char_does_not_match_compound_words():
    """R29: '深'/'沪' 单字 key 撞上 '深度/深入' 等常用词 → market_hint=CN
    且 market_preference 持久化，污染后续轮次的公司记忆与候选选择。"""
    cm = ContextManager()
    assert cm._extract_market_hint("深度分析苹果公司的财报") is None
    assert cm._extract_market_hint("深入研究一下TSLA") is None
    # 正例：真实市场词仍命中
    assert cm._extract_market_hint("深市有哪些机会") == "CN"
    assert cm._extract_market_hint("沪深300走势") == "CN"
    assert cm._extract_market_hint("上证指数") == "CN"


def test_market_hint_ascii_keys_need_word_boundary():
    """R29: ASCII key 裸子串 — 'us'⊂'discuss'、'eu'⊂'queue'、
    'adr'⊂'adrian'、'.t'⊂'.txt' 都把无关英文误判成市场偏好。"""
    cm = ContextManager()
    assert cm._extract_market_hint("discuss the outlook") is None
    assert cm._extract_market_hint("queue the jobs report") is None
    assert cm._extract_market_hint("ask Adrian about fees") is None
    assert cm._extract_market_hint("open file.txt") is None
    # 正例：独立词/代码后缀仍命中
    assert cm._extract_market_hint("us stocks today") == "US"
    assert cm._extract_market_hint("EU regulation news") == "EU"
    assert cm._extract_market_hint("vod.l 走势") == "UK"
    assert cm._extract_market_hint("600519.ss 分析") == "CN"


def test_false_market_hint_does_not_skip_company_memory():
    """端到端危害：先记 AAPL(US)，'深度分析苹果' 的假 CN hint 会让
    _apply_company_memory 跳过记忆 → ticker 不注入，下游按新公司处理。"""
    cm = ContextManager()
    cm._remember_company("苹果", "AAPL", {"matches": [{"symbol": "AAPL", "primaryExchange": "NASDAQ"}]})
    out = cm.preprocess_query("深度分析苹果的财报")
    assert "AAPL" in out["query"]
    assert out["market_hint"] is None
