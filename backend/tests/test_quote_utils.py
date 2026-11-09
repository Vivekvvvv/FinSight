# -*- coding: utf-8 -*-
"""Tests for shared quote parsing helpers."""

from __future__ import annotations

import builtins
import math
import sys
from types import SimpleNamespace

import pytest


def test_failed_nested_quote_cannot_fall_back_to_outer_price():
    for failure in ({"error": "bad"}, {"success": False}, {"status": " Failed "}):
        assert parse_quote_payload({"price": 100, "data": {"price": 200, **failure}}) is None
    assert parse_quote_payload({"price": 100, "data": {"change": 2}}) is None


def test_fallback_daily_quote_uses_unique_chronological_bars(monkeypatch):
    history = pd.DataFrame({"Close": [120, 125, 100]},
        index=pd.to_datetime(["2026-01-02", "2026-01-02", "2026-01-01"], utc=True))
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(
        Ticker=lambda ticker: SimpleNamespace(history=lambda **kwargs: history)))
    result = fallback_quote_yfinance("AAPL")
    assert result["price"] == 125
    assert result["change"] == 25
    assert result["change_percent"] == 25
    assert result["as_of"].startswith("2026-01-02")
    assert len(history) == 3


@pytest.mark.parametrize("bad_previous", [{"error": "bad"}, {"success": False}, {"status": " Failed "},
                                         {"ticker": "MSFT"}, {"symbol": "MSFT"}])
def test_invalid_previous_daily_bar_cannot_supply_fallback_change_baseline(monkeypatch, bad_previous):
    history = pd.DataFrame([{"Close": 100, **bad_previous}, {"Close": 120}], dtype=object)
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(
        Ticker=lambda ticker: SimpleNamespace(history=lambda **kwargs: history)))
    result = fallback_quote_yfinance("AAPL")
    assert result["price"] == 120
    assert result["change"] is None
    assert result["change_percent"] is None


@pytest.mark.parametrize("identity", [{"ticker": "MSFT"}, {"symbol": "MSFT"}, {"symbol": {}}])
def test_daily_fallback_quote_requires_latest_bar_matching_instrument(monkeypatch, identity):
    history = pd.DataFrame([{"Close": 100}, {"Close": 120, **identity}], dtype=object)
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(
        Ticker=lambda ticker: SimpleNamespace(history=lambda **kwargs: history)))
    assert fallback_quote_yfinance("AAPL") is None
    for field in ("symbol", "ticker"):
        history = pd.DataFrame([{"Close": 100, field: " aapl "}, {"Close": 120, field: "AAPL"}])
        assert fallback_quote_yfinance("AAPL")["price"] == 120


@pytest.mark.parametrize("failure", [{"error": "bad"}, {"success": False}, {"status": " Unavailable "}])
def test_failed_latest_daily_bar_cannot_supply_a_fallback_quote(monkeypatch, failure):
    history = pd.DataFrame([{"Close": 100}, {"Close": 120, **failure}], dtype=object)
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(
        Ticker=lambda ticker: SimpleNamespace(history=lambda **kwargs: history)))
    assert fallback_quote_yfinance("AAPL") is None

import pandas as pd


@pytest.mark.parametrize("status", ["error", " Failed ", "unavailable"])
@pytest.mark.parametrize("nested", [False, True])
def test_failed_status_quotes_cannot_supply_prices_or_block_fallback(monkeypatch, status, nested):
    payload = {"status": status, "price": 200}
    raw = {"data": payload} if nested else {**payload, "data": {"price": 200}}
    monkeypatch.setattr("backend.utils.quote.fallback_quote_yfinance",
                        lambda ticker: {"price": 100, "source": "yfinance_fallback"})
    assert parse_quote_payload(raw) is None
    quote, returned = resolve_live_quote("AAPL", lambda ticker: raw)
    assert quote["price"] == 100
    assert quote["source"] == "yfinance_fallback"
    assert returned == raw

from backend.utils.quote import (
    fallback_quote_yfinance,
    parse_quote_payload,
    resolve_live_quote,
    safe_float,
)


@pytest.mark.parametrize("field", ["ticker", "symbol"])
def test_resolver_rejects_conflicting_outer_identity_before_nested_metadata(monkeypatch, field):
    raw = {field: "MSFT", "data": {field: "AAPL", "price": 200.0}}
    monkeypatch.setattr("backend.utils.quote.fallback_quote_yfinance", lambda _ticker: {
        "price": 101.0, "source": "yfinance_fallback",
    })

    quote, returned = resolve_live_quote("AAPL", lambda _ticker: raw)

    assert quote["price"] == 101.0
    assert quote["source"] == "yfinance_fallback"
    assert returned == raw


@pytest.mark.parametrize("percentage", [-100.01, -150.0])
@pytest.mark.parametrize("formatted", [False, True])
def test_quote_change_cannot_report_a_loss_beyond_one_hundred_percent(percentage, formatted):
    payload = f"Current Price: $100 Change: -500 ({percentage}%)" if formatted else {
        "price": 100.0, "change_percent": percentage,
    }

    result = parse_quote_payload(payload)

    assert result["price"] == 100.0
    assert result["change_percent"] is None


def test_rounded_one_hundred_percent_loss_remains_usable():
    assert parse_quote_payload({"price": 0.01, "change_percent": -100.0})["change_percent"] == -100.0


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "provider unavailable"}])
@pytest.mark.parametrize("nested", [False, True])
def test_failed_payload_prices_do_not_block_fallback(monkeypatch, failure, nested):
    raw = {**failure, "data": {"price": 200}} if nested else {**failure, "price": 200}
    monkeypatch.setattr("backend.utils.quote.fallback_quote_yfinance", lambda _ticker: {"price": 100, "source": "yfinance_fallback"})
    assert parse_quote_payload(raw) is None
    quote, returned = resolve_live_quote("AAPL", lambda _ticker: raw)
    assert quote["price"] == 100
    assert quote["source"] == "yfinance_fallback"
    assert returned == raw


@pytest.mark.parametrize("price", ["-1", "-10.25", "-1,234.50"])
def test_signed_current_price_does_not_reuse_previous_close(price):
    assert parse_quote_payload(f"Current Price: ${price}; Previous Close: $100") is None


def test_explicit_positive_sign_is_a_valid_current_price():
    assert parse_quote_payload("Current Price: $+25; Previous Close: $100")["price"] == 25


def test_deep_quote_envelope_preserves_identity_and_freshness(monkeypatch):
    monkeypatch.setattr("backend.utils.quote.fallback_quote_yfinance", lambda _ticker: None)
    raw = {"data": {"data": {"price": 100, "ticker": "MSFT", "freshness_status": "cached"}}}
    assert resolve_live_quote("AAPL", lambda _ticker: raw)[0] is None
    raw["data"]["data"]["ticker"] = "AAPL"
    quote, _ = resolve_live_quote("AAPL", lambda _ticker: raw)
    assert quote["freshness_status"] == "cached"
    assert quote["fallback_level"] == 2


@pytest.mark.parametrize("freshness", ["cached", "stale", "unknown", "demo", "delayed_15min"])
def test_missing_non_live_observation_time_is_not_fetch_time(freshness):
    quote, _ = resolve_live_quote("AAPL", lambda _ticker: {"price": 100, "freshness_status": freshness})
    assert quote["as_of"] is None


def test_missing_non_live_observation_time_in_fallback_stays_unknown(monkeypatch):
    monkeypatch.setattr("backend.utils.quote.fallback_quote_yfinance", lambda _ticker: {"price": 100, "source": "yfinance_fallback"})
    quote, _ = resolve_live_quote("AAPL", lambda _ticker: None)
    assert quote["as_of"] is None
    assert quote["freshness_status"] == "stale"


class TestResolveLiveQuote:
    @pytest.mark.parametrize("field", ["ticker", "symbol"])
    @pytest.mark.parametrize("nested", [False, True])
    def test_unrelated_declared_ticker_does_not_block_fallback(self, monkeypatch, field, nested):
        calls = []
        monkeypatch.setattr("backend.utils.quote.fallback_quote_yfinance", lambda ticker: calls.append(ticker) or {
            "price": 101.0, "source": "yfinance_fallback", "freshness_status": "stale",
        })
        payload = {"price": 200, field: "MSFT"}
        raw = {"data": payload} if nested else payload

        quote, returned_raw = resolve_live_quote("AAPL", lambda _ticker: raw)

        assert quote["price"] == 101.0
        assert quote["source"] == "yfinance_fallback"
        assert calls == ["AAPL"]
        assert returned_raw == raw

    def test_conflicting_declared_quote_symbols_do_not_supply_price(self, monkeypatch):
        monkeypatch.setattr("backend.utils.quote.fallback_quote_yfinance", lambda _ticker: None)
        quote, _ = resolve_live_quote("AAPL", lambda _ticker: {"price": 200, "ticker": "AAPL", "symbol": "MSFT"})
        assert quote is None

    @pytest.mark.parametrize("field", ["ticker", "symbol"])
    def test_declared_quote_identity_accepts_case_and_spaces(self, field):
        quote, _ = resolve_live_quote("AAPL", lambda _ticker: {"price": 100, field: " aapl "})
        assert quote["price"] == 100.0
        assert quote["source"] == "tools_bridge"

    def test_bare_payload_keeps_legacy_live_default(self):
        quote, raw = resolve_live_quote("AAPL", lambda _ticker: {"price": 100})

        assert raw == {"price": 100}
        assert quote["source"] == "tools_bridge"
        assert quote["freshness_status"] == "live"
        assert quote["fallback_level"] == 0
        assert quote["as_of"]

    def test_cached_upstream_is_not_relabelled_live(self):
        as_of = "2026-01-02T03:04:05+00:00"
        raw_payload = {
            "data": {
                "price": 100,
                "freshness_status": "cached",
                "as_of": as_of,
                "fallback_level": 2,
            }
        }

        quote, _ = resolve_live_quote("AAPL", lambda _ticker: raw_payload)

        assert quote["freshness_status"] == "cached"
        assert quote["fallback_level"] == 2
        assert quote["as_of"] == as_of

    def test_delayed_upstream_freshness_is_preserved(self):
        quote, _ = resolve_live_quote(
            "AAPL",
            lambda _ticker: {"price": 100, "freshness_status": "delayed_15min"},
        )

        assert quote["freshness_status"] == "delayed_15min"
        assert quote["fallback_level"] == 1

    def test_invalid_upstream_freshness_is_unknown_not_live(self):
        quote, _ = resolve_live_quote(
            "AAPL",
            lambda _ticker: {"price": 100, "freshness_status": "not-a-status"},
        )

        assert quote["freshness_status"] == "unknown"

    def test_upstream_as_of_is_not_overwritten(self):
        as_of = "2025-12-31T00:00:00Z"

        quote, _ = resolve_live_quote("AAPL", lambda _ticker: {"price": 100, "as_of": as_of})

        assert quote["as_of"] == as_of

    def test_yfinance_fallback_keeps_stale_freshness_and_bar_as_of(self, monkeypatch):
        bar_as_of = "2026-10-16T00:00:00+00:00"
        monkeypatch.setattr(
            "backend.utils.quote.fallback_quote_yfinance",
            lambda _ticker: {
                "price": 100.0,
                "source": "yfinance_fallback",
                "freshness_status": "stale",
                "as_of": bar_as_of,
            },
        )

        quote, _ = resolve_live_quote("AAPL", lambda _ticker: None)

        assert quote["freshness_status"] == "stale"
        assert quote["as_of"] == bar_as_of


class TestSafeFloat:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (123, 123.0),
            (123.45, 123.45),
            ("123.45", 123.45),
            ("-42.5", -42.5),
            (0, 0.0),
            ("0", 0.0),
            (None, None),
            ("", None),
            ("abc", None),
            (float("nan"), None),
            (float("inf"), None),
            (float("-inf"), None),
        ],
    )
    def test_safe_float(self, value, expected):
        out = safe_float(value)
        if expected is None:
            assert out is None
        else:
            assert out == pytest.approx(expected)


class TestParseQuotePayload:
    @pytest.mark.parametrize("payload", [
        {"price": 200, "ticker": "MSFT"},
        {"ticker": "MSFT", "data": {"price": 200, "ticker": "AAPL"}},
        {"price": 200, "data": {"price": 300, "symbol": "MSFT"}},
    ])
    def test_expected_identity_is_checked_in_each_envelope(self, payload):
        assert parse_quote_payload(payload, expected_ticker="AAPL") is None

    def test_expected_identity_accepts_normalized_matching_payload(self):
        parsed = parse_quote_payload({"data": {"price": 100, "symbol": " aapl "}}, expected_ticker="AAPL")
        assert parsed["price"] == 100

    @pytest.mark.parametrize("price", [0, -1, "0", "-1"])
    @pytest.mark.parametrize("nested", [False, True])
    def test_non_positive_price_is_not_a_usable_quote(self, price, nested):
        payload = {"price": price, "change": 1}
        assert parse_quote_payload({"data": payload} if nested else payload) is None

    @pytest.mark.parametrize("payload", ["Current Price: $0", "Last traded at $0.00"])
    def test_non_positive_text_price_is_not_a_usable_quote(self, payload):
        assert parse_quote_payload(payload) is None

    def test_none_payload(self):
        assert parse_quote_payload(None) is None

    def test_plain_dict_payload(self):
        payload = {"price": "123.4", "change": "-1.2", "change_percent": "-0.96"}
        parsed = parse_quote_payload(payload)
        assert parsed == {
            "price": 123.4,
            "change": -1.2,
            "change_percent": -0.96,
        }

    def test_nested_data_payload(self):
        payload = {"data": {"price": 88, "change": 2, "change_percent": 2.33}}
        parsed = parse_quote_payload(payload)
        assert parsed == {
            "price": 88.0,
            "change": 2.0,
            "change_percent": 2.33,
        }

    def test_nested_payload_without_price(self):
        payload = {"data": {"change": 1.2}}
        assert parse_quote_payload(payload) is None

    def test_dict_payload_with_nan_price(self):
        payload = {"price": float("nan"), "change": 1.0, "change_percent": 1.2}
        assert parse_quote_payload(payload) is None

    def test_text_payload_full_pattern(self):
        payload = "Current Price: $145.56 | Change: -2.10 (-1.42%)"
        parsed = parse_quote_payload(payload)
        assert parsed == {
            "price": 145.56,
            "change": -2.1,
            "change_percent": -1.42,
        }

    def test_text_payload_fallback_price_pattern(self):
        payload = "AAPL last seen around $199.7 in pre-market"
        parsed = parse_quote_payload(payload)
        assert parsed == {
            "price": 199.7,
            "change": None,
            "change_percent": None,
        }

    def test_text_payload_without_price(self):
        payload = "No market data available"
        assert parse_quote_payload(payload) is None

    def test_fallback_price_keeps_thousands_separator(self):
        # R41: 兜底路径（无 "Current Price:" 前缀）此前在逗号处截断 → $612,345.67 读成 1.0
        parsed = parse_quote_payload("BRK.A around $612,345.67 today")
        assert parsed is not None
        assert parsed["price"] == pytest.approx(612345.67)

    def test_change_keeps_thousands_separator(self):
        # R41: Change 正则此前也在逗号处截断 → "-1,234.5" 读成 -1
        parsed = parse_quote_payload("AAPL Current Price: $1,234.56 | Change: -1,234.5 (-2.5%)")
        assert parsed is not None
        assert parsed["price"] == pytest.approx(1234.56)
        assert parsed["change"] == pytest.approx(-1234.5)
        assert parsed["change_percent"] == pytest.approx(-2.5)

    def test_change_percent_field_name_is_standardized(self):
        parsed = parse_quote_payload({"price": 100, "change": 1, "change_percent": 1})
        assert parsed is not None
        assert "change_percent" in parsed
        assert "change_pct" not in parsed


class TestFallbackQuoteYfinance:
    @pytest.mark.parametrize("previous", [1e-308, 1e-320])
    def test_overflowing_fallback_percentage_stays_unavailable(self, monkeypatch, previous):
        fake = SimpleNamespace(Ticker=lambda ticker: SimpleNamespace(
            history=lambda **kwargs: pd.DataFrame({"Close": [previous, 100.0]}),
        ))
        monkeypatch.setitem(sys.modules, "yfinance", fake)

        quote = fallback_quote_yfinance("AAPL")

        assert quote["price"] == 100.0
        assert quote["change"] == 100.0
        assert quote["change_percent"] is None

    @pytest.mark.parametrize("price", [0.0, -1.0])
    def test_non_positive_latest_close_is_not_a_usable_quote(self, monkeypatch, price):
        fake = SimpleNamespace(Ticker=lambda _ticker: SimpleNamespace(
            history=lambda **_kwargs: pd.DataFrame({"Close": [100.0, price]}),
        ))
        monkeypatch.setitem(sys.modules, "yfinance", fake)
        assert fallback_quote_yfinance("AAPL") is None

    def test_negative_previous_close_cannot_supply_percentage(self, monkeypatch):
        fake = SimpleNamespace(Ticker=lambda _ticker: SimpleNamespace(
            history=lambda **_kwargs: pd.DataFrame({"Close": [-100.0, 105.0]}),
        ))
        monkeypatch.setitem(sys.modules, "yfinance", fake)
        quote = fallback_quote_yfinance("AAPL")
        assert quote["price"] == 105.0
        assert quote["change"] is None
        assert quote["change_percent"] is None

    def test_yfinance_import_error(self, monkeypatch: pytest.MonkeyPatch):
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "yfinance":
                raise ImportError("yfinance not installed")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        assert fallback_quote_yfinance("AAPL") is None

    def test_success_with_mock_yfinance(self, monkeypatch: pytest.MonkeyPatch):
        class FakeTicker:
            def history(self, period: str, interval: str):
                assert period == "5d"
                assert interval == "1d"
                return pd.DataFrame({"Close": [100.0, 101.0, 103.0]})

        fake_module = SimpleNamespace(Ticker=lambda _ticker: FakeTicker())
        monkeypatch.setitem(sys.modules, "yfinance", fake_module)

        result = fallback_quote_yfinance("AAPL")

        assert result is not None
        assert result["price"] == pytest.approx(103.0)
        assert result["change"] == pytest.approx(2.0)
        assert result["change_percent"] == pytest.approx((2.0 / 101.0) * 100.0)
        assert result["source"] == "yfinance_fallback"

    def test_daily_close_fallback_is_stale_and_uses_bar_date_as_of(
        self, monkeypatch: pytest.MonkeyPatch,
    ):
        bar_index = pd.date_range("2026-10-14", periods=3, freq="D", tz="UTC")

        class FakeTicker:
            def history(self, period: str, interval: str):
                return pd.DataFrame({"Close": [100.0, 101.0, 103.0]}, index=bar_index)

        fake_module = SimpleNamespace(Ticker=lambda _ticker: FakeTicker())
        monkeypatch.setitem(sys.modules, "yfinance", fake_module)

        result = fallback_quote_yfinance("AAPL")

        # 日线收盘不是 15 分钟延迟报价，as_of 必须是最后一根 K 线时间
        assert result["freshness_status"] == "stale"
        assert result["as_of"].startswith("2026-10-16")

    def test_returns_none_when_history_empty(self, monkeypatch: pytest.MonkeyPatch):
        class FakeTicker:
            def history(self, period: str, interval: str):
                return pd.DataFrame({"Close": []})

        fake_module = SimpleNamespace(Ticker=lambda _ticker: FakeTicker())
        monkeypatch.setitem(sys.modules, "yfinance", fake_module)

        assert fallback_quote_yfinance("AAPL") is None

    def test_returns_none_when_close_is_invalid(self, monkeypatch: pytest.MonkeyPatch):
        class FakeTicker:
            def history(self, period: str, interval: str):
                return pd.DataFrame({"Close": [100.0, math.inf]})

        fake_module = SimpleNamespace(Ticker=lambda _ticker: FakeTicker())
        monkeypatch.setitem(sys.modules, "yfinance", fake_module)

        assert fallback_quote_yfinance("AAPL") is None
