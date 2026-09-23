# -*- coding: utf-8 -*-
"""authoritative_feeds._extract_tickers：整句 .upper() 后按 \\b[A-Z]{1,5}\\b 提取。

修复前每个英文单词都被当成 ticker（"what is..."→["WHAT","IS"]、
"should I buy..."→["SHOULD","I"]），为假标的白拉 Yahoo RSS feed；
修复后委托 ticker_mapping.extract_tickers（KNOWN_TICKERS + 全大写显式
输入 + COMMON_WORDS 过滤），行为与全站 ticker 提取一致。
"""
from __future__ import annotations

from backend.tools.authoritative_feeds import _extract_tickers


def test_ordinary_english_words_not_tickers():
    # 修复前：[:2] 取到 ["WHAT","IS"] → 为 "WHAT"/"IS" 拉 Yahoo feed
    assert _extract_tickers("what is the latest market news") == []


def test_pronoun_and_common_words_not_tickers():
    # 修复前 {1,5} 连大写单字母 "I" 都提取 → ["I","WANT"]
    assert _extract_tickers("I want market updates") == []


def test_uppercase_ticker_still_extracted():
    assert _extract_tickers("latest news for AAPL") == ["AAPL"]


def test_lowercase_known_ticker_kept():
    # KNOWN_TICKERS 大小写不敏感——修复前靠整句 upper 才有此召回
    assert "AAPL" in _extract_tickers("aapl earnings preview")


def test_chinese_company_maps_to_feed_ticker():
    # 委托 canonical extractor 后中文名也能定向（修复前提取不到任何 ticker）
    assert _extract_tickers("苹果最新研报") == ["AAPL"]


def test_capped_at_two():
    assert _extract_tickers("AAPL MSFT NVDA TSLA") == ["AAPL", "MSFT"]
