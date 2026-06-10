# -*- coding: utf-8 -*-
"""AI 研究输出边界测试。"""

from backend.handlers.chat_handler import ChatHandler
from backend.report.validator import ReportValidator
from backend.research_policy import (
    RESEARCH_DISCLAIMER,
    RESEARCH_STANCE_DEFAULT,
    append_research_disclaimer,
    sanitize_research_stance,
)


def test_policy_sanitizes_trade_recommendations():
    assert sanitize_research_stance("BUY") == RESEARCH_STANCE_DEFAULT
    assert sanitize_research_stance("建议买入") == RESEARCH_STANCE_DEFAULT
    assert sanitize_research_stance("目标价 180，止损 140") == RESEARCH_STANCE_DEFAULT
    assert sanitize_research_stance("优先复查现金流和财报证据") == "优先复查现金流和财报证据"


def test_policy_appends_research_disclaimer_once():
    text = append_research_disclaimer("请复查最新财报。")
    assert RESEARCH_DISCLAIMER in text
    assert append_research_disclaimer(text).count(RESEARCH_DISCLAIMER) == 1


def test_chat_advice_query_returns_research_review_without_llm():
    handler = ChatHandler(llm=None, orchestrator=None)

    result = handler._handle_advice_query("AAPL", "AAPL 现在能买吗")

    assert result["success"] is True
    assert result["intent"] == "research_review"
    assert "买入、卖出或持有指令" in result["response"]
    assert RESEARCH_DISCLAIMER in result["response"]
    assert "分批建仓" not in result["response"]


def test_generic_recommendation_returns_candidate_research_pool():
    handler = ChatHandler(llm=None, orchestrator=None)

    result = handler._handle_generic_recommendation("推荐几只股票")

    assert result["success"] is True
    assert result["intent"] == "research_discovery"
    assert "候选研究标的池" in result["response"]
    assert "分批建仓" not in result["response"]
    assert "仓位" not in result["response"]
    assert RESEARCH_DISCLAIMER in result["response"]


def test_report_validator_sanitizes_recommendation_field():
    result = ReportValidator.validate_and_fix(
        {
            "ticker": "NVDA",
            "summary": "Summary",
            "recommendation": "BUY",
        },
        as_dict=True,
    )

    assert result["recommendation"] == RESEARCH_STANCE_DEFAULT
