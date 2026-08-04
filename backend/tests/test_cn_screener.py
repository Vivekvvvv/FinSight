# -*- coding: utf-8 -*-
"""cn_screener（东财全市场筛选）单测 + screen_stocks 接线回归。

CN/HK 此前只有 15 只硬编码热门票；现在优先走东财 clist 全市场接口，
上游故障返回 None 回落既有链，降级语义不变。
"""
from __future__ import annotations

from typing import Any

from backend.tools import cn_screener as mod


class _Resp:
    def __init__(self, payload: Any, status_code: int = 200):
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


def _cn_rows() -> list[dict[str, Any]]:
    return [
        {"f12": "600519", "f13": "1", "f14": "贵州茅台", "f2": 1700.0, "f3": 1.2,
         "f5": 25000, "f9": 22.5, "f20": 2.1e12, "f23": 8.1, "f8": 0.3, "f62": 1.5e8, "f100": "酿酒行业"},
        {"f12": "000001", "f13": "0", "f14": "平安银行", "f2": 11.5, "f3": -0.4,
         "f5": 900000, "f9": 4.8, "f20": 2.2e11, "f23": 0.6, "f8": 0.9, "f62": -3.0e7, "f100": "银行"},
        {"f12": "300750", "f13": "0", "f14": "宁德时代", "f2": 210.0, "f3": 2.8,
         "f5": 300000, "f9": 28.0, "f20": 9.2e11, "f23": 5.5, "f8": 1.2, "f62": 6.0e8, "f100": "电池"},
    ]


def test_cn_full_market_rows_parsed(monkeypatch):
    monkeypatch.setattr(mod, "_http_get", lambda *a, **k: _Resp({"data": {"diff": _cn_rows()}}))

    result = mod.eastmoney_screen_stocks(
        market="CN", filters={}, limit=20, page=1, sort_by="marketCap", sort_order="desc",
    )

    assert result is not None and result["success"] is True
    assert result["source"] == "eastmoney_clist_screener"
    assert result["count"] == 3
    by_symbol = {item["symbol"]: item for item in result["items"]}
    # f13=1 → .SS，f13=0 → .SZ（项目通用 Yahoo 后缀）
    assert "600519.SS" in by_symbol and "000001.SZ" in by_symbol and "300750.SZ" in by_symbol
    mt = by_symbol["600519.SS"]
    assert mt["name"] == "贵州茅台"
    assert mt["sector"] == "酿酒行业"
    assert mt["price"] == 1700.0
    assert mt["volume"] == 25000 * 100  # A股 f5 是手，转股数
    assert mt["market_cap"] == 2.1e12
    assert mt["pe"] == 22.5


def test_hk_symbol_padded_to_four_digits(monkeypatch):
    rows = [{"f12": "00700", "f13": "116", "f14": "腾讯控股", "f2": 380.0, "f3": 0.8,
             "f5": 1.2e7, "f20": 3.6e12, "f100": "资讯科技业"}]
    monkeypatch.setattr(mod, "_http_get", lambda *a, **k: _Resp({"data": {"diff": rows}}))

    result = mod.eastmoney_screen_stocks(
        market="HK", filters={}, limit=10, page=1, sort_by="marketCap", sort_order="desc",
    )

    assert result is not None
    assert result["items"][0]["symbol"] == "0700.HK"
    assert result["items"][0]["exchange"] == "HKEX"
    # 港股 f5 不做手→股换算
    assert result["items"][0]["volume"] == 1.2e7


def test_local_filters_applied(monkeypatch):
    monkeypatch.setattr(mod, "_http_get", lambda *a, **k: _Resp({"data": {"diff": _cn_rows()}}))

    result = mod.eastmoney_screen_stocks(
        market="CN",
        filters={"priceMoreThan": 100, "marketCapMoreThan": 1e12},
        limit=20, page=1, sort_by="marketCap", sort_order="desc",
    )

    assert result is not None
    symbols = [item["symbol"] for item in result["items"]]
    assert symbols == ["600519.SS"]  # 平安银行价格不足 100，宁德市值不足 1e12


def test_first_page_failure_returns_none(monkeypatch):
    def _boom(*a, **k):
        raise ConnectionError("eastmoney down")

    monkeypatch.setattr(mod, "_http_get", _boom)
    assert mod.eastmoney_screen_stocks(
        market="CN", filters={}, limit=20, page=1, sort_by="marketCap", sort_order="desc",
    ) is None


def test_primary_endpoint_failure_uses_delay_endpoint(monkeypatch):
    requested_urls: list[str] = []

    def _get(url, *args, **kwargs):
        requested_urls.append(url)
        if len(requested_urls) == 1:
            return _Resp({}, status_code=503)
        return _Resp({"data": {"diff": _cn_rows()}})

    monkeypatch.setattr(mod, "_http_get", _get)

    result = mod.eastmoney_screen_stocks(
        market="CN", filters={}, limit=20, page=1, sort_by="marketCap", sort_order="desc",
    )

    assert result is not None
    assert result["count"] == 3
    assert requested_urls == list(mod._EASTMONEY_LIST_URLS)


def test_unknown_market_returns_none():
    assert mod.eastmoney_screen_stocks(
        market="US", filters={}, limit=20, page=1, sort_by="marketCap", sort_order="desc",
    ) is None


def test_pagination_slices_second_page(monkeypatch):
    monkeypatch.setattr(mod, "_http_get", lambda *a, **k: _Resp({"data": {"diff": _cn_rows()}}))

    result = mod.eastmoney_screen_stocks(
        market="CN", filters={}, limit=2, page=2, sort_by="marketCap", sort_order="desc",
    )

    assert result is not None
    # 3 行、每页 2 行 → 第二页只剩第 3 行
    assert [item["symbol"] for item in result["items"]] == ["300750.SZ"]


# ── screen_stocks 接线 ───────────────────────────────────────────


def test_screen_stocks_prefers_eastmoney_for_cn(monkeypatch):
    from backend.tools import screener
    import backend.tools.cn_screener as cn_mod

    sentinel = {"success": True, "items": [{"symbol": "600519.SS"}], "count": 1,
                "results": [], "source": "eastmoney_clist_screener"}
    monkeypatch.setattr(cn_mod, "eastmoney_screen_stocks", lambda **kwargs: sentinel)

    result = screener.screen_stocks(market="CN", filters={}, limit=10)
    assert result is sentinel


def test_screen_stocks_falls_back_when_eastmoney_down(monkeypatch):
    from backend.tools import screener
    import backend.tools.cn_screener as cn_mod

    fallback_sentinel = {"success": True, "items": [], "source": "yfinance_popular"}
    monkeypatch.setattr(cn_mod, "eastmoney_screen_stocks", lambda **kwargs: None)
    monkeypatch.setattr(screener, "_yfinance_screen_stocks", lambda *a, **k: fallback_sentinel)

    result = screener.screen_stocks(market="CN", filters={}, limit=10)
    assert result is fallback_sentinel
