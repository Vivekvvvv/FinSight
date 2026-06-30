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
