# -*- coding: utf-8 -*-
import backend.tools.earnings_transcripts as transcripts_mod


def test_get_earnings_call_transcripts_cn_market_builds_cn_queries(monkeypatch):
    captured_queries: list[str] = []

    def _fake_search(query: str) -> str:
        captured_queries.append(query)
        return ""

    monkeypatch.setattr(transcripts_mod, "search", _fake_search)

    payload = transcripts_mod.get_earnings_call_transcripts("600519.SS", limit=3)

    assert payload.get("market") == "CN"
    assert payload.get("count") == 0
    assert any("业绩说明会" in query for query in captured_queries)
    assert any("电话会议" in query for query in captured_queries)


def test_get_earnings_call_transcripts_cn_market_parses_chinese_row(monkeypatch):
    raw = (
        "[贵州茅台 业绩说明会 纪要]"
        "(https://www.cninfo.com.cn/new/disclosure/detail?stockCode=600519)"
    )
    monkeypatch.setattr(transcripts_mod, "search", lambda _query: raw)
    monkeypatch.setattr(transcripts_mod, "_maybe_enrich_snippet", lambda _url, snippet: snippet)

    payload = transcripts_mod.get_earnings_call_transcripts("600519.SS", limit=3)

    assert payload.get("market") == "CN"
    assert payload.get("count", 0) >= 1
    row = payload.get("transcripts")[0]
    assert row.get("domain") == "cninfo.com.cn"
    assert row.get("type") == "transcript"


def test_get_earnings_call_transcripts_hk_market_parses_results_presentation(monkeypatch):
    raw = (
        "[Tencent FY2025 results presentation transcript]"
        "(https://www.hkexnews.hk/listedco/listconews/sehk/2026/0210/2026021000012.pdf)"
    )
    monkeypatch.setattr(transcripts_mod, "search", lambda _query: raw)
    monkeypatch.setattr(transcripts_mod, "_maybe_enrich_snippet", lambda _url, snippet: snippet)

    payload = transcripts_mod.get_earnings_call_transcripts("0700.HK", limit=3)

    assert payload.get("market") == "HK"
    assert payload.get("count", 0) >= 1
    row = payload.get("transcripts")[0]
    assert "hkexnews.hk" in str(row.get("domain") or "")
    assert row.get("type") == "transcript"


def test_build_market_queries_hk_includes_short_symbol():
    """R61：0700.HK 时专门计算的港股短码 '700' 被 symbols[:2] 切掉——
    hk_short 只能落在 index 2（0=0700.HK，1=0700），切片永远丢它，
    写入的 lstrip('0') 逻辑是死代码。修复后应有 '700 ...' 查询。"""
    queries = transcripts_mod._build_market_queries("0700.HK", "HK")
    assert any(query.startswith("700 ") for query in queries)
    # 原有两种形态不回归
    assert any(query.startswith("0700.HK ") for query in queries)
    assert any(query.startswith("0700 ") for query in queries)
