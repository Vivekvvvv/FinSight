# -*- coding: utf-8 -*-
"""R62：local_disclosure._extract_date 零填充即放行——版本号/编号串里的
"2026.13.45" 被格式化成不可能的 ISO 日期写进 filing_date，下游按日期
排序/解析时拿到非法值。合法日期应原样通过，非法匹配应跳过继续找。"""
from __future__ import annotations

import backend.tools.local_disclosure as ld


def test_local_filings_search_failure_is_not_reported_as_no_filings(monkeypatch, caplog):
    def fail_search(_query):
        raise TimeoutError("PRIVATE_SEARCH_TOKEN")

    monkeypatch.setattr(ld, "search", fail_search)
    payload = ld.get_local_market_filings("600519.SS")
    assert payload["count"] == 0
    assert payload["error"] == "search_failed"
    assert "PRIVATE_SEARCH_TOKEN" not in str(payload)
    assert "PRIVATE_SEARCH_TOKEN" not in caplog.text


def test_local_filings_successful_empty_search_is_not_a_failure(monkeypatch):
    monkeypatch.setattr(ld, "search", lambda _query: "")
    payload = ld.get_local_market_filings("600519.SS")
    assert payload["count"] == 0
    assert payload["error"] is None


def test_local_filings_partial_failure_preserves_valid_filings(monkeypatch):
    calls = []

    def search(_query):
        calls.append(_query)
        if len(calls) == 1:
            raise TimeoutError("upstream unavailable")
        return "[2026-11-18 annual report](https://www.cninfo.com.cn/report)"

    monkeypatch.setattr(ld, "search", search)
    payload = ld.get_local_market_filings("600519.SS", limit=1)
    assert payload["count"] == 1
    assert payload["error"] is None
    assert payload["filings"][0]["filing_date"] == "2026-11-18"


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
