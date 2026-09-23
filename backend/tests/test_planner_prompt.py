# -*- coding: utf-8 -*-
from langchain_core.messages import AIMessage, HumanMessage

from backend.graph.planner_prompt import _format_conversation_history, build_planner_prompt


def test_history_skips_last_duplicate_of_current_query():
    """R90：planner 版 _format_conversation_history 的 messages.index(msg)
    与 R63 修复的 synthesize 版是同一个缺陷——重复提问时当前 query
    消息按值相等命中第一条的下标，"后面还有同名消息"误判成立而不被
    跳过，当前 query 被复制进 <conversation_history>（inputs.query
    里还有一份，planner 看到两遍）。"""
    state = {
        "query": "分析AAPL",
        "messages": [
            HumanMessage(content="分析AAPL"),
            AIMessage(content="上次结论：中性"),
            HumanMessage(content="分析AAPL"),  # 当前 query（用户重复提问）
        ],
    }
    out = _format_conversation_history(state)
    assert out.count("[user]: 分析AAPL") == 1
    assert "[assistant]:" in out


def test_history_skips_single_current_query():
    state = {
        "query": "现在多少钱",
        "messages": [
            HumanMessage(content="帮我看行情"),
            AIMessage(content="好的"),
            HumanMessage(content="现在多少钱"),
        ],
    }
    out = _format_conversation_history(state)
    assert "现在多少钱" not in out
    assert "帮我看行情" in out


def test_planner_prompt_includes_allowlists_and_operation():
    state = {
        "query": "分析影响",
        "subject": {"subject_type": "news_item", "selection_payload": [{"id": "n1"}]},
        "operation": {"name": "analyze_impact", "confidence": 0.7, "params": {}},
        "output_mode": "brief",
        "policy": {"allowed_tools": ["search"], "allowed_agents": ["news_agent"], "budget": {"max_rounds": 3, "max_tools": 4}},
    }
    prompt = build_planner_prompt(state)
    assert "allowed_tools" in prompt
    assert "analyze_impact" in prompt
    assert "news_agent" in prompt
    assert "FIRST step MUST summarize selection" in prompt or "第一步必须为 summarize_selection" in prompt


def test_planner_prompt_variant_a_and_b_are_distinct_and_tagged():
    state = {
        "query": "compare AAPL MSFT",
        "subject": {"subject_type": "company", "tickers": ["AAPL", "MSFT"], "selection_payload": []},
        "operation": {"name": "compare", "confidence": 0.8, "params": {}},
        "output_mode": "brief",
        "policy": {"allowed_tools": ["get_performance_comparison"], "allowed_agents": [], "budget": {"max_rounds": 3, "max_tools": 4}},
    }
    prompt_a = build_planner_prompt(state, variant="A")
    prompt_b = build_planner_prompt(state, variant="B")

    assert "<planner_variant>A</planner_variant>" in prompt_a
    assert "<planner_variant>B</planner_variant>" in prompt_b
    assert "Variant A" in prompt_a
    assert "Variant B" in prompt_b
    assert prompt_a != prompt_b


def test_planner_prompt_includes_new_tool_allowlist_entries():
    state = {
        "query": "AAPL eps revisions and option skew",
        "subject": {"subject_type": "company", "tickers": ["AAPL"], "selection_payload": []},
        "operation": {"name": "qa", "confidence": 0.8, "params": {}},
        "output_mode": "brief",
        "policy": {
            "allowed_tools": [
                "get_earnings_estimates",
                "get_eps_revisions",
                "get_option_chain_metrics",
                "get_factor_exposure",
                "run_portfolio_stress_test",
                "get_event_calendar",
                "score_news_source_reliability",
            ],
            "allowed_agents": [],
            "budget": {"max_rounds": 3, "max_tools": 6},
        },
    }
    prompt = build_planner_prompt(state)
    for tool_name in state["policy"]["allowed_tools"]:
        assert tool_name in prompt
