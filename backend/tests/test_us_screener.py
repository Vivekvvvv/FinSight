from __future__ import annotations

from backend.tools import us_screener


def _row(index: int) -> dict[str, str]:
    return {
        "symbol": f"REAL{index:03d}",
        "name": f"Real Company {index}",
        "lastsale": f"${100 + index:,.2f}",
        "pctchange": f"{index / 10:.2f}%",
        "volume": f"{1_000_000 + index:,}",
        "marketCap": f"{10_000_000_000 + index:,}",
        "country": "United States",
        "sector": "Technology",
        "industry": "Software",
    }


class _Response:
    status_code = 200

    def json(self):
        return {"data": {"rows": [_row(index) for index in range(150)]}}


def test_nasdaq_screener_returns_more_than_one_hundred_real_rows(monkeypatch):
    monkeypatch.setattr(us_screener, "_CACHE", {"expires_at": 0.0, "items": None})
    monkeypatch.setattr(us_screener, "_http_get", lambda *_args, **_kwargs: _Response())

    result = us_screener.nasdaq_screen_stocks(
        filters={},
        limit=120,
        page=1,
        sort_by="marketCap",
        sort_order="desc",
    )

    assert result is not None
    assert result["source"] == "nasdaq_public_screener"
    assert result["count"] == 120
    assert result["total"] == 150
    assert result["items"][0]["symbol"] == "REAL149"
    assert result["items"][0]["price"] == 249.0


def test_nasdaq_screener_filters_and_pages(monkeypatch):
    monkeypatch.setattr(us_screener, "_CACHE", {"expires_at": 0.0, "items": None})
    monkeypatch.setattr(us_screener, "_http_get", lambda *_args, **_kwargs: _Response())

    result = us_screener.nasdaq_screen_stocks(
        filters={"priceMoreThan": 200, "sector": "Technology"},
        limit=20,
        page=2,
        sort_by="price",
        sort_order="asc",
    )

    assert result is not None
    assert result["count"] == 20
    assert result["items"][0]["price"] == 220.0


def test_nasdaq_screener_returns_none_when_upstream_fails(monkeypatch):
    monkeypatch.setattr(us_screener, "_CACHE", {"expires_at": 0.0, "items": None})
    monkeypatch.setattr(
        us_screener,
        "_http_get",
        lambda *_args, **_kwargs: type("FailedResponse", (), {"status_code": 503})(),
    )

    result = us_screener.nasdaq_screen_stocks(
        filters={},
        limit=120,
        page=1,
        sort_by="marketCap",
        sort_order="desc",
    )

    assert result is None
