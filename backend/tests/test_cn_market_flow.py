# -*- coding: utf-8 -*-
from __future__ import annotations

from backend.tools import cn_market_flow


class _DummyResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_fetch_fund_flow_parses_rows(monkeypatch):
    def _fake_get(_url: str, params: dict, timeout: int, headers: dict):
        return _DummyResponse(
            200,
            {
                "data": {
                    "diff": [
                        {"f12": "600519", "f13": "1", "f14": "贵州茅台", "f2": "1680.5", "f3": "2.15", "f62": "1000", "f184": "3.2"}
                    ]
                }
            },
        )

    monkeypatch.setattr(cn_market_flow, "_http_get", _fake_get)

    result = cn_market_flow.fetch_fund_flow(limit=10)

    assert result["success"] is True
    assert result["count"] == 1
    assert result["items"][0]["symbol"] == "600519.SS"
    assert result["items"][0]["change_percent"] == 2.15


def test_build_symbol_shanghai_uses_canonical_ss_suffix():
    """R88: f13=="1" 沪市行产出 .SH 后缀——代码库 CN 判定链
    （is_cn_symbol、to_tencent_code、market_router 的 A股校验、
    前端 .SS/.SZ 过滤）只认 .SS/.SZ/.BJ。资金流列表返回的
    600519.SH 回填任意 CN 端点/工具都被判"非A股"（top-list 400、
    腾讯 code None），必须用全局一致的 .SS。"""
    from backend.tools.tencent_provider import is_cn_symbol

    symbol = cn_market_flow._build_symbol({"f12": "600519", "f13": "1"})
    assert symbol == "600519.SS"
    assert is_cn_symbol(symbol)


def test_fetch_northbound_empty_payload(monkeypatch):
    def _fake_get(_url: str, params: dict, timeout: int, headers: dict):
        return _DummyResponse(200, {"data": {"diff": []}})

    monkeypatch.setattr(cn_market_flow, "_http_get", _fake_get)

    result = cn_market_flow.fetch_northbound(limit=5)

    assert result["success"] is True
    assert result["count"] == 0
    assert result["items"] == []
