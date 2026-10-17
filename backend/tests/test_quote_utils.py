# -*- coding: utf-8 -*-
"""Tests for shared quote parsing helpers."""

from __future__ import annotations

import builtins
import math
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.utils.quote import (
    fallback_quote_yfinance,
    parse_quote_payload,
    resolve_live_quote,
    safe_float,
)


class TestResolveLiveQuote:
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
