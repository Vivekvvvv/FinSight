# -*- coding: utf-8 -*-
"""R5 回归：K线降级源的 epoch→日期转换必须按 UTC 取日。

裸 datetime.fromtimestamp 按服务器本地时区取日：Finnhub/Polygon 日线
时间戳常为收盘时刻（约 21:00 UTC），东八区部署 +8h 会把日期偏到次日，
与 yfinance/stooq 等直给 YYYY-MM-DD 的源拼接时整体错位一天。
"""
from __future__ import annotations

from datetime import UTC, datetime


def test_massive_kline_dates_use_utc(monkeypatch):
    from backend.tools import price as price_module

    monkeypatch.setattr(price_module, "MASSIVE_API_KEY", "test-key")

    # 2026-07-06 21:00 UTC（美股收盘后）；东八区本地取日会得到 2026-07-07
    ts_ms = int(datetime(2026, 7, 6, 21, 0, tzinfo=UTC).timestamp() * 1000)

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return {
                "status": "OK",
                "results": [{"t": ts_ms, "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 100}],
            }

    monkeypatch.setattr(price_module, "_http_get", lambda *a, **k: _Resp())

    result = price_module._fetch_with_massive_io("AAPL", period="1mo")
    assert result is not None
    assert result["kline_data"][0]["time"] == "2026-07-06"


def test_stooq_hourly_request_returns_none_not_fabricated_bars(monkeypatch):
    """R7 回归：stooq 只有日线，小时请求不得伪造 OHLC 全等平线冒充 1h 数据。"""
    from backend.tools import price as price_module

    csv_text = (
        "Date,Open,High,Low,Close,Volume\n"
        "2026-07-02,10,11,9,10.5,1000\n"
        "2026-07-03,10.5,12,10,11.5,1200\n"
    )

    class _Resp:
        status_code = 200
        text = csv_text

    monkeypatch.setattr(price_module, "_http_get", lambda *a, **k: _Resp())

    # 日线请求正常返回
    daily = price_module._fetch_with_stooq_history("AAPL", period="1mo", interval="1d")
    assert daily is not None
    assert daily["interval"] == "1d"
    assert len(daily["kline_data"]) == 2

    # 小时请求如实返回 None，不冒充
    hourly = price_module._fetch_with_stooq_history("AAPL", period="1mo", interval="1h")
    assert hourly is None
