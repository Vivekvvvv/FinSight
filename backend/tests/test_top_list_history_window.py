# -*- coding: utf-8 -*-
"""fetch_cn_top_list_history：pageSize 恒取 days（默认 7），显式
start_date/end_date 的更长日期窗口被静默截断。

端点 /api/stock/top-list/{ticker}/history 文档明确 start_date 优先级
高于 days，但东财请求 pageSize 只按 days 取 → 查 31 天区间最多返回 7 行。
修复：pageSize 覆盖请求窗口（上限 100），days 只作下限兜底。
"""
from __future__ import annotations

import backend.tools.tencent_history_providers as thp


class _Resp:
    status_code = 200

    def json(self):
        return {"result": {"data": []}}


def _capture_calls(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    def fake_get(url, params=None, timeout=None, headers=None):
        calls.append(params or {})
        return _Resp()

    monkeypatch.setattr(thp, "_http_get", fake_get)
    return calls


def test_pagesize_covers_explicit_date_window(monkeypatch):
    calls = _capture_calls(monkeypatch)
    thp.fetch_cn_top_list_history(
        "600519.SS", start_date="2026-01-01", end_date="2026-01-31",
    )
    # 首个请求（东财数据中心）31 天窗口至少要请求 31 行；修复前恒为 days=7 → 截断
    assert int(calls[0]["pageSize"]) >= 31


def test_pagesize_default_days_path(monkeypatch):
    calls = _capture_calls(monkeypatch)
    thp.fetch_cn_top_list_history("600519.SS", days=10)
    assert int(calls[0]["pageSize"]) >= 10


def test_pagesize_capped_at_100(monkeypatch):
    calls = _capture_calls(monkeypatch)
    thp.fetch_cn_top_list_history(
        "600519.SS", start_date="2025-01-01", end_date="2026-01-01",
    )
    assert int(calls[0]["pageSize"]) <= 100
