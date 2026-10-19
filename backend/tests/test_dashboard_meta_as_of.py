# -*- coding: utf-8 -*-
"""Dashboard meta 的 as_of 不能把"没取到数据"盖成"刚刚更新"。

`_build_meta` 用 `_extract_as_of(payload) or _utc_now_iso()` 兜底：段取数失败时
payload 是空 {}（或空列表），抽不出数据时间，于是盖上请求时刻。前端
`DataSourceBadge.vue` 会把该 as_of 渲染成"10/19 15:04"这类新鲜度时间戳——一次
失败的取数被展示成刚刚更新的行情（项目规则 2、finsight-silent-success-forbidden）。

payload 里带得出真实时间戳的段必须保持原行为，不能被一刀切成空。
"""
from __future__ import annotations

from backend.api.dashboard_router import _build_meta


def _meta(payload, fallback_reason=None):
    return _build_meta(
        provider="yfinance",
        source_type="snapshot",
        started_at=0.0,
        payload=payload,
        fallback_reason=fallback_reason,
    )


def test_build_meta_empty_payload_has_no_as_of():
    assert _meta({})["as_of"] == ""


def test_build_meta_empty_list_payload_has_no_as_of():
    assert _meta([])["as_of"] == ""


def test_build_meta_keeps_real_as_of_from_payload():
    payload = {"price": 100.0, "as_of": "2026-10-17T14:30:00+00:00"}
    assert _meta(payload)["as_of"] == "2026-10-17T14:30:00+00:00"


def test_build_meta_keeps_latest_timestamp_in_list_payload():
    payload = [
        {"time": "2026-10-17T14:30:00+00:00"},
        {"time": "2026-10-17T15:00:00+00:00"},
    ]
    assert _meta(payload)["as_of"] == "2026-10-17T15:00:00+00:00"


def test_build_meta_failure_keeps_fallback_marker_and_no_as_of():
    meta = _meta({}, fallback_reason="snapshot_unavailable")
    assert meta["as_of"] == ""
    assert meta["fallback_used"] is True
    assert meta["fallback_reason"] == "snapshot_unavailable"
    assert meta["confidence"] == 0.35


def test_build_meta_falls_back_to_request_time_only_with_real_payload():
    """带得出内容的 payload 仍保留原有的请求时刻兜底。"""
    assert _meta({"price": 100.0})["as_of"] != ""
