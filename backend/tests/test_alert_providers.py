"""Regression tests for alert quote provider identity and fallback behavior."""
from types import SimpleNamespace
import sys

import pytest

from backend.services import alert_providers as providers
from backend.services.alert_scheduler import PriceChangeScheduler


def test_yfinance_fast_info_public_last_price_key_supplies_alert_snapshot(monkeypatch):
    from yfinance.scrapers.quote import FastInfo
    fast_info = FastInfo(SimpleNamespace())
    fast_info._last_price = 120
    fast_info._prev_close = 100
    fast_info._reg_prev_close = 100
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(
        Ticker=lambda ticker: SimpleNamespace(fast_info=fast_info)))
    snapshot = providers._fetch_with_yfinance("AAPL")
    assert snapshot is not None
    assert snapshot.price == 120
    assert snapshot.change_percent == pytest.approx(20)


def test_news_request_normalizes_ticker_before_fetch_and_related_matching(monkeypatch):
    from datetime import datetime, timezone
    calls = []
    published = datetime.now(timezone.utc).timestamp() - 60
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda ticker:
        calls.append(ticker) or SimpleNamespace(news=[
            {"title": "matching", "providerPublishTime": published, "relatedTickers": ["AAPL"]}
        ])))
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    assert [row["title"] for row in providers.fetch_news_articles(" aapl ")] == ["matching"]
    assert calls == ["AAPL"]
    assert providers.fetch_news_articles("   ") == []
    assert calls == ["AAPL"]


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_stooq_failed_envelope_cannot_supply_retained_prices(monkeypatch, failure):
    _mock_response(monkeypatch, {"symbols": [{"symbol": "AAPL.US", "close": 120}], **failure})
    assert providers._fetch_with_stooq("AAPL") is None


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_yahoo_quote_failed_envelope_cannot_supply_retained_prices(monkeypatch, failure):
    _mock_response(monkeypatch, {"quoteResponse": {"result": [
        {"symbol": "AAPL", "regularMarketPrice": 120, "regularMarketPreviousClose": 100}
    ], **failure}})
    assert providers._fetch_with_yahoo_quote("AAPL") is None


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_alpha_vantage_failed_envelope_cannot_supply_retained_news(monkeypatch, failure):
    from datetime import datetime, timezone, timedelta
    published = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y%m%dT%H%M%S")
    _mock_alpha_vantage_news(monkeypatch, [])
    _mock_response(monkeypatch, {"feed": [{"title": "retained", "time_published": published}], **failure})
    assert providers.fetch_news_articles("AAPL") == []


@pytest.mark.parametrize("hours", [0, -1])
def test_empty_news_windows_stop_before_provider_io(monkeypatch, hours):
    calls = []
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda ticker: calls.append(ticker)))
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    assert providers.fetch_news_articles("AAPL", lookback_hours=hours) == []
    assert calls == []


@pytest.mark.parametrize("status_code", [429, 500])
def test_alpha_vantage_http_failures_cannot_supply_retained_news(monkeypatch, status_code):
    from datetime import datetime, timezone, timedelta
    published = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y%m%dT%H%M%S")
    _mock_alpha_vantage_news(monkeypatch, [])
    response = SimpleNamespace(status_code=status_code, json=lambda:
                               {"feed": [{"title": "bad", "time_published": published}]})
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=lambda *args, **kwargs: response))
    assert providers.fetch_news_articles("AAPL") == []


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_failed_nested_yfinance_news_content_cannot_generate_alerts(monkeypatch, failure):
    from datetime import datetime, timezone, timedelta
    published = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda ticker: SimpleNamespace(news=[
        {"content": {"title": "bad", "pubDate": published, **failure}},
        {"content": {"title": "valid", "pubDate": published}}])))
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    assert [row["title"] for row in providers.fetch_news_articles("AAPL")] == ["valid"]


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_failed_alpha_vantage_news_records_cannot_generate_alerts(monkeypatch, failure):
    from datetime import datetime, timezone, timedelta
    published = (datetime.now(timezone.utc) - timedelta(minutes=1)).strftime("%Y%m%dT%H%M%S")
    _mock_alpha_vantage_news(monkeypatch, [{"title": "bad", "time_published": published, **failure},
                                         {"title": "valid", "time_published": published}])
    assert [row["title"] for row in providers.fetch_news_articles("AAPL")] == ["valid"]


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_failed_finnhub_news_records_cannot_generate_news_alerts(monkeypatch, failure):
    from datetime import datetime, timezone
    published = datetime.now(timezone.utc).timestamp() - 60
    _mock_finnhub_news(monkeypatch, [{"headline": "bad", "datetime": published, **failure},
                                   {"headline": "valid", "datetime": published}])
    assert [row["title"] for row in providers.fetch_news_articles("AAPL")] == ["valid"]


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_failed_yfinance_news_does_not_block_valid_fallback(monkeypatch, failure):
    from datetime import datetime, timezone
    published = datetime.now(timezone.utc).timestamp() - 60
    _mock_finnhub_news(monkeypatch, [{"headline": "valid", "datetime": published}])
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda ticker:
                        SimpleNamespace(news=[{"title": "bad", "providerPublishTime": published, **failure}])))
    assert [row["title"] for row in providers.fetch_news_articles("AAPL")] == ["valid"]


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_failed_chart_result_cannot_supply_alert_prices(monkeypatch, failure):
    _mock_response(monkeypatch, {"chart": {"result": [{
        "meta": {"symbol": "AAPL"}, "indicators": {"quote": [{"close": [100, 120]}]}, **failure}]}})
    assert providers._fetch_with_yahoo_chart("AAPL") is None


def test_yahoo_chart_error_envelope_cannot_supply_alert_prices(monkeypatch):
    _mock_response(monkeypatch, {"chart": {"error": {"code": "Not Found"}, "result": [{
        "meta": {"symbol": "AAPL"}, "indicators": {"quote": [{"close": [100, 120]}]}}]}})
    assert providers._fetch_with_yahoo_chart("AAPL") is None


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_stooq_failed_quote_records_cannot_supply_alert_prices(monkeypatch, failure):
    _mock_response(monkeypatch, {"symbols": [{"symbol": "AAPL.US", "close": 120, **failure}]})
    assert providers._fetch_with_stooq("AAPL") is None


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_failed_yahoo_quote_records_do_not_supply_alert_prices(monkeypatch, failure):
    _mock_response(monkeypatch, {"quoteResponse": {"result": [
        {"symbol": "AAPL", "regularMarketPrice": 120, "regularMarketPreviousClose": 100, **failure}]}})
    assert providers._fetch_with_yahoo_quote("AAPL") is None


@pytest.mark.parametrize("field", ["ticker", "symbol"])
def test_yfinance_quote_requires_matching_explicit_instrument(monkeypatch, field):
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda ticker:
                        SimpleNamespace(fast_info={"last_price": 120, "previous_close": 100, field: "MSFT"})))
    assert providers._fetch_with_yfinance("AAPL") is None


@pytest.mark.parametrize("failure", [{"success": False}, {"error": "bad"}, {"status": " Failed "}])
def test_yfinance_quote_business_failures_cannot_supply_alert_prices(monkeypatch, failure):
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda ticker:
                        SimpleNamespace(fast_info={"last_price": 120, "previous_close": 100, **failure})))
    assert providers._fetch_with_yfinance("AAPL") is None


def _mock_response(monkeypatch, payload):
    response = SimpleNamespace(status_code=200, json=lambda: payload)
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=lambda *_args, **_kwargs: response))


@pytest.mark.parametrize("symbol", ["TSLA", None, ""])
def test_yahoo_quote_rejects_unidentified_or_unrelated_quote(monkeypatch, symbol):
    _mock_response(monkeypatch, {"quoteResponse": {"result": [{
        "symbol": symbol, "regularMarketPrice": 120.0, "regularMarketPreviousClose": 100.0,
    }]}})

    assert providers._fetch_with_yahoo_quote("AAPL") is None


def test_yahoo_quote_selects_matching_symbol_instead_of_first_result(monkeypatch):
    _mock_response(monkeypatch, {"quoteResponse": {"result": [
        {"symbol": "TSLA", "regularMarketPrice": 300.0, "regularMarketPreviousClose": 250.0},
        {"symbol": " aapl ", "regularMarketPrice": 105.0, "regularMarketPreviousClose": 100.0},
    ]}})

    snapshot = providers._fetch_with_yahoo_quote("AAPL")

    assert snapshot is not None
    assert snapshot.ticker == "AAPL"
    assert snapshot.price == 105.0
    assert snapshot.change_percent == pytest.approx(5.0)


def test_yahoo_quote_mismatch_cannot_trigger_price_alert(monkeypatch):
    _mock_response(monkeypatch, {"quoteResponse": {"result": [{
        "symbol": "TSLA", "regularMarketPrice": 120.0, "regularMarketPreviousClose": 100.0,
    }]}})
    attempts = []
    sends = []
    subscription_service = SimpleNamespace(
        get_subscriptions=lambda **_kwargs: [{
            "email": "alice@example.invalid", "ticker": "AAPL", "alert_types": ["price_change"],
            "alert_mode": "price_target", "price_target": 110.0, "direction": "above",
        }],
        is_valid_email=lambda _email: True,
        record_alert_attempt=lambda *args, **kwargs: attempts.append((args, kwargs)),
        set_price_target_fired=lambda *args: attempts.append(args),
        record_alert_event=lambda *args, **kwargs: attempts.append((args, kwargs)),
    )
    scheduler = PriceChangeScheduler(
        subscription_service,
        SimpleNamespace(send_stock_alert=lambda **kwargs: sends.append(kwargs) or True),
        providers._fetch_with_yahoo_quote,
    )

    assert scheduler.run_once() == []
    assert sends == []
    assert attempts == []
    assert scheduler.last_price_unavailable == 1


@pytest.mark.parametrize("symbol", ["TSLA", None, ""])
def test_yahoo_chart_rejects_unidentified_or_unrelated_result(monkeypatch, symbol):
    _mock_response(monkeypatch, {"chart": {"result": [{
        "meta": {"symbol": symbol}, "indicators": {"quote": [{"close": [100.0, 120.0]}]},
    }]}})

    assert providers._fetch_with_yahoo_chart("AAPL") is None


def test_yahoo_chart_accepts_normalized_matching_symbol(monkeypatch):
    _mock_response(monkeypatch, {"chart": {"result": [{
        "meta": {"symbol": " aapl "}, "indicators": {"quote": [{"close": [100.0, 105.0]}]},
    }]}})

    snapshot = providers._fetch_with_yahoo_chart("AAPL")

    assert snapshot is not None
    assert snapshot.ticker == "AAPL"
    assert snapshot.price == 105.0
    assert snapshot.change_percent == pytest.approx(5.0)


@pytest.mark.parametrize("closes", [[100.0, None, 105.0], [100.0, 105.0, None], [None, 100.0, None, 105.0, None]])
def test_yahoo_chart_null_gaps_do_not_discard_valid_trading_closes(monkeypatch, closes):
    _mock_response(monkeypatch, {"chart": {"result": [{
        "meta": {"symbol": "AAPL"}, "indicators": {"quote": [{"close": closes}]},
    }]}})

    snapshot = providers._fetch_with_yahoo_chart("AAPL")

    assert snapshot is not None
    assert snapshot.price == 105.0
    assert snapshot.change_percent == pytest.approx(5.0)


@pytest.mark.parametrize("latest", [True, -1.0, "bad"])
def test_yahoo_chart_invalid_latest_value_does_not_reuse_older_close(monkeypatch, latest):
    _mock_response(monkeypatch, {"chart": {"result": [{
        "meta": {"symbol": "AAPL"}, "indicators": {"quote": [{"close": [100.0, 105.0, latest]}]},
    }]}})

    assert providers._fetch_with_yahoo_chart("AAPL") is None


@pytest.mark.parametrize("symbol", ["TSLA.US", None, ""])
def test_stooq_rejects_unidentified_or_unrelated_quote(monkeypatch, symbol):
    _mock_response(monkeypatch, {"symbols": [{"symbol": symbol, "close": 120.0}]})

    assert providers._fetch_with_stooq("AAPL") is None


def test_stooq_accepts_normalized_matching_symbol(monkeypatch):
    _mock_response(monkeypatch, {"symbols": [{"symbol": " aapl.US ", "close": 105.0}]})

    snapshot = providers._fetch_with_stooq("AAPL")

    assert snapshot is not None
    assert snapshot.ticker == "AAPL"
    assert snapshot.price == 105.0


@pytest.mark.parametrize("days_since_quote", [1, 2, 3])
def test_stooq_uses_previous_trading_close_for_older_quote(monkeypatch, days_since_quote):
    from datetime import datetime, timedelta, timezone

    quote_date = datetime.now(timezone.utc).date() - timedelta(days=days_since_quote)
    quote_response = SimpleNamespace(status_code=200, json=lambda: {"symbols": [{
        "symbol": "AAPL.US", "date": quote_date.isoformat(), "close": 105.0,
    }]})
    history_response = SimpleNamespace(
        status_code=200,
        text=f"Date,Close\n{quote_date - timedelta(days=1)},100.0\n{quote_date},105.0\n",
    )
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(
        get=lambda url, **_kwargs: history_response if "/q/d/l/" in url else quote_response,
    ))

    snapshot = providers._fetch_with_stooq("AAPL")

    assert snapshot is not None
    assert snapshot.change_percent == pytest.approx(5.0)


@pytest.mark.parametrize("row_order", [(0, 1), (1, 0)])
def test_stooq_previous_close_uses_latest_date_instead_of_csv_order(monkeypatch, row_order):
    from datetime import datetime, timedelta, timezone

    quote_date = datetime.now(timezone.utc).date()
    rows = [f"{quote_date - timedelta(days=2)},90.0", f"{quote_date - timedelta(days=1)},100.0"]
    quote_response = SimpleNamespace(status_code=200, json=lambda: {"symbols": [{
        "symbol": "AAPL.US", "date": quote_date.isoformat(), "close": 110.0,
    }]})
    history_response = SimpleNamespace(status_code=200, text="Date,Close\n" + "\n".join(rows[i] for i in row_order))
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(
        get=lambda url, **_kwargs: history_response if "/q/d/l/" in url else quote_response,
    ))

    snapshot = providers._fetch_with_stooq("AAPL")

    assert snapshot is not None
    assert snapshot.change_percent == pytest.approx(10.0)


@pytest.mark.parametrize("suffix", ["-bad", "Tbad", "Z"])
@pytest.mark.parametrize("valid_history", [False, True])
def test_stooq_invalid_history_date_cannot_supply_previous_close(monkeypatch, suffix, valid_history):
    from datetime import datetime, timedelta, timezone

    quote_date = datetime.now(timezone.utc).date()
    rows = [f"{quote_date - timedelta(days=1)}{suffix},50.0"]
    if valid_history:
        rows.append(f"{quote_date - timedelta(days=2)},100.0")
    quote_response = SimpleNamespace(status_code=200, json=lambda: {"symbols": [{
        "symbol": "AAPL.US", "date": quote_date.isoformat(), "close": 105.0,
    }]})
    history_response = SimpleNamespace(status_code=200, text="Date,Close\n" + "\n".join(rows))
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(
        get=lambda url, **_kwargs: history_response if "/q/d/l/" in url else quote_response,
    ))

    snapshot = providers._fetch_with_stooq("AAPL")

    assert snapshot is not None
    assert snapshot.price == 105.0
    assert snapshot.change_percent == (pytest.approx(5.0) if valid_history else None)


def _mock_fetchers(monkeypatch, snapshots):
    monkeypatch.setattr(providers, "_PRICE_CACHE", {})
    calls = []
    for name, snapshot in zip((
        "_fetch_with_stooq", "_fetch_with_yfinance", "_fetch_with_yahoo_quote", "_fetch_with_yahoo_chart",
    ), snapshots):
        def fetch(_ticker, result=snapshot, provider_name=name):
            calls.append(provider_name)
            return result
        monkeypatch.setattr(providers, name, fetch)
    return calls


def test_snapshot_fallback_prefers_complete_quote_after_price_only_result(monkeypatch):
    partial = providers.PriceSnapshot("AAPL", 105.0, None)
    complete = providers.PriceSnapshot("AAPL", 105.0, 5.0)
    calls = _mock_fetchers(monkeypatch, [partial, complete, None, None])

    snapshot = providers.fetch_price_snapshot("AAPL")

    assert snapshot == complete
    assert calls == ["_fetch_with_stooq", "_fetch_with_yfinance"]
    assert providers._get_cached_snapshot("AAPL") == complete


@pytest.mark.parametrize("symbol", ["TSLA", "", None])
@pytest.mark.parametrize("change_percent", [None, 5.0])
@pytest.mark.parametrize("available", [False, True])
def test_unrelated_provider_snapshot_cannot_block_valid_fallback(monkeypatch, symbol, change_percent, available):
    wrong = providers.PriceSnapshot(symbol, 300.0, change_percent)
    correct = providers.PriceSnapshot("AAPL", 105.0, 5.0) if available else None
    calls = _mock_fetchers(monkeypatch, [wrong, correct, None, None])

    snapshot = providers.fetch_price_snapshot("AAPL")

    assert snapshot == correct
    assert len(calls) == (2 if available else 4)
    assert providers._get_cached_snapshot("AAPL") == correct


def test_matching_provider_snapshot_keeps_normalized_symbol(monkeypatch):
    quote = providers.PriceSnapshot(" aapl ", 105.0, 5.0)
    calls = _mock_fetchers(monkeypatch, [quote, None, None, None])

    assert providers.fetch_price_snapshot("AAPL") == quote
    assert calls == ["_fetch_with_stooq"]


def test_snapshot_fallback_keeps_price_only_quote_when_later_sources_fail(monkeypatch):
    partial = providers.PriceSnapshot("AAPL", 105.0, None)
    calls = _mock_fetchers(monkeypatch, [partial, None, None, None])

    snapshot = providers.fetch_price_snapshot("AAPL")

    assert snapshot == partial
    assert len(calls) == 4
    assert providers._get_cached_snapshot("AAPL") == partial


@pytest.mark.parametrize("cached_ticker", ["TSLA", "", None])
def test_mismatched_cached_quote_is_evicted_before_source_fallback(monkeypatch, cached_ticker):
    complete = providers.PriceSnapshot("AAPL", 105.0, 5.0)
    calls = _mock_fetchers(monkeypatch, [complete, None, None, None])
    providers._PRICE_CACHE["AAPL"] = (
        providers.PriceSnapshot(cached_ticker, 300.0, 10.0), providers.time.time(),
    )

    snapshot = providers.fetch_price_snapshot("AAPL")

    assert snapshot == complete
    assert calls == ["_fetch_with_stooq"]
    assert providers._get_cached_snapshot("AAPL") == complete


def test_matching_cached_ticker_accepts_case_and_spaces_without_fetch(monkeypatch):
    calls = _mock_fetchers(monkeypatch, [None, None, None, None])
    snapshot = providers.PriceSnapshot(" aapl ", 105.0, 5.0)
    providers._PRICE_CACHE["AAPL"] = (snapshot, providers.time.time())

    assert providers.fetch_price_snapshot("AAPL") == snapshot
    assert calls == []


@pytest.mark.parametrize("origin", ["provider", "cache"])
@pytest.mark.parametrize("field,value", [
    ("price", None), ("price", 0), ("price", -1), ("price", True), ("price", "bad"),
    ("price", float("nan")), ("price", float("inf")), ("price", "1e309"),
    ("change_percent", True), ("change_percent", "bad"),
    ("change_percent", float("nan")), ("change_percent", float("inf")),
    ("change_percent", float("-inf")), ("change_percent", "1e309"),
])
def test_invalid_quote_numbers_do_not_block_source_fallback(monkeypatch, origin, field, value):
    invalid = providers.PriceSnapshot("AAPL", 105.0, 5.0)
    setattr(invalid, field, value)
    complete = providers.PriceSnapshot("AAPL", 105.0, 5.0)
    sources = [invalid, complete, None, None] if origin == "provider" else [complete, None, None, None]
    calls = _mock_fetchers(monkeypatch, sources)
    if origin == "cache":
        providers._PRICE_CACHE["AAPL"] = (invalid, providers.time.time())

    assert providers.fetch_price_snapshot("AAPL") is complete
    assert calls == (["_fetch_with_stooq", "_fetch_with_yfinance"] if origin == "provider" else ["_fetch_with_stooq"])
    assert providers._get_cached_snapshot("AAPL") is complete


def test_overflowing_yfinance_percentage_falls_back_to_healthy_quote(monkeypatch):
    yfinance_fetcher = providers._fetch_with_yfinance
    complete = providers.PriceSnapshot("AAPL", 105.0, 5.0)
    calls = _mock_fetchers(monkeypatch, [None, None, complete, None])
    monkeypatch.setattr(providers, "_fetch_with_yfinance", yfinance_fetcher)
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(
        Ticker=lambda _ticker: SimpleNamespace(fast_info={"last_price": 1e308, "previous_close": 1e-308}),
    ))

    assert providers.fetch_price_snapshot("AAPL") is complete
    assert providers.fetch_price_snapshot("AAPL") is complete
    assert calls == ["_fetch_with_stooq", "_fetch_with_yahoo_quote"]


@pytest.mark.parametrize("change_percent", [0.0, -5.0])
def test_valid_cached_quote_numbers_keep_cache_hit(monkeypatch, change_percent):
    calls = _mock_fetchers(monkeypatch, [None, None, None, None])
    snapshot = providers.PriceSnapshot("AAPL", 105.0, change_percent)
    providers._PRICE_CACHE["AAPL"] = (snapshot, providers.time.time())

    assert providers.fetch_price_snapshot("AAPL") is snapshot
    assert calls == []


@pytest.mark.parametrize("available", [False, True])
def test_price_only_cache_allows_percentage_fallback_without_extending_its_age(monkeypatch, available):
    partial = providers.PriceSnapshot("AAPL", 105.0, None)
    complete = providers.PriceSnapshot("AAPL", 110.0, 10.0) if available else None
    calls = _mock_fetchers(monkeypatch, [None, complete, None, None])
    monkeypatch.setattr(providers.time, "time", lambda: 1000.0)
    providers._PRICE_CACHE["AAPL"] = (partial, 900.0)

    result = providers.fetch_price_snapshot("AAPL")

    assert result is (complete if available else partial)
    assert len(calls) == (2 if available else 4)
    assert providers._PRICE_CACHE["AAPL"][1] == (1000.0 if available else 900.0)


def test_invalid_percentage_keeps_valid_price_when_fallback_sources_fail(monkeypatch):
    partial = providers.PriceSnapshot("AAPL", 105.0, float("inf"))
    calls = _mock_fetchers(monkeypatch, [partial, None, None, None])

    snapshot = providers.fetch_price_snapshot("AAPL")

    assert snapshot is not None
    assert snapshot.price == 105.0
    assert snapshot.change_percent is None
    assert len(calls) == 4
    assert providers._get_cached_snapshot("AAPL") is snapshot


def test_provider_numeric_strings_are_normalized_without_extra_fallback(monkeypatch):
    snapshot = providers.PriceSnapshot("AAPL", "105", "-5")
    calls = _mock_fetchers(monkeypatch, [snapshot, None, None, None])

    result = providers.fetch_price_snapshot("AAPL")

    assert result is not None
    assert result.price == 105.0
    assert result.change_percent == -5.0
    assert calls == ["_fetch_with_stooq"]


def _mock_finnhub_news(monkeypatch, payload):
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _ticker: SimpleNamespace(news=[])))
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    _mock_response(monkeypatch, payload)


def _mock_alpha_vantage_news(monkeypatch, feed):
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _ticker: SimpleNamespace(news=[])))
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")
    _mock_response(monkeypatch, {"feed": feed})


@pytest.mark.parametrize("source", ["yfinance", "finnhub", "alpha_vantage"])
def test_future_dated_news_cannot_enter_alert_feed(monkeypatch, source):
    from datetime import datetime, timedelta, timezone

    future = datetime.now(timezone.utc) + timedelta(hours=2)
    if source == "alpha_vantage":
        _mock_alpha_vantage_news(monkeypatch, [{
            "title": "Future earnings release", "time_published": future.strftime("%Y%m%dT%H%M%S"),
        }])
    elif source == "finnhub":
        _mock_finnhub_news(monkeypatch, [{"headline": "Future earnings release", "datetime": future.timestamp()}])
        monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    else:
        monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _ticker: SimpleNamespace(news=[{
            "title": "Future earnings release", "providerPublishTime": future.timestamp(),
        }])))
        monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
        monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)

    assert providers.fetch_news_articles("AAPL") == []


def test_future_primary_news_does_not_block_valid_fallback(monkeypatch):
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    _mock_finnhub_news(monkeypatch, [{
        "headline": "Actual earnings release", "datetime": (now - timedelta(hours=1)).timestamp(), "related": "AAPL",
    }])
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _ticker: SimpleNamespace(news=[{
        "title": "Future earnings release", "providerPublishTime": (now + timedelta(hours=2)).timestamp(),
    }])))

    articles = providers.fetch_news_articles("AAPL")

    assert [article["title"] for article in articles] == ["Actual earnings release"]


@pytest.mark.parametrize("primary", ["yfinance", "finnhub"])
def test_explicitly_unrelated_primary_news_does_not_block_relevant_fallback(monkeypatch, primary):
    from datetime import datetime, timedelta, timezone

    published = datetime.now(timezone.utc) - timedelta(hours=1)
    requests = []
    fallback = SimpleNamespace(status_code=200, json=lambda: {"feed": [{
        "title": "Actual earnings release", "time_published": published.strftime("%Y%m%dT%H%M%S"),
        "ticker_sentiment": [{"ticker": "AAPL"}],
    }]})
    wrong_finnhub = SimpleNamespace(status_code=200, json=lambda: [{
        "headline": "AAPL mentioned in another company's story", "datetime": published.timestamp(), "related": "MSFT",
    }])

    def fetch(url, **_kwargs):
        requests.append(url)
        return wrong_finnhub if "finnhub.io" in url else fallback

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=fetch))
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")
    if primary == "finnhub":
        monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
        news = []
    else:
        monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
        news = [{
            "title": "AAPL mentioned in another company's story", "providerPublishTime": published.timestamp(),
            "relatedTickers": ["MSFT"],
        }]
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _ticker: SimpleNamespace(news=news)))

    articles = providers.fetch_news_articles("AAPL")

    assert [article["title"] for article in articles] == ["Actual earnings release"]
    assert articles[0]["related_tickers"] == ["AAPL"]
    assert any("alphavantage.co" in url for url in requests)


@pytest.mark.parametrize("source", ["yfinance", "finnhub"])
@pytest.mark.parametrize("timestamp", ["0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-14:00"])
def test_overflowing_news_timezone_does_not_drop_following_article(monkeypatch, source, timestamp):
    from datetime import datetime, timedelta, timezone

    published = (datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    if source == "finnhub":
        _mock_finnhub_news(monkeypatch, [
            {"headline": "Invalid timezone", "datetime": timestamp},
            {"headline": "Actual earnings release", "datetime": published, "related": "AAPL"},
        ])
    else:
        monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
        monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _ticker: SimpleNamespace(news=[
            {"title": "Invalid timezone", "providerPublishTime": timestamp},
            {"title": "Actual earnings release", "providerPublishTime": published, "relatedTickers": ["AAPL"]},
        ])))

    articles = providers.fetch_news_articles("AAPL")

    assert [article["title"] for article in articles] == ["Actual earnings release"]
    assert articles[0]["related_tickers"] == ["AAPL"]


@pytest.mark.parametrize("timestamp_format", ["%Y%m%dT%H%M%S", "%Y%m%d%H%M%S", "%Y%m%d%H%M"])
def test_alpha_vantage_news_timestamp_keeps_feed_format_and_precision(monkeypatch, timestamp_format):
    from datetime import datetime, timedelta, timezone

    published = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0, second=37)
    _mock_alpha_vantage_news(monkeypatch, [{
        "title": "AAPL earnings release", "time_published": published.strftime(timestamp_format),
        "ticker_sentiment": [{"ticker": "AAPL"}],
    }])

    articles = providers.fetch_news_articles("AAPL")

    assert len(articles) == 1
    expected = published.replace(tzinfo=None)
    if timestamp_format == "%Y%m%d%H%M":
        expected = expected.replace(second=0)
    assert articles[0]["published_at"] == expected
    assert articles[0]["related_tickers"] == ["AAPL"]


@pytest.mark.parametrize("related", [None, 123, True, "bad", {"ticker": "AAPL"}])
def test_bad_alpha_vantage_related_field_does_not_drop_following_news(monkeypatch, related):
    from datetime import datetime, timedelta, timezone

    published = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y%m%dT%H%M%S")
    _mock_alpha_vantage_news(monkeypatch, [
        {"title": "AAPL first earnings release", "time_published": published, "ticker_sentiment": related},
        {"title": "AAPL second earnings release", "time_published": published, "ticker_sentiment": [{"ticker": "AAPL"}]},
    ])

    articles = providers.fetch_news_articles("AAPL")

    assert [article["title"] for article in articles] == ["AAPL first earnings release", "AAPL second earnings release"]
    assert articles[1]["related_tickers"] == ["AAPL"]


@pytest.mark.parametrize("timestamp", [None, "bad", {}, [], True, float("inf"), float("nan"), 1e100])
def test_bad_finnhub_timestamp_does_not_drop_following_news(monkeypatch, timestamp):
    from datetime import datetime, timedelta, timezone

    published = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
    _mock_finnhub_news(monkeypatch, [
        {"headline": "AAPL malformed timestamp", "datetime": timestamp, "related": "AAPL"},
        {"headline": "AAPL valid news", "datetime": published, "related": "AAPL"},
    ])

    articles = providers.fetch_news_articles("AAPL")

    assert [article["title"] for article in articles] == ["AAPL valid news"]
    assert articles[0]["published_at"] == datetime.fromtimestamp(published, tz=timezone.utc).replace(tzinfo=None)


@pytest.mark.parametrize("timestamp_format", ["epoch", "numeric_string", "iso"])
def test_finnhub_timestamp_formats_keep_utc_news(monkeypatch, timestamp_format):
    from datetime import datetime, timedelta, timezone

    published = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0)
    timestamp = {
        "epoch": published.timestamp(),
        "numeric_string": str(int(published.timestamp())),
        "iso": published.astimezone(timezone(timedelta(hours=8))).isoformat(),
    }[timestamp_format]
    _mock_finnhub_news(monkeypatch, [{"headline": "AAPL valid news", "datetime": timestamp}])

    articles = providers.fetch_news_articles("AAPL")

    assert len(articles) == 1
    assert articles[0]["published_at"] == published.replace(tzinfo=None)


@pytest.mark.parametrize("source", ["yfinance", "finnhub"])
@pytest.mark.parametrize("related,expected", [
    (" aapl , msft ", ["AAPL", "MSFT"]),
    ([" aapl ", None, 123, "msft"], ["AAPL", "MSFT"]),
    ({"symbol": "AAPL"}, []),
    (123, []),
    (True, []),
])
def test_news_related_tickers_normalize_without_dropping_following_articles(monkeypatch, source, related, expected):
    from datetime import datetime, timedelta, timezone

    published = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
    if source == "finnhub":
        _mock_finnhub_news(monkeypatch, [
            {"headline": "First earnings release", "datetime": published, "related": related},
            {"headline": "Second earnings release", "datetime": published, "related": "AAPL"},
        ])
    else:
        news = [
            {"title": "First earnings release", "providerPublishTime": published, "relatedTickers": related},
            {"title": "Second earnings release", "providerPublishTime": published, "relatedTickers": ["AAPL"]},
        ]
        monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _ticker: SimpleNamespace(news=news)))
        monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
        monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)

    articles = providers.fetch_news_articles("AAPL")

    assert [article["title"] for article in articles] == ["First earnings release", "Second earnings release"]
    assert articles[0]["related_tickers"] == expected
    assert articles[1]["related_tickers"] == ["AAPL"]


def test_string_related_ticker_can_deliver_news_without_symbol_in_title(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from backend.services.alert_scheduler import NewsAlertScheduler

    published = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
    news = [{"title": "Earnings exceed expectations", "providerPublishTime": published, "relatedTickers": "AAPL"}]
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _ticker: SimpleNamespace(news=news)))
    sends = []
    subscription_service = SimpleNamespace(
        get_subscriptions=lambda **_kwargs: [{
            "email": "alice@example.invalid", "ticker": "AAPL", "alert_types": ["news"],
        }],
        is_valid_email=lambda _email: True,
        record_alert_attempt=lambda *args, **kwargs: None,
        update_last_news=lambda *args, **kwargs: None,
        record_alert_event=lambda *args, **kwargs: None,
    )
    scheduler = NewsAlertScheduler(
        subscription_service, SimpleNamespace(send_stock_alert=lambda **kwargs: sends.append(kwargs) or True),
        providers.fetch_news_articles,
    )

    assert len(scheduler.run_once()) == 1
    assert len(sends) == 1
    assert "Earnings exceed expectations" in sends[0]["message"]


@pytest.mark.parametrize("source", ["yfinance", "finnhub", "alpha_vantage"])
@pytest.mark.parametrize("title", [None, "", " \t\n", 123, {"title": "bad"}])
def test_unusable_news_title_does_not_drop_following_headline(monkeypatch, source, title):
    from datetime import datetime, timedelta, timezone

    published = datetime.now(timezone.utc) - timedelta(hours=1)
    if source == "alpha_vantage":
        _mock_alpha_vantage_news(monkeypatch, [
            {"title": title, "time_published": published.strftime("%Y%m%dT%H%M%S")},
            {"title": "Actual earnings release", "time_published": published.strftime("%Y%m%dT%H%M%S")},
        ])
    elif source == "finnhub":
        _mock_finnhub_news(monkeypatch, [
            {"headline": title, "datetime": published.timestamp()},
            {"headline": "Actual earnings release", "datetime": published.timestamp()},
        ])
    else:
        monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
        monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
        news = [
            {"title": title, "providerPublishTime": published.timestamp()},
            {"title": "Actual earnings release", "providerPublishTime": published.timestamp()},
        ]
        monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _ticker: SimpleNamespace(news=news)))

    assert [article["title"] for article in providers.fetch_news_articles("AAPL")] == ["Actual earnings release"]


@pytest.mark.parametrize("primary", ["yfinance", "finnhub"])
@pytest.mark.parametrize("title", ["", " \t\n"])
def test_empty_primary_news_title_allows_valid_fallback(monkeypatch, primary, title):
    from datetime import datetime, timedelta, timezone

    published = datetime.now(timezone.utc) - timedelta(hours=1)
    fallback = SimpleNamespace(status_code=200, json=lambda: {"feed": [{
        "title": "Actual earnings release", "time_published": published.strftime("%Y%m%dT%H%M%S"),
        "ticker_sentiment": [{"ticker": "AAPL"}],
    }]})
    empty_finnhub = SimpleNamespace(status_code=200, json=lambda: [{
        "headline": title, "datetime": published.timestamp(), "related": "AAPL",
    }])
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(
        get=lambda url, **_kwargs: empty_finnhub if "finnhub.io" in url else fallback,
    ))
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")
    if primary == "finnhub":
        monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
        news = []
    else:
        monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
        news = [{"title": title, "providerPublishTime": published.timestamp(), "relatedTickers": ["AAPL"]}]
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _ticker: SimpleNamespace(news=news)))

    assert [article["title"] for article in providers.fetch_news_articles("AAPL")] == ["Actual earnings release"]


@pytest.mark.parametrize("primary", ["yfinance", "finnhub"])
def test_news_cycle_uses_fallback_when_primary_articles_are_outside_alert_window(monkeypatch, primary):
    from datetime import datetime, timedelta, timezone
    from backend.services import alert_scheduler, email_service, subscription_service

    now = datetime.now(timezone.utc)
    old = now - timedelta(hours=36)
    recent = now - timedelta(hours=1)
    fallback = SimpleNamespace(status_code=200, json=lambda: {"feed": [{
        "title": "Actual earnings release", "time_published": recent.strftime("%Y%m%dT%H%M%S"),
        "ticker_sentiment": [{"ticker": "AAPL"}],
    }]})
    old_finnhub = SimpleNamespace(status_code=200, json=lambda: [{
        "headline": "Old earnings release", "datetime": old.timestamp(), "related": "AAPL",
    }])
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(
        get=lambda url, **_kwargs: old_finnhub if "finnhub.io" in url else fallback,
    ))
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key")
    if primary == "finnhub":
        monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
        news = []
    else:
        monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
        news = [{"title": "Old earnings release", "providerPublishTime": old.timestamp(), "relatedTickers": ["AAPL"]}]
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _ticker: SimpleNamespace(news=news)))
    sends = []
    svc = SimpleNamespace(
        get_subscriptions=lambda **_kwargs: [{"email": "alice@example.invalid", "ticker": "AAPL", "alert_types": ["news"]}],
        is_valid_email=lambda _email: True,
        record_alert_attempt=lambda *args, **kwargs: None,
        update_last_news=lambda *args, **kwargs: None,
        record_alert_event=lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(subscription_service, "get_subscription_service", lambda: svc)
    monkeypatch.setattr(email_service, "get_email_service", lambda: SimpleNamespace(
        send_stock_alert=lambda **kwargs: sends.append(kwargs) or True,
    ))

    assert len(alert_scheduler.run_news_alert_cycle()) == 1
    assert len(sends) == 1
    assert "Actual earnings release" in sends[0]["message"]
    assert "Old earnings release" not in sends[0]["message"]


def test_default_news_provider_keeps_48_hour_window(monkeypatch):
    from datetime import datetime, timedelta, timezone

    old = datetime.now(timezone.utc) - timedelta(hours=36)
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    news = [{"title": "Old earnings release", "providerPublishTime": old.timestamp(), "relatedTickers": ["AAPL"]}]
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _ticker: SimpleNamespace(news=news)))

    assert [article["title"] for article in providers.fetch_news_articles("AAPL")] == ["Old earnings release"]
