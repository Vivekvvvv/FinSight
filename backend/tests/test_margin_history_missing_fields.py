# -*- coding: utf-8 -*-
"""R19 回归：融资融券历史里缺失的字段不能补 0。

`/api/stock/margin/{ticker}/history` 把行内数值原样交给前端表格，
旧代码 `safe_float(...) or 0.0` 让"上游没回该列"显示成"融资余额 0 元"
——一次从未取到过的余额被当成事实（项目规则 2）。真实的 0 必须保留。
"""
from __future__ import annotations

import backend.tools.tencent_history_providers as thp


def _json_resp(payload):
    class _Resp:
        status_code = 200

        def json(self):
            return payload

    return _Resp()


def _patch_rows(monkeypatch, rows):
    monkeypatch.setattr(thp, "_http_get", lambda *a, **k: _json_resp({"result": {"data": rows}}))


def test_margin_history_keeps_missing_fields_none(monkeypatch):
    _patch_rows(monkeypatch, [{"DATE": "2026-09-20", "RZYE": None, "RZMRE": "-"}])

    results = thp.fetch_margin_trading_history("600519.SS")

    assert len(results) == 1
    row = results[0]
    assert row["margin_balance"] is None
    assert row["margin_buy"] is None
    assert row["short_balance"] is None
    assert row["total_balance"] is None


def test_margin_history_keeps_genuine_zero(monkeypatch):
    _patch_rows(monkeypatch, [{"DATE": "2026-09-20", "RZYE": "0", "RZRQYE": 0}])

    results = thp.fetch_margin_trading_history("600519.SS")

    assert results[0]["margin_balance"] == 0.0
    assert results[0]["total_balance"] == 0.0


def test_top_list_history_keeps_missing_net_buy_none(monkeypatch):
    _patch_rows(monkeypatch, [{
        "TRADE_DATE": "2026-09-20",
        "SECURITY_NAME_ABBR": "贵州茅台",
        "BILLBOARD_NET_AMT": None,
    }])

    results = thp.fetch_cn_top_list_history(
        "600519.SS", start_date="2026-09-01", end_date="2026-09-30",
    )

    assert len(results) == 1
    assert results[0]["net_buy"] is None
    assert results[0]["buy_amount"] is None
