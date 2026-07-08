# -*- coding: utf-8 -*-
"""R18 回归：东财 kamt.rtmin 北向资金解析。

旧代码把 result_data["s2n"] 同时当标量 float（头部合计）与含 "data" 的
dict（分时列表）解析——但真实结构是字符串列表（每行
"HH:MM,沪流入,沪余额,深流入,北向合计"，万元），两个分支互斥且都不成立，
返回体恒为 north_flow=0.0 + data_points=[]，北向资金功能整体静默失效。
"""
from __future__ import annotations

from backend.tools import tencent_provider


class _FakeResp:
    status_code = 200
    text = (
        'jQuery({"rc":0,"rt":6,"svr":1,"lt":1,"full":1,"data":{'
        '"s2n":["09:30,-,-,-,-",'
        '"09:31,1000.5,520000.0,500.25,1500.75",'
        '"09:32,2000.0,519000.0,1000.0,3000.0"]}})'
    )


def test_north_flow_parses_kamt_rtmin_rows(monkeypatch):
    monkeypatch.setattr(tencent_provider, "_http_get", lambda *a, **k: _FakeResp())

    result = tencent_provider.fetch_north_flow(date="2026-07-06")

    assert result is not None
    # 头部合计取最新有效分时点，万元转元
    assert result["north_flow"] == 3000.0 * 10000
    assert result["sh_flow"] == 2000.0 * 10000
    assert result["sz_flow"] == 1000.0 * 10000
    # 分时点：跳过未开盘的 "-" 行，其余按北向合计列生成
    assert [p["time"] for p in result["data_points"]] == ["09:31", "09:32"]
    assert result["data_points"][0]["north"] == 1500.75 * 10000


def test_north_flow_returns_zero_when_all_rows_premarket(monkeypatch):
    class _EmptyResp:
        status_code = 200
        text = 'jQuery({"rc":0,"data":{"s2n":["09:15,-,-,-,-"]}})'

    monkeypatch.setattr(tencent_provider, "_http_get", lambda *a, **k: _EmptyResp())
    result = tencent_provider.fetch_north_flow(date="2026-07-06")
    assert result is not None
    assert result["north_flow"] == 0.0
    assert result["data_points"] == []
