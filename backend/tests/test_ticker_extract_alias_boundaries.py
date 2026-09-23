# -*- coding: utf-8 -*-
"""extract_tickers：ASCII 别名子串命中产生幻影标的。

三处别名匹配都用裸子串（无词边界）：
- INDEX_ALIASES（re.IGNORECASE）："dow"⊂"window"/"shadow"、"vix"⊂"vixen"
- CN_TO_TICKER 英文键（大小写敏感）："oil"⊂"soil"/"spoil"、"gold"⊂"goldman"、
  "VIX"⊂"VIXEN"
- COMPANY_MAP 公司名（len>4，query.lower() 子串）："intel"⊂"intelligent"、
  "apple"⊂"pineapple"

幻影 ticker 会进入 metadata['tickers'] → resolve_subject 定错焦点 +
行情/新闻按错误标的拉数据。修复：ASCII 别名一律整词边界匹配；
中文别名保持子串匹配不变。
"""
from __future__ import annotations

from backend.config.ticker_mapping import extract_tickers


def _tickers(query: str) -> list[str]:
    return extract_tickers(query)["tickers"]


class TestIndexAliasBoundaries:
    def test_dow_inside_words_no_phantom(self):
        assert _tickers("the window is broken") == []
        assert _tickers("shadow banking risk") == []
        assert _tickers("a meadow review") == []

    def test_vix_inside_word_no_phantom(self):
        assert _tickers("vixen motors report") == []

    def test_dow_at_boundary_still_matches(self):
        assert "^DJI" in _tickers("dow jones today")
        assert "^DJI" in _tickers("is the dow up")
        assert "^IXIC" in _tickers("nasdaq today")
        assert "^VIX" in _tickers("vix spiking")


class TestCnTickerAsciiKeyBoundaries:
    def test_oil_inside_words_no_phantom(self):
        assert _tickers("check the soil report") == []
        assert _tickers("a spoiled earnings call") == []
        assert _tickers("toilet paper demand") == []

    def test_gold_vix_inside_words_no_phantom(self):
        assert _tickers("goldman sachs earnings") == []
        # "VIXEN" 全大写会被 step2 当作显式 ticker 提取（既有语义，非本 bug）；
        # 本断言只关心不再经 'VIX' 别名幻影出 ^VIX。
        assert "^VIX" not in _tickers("VIXEN motors filing")

    def test_commodity_words_at_boundary_still_match(self):
        assert "GC=F" in _tickers("buy gold now")
        assert "CL=F" in _tickers("crude oil price")
        assert "SI=F" in _tickers("silver outlook")


class TestCompanyNameBoundaries:
    def test_intel_inside_words_no_phantom(self):
        assert _tickers("intelligent investing strategies") == []
        assert _tickers("artificial intelligence etf") == []

    def test_apple_inside_words_no_phantom(self):
        assert _tickers("pineapple juice futures") == []

    def test_company_names_at_boundary_still_match(self):
        assert "INTC" in _tickers("should I buy intel stock")
        assert "AAPL" in _tickers("is apple overvalued")


class TestChineseNamesUnchanged:
    def test_chinese_substring_matching_kept(self):
        assert "^IXIC" in _tickers("纳指行情")
        assert "AAPL" in _tickers("苹果股价")
        assert "^DJI" in _tickers("道琼斯指数走势")
