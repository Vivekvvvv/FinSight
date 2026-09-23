# -*- coding: utf-8 -*-
"""R32 回归：ticker 为 None 的报告（宏观/组合级）不得让待复查接口崩溃。

report_index.upsert_report 对无标的报告显式写入 ticker=None；
reports_to_review 用 report.get("ticker", "").upper()——get 默认值只对
缺键生效，键存在值 None 时 None.upper() 抛 AttributeError，
get_reports_to_review 整体 500。
"""
from __future__ import annotations

from datetime import datetime, timezone

from backend.services import reports_to_review as module


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
