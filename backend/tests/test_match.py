# -*- coding: utf-8 -*-
"""conversation/_match.py 词边界 helper 测试——三套边界语义逐点对齐 context.py 既有修复。"""
from __future__ import annotations

from backend.conversation._match import (
    contains_ascii_word,
    contains_name,
    contains_suffix_code,
    contains_symbol,
    has_cjk,
)


def test_has_cjk():
    assert has_cjk("苹果")
    assert has_cjk("深度分析")
    assert not has_cjk("apple")
    assert not has_cjk("")


def test_contains_symbol_token_boundary():
    """R30/R33/R34 同型：ticker/tag 裸子串把无关词误判。"""
    assert not contains_symbol("said bidu please", "AI")
    assert not contains_symbol("the hk one", "T")
    assert not contains_symbol("Australian miner NYSE", "US")   # US⊄AUSTRALIAN
    assert not contains_symbol("Sumitomo Industries", "US")     # US⊄INDUSTRIES
    assert not contains_symbol("October filing", "OTC")         # OTC⊄OCTOBER
    # 正例
    assert contains_symbol("AAPL 的财报", "AAPL")
    assert contains_symbol("us stocks today".upper(), "US")
    assert contains_symbol("AAPL.HK exchange", "AAPL")          # 右侧允许 .HK 后缀
    # 空输入
    assert not contains_symbol("", "AAPL")
    assert not contains_symbol("AAPL", "")


def test_contains_symbol_left_dot_blocked():
    """左界排除 '.' —— 'X.AAPL' 里的 AAPL 不命中（防代码前缀粘连）。"""
    assert not contains_symbol("X.AAPL", "AAPL")


def test_contains_ascii_word():
    """R29/R-类同型：ASCII 词独立成词才命中。"""
    assert not contains_ascii_word("applepie recipe", "apple")
    assert not contains_ascii_word("delllaptop review", "dell")
    assert not contains_ascii_word("discuss the outlook", "us")
    assert not contains_ascii_word("ask Adrian about fees", "adr")
    # 正例
    assert contains_ascii_word("apple earnings today", "apple")
    assert contains_ascii_word("US stocks today", "us")
    assert contains_ascii_word("deep-dive.", "deep-dive")
    assert not contains_ascii_word("", "us")
    assert not contains_ascii_word("text", "")


def test_contains_suffix_code():
    """'.l'/'.t' 代码后缀：左界允许紧贴代码，右界不成词。"""
    assert contains_suffix_code("vod.l 走势", ".l")
    assert not contains_suffix_code("open file.txt", ".t")
    assert not contains_suffix_code("", ".l")
    assert not contains_suffix_code("vod.l", "")


def test_contains_name_dispatch_by_script():
    """公司名按书写系统分流：CJK 子串、ASCII 词界。"""
    assert contains_name("深度分析苹果的财报", "苹果")
    assert not contains_name("applepie recipe", "Apple")
    assert contains_name("apple earnings", "Apple")
    assert contains_name("Apple 财报", "Apple")
    assert not contains_name("", "苹果")
    assert not contains_name("苹果", "")
