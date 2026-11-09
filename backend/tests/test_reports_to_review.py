# -*- coding: utf-8 -*-
"""R32 回归：ticker 为 None 的报告（宏观/组合级）不得让待复查接口崩溃。

report_index.upsert_report 对无标的报告显式写入 ticker=None；
reports_to_review 用 report.get("ticker", "").upper()——get 默认值只对
缺键生效，键存在值 None 时 None.upper() 抛 AttributeError，
get_reports_to_review 整体 500。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.services import reports_to_review as module


def test_future_report_data_time_requires_review(monkeypatch):
    from datetime import timedelta
    rows = [{"report_id": "future", "ticker": "AAPL",
             "as_of": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}]
    monkeypatch.setattr(module, "get_report_index_store",
                        lambda: type("Store", (), {"list_reports": lambda self, **kwargs: rows})())
    result = module.get_reports_to_review("s", ["AAPL"], [])
    assert [row["report_id"] for row in result] == ["future"]
    assert result[0]["_review_score"] == 25


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_failed_reports_do_not_displace_valid_review_candidates(monkeypatch, failure):
    rows = [{"report_id": "bad", "review_status": "watch", **failure},
            {"report_id": "valid", "review_status": "watch"}]
    monkeypatch.setattr(module, "get_report_index_store",
                        lambda: type("Store", (), {"list_reports": lambda self, **kwargs: rows})())
    assert [row["report_id"] for row in module.get_reports_to_review("s", [], [], limit=1)] == ["valid"]


@pytest.mark.parametrize("report_id", [None, "", "  ", True, [], 123])
def test_review_candidates_require_report_identifiers(monkeypatch, report_id):
    rows = [{"report_id": report_id, "review_status": "watch"}, {"report_id": "valid", "review_status": "watch"}]
    monkeypatch.setattr(module, "get_report_index_store",
                        lambda: type("Store", (), {"list_reports": lambda self, **kwargs: rows})())
    assert [row["report_id"] for row in module.get_reports_to_review("s", [], [], limit=1)] == ["valid"]


@pytest.mark.parametrize("limit", [0, -1])
def test_empty_review_limits_stop_before_reading_reports(monkeypatch, limit):
    calls = []
    monkeypatch.setattr(module, "get_report_index_store", lambda: calls.append("store"))
    assert module.get_reports_to_review("session", [], [], limit=limit) == []
    assert calls == []


def test_review_watched_tickers_skip_malformed_entries(monkeypatch):
    monkeypatch.setattr(module, "get_report_index_store", lambda: type("Store", (), {
        "list_reports": lambda self, **kwargs: [{"report_id": "r1", "ticker": "AAPL", "as_of": "2020-01-01"}],
    })())
    result = module.get_reports_to_review("session", [None, 123, {}, "AAPL"], [])
    assert [report["report_id"] for report in result] == ["r1"]


@pytest.mark.parametrize("watched, reported", [("AAPL", " aapl "), (" AAPL ", "aapl")])
def test_review_matches_normalized_report_and_watched_symbols(monkeypatch, watched, reported):
    monkeypatch.setattr(module, "get_report_index_store", lambda: type("Store", (), {
        "list_reports": lambda self, **kwargs: [{"report_id": "r1", "ticker": reported, "as_of": "2020-01-01"}],
    })())
    result = module.get_reports_to_review("session", [watched], [])
    assert [report["report_id"] for report in result] == ["r1"]


def test_review_annotations_do_not_mutate_source_report_rows(monkeypatch):
    reports = [{"report_id": "r1", "ticker": "AAPL", "review_status": "watch"}]
    original = dict(reports[0])
    monkeypatch.setattr(module, "get_report_index_store", lambda: type("Store", (), {
        "list_reports": lambda self, **kwargs: reports,
    })())
    result = module.get_reports_to_review("session", [], [])
    assert result[0]["_review_score"] == 50
    assert reports[0] == original


def test_review_list_preserves_valid_reports_after_malformed_rows(monkeypatch):
    monkeypatch.setattr(module, "get_report_index_store", lambda: type("Store", (), {
        "list_reports": lambda self, **kwargs: [None, "bad", {"report_id": "r1", "review_status": "watch"}],
    })())
    result = module.get_reports_to_review("session", [], [])
    assert [report["report_id"] for report in result] == ["r1"]


def test_review_flags_normalize_case_and_whitespace(monkeypatch):
    monkeypatch.setattr(module, "get_report_index_store", lambda: type("Store", (), {
        "list_reports": lambda self, **kwargs: [{"report_id": "r1", "review_status": " WATCH ",
                                               "freshness_status": " LIVE ", "quality_state": " BLOCK "}],
    })())
    result = module.get_reports_to_review("session", [], [])
    assert result[0]["_review_score"] == 90


@pytest.mark.parametrize("as_of", [None, "not-a-date", 123, {"bad": "timestamp"}])
def test_watched_report_with_unknown_data_age_requires_review(monkeypatch, as_of):
    reports = [
        {"report_id": "unknown", "ticker": "AAPL", "as_of": as_of, "generated_at": None,
         "freshness_status": "live", "quality_state": "pass", "review_status": "new"},
        {"report_id": "unwatched", "ticker": "MSFT", "generated_at": None},
    ]

    class Store:
        def list_reports(self, **kwargs):
            return reports

    monkeypatch.setattr(module, "get_report_index_store", lambda: Store())

    result = module.get_reports_to_review("session", ["AAPL"], [])

    assert [report["report_id"] for report in result] == ["unknown"]
    assert any("时间不可用" in reason for reason in result[0]["_review_reasons"])


def test_none_ticker_report_does_not_crash(monkeypatch):
    reports = [
        {
            "report_id": "r-macro-1",
            "ticker": None,  # 宏观报告：键存在、值为 None
            "as_of": datetime.now(timezone.utc).isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "review_status": "watch",
            "freshness_status": "live",
            "quality_state": "pass",
            "title": "宏观周报",
        },
        {
            "report_id": "r-aapl-1",
            "ticker": "AAPL",
            "as_of": "2020-01-01T00:00:00+00:00",  # 过期且在关注列表 → 命中规则 4
            "generated_at": "2020-01-01T00:00:00+00:00",
            "review_status": "",
            "freshness_status": "live",
            "quality_state": "pass",
            "title": "AAPL 深度",
        },
    ]

    class _FakeStore:
        def list_reports(self, **_kwargs):
            return reports

    monkeypatch.setattr(module, "get_report_index_store", lambda: _FakeStore())

    result = module.get_reports_to_review(
        "private:alice:default", ["AAPL"], [],
    )
    # 旧代码在宏观报告的 None.upper() 处 AttributeError
    assert any(item.get("report_id") == "r-aapl-1" for item in result)


def test_naive_generated_at_stale_report_not_hidden_by_tz_misinterpretation(monkeypatch):
    """report_index 里的 generated_at 由 ir.py/validator.py 以
    datetime.now().isoformat() 写入——naive 本地时间。
    replace(tzinfo=utc) 把它当成 UTC → 瞬间后移 +8h：
    真实已 7d5h 的陈旧报告被算成 6d21h，规则 4 漏判、从待复查列表消失。
    naive 值须按本机时区归一（与 task_router 的既有修复一致）。"""
    from datetime import timedelta

    naive_generated = (datetime.now() - timedelta(days=7, hours=5)).isoformat()
    reports = [
        {
            "report_id": "r-stale-1",
            "ticker": "OLD1",
            "as_of": None,                      # 落到 generated_at 回退
            "generated_at": naive_generated,    # naive 本地时间，已超 7 天阈值
            "review_status": "",
            "freshness_status": "live",
            "quality_state": "pass",
            "title": "OLD1 旧报告",
        },
    ]

    class _FakeStore:
        def list_reports(self, **_kwargs):
            return reports

    monkeypatch.setattr(module, "get_report_index_store", lambda: _FakeStore())

    result = module.get_reports_to_review("s1", ["OLD1"], [])
    ids = [item.get("report_id") for item in result]
    assert "r-stale-1" in ids, (
        "naive generated_at 被当作 UTC 后移 +8h，7d5h 的陈旧报告漏判"
    )
