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


def test_candidate_symbol_match_requires_token_boundary():
    """R30: _match_candidate_by_symbol 裸子串 — 'AI'⊂'SAID' 先短路命中，
    用户明明说了 BIDU 却返回 AI（symbol 匹配先于 index/market 路径）。"""
    from datetime import datetime
    cm = ContextManager()
    cm.pending_clarification = {
        "company_hint": "某股",
        "candidates": [
            {"symbol": "AI", "primaryExchange": "NYSE"},
            {"symbol": "BIDU", "primaryExchange": "NASDAQ"},
        ],
        "original_query": "查一下某股",
        "intent": "stock",
        "created_at": datetime.now(),
    }
    out = cm._resolve_pending_clarification("said bidu please", None)
    assert out is not None
    assert out["selected_ticker"] == "BIDU"


def test_candidate_symbol_single_letter_inside_word_does_not_match():
    """R30: 'T'⊂'THE' — 用户回 'the hk one' 想选 HK 候选，
    裸子串却把第一个候选 T(NYSE) 短路返回。"""
    from datetime import datetime
    cm = ContextManager()
    cm.pending_clarification = {
        "company_hint": "某股",
        "candidates": [
            {"symbol": "T", "primaryExchange": "NYSE"},
            {"symbol": "0700.HK", "primaryExchange": "HKEX"},
        ],
        "original_query": "查一下某股",
        "intent": "stock",
        "created_at": datetime.now(),
    }
    out = cm._resolve_pending_clarification("the hk one", "HK")
    assert out is not None
    assert out["selected_ticker"] == "0700.HK"


def test_candidate_symbol_exact_single_letter_reply_still_works():
    """R30 正例：用户明确回复 'T' 应精确命中单字母候选。"""
    from datetime import datetime
    cm = ContextManager()
    cm.pending_clarification = {
        "company_hint": "某股",
        "candidates": [
            {"symbol": "T", "primaryExchange": "NYSE"},
            {"symbol": "F", "primaryExchange": "NYSE"},
        ],
        "original_query": "查一下某股",
        "intent": "stock",
        "created_at": datetime.now(),
    }
    out = cm._resolve_pending_clarification("T", None)
    assert out is not None
    assert out["selected_ticker"] == "T"


def test_apply_company_memory_ticker_presence_check_needs_boundary():
    """R33: _apply_company_memory 的 'ticker 已在 query 中' 判断用裸子串——
    记忆 T 后 query 'test 苹果' 里 "T"⊂"TEST" 被判成显式 ticker 提前
    return，排在其后的 苹果→AAPL 记忆永远轮不到注入。"""
    cm = ContextManager()
    cm._remember_company("AT&T", "T", {"matches": [{"symbol": "T", "primaryExchange": "NYSE"}]})
    cm._remember_company("苹果", "AAPL", {"matches": [{"symbol": "AAPL", "primaryExchange": "NASDAQ"}]})
    out = cm._apply_company_memory("test 苹果的财报", None)
    assert "AAPL" in out


def test_apply_company_memory_real_ticker_presence_still_skips_injection():
    """R33 正例：query 已含独立 ticker token 时仍应原样返回（不再注入）。"""
    cm = ContextManager()
    cm._remember_company("苹果", "AAPL", {"matches": [{"symbol": "AAPL", "primaryExchange": "NASDAQ"}]})
    assert cm._apply_company_memory("AAPL 的财报", None) == "AAPL 的财报"


def test_candidate_market_match_us_tag_needs_boundary():
    """R34: _candidate_matches_market 用 `tag in blob` —— 'US'⊂'AUSTRALIAN'、
    'US'⊂'INDUSTRIES'、'OTC'⊂'OCTOBER' 把非美候选误判成 US 并先返回。"""
    cm = ContextManager()
    au = {"symbol": "BHP.AX", "primaryExchange": "ASX", "description": "Australian miner"}
    us = {"symbol": "XYZ", "primaryExchange": "NYSE", "description": "US holdings"}
    assert cm._match_candidate_by_market([au, us], "US") == us

    ind = {"symbol": "SMT.L", "primaryExchange": "LSE", "description": "Sumitomo Industries"}
    assert cm._match_candidate_by_market([ind, us], "US") == us


def test_candidate_market_match_october_not_otc():
    cm = ContextManager()
    uk = {"symbol": "VOD.L", "primaryExchange": "LSE", "description": "October filing date"}
    us = {"symbol": "XYZ", "primaryExchange": "NYSE", "description": "US holdings"}
    assert cm._match_candidate_by_market([uk, us], "US") == us


def test_candidate_market_match_positive_controls():
    cm = ContextManager()
    us_desc = {"symbol": "ABC", "primaryExchange": "XETRA", "description": "US diversified holdings"}
    hk = {"symbol": "0700.HK", "primaryExchange": "HKEX", "description": "Tencent"}
    assert cm._match_candidate_by_market([us_desc], "US") == us_desc
    assert cm._match_candidate_by_market([hk], "HK") == hk
    assert cm._match_candidate_by_market([us_desc], "FR") is None
