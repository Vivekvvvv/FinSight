from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from backend import llm_config
from backend.services.financials_analyzer import analyze_financials


@pytest.mark.parametrize("company_name", [None, True, 123, [], {"name": "wrong"}, "  "])
def test_invalid_company_name_uses_requested_stock_identity(monkeypatch, company_name):
    calls = _patch_analysis(monkeypatch, {"overall_rating": {"score": 8}})
    result = asyncio.run(analyze_financials("AAPL", {"revenue": 100}, {"name": company_name}))
    assert result["status"] == "success"
    assert "公司名称：AAPL" in calls[0]


@pytest.mark.parametrize("field", ["ticker", "symbol"])
def test_model_financial_analysis_cannot_be_relabeled_from_another_stock(monkeypatch, field):
    _patch_analysis(monkeypatch, {field: "MSFT", "overall_rating": {"score": 8}})
    result = asyncio.run(analyze_financials("AAPL", {"revenue": 100}))
    assert result["status"] == "error"


@pytest.mark.parametrize("field", ["ticker", "symbol"])
def test_company_instrument_mismatch_cannot_reach_financial_model(monkeypatch, field):
    calls = _patch_analysis(monkeypatch, {"overall_rating": {"score": 8}})
    result = asyncio.run(analyze_financials("AAPL", {"revenue": 100}, {"name": "Microsoft", field: "MSFT"}))
    assert result["status"] == "error"
    assert calls == []


@pytest.mark.parametrize("company_info", ["bad", [1], True, 123])
def test_malformed_optional_company_info_does_not_break_valid_analysis(monkeypatch, company_info):
    calls = _patch_analysis(monkeypatch, {"overall_rating": {"score": 8}})
    result = asyncio.run(analyze_financials("AAPL", {"revenue": 100}, company_info))
    assert result["status"] == "success"
    assert len(calls) == 1


@pytest.mark.parametrize("field", ["ticker", "symbol"])
def test_financial_analysis_rejects_another_instrument_before_model_call(monkeypatch, field):
    calls = _patch_analysis(monkeypatch, {"overall_rating": {"score": 8}})
    result = asyncio.run(analyze_financials("AAPL", {"revenue": 100, field: "MSFT"}))
    assert result["status"] == "error"
    assert calls == []


def _patch_analysis(monkeypatch, payload):
    calls = []
    async def invoke(_prompt):
        calls.append(_prompt)
        return SimpleNamespace(content=json.dumps(payload))

    monkeypatch.setattr(llm_config, "create_llm", lambda **kwargs: SimpleNamespace(ainvoke=invoke))
    return calls


@pytest.mark.parametrize("failure", [
    {"error": "model failed"}, {"success": False},
    {"status": "error"}, {"status": " FAILED "}, {"status": "unavailable"},
])
def test_failed_model_analysis_cannot_be_promoted_to_success(monkeypatch, failure):
    _patch_analysis(monkeypatch, {**failure, "overall_rating": {"score": 8}})

    result = asyncio.run(analyze_financials("AAPL", {"revenue": 100}))

    assert result["status"] == "error"
    assert result["overall_rating"]["label"] == "数据不足"


@pytest.mark.parametrize("status", ["error", " FAILED ", "Unavailable"])
def test_failed_source_status_does_not_reach_the_model(monkeypatch, status):
    calls = _patch_analysis(monkeypatch, {"overall_rating": {"score": 8}})

    result = asyncio.run(analyze_financials("AAPL", {"revenue": 100, "status": status}))

    assert result["status"] == "error"
    assert calls == []


@pytest.mark.parametrize("section", ["revenue_analysis", "profitability", "cash_flow"])
@pytest.mark.parametrize("value", [None, [], "invalid"])
def test_malformed_analysis_sections_do_not_escape_as_successful_data(monkeypatch, section, value):
    _patch_analysis(monkeypatch, {"overall_rating": {"score": 8}, section: value})

    result = asyncio.run(analyze_financials("AAPL", {"revenue": 100}))

    assert result["status"] == "success"
    assert result[section] == {}
    assert result["overall_rating"]["score"] == 8


def test_valid_analysis_sections_are_preserved(monkeypatch):
    sections = {
        "revenue_analysis": {"trend": "增长", "yoy_growth": 0},
        "profitability": {"assessment": "良好"},
        "cash_flow": {"quality": "中"},
    }
    _patch_analysis(monkeypatch, {"overall_rating": {"score": 8}, **sections})

    result = asyncio.run(analyze_financials("AAPL", {"revenue": 100}))

    assert result["status"] == "success"
    for section, value in sections.items():
        assert result[section] == value


@pytest.mark.parametrize("section, maximum", [("risk_factors", 5), ("investment_highlights", 3)])
@pytest.mark.parametrize("value, expected", [
    (None, []), ("bad", []), ({"list": "bad"}, []),
    ({"list": [None, {}, "", "  有效分析  "]}, ["有效分析"]),
    ({"list": [f"item-{i}" for i in range(8)]}, [f"item-{i}" for i in range(5)]),
])
def test_analysis_bullet_sections_contain_only_bounded_text(monkeypatch, section, maximum, value, expected):
    _patch_analysis(monkeypatch, {"overall_rating": {"score": 8}, section: value})

    result = asyncio.run(analyze_financials("AAPL", {"revenue": 100}))

    assert result[section] == {"list": expected[:maximum]}
    assert result["status"] == "success"


@pytest.mark.parametrize("label, summary, expected_label, expected_summary", [
    (["优秀"], {"text": "wrong shape"}, "未评级", ""),
    (None, None, "未评级", ""),
    ("  良好  ", "  盈利改善  ", "良好", "盈利改善"),
    ("invalid", "财报" * 40, "未评级", ("财报" * 40)[:50]),
])
def test_rating_display_fields_are_safe_without_inventing_a_label(monkeypatch, label, summary, expected_label, expected_summary):
    _patch_analysis(monkeypatch, {"overall_rating": {"score": 8, "label": label, "summary": summary}})

    result = asyncio.run(analyze_financials("AAPL", {"revenue": 100}))

    assert result["overall_rating"] == {"score": 8.0, "label": expected_label, "summary": expected_summary}
    assert result["status"] == "success"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), {1, 2}])
def test_invalid_financial_data_does_not_reach_the_model(monkeypatch, value):
    calls = _patch_analysis(monkeypatch, {"overall_rating": {"score": 8}})

    result = asyncio.run(analyze_financials("AAPL", {"revenue": 100, "nested": [value]}))

    assert result["status"] == "error"
    assert calls == []


@pytest.mark.parametrize("financials", [None, {}, {"success": False, "revenue": 100}, {
    "error": "provider failed", "revenue": 100,
}])
def test_failed_financial_payload_cannot_be_analysed_using_retained_values(monkeypatch, financials):
    calls = _patch_analysis(monkeypatch, {"overall_rating": {"score": 8}})

    result = asyncio.run(analyze_financials("AAPL", financials))

    assert result["status"] == "error"
    assert calls == []


@pytest.mark.parametrize("score", [True, False, None, -1, 0, 11, [], {"value": 8}])
def test_invalid_model_rating_is_unavailable(monkeypatch, score):
    _patch_analysis(monkeypatch, {"overall_rating": {"score": score}})

    result = asyncio.run(analyze_financials("AAPL", {"revenue": 100}))

    assert result["status"] == "error"
    assert result["overall_rating"]["label"] == "数据不足"


@pytest.mark.parametrize("score, expected", [(1, 1.0), (10, 10.0), ("7.5", 7.5)])
def test_valid_model_rating_is_returned_as_a_number(monkeypatch, score, expected):
    _patch_analysis(monkeypatch, {"overall_rating": {"score": score}})

    result = asyncio.run(analyze_financials("AAPL", {"revenue": 100}))

    assert result["status"] == "success"
    assert result["overall_rating"]["score"] == expected
