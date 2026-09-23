# -*- coding: utf-8 -*-
from __future__ import annotations

from backend.tools import cn_market_board


class _DummyResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_fetch_limit_board_parses_rows(monkeypatch):
    def _fake_get(_url: str, params: dict, timeout: int, headers: dict):
        return _DummyResponse(
            200,
            {"data": {"diff": [{"f12": "000001", "f14": "平安银行", "f2": "12.30", "f3": "1.2", "f8": "3.5", "f10": "1.1", "f62": "500"}]}},
        )

    monkeypatch.setattr(cn_market_board, "_http_get", _fake_get)

    result = cn_market_board.fetch_limit_board(limit=20)

    assert result["success"] is True
    assert result["count"] == 1
    assert result["items"][0]["symbol"] == "000001.SZ"
    assert result["items"][0]["last_price"] == 12.3


def test_fetch_lhb_parses_rows(monkeypatch):
    def _fake_get(_url: str, params: dict, timeout: int, headers: dict):
        return _DummyResponse(
            200,
            {
                "result": {
                    "data": [
                        {
                            "SECURITY_CODE": "002594",
                            "SECURITY_NAME_ABBR": "比亚迪",
                            "TRADE_DATE": "2026-02-28",
                            "CLOSE_PRICE": "200",
                            "CHANGE_RATE": "5.0",
                            "NET_BUY_AMT": "1000000",
                            "BUY_AMT": "2000000",
                            "SELL_AMT": "1000000",
                            "EXPLAIN": "日涨幅偏离值达7%",
                        }
                    ]
                }
            },
        )

    monkeypatch.setattr(cn_market_board, "_http_get", _fake_get)

    result = cn_market_board.fetch_lhb(limit=20)

    assert result["success"] is True
    assert result["count"] == 1
    assert result["items"][0]["symbol"] == "002594.SZ"
    assert result["items"][0]["change_percent"] == 5.0


def test_board_symbols_carry_market_suffix(monkeypatch):
    """R89: limit_board/lhb 的 symbol 是裸 6 位代码——全库 CN 判定链
    （is_cn_symbol、to_tencent_code、market_router 的 A股校验、
    前端 .SS/.SZ 过滤）只认带后缀代码；"600519" 回填任何 CN 端点/
    工具都被判"非A股"。按代码段补 .SS/.SZ/.BJ，与 fund_flow 一致。"""
    from backend.tools.tencent_provider import is_cn_symbol

    def _fake_list_get(_url: str, params: dict, timeout: int, headers: dict):
        return _DummyResponse(
            200,
            {"data": {"diff": [
                {"f12": "600519", "f14": "贵州茅台", "f2": "1", "f3": "1", "f8": "1", "f10": "1", "f62": "1"},
                {"f12": "920001", "f14": "北交样本", "f2": "1", "f3": "1", "f8": "1", "f10": "1", "f62": "1"},
            ]}},
        )

    monkeypatch.setattr(cn_market_board, "_http_get", _fake_list_get)
    result = cn_market_board.fetch_limit_board(limit=20)
    assert [i["symbol"] for i in result["items"]] == ["600519.SS", "920001.BJ"]
    assert all(is_cn_symbol(i["symbol"]) for i in result["items"])

    def _fake_dc_get(_url: str, params: dict, timeout: int, headers: dict):
        return _DummyResponse(
            200,
            {"result": {"data": [
                {"SECURITY_CODE": "600519", "SECURITY_NAME_ABBR": "贵州茅台"},
                {"SECURITY_CODE": "430047", "SECURITY_NAME_ABBR": "北交样本"},
            ]}},
        )

    monkeypatch.setattr(cn_market_board, "_http_get", _fake_dc_get)
    result = cn_market_board.fetch_lhb(limit=20)
    assert [i["symbol"] for i in result["items"]] == ["600519.SS", "430047.BJ"]
    assert all(is_cn_symbol(i["symbol"]) for i in result["items"])
