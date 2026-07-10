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
    assert result["items"][0]["symbol"] == "600519.SH"


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
