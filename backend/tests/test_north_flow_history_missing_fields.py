# -*- coding: utf-8 -*-
"""R20 回归：北向/龙虎榜历史接口里缺失的字段不能补 0。

`fetch_north_flow_history` 与 `fetch_cn_top_list_history` 旧版分支把"上游没回
该列"补成 0，前端表格与走势条会把它显示成"北向净流入 0 元""机构净买入 0 元"
——一次从未取到过的资金流被当成事实结论（项目规则 2）。真实的 0 必须保留。
"""
from __future__ import annotations

import json

import backend.tools.tencent_history_providers as thp


def _json_resp(payload):
    class _Resp:
        status_code = 200

        def json(self):
            return payload

    return _Resp()


def _kline_resp(klines):
    """北向资金历史走 `json_loads_strict(resp.text)`，桩必须提供 text。"""

    class _Resp:
        status_code = 200
        text = json.dumps({"rc": 0, "data": {"klines": klines}})

    return _Resp()


def test_north_flow_history_keeps_missing_flows_none(monkeypatch):
    monkeypatch.setattr(
        thp, "_http_get",
        lambda *a, **k: _kline_resp(["2026-09-20,-,-,-", "2026-09-21,0.0,0.0,0.0"]),
    )
    # 只有 dash 占位行：任何"缺失即 0"的折叠都会在下游渲染成"净流入 0 元"。

    results = thp.fetch_north_flow_history(days=30)

    assert len(results) == 2
    by_date = {row["date"]: row for row in results}
    assert by_date["2026-09-20"]["north_flow"] is None
    assert by_date["2026-09-20"]["sh_flow"] is None
    assert by_date["2026-09-20"]["sz_flow"] is None
    # 真实平盘（0 元）是合法结论，不能被吞成 None。
    assert by_date["2026-09-21"]["north_flow"] == 0.0


def test_top_list_history_legacy_keeps_missing_amounts_none(monkeypatch):
    legacy_text = (
        'var data_tab_1 = [{"SCode":"600519","SName":"贵州茅台",'
        '"Tdate":"2026-09-20","Ctypedes":"日涨幅偏离值达7%",'
        '"ClosePrice":"1500.0","Chgradio":"3.2","Bmoney":null,"Smoney":"-",'
        '"JmMoney":null,"TurnoverRate":"1.1"}];'
    )

    class _Resp:
        status_code = 200
        text = legacy_text

        def json(self):
            # 新版接口返回空数据集，触发旧版分支。
            return {"result": {"data": []}}

    monkeypatch.setattr(thp, "_http_get", lambda *a, **k: _Resp())

    results = thp.fetch_cn_top_list_history(
        "600519.SS", start_date="2026-09-01", end_date="2026-09-30",
    )

    assert len(results) == 1
    row = results[0]
    assert row["buy_amount"] is None
    assert row["sell_amount"] is None
    assert row["net_buy"] is None
    assert row["close_price"] == 1500.0
