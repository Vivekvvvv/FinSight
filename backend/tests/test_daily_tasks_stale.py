# -*- coding: utf-8 -*-
"""daily_tasks._days_since 对 naive generated_at 必须按本机时区归一。

bug：report_index.generated_at 可为 naive 本地时间（report_generator.py、
report/ir.py、report/validator.py 用 datetime.now().isoformat() 写入——
task_router.py:83 与 reports_to_review.py:89 的修复注释已确认此存储惯例）。
_days_since 直接 aware_now - naive_dt 抛 TypeError，被 except 吞成 None，
调用方落入 "近期研报" 分支——9 天前的过期研报被判成"查看最新"，
"重新分析"任务永不生成。修复与另两处一致：naive 先 astimezone(utc)。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest

from backend.services.daily_tasks import _days_since, generate_daily_tasks


@pytest.mark.parametrize("symbol", ["MSFT", True, {}, ["AAPL"]])
def test_report_with_conflicting_symbol_cannot_suppress_new_daily_analysis(symbol):
    tasks = generate_daily_tasks(watchlist=["AAPL"], reports=[{
        "ticker": "AAPL", "symbol": symbol, "report_id": "wrong",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }])
    assert any(task["category"] == "generate" for task in tasks)
    assert all(task["category"] != "review" for task in tasks)


def test_nontext_report_ticker_cannot_suppress_first_analysis_for_a_numeric_symbol():
    tasks = generate_daily_tasks(watchlist=["600519"], reports=[{
        "ticker": 600519, "report_id": "malformed", "generated_at": datetime.now(timezone.utc).isoformat(),
    }])
    assert any(task["category"] == "generate" for task in tasks)
    assert all(task["category"] != "review" for task in tasks)


@pytest.mark.parametrize("order", ["old_first", "recent_first", "unknown_first"])
def test_daily_tasks_select_latest_valid_report_regardless_of_input_order(order):
    now = datetime.now(timezone.utc)
    older = {"ticker": "AAPL", "report_id": "old", "generated_at": (now - timedelta(days=9)).isoformat()}
    latest = {"ticker": "AAPL", "report_id": "latest", "generated_at": (now - timedelta(minutes=20)).isoformat()}
    same_day = {"ticker": "AAPL", "report_id": "same-day", "generated_at": (now - timedelta(hours=1)).isoformat()}
    unknown = {"ticker": "AAPL", "report_id": "unknown", "generated_at": "bad-date"}
    reports = {"old_first": [older, same_day, latest], "recent_first": [latest, older, same_day],
               "unknown_first": [unknown, older, latest]}[order]
    tasks = generate_daily_tasks(watchlist=["AAPL"], reports=reports)
    review = next(task for task in tasks if task["category"] == "review")
    assert review["action_url"] == "/chat?report_id=latest"
    assert all(task["category"] != "reanalyze" for task in tasks)


def test_daily_risk_preference_normalizes_case_and_whitespace():
    tasks = generate_daily_tasks(watchlist=[], reports=[], risk_preference=" Conservative ")
    assert any(item["category"] == "risk" for item in tasks)
    assert all(item["category"] != "rebalance" for item in tasks)


@pytest.mark.parametrize("news_count", [None, "bad", [], True, 2.5, float("inf"), -1])
def test_daily_news_counts_require_nonnegative_integers(news_count):
    tasks = generate_daily_tasks(watchlist=[], reports=[], news_count=news_count)
    assert all(item["category"] != "news" for item in tasks)


@pytest.mark.parametrize("report_id", [True, 123, [], {}, "  "])
def test_daily_review_routes_do_not_interpolate_invalid_report_identifiers(report_id):
    tasks = generate_daily_tasks(watchlist=["AAPL"], reports=[
        {"ticker": "AAPL", "generated_at": datetime.now(timezone.utc).isoformat(), "report_id": report_id}])
    item = next(item for item in tasks if item["category"] == "review")
    assert item["action_url"] == "/workbench?ticker=AAPL"


@pytest.mark.parametrize("bad", [None, "bad", [], 42])
def test_malformed_report_rows_do_not_hide_valid_daily_tasks(bad):
    tasks = generate_daily_tasks(watchlist=["AAPL"], reports=[bad, {
        "ticker": "AAPL", "report_id": "r1", "generated_at": datetime.now(timezone.utc).isoformat(),
    }])

    review = [task for task in tasks if task["category"] == "review"]
    assert len(review) == 1
    assert review[0]["action_url"] == "/chat?report_id=r1"


@pytest.mark.parametrize("failure", [{"error": "failed"}, {"success": False}, {"status": " ERROR "}])
def test_failed_recent_report_does_not_suppress_new_daily_analysis(failure):
    tasks = generate_daily_tasks(watchlist=["AAPL"], reports=[{
        **failure, "ticker": "AAPL", "report_id": "failed", "generated_at": datetime.now(timezone.utc).isoformat(),
    }])

    assert any(task["category"] == "generate" for task in tasks)
    assert all(task["category"] != "review" for task in tasks)


def test_future_report_time_requests_refresh_instead_of_recent_review():
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    tasks = generate_daily_tasks(watchlist=["AAPL"], reports=[{
        "ticker": "AAPL", "report_id": "future", "generated_at": future,
    }])

    task = next(task for task in tasks if task["category"] == "reanalyze")
    assert "未知" in task["title"]
    assert all(task["category"] != "review" for task in tasks)


def test_missing_report_timestamp_requests_refresh_instead_of_recent_review():
    for value in (None, "invalid-date", 0):
        tasks = generate_daily_tasks(watchlist=["AAPL"], reports=[{"ticker": "AAPL", "generated_at": value}])
        task = next(task for task in tasks if task["category"] == "reanalyze")
        assert "未知" in task["title"]
        assert "None" not in task["title"]
        assert all(task["category"] != "review" for task in tasks)


def test_normalized_watchlist_reports_do_not_generate_duplicate_analysis():
    tasks = generate_daily_tasks(
        watchlist=[" AAPL ", "aapl", "AAPL"],
        reports=[{"ticker": " aApL ", "generated_at": datetime.now(timezone.utc).isoformat(), "report_id": "r1"}],
    )
    assert sum(task["category"] == "review" for task in tasks) == 1
    assert all(task["category"] != "generate" for task in tasks)
    assert "AAPL" in next(task for task in tasks if task["category"] == "review")["title"]


def test_days_since_naive_local_generated_at_returns_days():
    old_naive_local = (datetime.now() - timedelta(days=9)).isoformat()
    assert _days_since(old_naive_local) is not None
    assert _days_since(old_naive_local) >= 8


def test_days_since_aware_generated_at_unchanged():
    old_aware = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    assert _days_since(old_aware) == 5


def test_days_since_unparseable_returns_none():
    assert _days_since("not-a-date") is None
    assert _days_since(None) is None


def test_stale_report_with_naive_generated_at_yields_reanalyze_task():
    """端到端：naive 过期研报应产出 reanalyze 而非 review 任务。"""
    old_naive_local = (datetime.now() - timedelta(days=9)).isoformat()
    tasks = generate_daily_tasks(
        watchlist=["AAPL"],
        reports=[{"ticker": "AAPL", "generated_at": old_naive_local, "report_id": "r1"}],
    )
    cats = [t["category"] for t in tasks]
    assert "reanalyze" in cats
    assert "review" not in cats
