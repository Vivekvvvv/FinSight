# -*- coding: utf-8 -*-
"""_fetch_top_list_seats：单个席位金额缺失不得拖垮全部席位明细。

bug：``"net_amount": buy_amt - sell_amt``——_wan_to_yuan 对 "-"/null 返回
None（本文件 R53 注释明确的约定：东财占位符经 safe_float→None），
None - None → TypeError → 被外层 except 吞成整个函数返回 None →
fetch_cn_top_list 静默丢失 buy_seats/sell_seats 全部席位（一个坏行灭掉
10 个席位）。修复：net_amount 任一侧 None 时返回 None，其余席位照常。
"""
from __future__ import annotations

from backend.tools import tencent_provider


class _Resp:
    status_code = 200

    def __init__(self, text: str):
        self.text = text


def _seat_payload_text() -> str:
    # data_tab_2=买入席位，data_tab_3=卖出席位；含 "-" 与 null 占位值
    return (
        'var data_tab_2 = ['
        '{"SName":"机构专用","Bmoney":"1000","Smoney":"500"},'
        '{"SName":"游资席位A","Bmoney":"-","Smoney":"-"},'
        '{"SName":"深股通专用","Bmoney":null,"Smoney":"300"}'
        '];'
        'var data_tab_3 = ['
        '{"SName":"卖出机构","Bmoney":"200","Smoney":"900"}'
        '];'
    )


def test_one_missing_seat_amount_does_not_lose_all_seats(monkeypatch):
    monkeypatch.setattr(
        tencent_provider,
        "_http_get",
        lambda *a, **k: _Resp(_seat_payload_text()),
    )

    seats = tencent_provider._fetch_top_list_seats("600519", "2026-06-14")

    # 修复前：TypeError → except → None（全部席位丢失）
    assert seats is not None
    assert len(seats["buy_seats"]) == 3
    assert len(seats["sell_seats"]) == 1

    # 正常席位照常算净额（万元→元）
    assert seats["buy_seats"][0]["net_amount"] == 5_000_000.0
    # 缺失两侧 → net_amount=None（字段缺失，不假装 0）
    assert seats["buy_seats"][1]["net_amount"] is None
    # 一侧缺失 → None
    assert seats["buy_seats"][2]["net_amount"] is None
    # 卖出席位不受影响
    assert seats["sell_seats"][0]["net_amount"] == -7_000_000.0


def test_seats_fetch_failure_still_returns_none(monkeypatch):
    """HTTP 失败仍返回 None（不破坏既有失败语义）。"""
    class _Bad:
        status_code = 500
        text = ""

    monkeypatch.setattr(tencent_provider, "_http_get", lambda *a, **k: _Bad())
    assert tencent_provider._fetch_top_list_seats("600519") is None
