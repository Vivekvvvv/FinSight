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


# ── R114：东财历史数据解析循环毒记录按条跳过 ──────────────────────────


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


def test_top_list_history_new_api_skips_poison_records(monkeypatch):
    """R114：新接口 rows 混入非 dict 条目 / TRADE_DATE=present-None——
    record.get 的 AttributeError 曾弃掉整批走旧版兜底；present-None 日期
    在排序时 None vs str TypeError 同样毁批。按条跳过；无日期记录保留
    （date=''，排序安全）。"""
    payload = {
        "result": {
            "data": [
                {
                    "SECURITY_NAME_ABBR": "贵州茅台",
                    "TRADE_DATE": "2026-09-24",
                    "EXPLANATION": "龙虎榜",
                    "CLOSE_PRICE": "1400",
                    "BILLBOARD_BUY_AMT": "1000",
                },
                "junk-entry",
                None,
                {"SECURITY_NAME_ABBR": "无日期股", "TRADE_DATE": None},
            ]
        }
    }

    def fake_get(url, **kw):
        if "datacenter-web" in url:
            return _JsonResp(payload)
        return _TextResp('var data_tab_1 = [{"SCode":"600519","SName":"LEGACY"}];')

    monkeypatch.setattr(thp, "_http_get", fake_get)

    results = thp.fetch_cn_top_list_history("600519.SS")

    assert results, "毒记录不得把整批逼回旧版"
    assert all(r["source"] == "eastmoney_datacenter" for r in results)
    # 无日期记录被日期窗口优雅过滤（date_key="" < 任何 start_date）
    assert len(results) == 1
    assert results[0]["date"] == "2026-09-24"


def test_top_list_history_legacy_skips_poison_records(monkeypatch):
    """R114：旧版 data_list 非 dict 条目 / Tdate=present-None——item.get
    AttributeError 或排序 TypeError 曾让整个旧版查询返回 []（无更深兜底）。"""
    payload = {"result": {"data": []}}  # 新接口空 → 走旧版
    legacy_text = (
        'var data_tab_1 = ['
        '"junk",'
        '{"SCode":"600519","SName":"贵州茅台","Tdate":"2026-09-24",'
        '"Bmoney":"1000","Smoney":"500","JmMoney":"500"},'
        '{"SCode":"600519","SName":"无日期股","Tdate":null}'
        '];'
    )

    def fake_get(url, **kw):
        if "datacenter-web" in url:
            return _JsonResp(payload)
        return _TextResp(legacy_text)

    monkeypatch.setattr(thp, "_http_get", fake_get)

    results = thp.fetch_cn_top_list_history("600519.SS")

    assert len(results) == 2, "旧版毒条目不得毁掉整个查询"
    assert results[0]["stock_name"] == "贵州茅台"


def test_north_flow_history_skips_non_string_klines(monkeypatch):
    """R114：北向资金 klines 混入非 str 条目——kline.split(',') 的
    AttributeError 落进函数级 except，整份历史返回 []。"""
    text = (
        '{"rc":0,"data":{"klines":['
        '"2026-09-24,1000,500,300",'
        '{"bad":1},'
        'null,'
        '"2026-09-23,900,400,200",'
        '"short"'
        ']}}'
    )
    monkeypatch.setattr(thp, "_http_get", lambda *a, **k: _TextResp(text))

    results = thp.fetch_north_flow_history(days=30)

    assert len(results) == 2
    assert results[0]["date"] == "2026-09-24"
    assert results[0]["north_flow"] == 10_000_000.0  # 万元转元


def test_margin_history_skips_poison_records(monkeypatch):
    """R114：融资融券历史两层接口各自毒记录按条跳过——
    新接口推导式非 dict → AttributeError 弃批落旧版；旧版循环同错 → []。
    DATE/TRADE_DATE present-None 在排序 None vs str TypeError 毁批。"""
    new_payload = {
        "result": {
            "data": [
                {"DATE": "2026-09-24", "RZYE": "111"},
                "junk-entry",
                {"DATE": None, "RZYE": "5"},
            ]
        }
    }
    legacy_payload = {
        "code": 0,
        "result": {
            "data": [
                {"TRADE_DATE": "2026-09-20", "RZYE": "999"},
                None,
            ]
        },
    }

    def fake_get(url, params=None, **kw):
        report = (params or {}).get("reportName", "")
        if report == "RPTA_WEB_RZRQ_GGMX":
            return _JsonResp(new_payload)
        return _JsonResp(legacy_payload)

    monkeypatch.setattr(thp, "_http_get", fake_get)

    # 新接口路径：毒记录不毁批，RZYE=111 证明走的新接口而非旧版兜底
    results = thp.fetch_margin_trading_history("600519.SS")
    assert len(results) == 2
    assert results[0]["margin_balance"] == 111.0

    # 新接口空 → 旧版路径毒记录同样按条跳过
    new_payload["result"]["data"] = []
    results = thp.fetch_margin_trading_history("600519.SS")
    assert len(results) == 1
    assert results[0]["margin_balance"] == 999.0
