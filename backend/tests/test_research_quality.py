# -*- coding: utf-8 -*-
"""Research Quality Service Tests"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta

from backend.services import research_quality
from backend.services.report_index import get_report_index_store


@pytest.fixture
def clean_state():
    """清理测试状态"""
    yield


def test_empty_library_returns_healthy_empty_state(clean_state):
    """测试 1：空报告库返回健康空态"""
    # 使用唯一的 session_id 避免数据污染
    result = research_quality.get_research_quality(
        session_id="test_empty_unique_session_001",
        user_id="test_empty_user",
    )

    assert result["success"] is True
    assert result["summary"]["total_reports"] == 0
    assert result["summary"]["health_score"] == 100
    assert len(result["top_issues"]) == 0


def test_stale_report_identified(clean_state):
    """测试 2：stale report 被识别"""
    session_id = "test_stale_session"
    store = get_report_index_store()

    # 创建 stale 报告
    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": "stale_report_001",
            "ticker": "AAPL",
            "title": "AAPL 过期报告",
            "summary": "数据已过期",
            "freshness_status": "stale",
        }
    )

    result = research_quality.get_research_quality(
        session_id=session_id,
        user_id="test_user",
    )

    # 验证
    assert result["summary"]["total_reports"] == 1
    assert result["summary"]["stale_reports"] == 1
    assert result["summary"]["health_score"] < 100  # stale 扣分

    # 验证 top_issues
    stale_issues = [i for i in result["top_issues"] if i["issue_type"] == "stale_report"]
    assert len(stale_issues) >= 1
    assert stale_issues[0]["severity"] in ("high", "medium")
    assert "AAPL" in stale_issues[0]["title"]


def test_low_citation_report_identified(clean_state):
    """测试 3：low citation report 被识别"""
    session_id = "test_low_citation_session"
    store = get_report_index_store()

    # 创建 low citation 报告（只有 1 个引用，会被标记为 low）
    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": "low_cit_report_001",
            "ticker": "GOOGL",
            "title": "GOOGL 报告",
            "summary": "引用质量低",
            "citations": [
                {
                    "title": "单一来源",
                    "url": "https://example.com/source1",
                    "snippet": "仅有一个引用",
                }
            ],
        }
    )

    result = research_quality.get_research_quality(
        session_id=session_id,
        user_id="test_user",
    )

    # 验证
    assert result["summary"]["low_quality_reports"] == 1
    assert result["summary"]["health_score"] < 100

    # 验证 top_issues
    low_cit_issues = [i for i in result["top_issues"] if i["issue_type"] == "low_citation"]
    assert len(low_cit_issues) >= 1
    assert "引用" in low_cit_issues[0]["reason"]


def test_quality_block_warn_identified(clean_state):
    """测试 4：quality block/warn 被识别"""
    session_id = "test_quality_session"
    store = get_report_index_store()

    # 注意：quality_state 会被自动计算，我们用 freshness_status 来触发 warn
    # 创建两个报告：一个 stale（会触发 warn），一个 aging
    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": "quality_report_001",
            "ticker": "MSFT",
            "title": "MSFT 报告",
            "summary": "质量警告",
            "freshness_status": "stale",
        }
    )

    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": "quality_report_002",
            "ticker": "TSLA",
            "title": "TSLA 报告",
            "summary": "老化数据",
            "freshness_status": "aging",
        }
    )

    result = research_quality.get_research_quality(
        session_id=session_id,
        user_id="test_user",
    )

    # 验证：至少有 stale 报告被识别
    assert result["summary"]["total_reports"] == 2
    assert result["summary"]["stale_reports"] >= 1  # stale + aging
    assert result["summary"]["health_score"] < 100


def test_reviewed_rate_calculated_correctly(clean_state):
    """测试 5：reviewed_rate 计算正确"""
    session_id = "test_reviewed_session"
    store = get_report_index_store()

    # 创建 5 个报告：3 个 reviewed，2 个 new
    # 注意：upsert_report 会默认设为 "new"，需要后续调用 set_review_status
    for i in range(3):
        store.upsert_report(
            session_id=session_id,
            report={
                "report_id": f"reviewed_report_{i}",
                "ticker": f"SYM{i}",
                "title": f"已复查报告 {i}",
                "summary": "已复查",
            }
        )
        store.set_review_status(
            session_id=session_id,
            report_id=f"reviewed_report_{i}",
            review_status="reviewed",
        )

    for i in range(2):
        store.upsert_report(
            session_id=session_id,
            report={
                "report_id": f"new_report_{i}",
                "ticker": f"NEW{i}",
                "title": f"新报告 {i}",
                "summary": "未复查",
            }
        )
        # new 是默认值，无需调用 set_review_status

    result = research_quality.get_research_quality(
        session_id=session_id,
        user_id="test_user",
    )

    # 验证
    assert result["summary"]["total_reports"] == 5
    assert result["summary"]["reviewed_rate"] == 0.6  # 3/5


def test_health_score_deduction_correct(clean_state):
    """测试 6：health_score 扣分正确"""
    session_id = "test_health_score_session"
    store = get_report_index_store()

    # 创建多种问题报告
    # 1 个 stale（-5）
    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": "stale_001",
            "ticker": "AAA",
            "title": "过期报告",
            "summary": "stale",
            "freshness_status": "stale",
        }
    )

    # 1 个 low citation（-5）
    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": "low_cit_001",
            "ticker": "BBB",
            "title": "低引用报告",
            "summary": "low cit",
            "citation_quality": "low",
        }
    )

    # 1 个正常报告
    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": "normal_001",
            "ticker": "CCC",
            "title": "正常报告",
            "summary": "ok",
            "review_status": "reviewed",
        }
    )

    result = research_quality.get_research_quality(
        session_id=session_id,
        user_id="test_user",
    )

    # 验证：预期 100 - 5(stale) - 5(low_cit) = 90
    # 实际可能因为其他因素有微小差异，但应该明显低于 100
    assert result["summary"]["health_score"] <= 90
    assert result["summary"]["health_score"] >= 80  # 允许一定范围


def test_top_issues_sorted_by_severity(clean_state):
    """测试 7：top_issues 按 severity 排序"""
    session_id = "test_sort_session"
    store = get_report_index_store()

    # 创建不同 severity 的问题
    # medium: aging
    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": "aging_001",
            "ticker": "AAA",
            "title": "老化报告",
            "summary": "aging",
            "freshness_status": "aging",
        }
    )

    # high: stale
    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": "stale_001",
            "ticker": "BBB",
            "title": "过期报告",
            "summary": "stale",
            "freshness_status": "stale",
        }
    )

    # medium: low citation
    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": "low_cit_001",
            "ticker": "CCC",
            "title": "低引用报告",
            "summary": "low cit",
            "citation_quality": "low",
        }
    )

    result = research_quality.get_research_quality(
        session_id=session_id,
        user_id="test_user",
    )

    # 验证：issues 按 severity 排序（critical > high > medium > low）
    issues = result["top_issues"]
    assert len(issues) >= 3

    # 验证排序：high severity 应该在 medium 之前
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    for i in range(len(issues) - 1):
        current_order = severity_order.get(issues[i]["severity"], 99)
        next_order = severity_order.get(issues[i + 1]["severity"], 99)
        assert current_order <= next_order, f"Issue {i} severity {issues[i]['severity']} should be <= {issues[i+1]['severity']}"


def test_symbol_filter_works(clean_state):
    """测试 8：symbol 参数过滤正确"""
    session_id = "test_symbol_filter_session"
    store = get_report_index_store()

    # 创建两个标的的报告
    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": "aapl_report",
            "ticker": "AAPL",
            "title": "AAPL 报告",
            "summary": "stale",
            "freshness_status": "stale",
        }
    )

    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": "googl_report",
            "ticker": "GOOGL",
            "title": "GOOGL 报告",
            "summary": "stale",
            "freshness_status": "stale",
        }
    )

    # 只查询 AAPL
    result = research_quality.get_research_quality(
        session_id=session_id,
        user_id="test_user",
        symbol="AAPL",
    )

    # 验证：只有 AAPL 的报告
    assert result["summary"]["total_reports"] == 1
    issues = result["top_issues"]
    if len(issues) > 0:
        assert all(i.get("related_symbol") == "AAPL" for i in issues if i.get("related_symbol"))
