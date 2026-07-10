# -*- coding: utf-8 -*-
"""R49 回归：无 FRED_API_KEY 时不得伪造宏观数据。

此前无 key 分支硬编码 cpi=3.0 / fed_rate=4.5 / unemployment=4.0（2024 估计值），
却仍返回 status="success"，被 dashboard 快照与 MacroAgent 当真实数据消费。
"""
from __future__ import annotations


def test_get_fred_data_without_key_returns_unavailable_not_fake(monkeypatch):
    from backend.tools import macro

    monkeypatch.setattr(macro, "FRED_API_KEY", "")

    result = macro.get_fred_data()

    assert result["status"] == "unavailable", "无 key 必须降级，不能报 success"
    assert result["source"] == "no_api_key"
    # 关键：数值保持 None，不得出现伪造的估计常量
    assert result["cpi"] is None
    assert result["fed_rate"] is None
    assert result["unemployment"] is None
    assert 3.0 not in result.values()
    assert 4.5 not in result.values()
    assert 4.0 not in result.values()
