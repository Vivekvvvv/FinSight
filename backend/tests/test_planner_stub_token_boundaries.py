# -*- coding: utf-8 -*-
"""R70：planner_stub._contains_any 用裸 `token in query_lower` 子串匹配，
短 ASCII token 无词边界——"eps" 命中 "steps"/"pepsi"、"cpi" 命中 "cpic"
（真实代码/词），普通提问被幻影注入 get_earnings_estimates /
get_event_calendar 等工具步骤。与 parse_operation._match_any 已建立的
≤3字符 ASCII 边界策略对齐。"""
from __future__ import annotations

from backend.graph.nodes.planner_stub import planner_stub


def _step_names(query: str, tickers: list[str], allowed_tools: list[str]) -> list[str]:
    state = {
        "query": query,
        "subject": {"subject_type": "company", "tickers": tickers},
        "operation": {"name": "qa"},
        "output_mode": "brief",
        "policy": {"allowed_tools": allowed_tools, "allowed_agents": []},
    }
    plan = planner_stub(state)["plan_ir"]
    return [step["name"] for step in plan["steps"]]


_TOOLS = ["get_earnings_estimates", "get_eps_revisions", "get_event_calendar"]


def test_steps_word_does_not_fire_eps_tools():
    """"steps" 里的 "eps" 子串不该触发盈利预期工具。"""
    names = _step_names("what steps has aapl announced recently", ["AAPL"], _TOOLS)
    assert "get_earnings_estimates" not in names
    assert "get_eps_revisions" not in names


def test_pepsi_name_does_not_fire_eps_tools():
    """公司名 "pepsi" 里的 "eps" 子串不该触发盈利预期工具。"""
    names = _step_names("pepsi beverage outlook", ["PEP"], _TOOLS)
    assert "get_earnings_estimates" not in names
    assert "get_eps_revisions" not in names


def test_cpic_ticker_does_not_fire_cpi_tool():
    """"cpic"（中国太保）里的 "cpi" 子串不该触发事件日历。"""
    names = _step_names("cpic quarterly outlook", ["CPIC"], _TOOLS)
    assert "get_event_calendar" not in names


def test_legit_eps_keyword_still_fires():
    """边界化后真实 "eps" 关键词仍命中——回归保护。"""
    names = _step_names("aapl eps revisions trend", ["AAPL"], _TOOLS)
    assert "get_earnings_estimates" in names
    assert "get_eps_revisions" in names


def test_legit_cpi_keyword_still_fires():
    """真实 "cpi" 关键词仍命中事件日历——回归保护。"""
    names = _step_names("aapl outlook into cpi print", ["AAPL"], _TOOLS)
    assert "get_event_calendar" in names
