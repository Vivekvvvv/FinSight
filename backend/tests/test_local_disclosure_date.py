# -*- coding: utf-8 -*-
"""R62：local_disclosure._extract_date 零填充即放行——版本号/编号串里的
"2026.13.45" 被格式化成不可能的 ISO 日期写进 filing_date，下游按日期
排序/解析时拿到非法值。合法日期应原样通过，非法匹配应跳过继续找。"""
from __future__ import annotations

import backend.tools.local_disclosure as ld


def test_extract_date_rejects_impossible_iso_month_day():
    assert ld._extract_date("公告版本 2026.13.45 最终稿") is None


def test_extract_date_rejects_zero_month():
    assert ld._extract_date("doc id 2026-00-15 rev") is None


def test_extract_date_accepts_valid_iso():
    assert ld._extract_date("披露日期 2026-03-05 公告") == "2026-03-05"


def test_extract_date_accepts_valid_cn():
    assert ld._extract_date("2026年3月5日 披露") == "2026-03-05"


def test_extract_date_cn_rejects_impossible():
    assert ld._extract_date("编号2026年13月45日") is None


def test_extract_date_skips_invalid_first_match():
    """文本里先出现非法日期、后出现合法日期时，应取后面合法的。"""
    text = "版本 2026.13.45；披露日期 2026-03-05"
    assert ld._extract_date(text) == "2026-03-05"


def test_get_local_market_filings_drops_impossible_filing_date(monkeypatch):
    """端到端：snippet 里的非法日期不得成为 filing_date。"""
    raw = (
        "[贵州茅台年报公告]"
        "(https://static.cninfo.com.cn/finalpage/20260305/121.PDF)\n"
        "版本 2026.13.45 修订稿"
    )
    monkeypatch.setattr(ld, "search", lambda _query: raw)

    payload = ld.get_local_market_filings("600519.SS", limit=3)

    assert payload.get("count", 0) >= 1
    filing = payload["filings"][0]
    assert filing["filing_date"] != "2026-13-45"
    # URL 里的合法日期 20260305 无分隔符不匹配本正则，filing_date 为 None
    assert filing["filing_date"] is None
