# -*- coding: utf-8 -*-
"""R52 回归：CN Eastmoney 工具在上游故障时必须报 success=False。

此前 fetch_fund_flow/fetch_northbound/fetch_limit_board/fetch_lhb/
fetch_concept_map 把请求异常/非 200 吞成空列表后无条件返回
success=True——Eastmoney 不可达（境外部署/被限流）时，agent 会把
"数据源中断"当成"今日无资金流/无概念/无龙虎榜"的真实市况。
修复后：故障 → success=False + error；接口正常应答 0 行（节假日）
仍是 success=True + count=0。
"""
from __future__ import annotations

from typing import Any


def test_malformed_concept_containers_cannot_be_reported_as_empty_results(monkeypatch):
    from backend.tools import concept_map as module
    for data in ({"diff": "bad"}, {"diff": {}}, ["bad"], 123):
        monkeypatch.setattr(module, "_http_get", lambda *args, **kwargs: _Resp(payload={"data": data}))
        assert module.fetch_concept_map()["success"] is False


def test_concept_board_business_failure_cannot_appear_as_success(monkeypatch):
    from backend.tools import concept_map as module
    for failure in ({"success": False}, {"error": "offline"}, {"status": " Failed "}, {"rc": 1}):
        monkeypatch.setattr(module, "_http_get", lambda *args, **kwargs: _Resp(payload={"data": None, **failure}))
        assert module.fetch_concept_map()["success"] is False


def test_lhb_invalid_result_shapes_cannot_appear_as_genuine_empty_data(monkeypatch):
    from backend.tools import cn_market_board as module
    for result in ({"data": "bad"}, {"data": {}}, [], 123):
        monkeypatch.setattr(module, "_http_get", lambda *args, **kwargs: _Resp(payload={"result": result}))
        assert module.fetch_lhb()["success"] is False


def test_lhb_business_failure_cannot_be_reported_as_success(monkeypatch):
    from backend.tools import cn_market_board as module
    for failure in ({"success": False}, {"error": "offline"}, {"status": " Failed "}):
        monkeypatch.setattr(module, "_http_get", lambda *args, **kwargs: _Resp(payload={"result": None, **failure}))
        assert module.fetch_lhb()["success"] is False


def test_malformed_board_rows_container_is_unavailable_not_a_valid_empty_list(monkeypatch):
    from backend.tools import cn_market_board as module
    for data in ({"diff": "bad"}, {"diff": {}}, ["bad"], None):
        payload = {"data": data} if data is not None else None
        monkeypatch.setattr(module, "_http_get", lambda *args, **kwargs: _Resp(payload=payload))
        assert module.fetch_limit_board()["success"] is False


def test_limit_board_business_failure_cannot_appear_as_an_empty_market_day(monkeypatch):
    from backend.tools import cn_market_board as module
    for failure in ({"success": False}, {"error": "offline"}, {"status": " Failed "}, {"rc": 1}):
        monkeypatch.setattr(module, "_http_get", lambda *args, **kwargs: _Resp(payload={"data": None, **failure}))
        assert module.fetch_limit_board()["success"] is False


def test_malformed_flow_rows_container_is_unavailable_not_a_valid_empty_list(monkeypatch):
    from backend.tools import cn_market_flow as module
    for data in ({"diff": "bad"}, {"diff": {}}, ["bad"], None):
        payload = {"data": data} if data is not None else None
        monkeypatch.setattr(module, "_http_get", lambda *args, **kwargs: _Resp(payload=payload))
        assert module.fetch_fund_flow()["success"] is False


def test_flow_business_failure_cannot_appear_as_an_empty_market_day(monkeypatch):
    from backend.tools import cn_market_flow as module
    for failure in ({"success": False}, {"error": "offline"}, {"status": " Failed "}, {"rc": 1}):
        monkeypatch.setattr(module, "_http_get", lambda *args, **kwargs: _Resp(payload={"data": None, **failure}))
        assert module.fetch_fund_flow()["success"] is False
        assert module.fetch_northbound()["success"] is False


class _Resp:
    def __init__(self, status_code: int = 200, payload: Any = None):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


def _boom(*args, **kwargs):
    raise ConnectionError("eastmoney unreachable")


# ── 故障 → success=False ─────────────────────────────────────────


def test_fund_flow_failure_is_not_success(monkeypatch):
    from backend.tools import cn_market_flow as mod

    monkeypatch.setattr(mod, "_http_get", _boom)
    result = mod.fetch_fund_flow(limit=5)
    assert result["success"] is False
    assert result["error"]
    assert result["items"] == []


def test_northbound_failure_is_not_success(monkeypatch):
    from backend.tools import cn_market_flow as mod

    monkeypatch.setattr(mod, "_http_get", _boom)
    result = mod.fetch_northbound(limit=5)
    assert result["success"] is False


def test_limit_board_failure_is_not_success(monkeypatch):
    from backend.tools import cn_market_board as mod

    monkeypatch.setattr(mod, "_http_get", _boom)
    result = mod.fetch_limit_board(limit=5)
    assert result["success"] is False


def test_lhb_failure_is_not_success(monkeypatch):
    from backend.tools import cn_market_board as mod

    monkeypatch.setattr(mod, "_http_get", _boom)
    result = mod.fetch_lhb(limit=5)
    assert result["success"] is False


def test_lhb_http_500_is_not_success(monkeypatch):
    from backend.tools import cn_market_board as mod

    monkeypatch.setattr(mod, "_http_get", lambda *a, **k: _Resp(status_code=502))
    result = mod.fetch_lhb(limit=5)
    assert result["success"] is False


def test_concept_map_failure_is_not_success(monkeypatch):
    from backend.tools import concept_map as mod

    monkeypatch.setattr(mod, "_http_get", _boom)
    result = mod.fetch_concept_map(keyword="", limit=5)
    assert result["success"] is False


# ── 正常应答（含真空）→ success=True ─────────────────────────────


def test_fund_flow_rows_parsed(monkeypatch):
    from backend.tools import cn_market_flow as mod

    payload = {"data": {"diff": [
        {"f12": "600519", "f13": "1", "f14": "贵州茅台", "f2": 1700.0, "f3": 1.2, "f62": 1.5e8, "f184": 3.2},
    ]}}
    monkeypatch.setattr(mod, "_http_get", lambda *a, **k: _Resp(payload=payload))
    result = mod.fetch_fund_flow(limit=5)
    assert result["success"] is True
    assert result["count"] == 1
    assert result["items"][0]["symbol"] == "600519.SS"


def test_fund_flow_genuinely_empty_still_success(monkeypatch):
    # 接口正常应答但 data 为 null（真的没有行）→ 不是故障
    from backend.tools import cn_market_flow as mod

    monkeypatch.setattr(mod, "_http_get", lambda *a, **k: _Resp(payload={"data": None}))
    result = mod.fetch_fund_flow(limit=5)
    assert result["success"] is True
    assert result["count"] == 0


def test_lhb_genuinely_empty_still_success(monkeypatch):
    # 周末/节假日 result 为 null 是合法的"当日无龙虎榜"
    from backend.tools import cn_market_board as mod

    monkeypatch.setattr(mod, "_http_get", lambda *a, **k: _Resp(payload={"result": None, "success": True}))
    result = mod.fetch_lhb(limit=5)
    assert result["success"] is True
    assert result["count"] == 0


def test_concept_map_rows_parsed(monkeypatch):
    from backend.tools import concept_map as mod

    payload = {"data": {"diff": [
        {"f12": "BK0800", "f14": "人工智能", "f3": 2.5, "f62": 8.0e8, "f104": 50, "f105": 10},
    ]}}
    monkeypatch.setattr(mod, "_http_get", lambda *a, **k: _Resp(payload=payload))
    result = mod.fetch_concept_map(keyword="智能", limit=5)
    assert result["success"] is True
    assert result["count"] == 1
    assert result["items"][0]["concept_name"] == "人工智能"
