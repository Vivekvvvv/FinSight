# -*- coding: utf-8 -*-
"""R61 回归：companyfacts 提取优先单季跨度，不拿 YTD 累计值。

flow concept(Revenues/NetIncomeLoss)的 Q2/Q3 10-Q 同时含 3-month 与
YTD(6/9-month)context，end/fp/filed 都相同。旧代码仅按 filed tiebreak，
相等时由数组顺序决定，可能选中 YTD → Q2/Q3 虚高 2-3 倍。用 start→end
跨度区分，优先取单季(~91 天)。instant(无 start)退回按 filed 取新。
"""
from __future__ import annotations

import backend.tools.sec as sec


def _payload(concept: str, unit: str, entries: list[dict]) -> dict:
    return {"facts": {"us-gaap": {concept: {"units": {unit: entries}}}}}


def test_extract_prefers_quarter_span_over_ytd():
    # YTD 6-month(val=190)在数组里排在单季(val=100)之前，模拟旧代码会选中它
    payload = _payload("Revenues", "USD", [
        {"start": "2025-01-01", "end": "2025-06-30", "val": 190.0, "form": "10-Q", "fp": "Q2", "filed": "2025-08-01"},
        {"start": "2025-04-01", "end": "2025-06-30", "val": 100.0, "form": "10-Q", "fp": "Q2", "filed": "2025-08-01"},
    ])
    result = sec._extract_companyfacts_metric(payload, concepts=("Revenues",), unit_candidates=("USD",))
    assert result["2025Q2"] == 100.0, "应取单季值，而非 YTD 累计 190"


def test_extract_quarter_span_wins_regardless_of_order():
    # 单季在前、YTD 在后，也应保留单季
    payload = _payload("NetIncomeLoss", "USD", [
        {"start": "2025-07-01", "end": "2025-09-30", "val": 30.0, "form": "10-Q", "fp": "Q3", "filed": "2025-11-01"},
        {"start": "2025-01-01", "end": "2025-09-30", "val": 85.0, "form": "10-Q", "fp": "Q3", "filed": "2025-11-01"},
    ])
    result = sec._extract_companyfacts_metric(payload, concepts=("NetIncomeLoss",), unit_candidates=("USD",))
    assert result["2025Q3"] == 30.0, "9-month YTD(85)不应覆盖单季(30)"


def test_extract_instant_falls_back_to_latest_filed():
    # instant(无 start)：两个 entry 都非季度跨度，退回按 filed 取新（行为不变）
    payload = _payload("Assets", "USD", [
        {"end": "2025-06-30", "val": 500.0, "form": "10-Q", "fp": "Q2", "filed": "2025-08-01"},
        {"end": "2025-06-30", "val": 510.0, "form": "10-Q", "fp": "Q2", "filed": "2025-08-15"},
    ])
    result = sec._extract_companyfacts_metric(payload, concepts=("Assets",), unit_candidates=("USD",))
    assert result["2025Q2"] == 510.0, "instant 应取 filed 更新的值"
