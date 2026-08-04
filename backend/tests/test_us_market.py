from __future__ import annotations

from backend.tools import us_market


class _Response:
    status_code = 200

    def __init__(self, data):
        self._data = data

    def json(self):
        return {"data": self._data}


def test_nasdaq_quote_is_normalized(monkeypatch):
    monkeypatch.setattr(us_market, "_http_get", lambda *_args, **_kwargs: _Response({
        "symbol": "WDC",
        "companyName": "Western Digital Corporation",
        "primaryData": {
            "lastSalePrice": "$539.02",
            "netChange": "+11.80",
            "percentageChange": "+2.24%",
            "volume": "8,279,896",
            "isRealTime": True,
        },
    }))

    result = us_market.fetch_nasdaq_quote("WDC")

    assert result is not None
    assert result["price"] == 539.02
    assert result["change"] == 11.8
    assert result["change_percent"] == 2.24
    assert result["volume"] == 8_279_896
    assert result["source"] == "nasdaq_quote"


def test_nasdaq_intraday_keeps_real_line_points(monkeypatch):
    monkeypatch.setattr(us_market, "_http_get", lambda *_args, **_kwargs: _Response({
        "symbol": "WDC",
        "chart": [
            {"x": 1_725_000_000_000, "y": 72.5},
            {"x": 1_725_000_060_000, "y": 72.8},
        ],
    }))

    result = us_market.fetch_nasdaq_intraday("WDC")

    assert result is not None
    assert result["chart_kind"] == "intraday_line"
    assert result["line_data"][0]["value"] == 72.5
    assert "open" not in result["line_data"][0]
