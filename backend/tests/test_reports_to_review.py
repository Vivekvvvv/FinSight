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
