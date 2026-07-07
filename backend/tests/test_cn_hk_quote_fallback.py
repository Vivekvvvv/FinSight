# -*- coding: utf-8 -*-
from __future__ import annotations

from backend.tools import cn_hk_market


class _JsonResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload
        self.text = ""

    def json(self):
        return self._payload


class _TextResponse:
    status_code = 200

    def __init__(self, text: str):
        self.text = text


def test_cn_quote_falls_back_to_tencent_when_eastmoney_disconnects(monkeypatch):
    def fake_http_get(url, **kwargs):
        if "push2.eastmoney.com" in url:
            raise RuntimeError("eastmoney closed connection")
        if "qt.gtimg.cn" in url:
            return _TextResponse(
                'v_sh600519="1~贵州茅台~600519~1185.49~1194.96~1187.00~39608~'
                '18062~21546~1185.49~40~1185.20~1~1185.00~25~1184.98~1~'
                '1184.86~1~1185.90~1~1185.92~1~1185.97~8~1185.99~2~'
                '1186.00~24~~20260630161413~-9.47~-0.79~1195.67~1176.00~'
                '1185.49/39608/4684236159~39608~468424~0.32~17.92~~'
                '1195.67~1176.00~1.65~14819.59~14819.59~6.36";'
            )
        raise AssertionError(url)

    monkeypatch.setattr(cn_hk_market, "_http_get", fake_http_get)

    result = cn_hk_market.fetch_cn_hk_quote_metrics("600519.SS", timeout=1)

    assert result is not None
    assert result["source"] == "tencent_quote"
    assert result["name"] == "贵州茅台"
    assert result["last_price"] == 1185.49


def test_hk_quote_falls_back_to_tencent_when_eastmoney_disconnects(monkeypatch):
    def fake_http_get(url, **kwargs):
        if "push2.eastmoney.com" in url:
            raise RuntimeError("eastmoney closed connection")
        if "qt.gtimg.cn" in url:
            return _TextResponse(
                'v_hk00700="100~腾讯控股~00700~429.800~420.200~421.200~'
                '38994409.0~0~0~429.800~0~0~0~0~0~0~0~0~0~429.800~0~0~0~'
                '0~0~0~0~0~0~38994409.0~2026/06/30 16:08:12~9.600~2.28~'
                '435.600~418.400~429.800~38994409.0~16688485489.052~0~'
                '15.70~~0~0~4.09~39078.4253~39078.4253~TENCENT";'
            )
        raise AssertionError(url)

    monkeypatch.setattr(cn_hk_market, "_http_get", fake_http_get)

    result = cn_hk_market.fetch_cn_hk_quote_metrics("0700.HK", timeout=1)

    assert result is not None
    assert result["source"] == "tencent_quote"
    assert result["market"] == "HK"
    assert result["name"] == "腾讯控股"
    assert result["last_price"] == 429.8


# ── R4 回归：CN/HK K线降级链须尊重 period/interval ──────────────────────────


def test_kline_params_for_maps_period_and_interval():
    assert cn_hk_market.kline_params_for("1y", "1d") == ("101", 261)
    assert cn_hk_market.kline_params_for("5y", "1d") == ("101", 1200)  # cap 1200
    assert cn_hk_market.kline_params_for("1y", "1wk") == ("102", 53)
    assert cn_hk_market.kline_params_for("1mo", "1h") == ("60", 89)
    assert cn_hk_market.kline_params_for("1y", "2m") is None  # 不支持的粒度不冒充
    assert cn_hk_market.kline_params_for(None, None) == ("101", 261)  # 缺省 1y/1d


def test_load_ohlcv_frame_passes_klt_and_limit_for_cn(monkeypatch):
    """旧代码固定 fetch_cn_hk_kline(symbol, limit=300)：5y 请求被静默截断、
    周线视图拿到日线。修复后必须把映射后的 klt/limit 传给东财源。"""
    from backend.dashboard import data_service

    captured: dict = {}

    def fake_fetch(symbol, *, limit, klt="101", fqt="1"):
        captured["limit"] = limit
        captured["klt"] = klt
        # 返回有效行让函数在东财分支直接命中返回，不落到真实网络源
        return [
            {"time": "2026-01-05", "open": 1.0, "high": 1.2, "low": 0.9, "close": 1.1, "volume": 100},
            {"time": "2026-01-12", "open": 1.1, "high": 1.3, "low": 1.0, "close": 1.2, "volume": 100},
        ]

    monkeypatch.setattr(cn_hk_market, "fetch_cn_hk_kline", fake_fetch)
    frame = data_service._load_ohlcv_frame("600519.SS", period="5y", interval="1wk")
    assert captured["klt"] == "102"
    assert captured["limit"] == 261  # 5y≈1300 交易日 → 260 周
    assert frame is not None and len(frame) == 2


def test_load_ohlcv_frame_skips_eastmoney_for_unsupported_interval(monkeypatch):
    import sys
    import types

    import pandas as pd

    from backend.dashboard import data_service

    def fake_fetch(*_args, **_kwargs):
        raise AssertionError("unsupported interval must skip eastmoney source")

    monkeypatch.setattr(cn_hk_market, "fetch_cn_hk_kline", fake_fetch)

    # 堵住后续真实网络源：yfinance 直接返回非空 frame 短路
    class _FakeTicker:
        def __init__(self, _symbol):
            pass

        def history(self, period=None, interval=None):
            return pd.DataFrame(
                {"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [0]},
                index=pd.DatetimeIndex(["2026-01-05"]),
            )

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=_FakeTicker))

    # 2m 粒度东财不支持 → 不得调用东财，落到 yfinance
    frame = data_service._load_ohlcv_frame("600519.SS", period="1y", interval="2m")
    assert frame is not None
