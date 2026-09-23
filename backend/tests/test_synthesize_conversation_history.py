# -*- coding: utf-8 -*-
"""R63：_format_conversation_history_for_synth 用 messages.index(msg) 定位——
相同内容的重复 HumanMessage 会命中第一条的索引，最后那条（即当前 query）
误以为"后面还有同名消息"而不被跳过，当前 query 被复制进
<conversation_history>，合成 prompt 里同一句话出现两次。"""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from backend.graph.nodes.synthesize_format import _format_conversation_history_for_synth


def _state(query: str, messages: list) -> dict:
    return {"query": query, "messages": messages}


def test_history_skips_last_duplicate_of_current_query():
    state = _state(
        "分析AAPL",
        [
            HumanMessage(content="分析AAPL"),
            AIMessage(content="上次结论：中性"),
            HumanMessage(content="分析AAPL"),  # 当前 query（用户重复提问）
        ],
    )
    out = _format_conversation_history_for_synth(state)
    # 第一条同名消息是真实历史，应保留；最后一条是当前 query，应跳过
    assert out.count("[user]: 分析AAPL") == 1
    assert "[assistant]:" in out


def test_history_skips_single_current_query():
    state = _state(
        "现在多少钱",
        [
            HumanMessage(content="帮我看行情"),
            AIMessage(content="好的"),
            HumanMessage(content="现在多少钱"),  # 当前 query
        ],
    )
    out = _format_conversation_history_for_synth(state)
    assert "现在多少钱" not in out
    assert "帮我看行情" in out


def test_history_keeps_all_when_query_not_in_messages():
    state = _state(
        "当前问题",
        [
            HumanMessage(content="问题一"),
            AIMessage(content="回答一"),
            HumanMessage(content="问题二"),
        ],
    )
    out = _format_conversation_history_for_synth(state)
    assert "问题一" in out and "问题二" in out


def test_history_empty_when_only_current_query():
    state = _state("唯一问题", [HumanMessage(content="唯一问题")])
    assert _format_conversation_history_for_synth(state) == ""
