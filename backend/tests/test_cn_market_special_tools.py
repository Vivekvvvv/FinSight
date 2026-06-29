from __future__ import annotations

from backend.tools import tencent_provider


class _FakeResponse:
    status_code = 200

    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_fetch_cn_top_list_uses_current_eastmoney_datacenter(monkeypatch):
    calls: list[dict] = []

    def fake_http_get(url, params=None, **kwargs):
        calls.append({"url": url, "params": params, "kwargs": kwargs})
        return _FakeResponse(
            {
                "result": {
                    "data": [
                        {
                            "TRADE_DATE": "2026-06-26 00:00:00",
                            "SECURITY_CODE": "000001",
                            "SECURITY_NAME_ABBR": "平安银行",
                            "EXPLANATION": "日涨幅偏离值达到7%的前5只证券",
                            "CLOSE_PRICE": 10.8,
                            "CHANGE_RATE": 9.9796,
                            "BILLBOARD_BUY_AMT": 994426871.29,
                            "BILLBOARD_SELL_AMT": 429200090.1,
                            "BILLBOARD_NET_AMT": 565226781.19,
                            "TURNOVERRATE": 2.6051,
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr(tencent_provider, "_http_get", fake_http_get)

    result = tencent_provider.fetch_cn_top_list("000001.SZ", include_seats=False)

    assert result is not None
    assert result["stock_code"] == "000001"
    assert result["stock_name"] == "平安银行"
    assert result["source"] == "eastmoney_datacenter"
    assert result["net_buy"] == 565226781.19
    assert calls[0]["params"]["reportName"] == "RPT_DAILYBILLBOARD_DETAILSNEW"


def test_fetch_cn_top_list_hides_stale_records(monkeypatch):
    def fake_http_get(url, params=None, **kwargs):
        return _FakeResponse(
            {
                "result": {
                    "data": [
                        {
                            "TRADE_DATE": "2013-01-28 00:00:00",
                            "SECURITY_CODE": "600519",
                            "SECURITY_NAME_ABBR": "贵州茅台",
                            "EXPLANATION": "历史龙虎榜记录",
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr(tencent_provider, "_http_get", fake_http_get)

    assert tencent_provider.fetch_cn_top_list("600519.SS", include_seats=False) is None


def test_fetch_margin_trading_uses_current_eastmoney_report(monkeypatch):
    calls: list[dict] = []

    def fake_http_get(url, params=None, **kwargs):
        calls.append({"url": url, "params": params, "kwargs": kwargs})
        return _FakeResponse(
            {
                "result": {
                    "data": [
                        {
                            "DATE": "2026-06-26 00:00:00",
                            "SCODE": "600519",
                            "RZYE": 19566752185,
                            "RZMRE": 399270757,
                            "RZCHE": 962027703,
                            "RQYL": 106809,
                            "RQMCL": 2042,
                            "RQCHL": 2661,
                            "RZRQYE": 19691572386.67,
                            "SZ": 1460882861376.63,
                        }
                    ]
                }
            }
        )

    monkeypatch.setattr(tencent_provider, "_http_get", fake_http_get)

    result = tencent_provider.fetch_margin_trading("600519.SS")

    assert result is not None
    assert result["stock_code"] == "600519"
    assert result["margin_balance"] == 19566752185
    assert result["short_sell"] == 2042
    assert result["margin_buy_ratio"] == 0.0273
    assert calls[0]["params"]["reportName"] == "RPTA_WEB_RZRQ_GGMX"
    assert calls[0]["params"]["filter"] == '(SCODE="600519")'
