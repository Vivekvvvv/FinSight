from types import SimpleNamespace

from backend.tools import baostock_provider as bp


def test_baostock_login_requires_explicit_success(monkeypatch):
    calls = []
    monkeypatch.setattr(bp, "_load_baostock", lambda: SimpleNamespace(
        login=lambda: SimpleNamespace(), logout=lambda: calls.append("logout"),
        query_history_k_data_plus=lambda *a, **kw: calls.append("query")))
    assert bp._history_rows("600519.SS") == []
    assert calls == []


def test_baostock_single_day_quote_uses_reported_previous_close(monkeypatch):
    _mock_history(monkeypatch, [_bar(preclose="100")])
    quote = bp.fetch_cn_quote("600519.SS")
    assert quote["change"] == 1
    assert quote["change_percent"] == 1


def test_baostock_quote_percentage_overflow_is_unavailable(monkeypatch):
    import json
    _mock_history(monkeypatch, [_bar(date="2026-11-05", open="1e-320", high="1e-320",
                                   low="1e-320", close="1e-320"), _bar(preclose="1e-320")])
    quote = bp.fetch_cn_quote("600519.SS")
    assert quote["change_percent"] is None
    json.dumps(quote, allow_nan=False)


def test_baostock_quote_symbol_matches_normalized_request(monkeypatch):
    _mock_history(monkeypatch, [_bar()])
    assert bp.fetch_cn_quote(" 600519.ss ")["symbol"] == "600519.SS"


def test_baostock_history_is_ordered_unique_for_latest_quote(monkeypatch):
    _mock_history(monkeypatch, [_bar(date="2026-11-06"), _bar(date="2026-11-06", close="102"),
                               _bar(date="2026-11-05", close="100")])
    rows = bp._history_rows("600519.SS")
    assert [r["time"] for r in rows] == ["2026-11-05", "2026-11-06"]
    assert bp.fetch_cn_quote("600519.SS")["price"] == 102


def test_baostock_negative_amount_is_unavailable(monkeypatch):
    _mock_history(monkeypatch, [_bar(amount="-1")])
    assert bp._history_rows("600519.SS")[0]["amount"] is None


def test_baostock_negative_volume_is_unavailable(monkeypatch):
    _mock_history(monkeypatch, [_bar(volume="-1")])
    assert bp._history_rows("600519.SS")[0]["volume"] is None


def test_baostock_history_price_geometry_must_be_possible(monkeypatch):
    _mock_history(monkeypatch, [_bar(high="100"), _bar(low="101"), _bar()])
    assert len(bp._history_rows("600519.SS")) == 1


def test_baostock_history_requires_complete_positive_ohlc(monkeypatch):
    _mock_history(monkeypatch, [_bar(open="bad"), _bar(high="0"), _bar(low="-1"), _bar()])
    assert len(bp._history_rows("600519.SS")) == 1


def test_baostock_history_requires_positive_close(monkeypatch):
    _mock_history(monkeypatch, [_bar(close=price) for price in ("0", "-1", "101")])
    assert [r["close"] for r in bp._history_rows("600519.SS")] == [101]


def test_baostock_history_requires_valid_calendar_date(monkeypatch):
    _mock_history(monkeypatch, [_bar(date=day) for day in ("2026-02-30", "bad", None, "2026-11-06")])
    assert [r["time"] for r in bp._history_rows("600519.SS")] == ["2026-11-06"]


def test_baostock_partial_query_failure_is_unavailable(monkeypatch):
    _mock_history(monkeypatch, [_bar()], error_code="1001")
    assert bp._history_rows("600519.SS") == []


def _mock_history(monkeypatch, rows, error_code="0"):
    class Result:
        fields = list(rows[0]) if rows else []

        def __init__(self):
            self.error_code = "0"
            self.index = -1

        def next(self):
            self.index += 1
            if self.index < len(rows):
                return True
            self.error_code = error_code
            return False

        def get_row_data(self):
            return [rows[self.index].get(field) for field in self.fields]

    monkeypatch.setattr(bp, "_load_baostock", lambda: SimpleNamespace(
        login=lambda: SimpleNamespace(error_code="0"), logout=lambda: None,
        query_history_k_data_plus=lambda *a, **kw: Result()))


def _bar(**changes):
    return {"date": "2026-11-06", "code": "sh.600519", "open": "100", "high": "102",
            "low": "99", "close": "101", "preclose": "100", "volume": "10",
            "amount": "1010", "pctChg": "1", **changes}


def test_baostock_history_requires_matching_security(monkeypatch):
    _mock_history(monkeypatch, [_bar(code="sh.600000"), _bar()])
    assert len(bp._history_rows("600519.SS")) == 1


def test_baostock_code_requires_six_digits():
    for symbol in (".SS", "abc.SZ", "123.SS", "6005199.SS", "600 19.SS"):
        assert bp.to_baostock_code(symbol) is None
    assert bp.to_baostock_code(" 600519.ss ") == "sh.600519"


def test_baostock_non_daily_interval_does_not_return_daily_bars(monkeypatch):
    calls = []
    monkeypatch.setattr(bp, "_history_rows", lambda *a, **kw: calls.append(kw) or [
        {"time": "2026-11-06", "open": 100, "high": 102, "low": 99, "close": 101}
    ])
    for interval in ("1h", "5m", "1wk", "bad"):
        assert bp.fetch_cn_kline("600519.SS", interval=interval) is None
    assert calls == []
