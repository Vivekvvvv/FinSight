# -*- coding: utf-8 -*-
from backend.graph.capability_registry import (
    REPORT_AGENT_CANDIDATES,
    required_agents_for_request,
    score_agent_for_request,
    select_agents_for_request,
)


def _state(*, query: str, subject_type: str, operation: str = "generate_report") -> dict:
    return {
        "query": query,
        "output_mode": "investment_report",
        "operation": {"name": operation, "confidence": 0.9, "params": {}},
        "subject": {"subject_type": subject_type, "tickers": ["AAPL"], "selection_types": []},
    }


def test_required_agents_company_report_has_foundation_trio():
    state = _state(query="Analyze AAPL and produce an investment report", subject_type="company")
    required = required_agents_for_request(state, REPORT_AGENT_CANDIDATES)
    # company + investment_report now requires all 5 core agents (macro + technical added)
    assert required == ["price_agent", "news_agent", "fundamental_agent", "macro_agent", "technical_agent"]


def test_select_agents_company_report_does_not_default_to_deep_search():
    state = _state(query="Analyze AAPL and produce an investment report", subject_type="company")
    selected = select_agents_for_request(state, REPORT_AGENT_CANDIDATES, max_agents=4, min_agents=2)
    names = selected.get("selected") or []
    assert {"price_agent", "news_agent", "fundamental_agent"}.issubset(set(names))
    assert "deep_search_agent" not in names
    # 5 required agents (includes macro + technical), target clamps up to match
    assert len(names) <= 5


def test_select_agents_deep_hint_enables_deep_search():
    state = _state(query="Deep research on AAPL and produce a report", subject_type="company")
    selected = select_agents_for_request(state, REPORT_AGENT_CANDIDATES, max_agents=4, min_agents=2)
    names = selected.get("selected") or []
    assert "deep_search_agent" in names


def test_select_agents_filing_prioritizes_document_agents():
    state = _state(query="Read filing and create report", subject_type="filing")
    selected = select_agents_for_request(state, REPORT_AGENT_CANDIDATES, max_agents=4, min_agents=2)
    names = selected.get("selected") or []
    assert "deep_search_agent" in names
    assert "fundamental_agent" in names
    assert len(names) <= 4


def test_ascii_hint_ma_not_matched_inside_market():
    """R59：'ma' 裸子串命中 market/margin/dynamic 等——几乎所有英文 query
    都含 "ma"，investment_report 下强塞 technical_agent。词边界修复后
    纯新闻请求不应带技术 agent。"""
    state = _state(query="morning market headlines digest", subject_type="news_set")
    required = required_agents_for_request(state, REPORT_AGENT_CANDIDATES)
    assert required == ["news_agent", "price_agent"]


def test_ascii_hint_var_not_matched_inside_variable():
    """'var' 裸子串命中 'variable' → risk_agent 误拿 keyword_boost +0.35
    （var 本意是 value-at-risk，不是 variable/varying）。"""
    state = _state(query="variable annuity product review", subject_type="portfolio")
    score, reasons = score_agent_for_request("risk_agent", state)
    assert not any(r.startswith("keyword:") for r in reasons)


def test_keyword_boost_not_fired_by_embedded_ma():
    """'margin' 中的 'ma' 不应给 technical_agent 加 keyword_boost。"""
    state = _state(query="gross margin trend report", subject_type="company")
    score, reasons = score_agent_for_request("technical_agent", state)
    assert not any(r.startswith("keyword:") for r in reasons)


def test_standalone_technical_terms_still_match():
    """独立词 rsi/ma/macd 仍应命中（边界内 + 复数 s? 回归保护）。"""
    state = _state(query="rsi oversold headline scan", subject_type="news_set")
    required = required_agents_for_request(state, REPORT_AGENT_CANDIDATES)
    assert "technical_agent" in required and "price_agent" in required

    state2 = _state(query="check ma lines for aapl", subject_type="company")
    score, reasons = score_agent_for_request("technical_agent", state2)
    assert any(r.startswith("keyword:") for r in reasons)


def test_chinese_hints_still_substring_match():
    """中文词无词界概念，保持子串匹配。"""
    state = _state(query="分析一下均线和最新快讯", subject_type="news_set")
    required = required_agents_for_request(state, REPORT_AGENT_CANDIDATES)
    assert "technical_agent" in required
