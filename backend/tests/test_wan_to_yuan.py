# -*- coding: utf-8 -*-
"""R53 回归：万元转元不因单行非数值占位而丢弃整批数据。

safe_float 对空串/"-"/None 返回 None，此前 `safe_float(x) * 10000` 会
`None * 10000` 抛 TypeError，在循环里被外层 except 吞成 return []，
一行停牌/节假日占位就丢弃整个多日北向序列或整批龙虎榜。_wan_to_yuan
让坏字段变 None、不牵连整批。
"""
from __future__ import annotations

import pytest

from backend.tools import tencent_provider as mod
from backend.tools.tencent_provider import _wan_to_yuan


def test_wan_to_yuan_handles_bad_values():
    assert _wan_to_yuan("5") == 50000.0
    assert _wan_to_yuan(3.2) == 32000.0
    assert _wan_to_yuan(0) == 0.0
    # 关键：非数值占位返回 None 而不是抛 TypeError
    assert _wan_to_yuan("-") is None
    assert _wan_to_yuan("") is None
    assert _wan_to_yuan(None) is None


class _Resp:
    status_code = 200
    text = (
        '{"rc": 0, "data": {"klines": ['
        '"2026-01-05,100,60,40",'
        '"2026-01-06,-,-,-",'          # 停牌/节假日占位行
        '"2026-01-07,200,120,80"'
        ']}}'
    )


def test_north_flow_history_survives_placeholder_row(monkeypatch):
    monkeypatch.setattr(mod, "_http_get", lambda *a, **k: _Resp())

    records = mod.fetch_north_flow_history(days=3)

    # 修复前：占位行 safe_float("-")*10000 崩溃 → except → 整批返回 []
    assert len(records) == 3, "一行占位不应丢弃整个多日序列"

    by_date = {r["date"]: r for r in records}
    # 好行正确万元转元
    assert by_date["2026-01-05"]["north_flow"] == 100 * 10000
    assert by_date["2026-01-07"]["sh_flow"] == 120 * 10000
    # 坏行字段降级为 None，但该行（日期）仍保留可见
    assert by_date["2026-01-06"]["north_flow"] is None
    assert by_date["2026-01-06"]["sh_flow"] is None
