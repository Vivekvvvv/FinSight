from __future__ import annotations

from backend.tools import us_market


def test_empty_or_nontext_nasdaq_tickers_do_not_trigger_network_requests(monkeypatch):
    calls = []
    monkeypatch.setattr(us_market, "_http_get", lambda *a, **kw: calls.append(a) or _Response({}))
    for ticker in ("", "   ", None, 123, {}):
        assert us_market.fetch_nasdaq_quote(ticker) is None
        assert us_market.fetch_nasdaq_intraday(ticker) is None
    assert calls == []


def test_delayed_nasdaq_quote_has_a_nonprimary_fallback_level(monkeypatch):
    for realtime, expected_level in ((False, 1), (True, 0)):
        monkeypatch.setattr(us_market, "_http_get", lambda *_a, **_kw: _Response({
            "primaryData": {"lastSalePrice": "$100", "isRealTime": realtime}}))
        assert us_market.fetch_nasdaq_quote("WDC")["fallback_level"] == expected_level


def test_nasdaq_intraday_symbol_is_normalized(monkeypatch):
    monkeypatch.setattr(us_market, "_http_get", lambda *_a, **_kw: _Response({
        "symbol": " wdc ", "chart": [{"x": 1725000000000, "y": 100}]}))
    assert us_market.fetch_nasdaq_intraday("WDC")["symbol"] == "WDC"


def test_nasdaq_primary_identity_cannot_override_requested_stock(monkeypatch):
    for marker in ({"symbol": "MSFT"}, {"ticker": "MSFT"}, {"symbol": {}}):
        monkeypatch.setattr(us_market, "_http_get", lambda *_a, **_kw: _Response({
            "symbol": "WDC", "primaryData": {"lastSalePrice": "$100", **marker}}))
        assert us_market.fetch_nasdaq_quote("WDC") is None


def test_nasdaq_envelope_identity_is_checked_before_inner_data(monkeypatch):
    class Response:
        status_code = 200
        def json(self):
            return {"symbol": "MSFT", "data": {"symbol": "WDC", "primaryData": {"lastSalePrice": "$100"}}}
    monkeypatch.setattr(us_market, "_http_get", lambda *_a, **_kw: Response())
    assert us_market.fetch_nasdaq_quote("WDC") is None


def test_nasdaq_quote_name_requires_text(monkeypatch):
    for name in ({"name": "wrong"}, 123, "   "):
        monkeypatch.setattr(us_market, "_http_get", lambda *_a, **_kw: _Response({
            "companyName": name, "primaryData": {"lastSalePrice": "$100"}}))
        assert us_market.fetch_nasdaq_quote("WDC")["name"] == "WDC"


def test_nasdaq_realtime_label_requires_a_boolean_true(monkeypatch):
    for flag in ("false", "true", 1, {}, []):
        monkeypatch.setattr(us_market, "_http_get", lambda *_a, **_kw: _Response({
            "primaryData": {"lastSalePrice": "$100", "isRealTime": flag}}))
        assert us_market.fetch_nasdaq_quote("WDC")["freshness_status"] == "delayed_15min"


def test_nasdaq_negative_quote_volume_is_unknown(monkeypatch):
    monkeypatch.setattr(us_market, "_http_get", lambda *_a, **_kw: _Response({
        "primaryData": {"lastSalePrice": "$100", "volume": "-10"}}))
    assert us_market.fetch_nasdaq_quote("WDC")["volume"] is None


def test_nasdaq_impossible_percentage_change_is_unavailable(monkeypatch):
    for percentage in ("-100.1%", "-500%"):
        monkeypatch.setattr(us_market, "_http_get", lambda *_a, **_kw: _Response({
            "primaryData": {"lastSalePrice": "$100", "percentageChange": percentage}}))
        result = us_market.fetch_nasdaq_quote("WDC")
        assert result["price"] == 100
        assert result["change_percent"] is None


def test_nasdaq_chart_order_and_duplicates_cannot_change_latest_observation(monkeypatch):
    monkeypatch.setattr(us_market, "_http_get", lambda *_a, **_kw: _Response({
        "chart": [{"x": 1725000060000, "y": 102}, {"x": 1725000060000, "y": 103},
                  {"x": 1725000000000, "y": 100}]}))
    result = us_market.fetch_nasdaq_intraday("WDC")
    assert [point["value"] for point in result["line_data"]] == [100, 103]
    assert result["as_of"] == result["line_data"][-1]["time"]


def test_nasdaq_nonpositive_intraday_values_are_skipped(monkeypatch):
    monkeypatch.setattr(us_market, "_http_get", lambda *_a, **_kw: _Response({
        "chart": [{"x": 1725000000000, "y": 0}, {"x": 1725000060000, "y": -1},
                  {"x": 1725000120000, "y": 101}]}))
    result = us_market.fetch_nasdaq_intraday("WDC")
    assert [point["value"] for point in result["line_data"]] == [101]


def test_nasdaq_chart_points_must_match_requested_stock(monkeypatch):
    for marker in ({"symbol": "MSFT"}, {"ticker": "MSFT"}, {"symbol": {}}):
        monkeypatch.setattr(us_market, "_http_get", lambda *_a, **_kw: _Response({
            "chart": [{"x": 1725000000000, "y": 100, **marker}, {"x": 1725000060000, "y": 101, "symbol": " wdc "}]}))
        result = us_market.fetch_nasdaq_intraday("WDC")
        assert [point["value"] for point in result["line_data"]] == [101]


def test_nasdaq_failed_chart_points_do_not_enter_the_line(monkeypatch):
    for marker in ({"error": "bad"}, {"success": False}, {"status": " Failed "}):
        monkeypatch.setattr(us_market, "_http_get", lambda *_a, **_kw: _Response({
            "chart": [{"x": 1725000000000, "y": 100, **marker}, {"x": 1725000060000, "y": 101}]}))
        result = us_market.fetch_nasdaq_intraday("WDC")
        assert [point["value"] for point in result["line_data"]] == [101]


def test_nonpositive_nasdaq_quote_price_is_unavailable(monkeypatch):
    for price in ("$0", "$-1"):
        monkeypatch.setattr(us_market, "_http_get", lambda *_a, **_kw: _Response({
            "primaryData": {"lastSalePrice": price}}))
        assert us_market.fetch_nasdaq_quote("WDC") is None


def test_failed_primary_quote_does_not_supply_a_price(monkeypatch):
    for marker in ({"error": "bad"}, {"success": False}, {"status": " Failed "}):
        monkeypatch.setattr(us_market, "_http_get", lambda *_a, **_kw: _Response({
            "primaryData": {"lastSalePrice": "$100", **marker}}))
        assert us_market.fetch_nasdaq_quote("WDC") is None


def test_failed_nasdaq_data_cannot_supply_quote_or_chart(monkeypatch):
    for marker in ({"error": "bad"}, {"success": False}, {"status": " unavailable "}):
        monkeypatch.setattr(us_market, "_http_get", lambda *_a, **_kw: _Response({
            "primaryData": {"lastSalePrice": "$100"}, "chart": [{"x": 1725000000000, "y": 100}], **marker}))
        assert us_market.fetch_nasdaq_quote("WDC") is None
        assert us_market.fetch_nasdaq_intraday("WDC") is None


def test_failed_nasdaq_envelope_cannot_supply_quote_or_chart(monkeypatch):
    for marker in ({"error": "bad"}, {"success": False}, {"status": " Failed "}, {"status": {"rCode": 503}}):
        class Response:
            status_code = 200
            def json(self):
                return {"data": {"primaryData": {"lastSalePrice": "$100"},
                    "chart": [{"x": 1725000000000, "y": 100}]}, **marker}
        monkeypatch.setattr(us_market, "_http_get", lambda *_a, **_kw: Response())
        assert us_market.fetch_nasdaq_quote("WDC") is None
        assert us_market.fetch_nasdaq_intraday("WDC") is None
    class GoodResponse(Response):
        def json(self):
            return {"status": {"rCode": 200}, "data": {"primaryData": {"lastSalePrice": "$100"}}}
    monkeypatch.setattr(us_market, "_http_get", lambda *_a, **_kw: GoodResponse())
    assert us_market.fetch_nasdaq_quote("WDC")["price"] == 100


def test_nasdaq_identity_must_match_requested_stock(monkeypatch):
    for identity in ({"symbol": "MSFT"}, {"ticker": "MSFT"}, {"symbol": {}}):
        monkeypatch.setattr(us_market, "_http_get", lambda *_a, **_kw: _Response({
            "primaryData": {"lastSalePrice": "$100"}, "chart": [{"x": 1725000000000, "y": 100}], **identity}))
        assert us_market.fetch_nasdaq_quote("WDC") is None
        assert us_market.fetch_nasdaq_intraday("WDC") is None
    monkeypatch.setattr(us_market, "_http_get", lambda *_a, **_kw: _Response({
        "symbol": " wdc ", "primaryData": {"lastSalePrice": "$100"}}))
    assert us_market.fetch_nasdaq_quote("WDC")["price"] == 100


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


def test_nasdaq_intraday_as_of_is_last_point_not_fetch_time(monkeypatch):
    """盘后取数时 as_of=now 会把昨天的分时图伪装成刚更新；应为最后一条点的时间。"""
    monkeypatch.setattr(us_market, "_http_get", lambda *_args, **_kwargs: _Response({
        "symbol": "WDC",
        "chart": [
            {"x": 1_725_000_000_000, "y": 72.5},
            {"x": 1_725_000_060_000, "y": 72.8},
        ],
    }))

    result = us_market.fetch_nasdaq_intraday("WDC")

    assert result["as_of"] == result["line_data"][-1]["time"]


def test_nasdaq_intraday_skips_malformed_timestamp(monkeypatch):
    """单个畸形 x 值（超出 fromtimestamp 范围）应跳过而非抛出——
    修前一行坏数据让整段分时 raise，违反 tools 返回 None 不抛的约定。"""
    monkeypatch.setattr(us_market, "_http_get", lambda *_args, **_kwargs: _Response({
        "symbol": "WDC",
        "chart": [
            {"x": 1_725_000_000_000, "y": 72.5},
            {"x": 9_999_999_999_999_999, "y": 73.0},
            {"x": 1_725_000_060_000, "y": 72.8},
        ],
    }))

    result = us_market.fetch_nasdaq_intraday("WDC")

    assert result is not None
    assert len(result["line_data"]) == 2
    assert [p["value"] for p in result["line_data"]] == [72.5, 72.8]


def test_nasdaq_intraday_all_bad_timestamps_returns_none(monkeypatch):
    """全部时间点畸形 → 返回 None（不抛异常、不返回空 dict）。"""
    monkeypatch.setattr(us_market, "_http_get", lambda *_args, **_kwargs: _Response({
        "symbol": "WDC",
        "chart": [{"x": 9_999_999_999_999_999, "y": 73.0}],
    }))

    assert us_market.fetch_nasdaq_intraday("WDC") is None
