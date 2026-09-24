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


# ── R113：龙虎榜毒记录不得毁批 / 日期不可解析不得当"过期"跳过兜底 ──────


class _JsonResp:
    status_code = 200
    text = ""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _TextResp:
    status_code = 200

    def __init__(self, text: str):
        self.text = text


_LEGACY_TOP_LIST_TEXT = (
    'var data_tab_1 = ['
    '"junk-entry",'
    'null,'
    '{"SCode":"600519","SName":"贵州茅台","Tdate":"2026-09-24",'
    '"Bmoney":"1000","Smoney":"500","JmMoney":"500",'
    '"ClosePrice":"1400","Chgradio":"2.5","Ctypedes":"龙虎榜",'
    '"TurnoverRate":"1.2"}'
    '];'
)


def _route_top_list(monkeypatch, new_api_payload):
    """新接口返回给定 payload，旧版接口返回含毒条目的合法 data_tab_1。"""

    def fake_get(url, **kw):
        if "datacenter-web" in url:
            return _JsonResp(new_api_payload)
        return _TextResp(_LEGACY_TOP_LIST_TEXT)

    monkeypatch.setattr(tencent_provider, "_http_get", fake_get)


def test_top_list_none_date_falls_back_to_legacy(monkeypatch):
    """R113：新接口最新记录 TRADE_DATE=None——不可解析≠过期。

    _is_recent_eastmoney_date(None) → False → 旧代码直接 return None，
    旧版龙虎榜兜底被跳过。毒记录应落到旧版接口再试。"""
    _route_top_list(
        monkeypatch,
        {"result": {"data": [{"SECURITY_NAME_ABBR": "X", "TRADE_DATE": None}]}},
    )

    result = tencent_provider.fetch_cn_top_list("600519.SS", include_seats=False)

    assert result is not None, "TRADE_DATE=None 不得当过期放弃旧版兜底"
    assert result["source"] == "eastmoney"
    assert result["stock_name"] == "贵州茅台"


def test_top_list_stale_record_still_returns_none(monkeypatch):
    """日期可解析且确超龄 → 仍是"过期"语义：返回 None，不落旧版（旧版
    只会给出同样的陈旧数据）。保护既有短路行为不被本修复破坏。"""
    _route_top_list(
        monkeypatch,
        {"result": {"data": [{"SECURITY_NAME_ABBR": "X", "TRADE_DATE": "2020-01-01"}]}},
    )

    assert tencent_provider.fetch_cn_top_list("600519.SS", include_seats=False) is None


def test_top_list_non_dict_record_falls_back_and_legacy_skips_poison(monkeypatch):
    """R113 同缺陷类两处：
    1) 新接口 rows[0] 非 dict——此前靠 AttributeError→except 碰巧落到旧版，
       现显式跳过新版解析落兜底（结果不变，不再依赖异常驱动）。
    2) 旧版 data_list 里非 dict 条目（'junk-entry'/null）——item.get 抛
       AttributeError 曾让整个旧版查询返回 None，现按条跳过。"""
    _route_top_list(
        monkeypatch,
        {"result": {"data": ["not-a-dict"]}},
    )

    result = tencent_provider.fetch_cn_top_list("600519.SS", include_seats=False)

    assert result is not None, "旧版 data_list 毒条目不得毁掉整个查询"
    assert result["stock_name"] == "贵州茅台"
    assert result["buy_amount"] == 10_000_000.0  # Bmoney 1000万 → 元


def test_seats_skip_non_dict_entries(monkeypatch):
    """R113 同缺陷类：席位列表混入非 dict 条目 / data_tab 非 list——
    seat.get 的 AttributeError 与 [:5] 的 TypeError 曾被外层 except 吞成
    全部席位 None。按条跳过、非 list 置空。"""
    text = (
        'var data_tab_2 = ['
        '"junk",'
        '{"SName":"机构专用","Bmoney":"1000","Smoney":"500"},'
        'null'
        '];'
        'var data_tab_3 = {"not":"a list"};'  # 非 list → [:5] TypeError 变体
    )
    monkeypatch.setattr(
        tencent_provider, "_http_get", lambda *a, **k: _TextResp(text)
    )

    seats = tencent_provider._fetch_top_list_seats("600519", "2026-09-24")

    assert seats is not None
    assert len(seats["buy_seats"]) == 1
    assert seats["buy_seats"][0]["seat_name"] == "机构专用"
    assert seats["sell_seats"] == []
