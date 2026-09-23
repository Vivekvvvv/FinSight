# -*- coding: utf-8 -*-
r"""R65：_fallback_price_value 搜索兜底取首个 \d{3,6}——"S&P 500" 里的
500、年份 2026 都先于真实指数水平命中，错误数字被 _fetch_index_price
直接当现价展示给用户。应优先带千分位/小数的数字并跳过裸年份。"""
from __future__ import annotations

import backend.tools.price_history_providers as php


def _force_search_branch(monkeypatch, text: str):
    monkeypatch.setattr(php, "_map_to_stooq_symbol", lambda _ticker: None)
    monkeypatch.setattr(php, "search", lambda _query: text)


def test_sp500_name_digits_not_picked_over_real_level(monkeypatch):
    """"S&P 500" 的 500 在文本中先于 5,900——旧代码返回 500.0。"""
    _force_search_branch(monkeypatch, "S&P 500 index level today 5,900 pts")
    assert php._fallback_price_value("^GSPC") == 5900.0


def test_year_not_treated_as_price(monkeypatch):
    """"as of 2026-09-23" 的 2026 是年份不是价格。"""
    _force_search_branch(monkeypatch, "as of 2026-09-23 the index level is 5900")
    assert php._fallback_price_value("^GSPC") == 5900.0


def test_bare_year_only_returns_none(monkeypatch):
    """全文只有年份数字时返回 None，而不是拿 2026 当价格。"""
    _force_search_branch(monkeypatch, "published 2026 report, no numbers here")
    assert php._fallback_price_value("^GSPC") is None


def test_bare_level_without_separator_still_works(monkeypatch):
    """无千分位/小数的真实水平（如 18000）仍可提取——回归保护。"""
    _force_search_branch(monkeypatch, "nasdaq composite at 18000 today")
    assert php._fallback_price_value("^IXIC") == 18000.0


def test_comma_number_still_extracted(monkeypatch):
    """既有用例形态回归：带千分位的水平照常提取。"""
    _force_search_branch(monkeypatch, "benchmark index level today: 123,456 points")
    assert php._fallback_price_value("^GSPC") == 123456.0
