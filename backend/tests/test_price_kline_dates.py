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
