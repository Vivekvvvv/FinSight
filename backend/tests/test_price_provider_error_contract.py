import sys
from types import SimpleNamespace

from backend.tools import price
from backend.tools import price_history_providers as php


class _UnformattableTicker:
    def __init__(self, secret: str) -> None:
        self.secret = secret

    def __format__(self, _format_spec: str) -> str:
        raise RuntimeError(self.secret)


def test_yahoo_scrape_outer_error_does_not_dump_traceback(caplog, capsys):
    secret = "PRIVATE postgres://price:secret@db/yahoo"
    caplog.set_level("INFO")

    result = price._fetch_with_yahoo_scrape_historical(_UnformattableTicker(secret))
    captured = capsys.readouterr()

    assert result is None
    assert secret not in caplog.text
    assert secret not in captured.out
    assert secret not in captured.err
    assert "Traceback" not in captured.err
    assert "RuntimeError" in caplog.text


def test_massive_outer_error_does_not_dump_traceback(monkeypatch, caplog, capsys):
    secret = "PRIVATE postgres://price:secret@db/massive"
    caplog.set_level("INFO")
    monkeypatch.setattr(php, "MASSIVE_API_KEY", "test-key")

    result = price._fetch_with_massive_io(_UnformattableTicker(secret))
    captured = capsys.readouterr()

    assert result is None
    assert secret not in caplog.text
    assert secret not in captured.out
    assert secret not in captured.err
    assert "Traceback" not in captured.err
    assert "RuntimeError" in caplog.text


def test_yahoo_scrape_url_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE http://proxy-user:secret@proxy.local"
    caplog.set_level("INFO")

    def _fail_get(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(php, "_http_get", _fail_get)

    assert price._fetch_with_yahoo_scrape_historical("AAPL") is None
    assert secret not in caplog.text
    assert caplog.text.count("RuntimeError") == 2


def test_iex_historical_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE postgres://price:secret@db/iex"
    caplog.set_level("INFO")
    monkeypatch.setattr(php, "IEX_CLOUD_API_KEY", "test-key")
    monkeypatch.setattr(
        php,
        "_http_get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    assert price._fetch_with_iex_cloud("AAPL") is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_tiingo_historical_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE postgres://price:secret@db/tiingo"
    caplog.set_level("INFO")
    monkeypatch.setattr(php, "TIINGO_API_KEY", "test-key")
    monkeypatch.setattr(
        php,
        "_http_get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    assert price._fetch_with_tiingo("AAPL") is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_twelve_data_historical_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE postgres://price:secret@db/twelve"
    caplog.set_level("INFO")
    monkeypatch.setattr(php, "TWELVE_DATA_API_KEY", "test-key")
    monkeypatch.setattr(
        php,
        "_http_get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    assert price._fetch_with_twelve_data("AAPL") is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_marketstack_historical_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE postgres://price:secret@db/marketstack"
    caplog.set_level("INFO")
    monkeypatch.setattr(php, "MARKETSTACK_API_KEY", "test-key")
    monkeypatch.setattr(
        php,
        "_http_get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    assert price._fetch_with_marketstack("AAPL") is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_stooq_historical_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE postgres://price:secret@db/stooq"
    caplog.set_level("INFO")

    def _fail_mapping(_ticker):
        raise RuntimeError(secret)

    monkeypatch.setattr(php, "_map_to_stooq_symbol", _fail_mapping)

    assert price._fetch_with_stooq_history("AAPL") is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_alpha_vantage_price_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE https://api-key@alpha.example.com"
    caplog.set_level("INFO")
    monkeypatch.setattr(
        price,
        "_http_get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    assert price._fetch_with_alpha_vantage("AAPL") is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_finnhub_price_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE https://token@finnhub.example.com"
    caplog.set_level("INFO")

    class _FailingClient:
        def quote(self, _ticker):
            raise RuntimeError(secret)

    monkeypatch.setattr(price, "finnhub_client", _FailingClient())

    assert price._fetch_with_finnhub("AAPL") is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_yfinance_price_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE http://proxy-user:secret@proxy.local"
    caplog.set_level("INFO")
    monkeypatch.setattr(
        price.yf,
        "Ticker",
        lambda _ticker: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    assert price._fetch_with_yfinance("AAPL") is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_twelve_data_price_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE https://api-key@twelve.example.com"
    caplog.set_level("INFO")
    monkeypatch.setattr(price, "TWELVE_DATA_API_KEY", "test-key")
    monkeypatch.setattr(
        price,
        "_http_get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    assert price._fetch_with_twelve_data_price("AAPL") is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_yahoo_api_price_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE http://proxy-user:secret@proxy.local/yahoo"
    caplog.set_level("INFO")
    monkeypatch.setattr(
        price,
        "_http_get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    assert price._fetch_yahoo_api_v8("AAPL") is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_google_finance_price_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE http://proxy-user:secret@proxy.local/google"
    caplog.set_level("INFO")
    monkeypatch.setattr(
        price,
        "_http_get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    assert price._scrape_google_finance("AAPL") is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_cnbc_price_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE http://proxy-user:secret@proxy.local/cnbc"
    caplog.set_level("INFO")
    monkeypatch.setattr(
        price,
        "_http_get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    assert price._scrape_cnbc("AAPL") is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_pandas_datareader_price_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE http://proxy-user:secret@proxy.local/stooq"
    caplog.set_level("INFO")
    monkeypatch.setitem(
        sys.modules,
        "pandas_datareader",
        SimpleNamespace(
            get_data_stooq=lambda *_args: (_ for _ in ()).throw(RuntimeError(secret)),
        ),
    )

    assert price._fetch_with_pandas_datareader("AAPL") is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_yahoo_page_price_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE http://proxy-user:secret@proxy.local/yahoo-page"
    caplog.set_level("INFO")
    monkeypatch.setattr(
        price,
        "_http_get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    assert price._scrape_yahoo_finance("AAPL") is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_index_yfinance_price_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE http://proxy-user:secret@proxy.local/index"
    caplog.set_level("INFO")
    monkeypatch.setattr(
        price.yf,
        "download",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    monkeypatch.setattr(price, "_fetch_with_stooq_price", lambda _ticker: None)
    monkeypatch.setattr(price, "_fallback_price_value", lambda _ticker: None)

    assert price._fetch_index_price("^GSPC") is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_search_price_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE https://search-token@search.example.com"
    caplog.set_level("INFO")
    monkeypatch.setattr(
        price,
        "search",
        lambda _query: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    assert price._search_for_price("AAPL") is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_stooq_price_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE postgres://price:secret@db/stooq-quote"
    caplog.set_level("INFO")
    monkeypatch.setattr(
        price,
        "_map_to_stooq_symbol",
        lambda _ticker: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    assert price._fetch_with_stooq_price("AAPL") is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_price_source_orchestrator_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE postgres://price:secret@db/source"
    caplog.set_level("INFO")

    def _fail_source(_ticker):
        raise RuntimeError(secret)

    monkeypatch.setattr(price, "_fetch_yahoo_api_v8", _fail_source)
    monkeypatch.setattr(
        price,
        "_scrape_google_finance",
        lambda _ticker: "AAPL Current Price: $100.00",
    )

    result = price.get_stock_price("AAPL")

    assert "$100.00" in result
    assert secret not in result
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_price_source_without_dollar_value_is_returned(monkeypatch):
    fallback_calls = {"count": 0}

    def _unexpected_fallback(_ticker):
        fallback_calls["count"] += 1
        return "AAPL Current Price: $101.00"

    monkeypatch.setattr(price, "_fetch_yahoo_api_v8", lambda _ticker: "AAPL quote available")
    monkeypatch.setattr(price, "_scrape_google_finance", _unexpected_fallback)

    assert price.get_stock_price("AAPL") == "AAPL quote available"
    assert fallback_calls["count"] == 0


def test_initial_yfinance_historical_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE http://proxy-user:secret@proxy.local/history-initial"
    caplog.set_level("INFO")

    calls = {"count": 0}

    class _Ticker:
        def __init__(self, *_args, **_kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError(secret)

        def history(self, **_kwargs):
            return SimpleNamespace(empty=True)

    monkeypatch.setattr(price.yf, "Ticker", _Ticker)
    monkeypatch.setattr(price, "ALPHA_VANTAGE_API_KEY", "")
    monkeypatch.setattr(price.time, "sleep", lambda _seconds: None)

    result = price.get_stock_historical_data("AAPL")

    assert result == {"error": "No historical data for AAPL"}
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_alpha_vantage_historical_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE https://history-key@alpha.example.com"
    caplog.set_level("INFO")

    class _Ticker:
        def __init__(self, *_args, **_kwargs):
            pass

        def history(self, **_kwargs):
            return SimpleNamespace(empty=True)

    monkeypatch.setattr(price.yf, "Ticker", _Ticker)
    monkeypatch.setattr(price, "ALPHA_VANTAGE_API_KEY", "test-key")
    monkeypatch.setattr(
        price,
        "_http_get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    monkeypatch.setattr(price.time, "sleep", lambda _seconds: None)

    result = price.get_stock_historical_data("AAPL")

    assert result == {"error": "No historical data for AAPL"}
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_retry_yfinance_historical_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE http://proxy-user:secret@proxy.local/history-retry"
    caplog.set_level("INFO")
    calls = {"count": 0}

    class _Ticker:
        def __init__(self, *_args, **_kwargs):
            calls["count"] += 1

        def history(self, **_kwargs):
            if calls["count"] == 1:
                return SimpleNamespace(empty=True)
            raise RuntimeError(secret)

    expected = {
        "kline_data": [{"time": "2026-01-01", "close": 100.0}],
        "period": "1y",
        "interval": "1d",
    }
    monkeypatch.setattr(price.yf, "Ticker", _Ticker)
    monkeypatch.setattr(price, "ALPHA_VANTAGE_API_KEY", "")
    monkeypatch.setattr(price, "FINNHUB_API_KEY", "")
    monkeypatch.setattr(price.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(price, "_fetch_with_yahoo_scrape_historical", lambda *_args: expected)

    assert price.get_stock_historical_data("AAPL") == expected
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_finnhub_historical_orchestrator_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE https://history-token@finnhub.example.com"
    caplog.set_level("INFO")

    class _FailingTicker:
        def __init__(self, *_args, **_kwargs):
            raise LookupError("safe upstream failure")

    class _FailingFinnhub:
        def stock_candles(self, *_args, **_kwargs):
            raise RuntimeError(secret)

    expected = {
        "kline_data": [{"time": "2026-01-01", "close": 100.0}],
        "period": "1y",
        "interval": "1d",
    }
    monkeypatch.setattr(price.yf, "Ticker", _FailingTicker)
    monkeypatch.setattr(price, "ALPHA_VANTAGE_API_KEY", "")
    monkeypatch.setattr(price, "FINNHUB_API_KEY", "test-key")
    monkeypatch.setattr(price, "finnhub_client", _FailingFinnhub())
    monkeypatch.setattr(price, "_fetch_with_yahoo_scrape_historical", lambda *_args: expected)

    assert price.get_stock_historical_data("AAPL") == expected
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_yahoo_historical_orchestrator_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE http://proxy-user:secret@proxy.local/yahoo-wrapper"
    caplog.set_level("INFO")

    class _FailingTicker:
        def __init__(self, *_args, **_kwargs):
            raise LookupError("safe upstream failure")

    expected = {
        "kline_data": [{"time": "2026-01-01", "close": 100.0}],
        "period": "1y",
        "interval": "1d",
    }
    monkeypatch.setattr(price.yf, "Ticker", _FailingTicker)
    monkeypatch.setattr(price, "ALPHA_VANTAGE_API_KEY", "")
    monkeypatch.setattr(price, "FINNHUB_API_KEY", "")
    monkeypatch.setattr(
        price,
        "_fetch_with_yahoo_scrape_historical",
        lambda *_args: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    monkeypatch.setattr(price, "_fetch_with_iex_cloud", lambda *_args: expected)

    assert price.get_stock_historical_data("AAPL") == expected
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_index_historical_orchestrator_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE http://proxy-user:secret@proxy.local/index-history"
    caplog.set_level("INFO")
    calls = {"count": 0}

    class _FailingTicker:
        def __init__(self, *_args, **_kwargs):
            calls["count"] += 1
            if calls["count"] > 4:
                raise RuntimeError(secret)
            raise LookupError("safe upstream failure")

    expected = {
        "kline_data": [{"time": "2026-01-01", "close": 100.0}],
        "period": "1y",
        "interval": "1d",
    }
    monkeypatch.setattr(price.yf, "Ticker", _FailingTicker)
    monkeypatch.setattr(price, "FINNHUB_API_KEY", "")
    monkeypatch.setattr(price, "_fetch_with_stooq_history", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_yahoo_scrape_historical", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_iex_cloud", lambda *_args: expected)

    assert price.get_stock_historical_data("^GSPC") == expected
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_iex_historical_orchestrator_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE https://history-key@iex.example.com"
    caplog.set_level("INFO")

    class _FailingTicker:
        def __init__(self, *_args, **_kwargs):
            raise LookupError("safe upstream failure")

    expected = {
        "kline_data": [{"time": "2026-01-01", "close": 100.0}],
        "period": "1y",
        "interval": "1d",
    }
    monkeypatch.setattr(price.yf, "Ticker", _FailingTicker)
    monkeypatch.setattr(price, "ALPHA_VANTAGE_API_KEY", "")
    monkeypatch.setattr(price, "FINNHUB_API_KEY", "")
    monkeypatch.setattr(price, "_fetch_with_yahoo_scrape_historical", lambda *_args: None)
    monkeypatch.setattr(
        price,
        "_fetch_with_iex_cloud",
        lambda *_args: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    monkeypatch.setattr(price, "_fetch_with_tiingo", lambda *_args: expected)

    assert price.get_stock_historical_data("AAPL") == expected
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_tiingo_historical_orchestrator_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE https://history-key@tiingo.example.com"
    caplog.set_level("INFO")

    class _FailingTicker:
        def __init__(self, *_args, **_kwargs):
            raise LookupError("safe upstream failure")

    expected = {
        "kline_data": [{"time": "2026-01-01", "close": 100.0}],
        "period": "1y",
        "interval": "1d",
    }
    monkeypatch.setattr(price.yf, "Ticker", _FailingTicker)
    monkeypatch.setattr(price, "ALPHA_VANTAGE_API_KEY", "")
    monkeypatch.setattr(price, "FINNHUB_API_KEY", "")
    monkeypatch.setattr(price, "_fetch_with_yahoo_scrape_historical", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_iex_cloud", lambda *_args: None)
    monkeypatch.setattr(
        price,
        "_fetch_with_tiingo",
        lambda *_args: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    monkeypatch.setattr(price, "_fetch_with_twelve_data", lambda *_args: expected)

    assert price.get_stock_historical_data("AAPL") == expected
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_twelve_data_historical_orchestrator_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE https://history-key@twelve.example.com"
    caplog.set_level("INFO")

    class _FailingTicker:
        def __init__(self, *_args, **_kwargs):
            raise LookupError("safe upstream failure")

    expected = {
        "kline_data": [{"time": "2026-01-01", "close": 100.0}],
        "period": "1y",
        "interval": "1d",
    }
    monkeypatch.setattr(price.yf, "Ticker", _FailingTicker)
    monkeypatch.setattr(price, "ALPHA_VANTAGE_API_KEY", "")
    monkeypatch.setattr(price, "FINNHUB_API_KEY", "")
    monkeypatch.setattr(price, "_fetch_with_yahoo_scrape_historical", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_iex_cloud", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_tiingo", lambda *_args: None)
    monkeypatch.setattr(
        price,
        "_fetch_with_twelve_data",
        lambda *_args: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    monkeypatch.setattr(price, "_fetch_with_marketstack", lambda *_args: expected)

    assert price.get_stock_historical_data("AAPL") == expected
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_marketstack_historical_orchestrator_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE https://history-key@marketstack.example.com"
    caplog.set_level("INFO")

    class _FailingTicker:
        def __init__(self, *_args, **_kwargs):
            raise LookupError("safe upstream failure")

    expected = {
        "kline_data": [{"time": "2026-01-01", "close": 100.0}],
        "period": "1y",
        "interval": "1d",
    }
    monkeypatch.setattr(price.yf, "Ticker", _FailingTicker)
    monkeypatch.setattr(price, "ALPHA_VANTAGE_API_KEY", "")
    monkeypatch.setattr(price, "FINNHUB_API_KEY", "")
    monkeypatch.setattr(price, "_fetch_with_yahoo_scrape_historical", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_iex_cloud", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_tiingo", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_twelve_data", lambda *_args: None)
    monkeypatch.setattr(
        price,
        "_fetch_with_marketstack",
        lambda *_args: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    monkeypatch.setattr(price, "_fetch_with_massive_io", lambda *_args: expected)

    assert price.get_stock_historical_data("AAPL") == expected
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_massive_historical_orchestrator_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE https://history-key@massive.example.com"
    caplog.set_level("INFO")

    class _FailingTicker:
        def __init__(self, *_args, **_kwargs):
            raise LookupError("safe upstream failure")

    expected = {
        "kline_data": [{"time": "2026-01-01", "close": 100.0}],
        "period": "1y",
        "interval": "1d",
    }
    monkeypatch.setattr(price.yf, "Ticker", _FailingTicker)
    monkeypatch.setattr(price, "ALPHA_VANTAGE_API_KEY", "")
    monkeypatch.setattr(price, "FINNHUB_API_KEY", "")
    monkeypatch.setattr(price, "_fetch_with_yahoo_scrape_historical", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_iex_cloud", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_tiingo", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_twelve_data", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_marketstack", lambda *_args: None)
    monkeypatch.setattr(
        price,
        "_fetch_with_massive_io",
        lambda *_args: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    monkeypatch.setattr(price, "_fetch_with_stooq_history", lambda *_args: expected)

    assert price.get_stock_historical_data("AAPL") == expected
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_stooq_historical_orchestrator_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE http://proxy-user:secret@proxy.local/stooq-wrapper"
    caplog.set_level("INFO")

    class _FailingTicker:
        def __init__(self, *_args, **_kwargs):
            raise LookupError("safe upstream failure")

    monkeypatch.setattr(price.yf, "Ticker", _FailingTicker)
    monkeypatch.setattr(price.yf, "download", lambda *_args, **_kwargs: SimpleNamespace(empty=True))
    monkeypatch.setattr(price, "ALPHA_VANTAGE_API_KEY", "")
    monkeypatch.setattr(price, "FINNHUB_API_KEY", "")
    monkeypatch.setattr(price, "_fetch_with_yahoo_scrape_historical", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_iex_cloud", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_tiingo", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_twelve_data", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_marketstack", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_massive_io", lambda *_args: None)
    monkeypatch.setattr(
        price,
        "_fetch_with_stooq_history",
        lambda *_args: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    monkeypatch.setattr(price.time, "sleep", lambda _seconds: None)

    result = price.get_stock_historical_data("AAPL")

    assert result["error"].startswith("Failed to fetch historical data for AAPL")
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_final_yfinance_historical_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE http://proxy-user:secret@proxy.local/history-download"
    caplog.set_level("INFO")

    class _FailingTicker:
        def __init__(self, *_args, **_kwargs):
            raise LookupError("safe upstream failure")

    monkeypatch.setattr(price.yf, "Ticker", _FailingTicker)
    monkeypatch.setattr(
        price.yf,
        "download",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    monkeypatch.setattr(price, "ALPHA_VANTAGE_API_KEY", "")
    monkeypatch.setattr(price, "FINNHUB_API_KEY", "")
    monkeypatch.setattr(price, "_fetch_with_yahoo_scrape_historical", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_iex_cloud", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_tiingo", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_twelve_data", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_marketstack", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_massive_io", lambda *_args: None)
    monkeypatch.setattr(price, "_fetch_with_stooq_history", lambda *_args: None)
    monkeypatch.setattr(price.time, "sleep", lambda _seconds: None)

    result = price.get_stock_historical_data("AAPL")

    assert result["error"].startswith("Failed to fetch historical data for AAPL")
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_option_chain_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE http://proxy-user:secret@proxy.local/options"
    caplog.set_level("INFO")
    monkeypatch.setattr(
        price.yf,
        "Ticker",
        lambda _ticker: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    result = price.get_option_chain_metrics("AAPL")

    assert result["error"] == "fetch_failed:RuntimeError"
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_alpha_vantage_price_note_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE account-id=alpha-price-note"
    caplog.set_level("INFO")
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"Note": secret},
    )
    monkeypatch.setattr(price, "_http_get", lambda *_args, **_kwargs: response)

    assert price._fetch_with_alpha_vantage("AAPL") is None
    assert secret not in caplog.text
    assert "Alpha Vantage returned a note" in caplog.text


def test_alpha_vantage_price_error_response_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE account-id=alpha-price-error"
    caplog.set_level("INFO")
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"Error Message": secret},
    )
    monkeypatch.setattr(price, "_http_get", lambda *_args, **_kwargs: response)

    assert price._fetch_with_alpha_vantage("AAPL") is None
    assert secret not in caplog.text
    assert "Alpha Vantage returned an error" in caplog.text


def test_twelve_data_historical_status_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE account-id=twelve-history-status"
    caplog.set_level("INFO")
    response = SimpleNamespace(
        status_code=200,
        json=lambda: {"status": "error", "message": secret},
    )
    monkeypatch.setattr(php, "TWELVE_DATA_API_KEY", "test-key")
    monkeypatch.setattr(php, "_http_get", lambda *_args, **_kwargs: response)

    assert price._fetch_with_twelve_data("AAPL") is None
    assert secret not in caplog.text
    assert "Twelve Data 状态异常" in caplog.text


def test_marketstack_historical_error_response_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE account-id=marketstack-history-error"
    caplog.set_level("INFO")
    response = SimpleNamespace(
        status_code=200,
        json=lambda: {"error": {"message": secret}},
    )
    monkeypatch.setattr(php, "MARKETSTACK_API_KEY", "test-key")
    monkeypatch.setattr(php, "_http_get", lambda *_args, **_kwargs: response)

    assert price._fetch_with_marketstack("AAPL") is None
    assert secret not in caplog.text
    assert "Marketstack 返回错误" in caplog.text


def test_massive_historical_status_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE account-id=massive-history-status"
    caplog.set_level("INFO")
    response = SimpleNamespace(
        status_code=200,
        json=lambda: {"status": secret},
    )
    monkeypatch.setattr(php, "MASSIVE_API_KEY", "test-key")
    monkeypatch.setattr(php, "_http_get", lambda *_args, **_kwargs: response)

    assert price._fetch_with_massive_io("AAPL") is None
    assert secret not in caplog.text
    assert "Massive.com 返回空数据或错误" in caplog.text


def test_massive_historical_error_detail_is_not_logged(monkeypatch, caplog):
    secret = "PRIVATE account-id=massive-history-detail"
    caplog.set_level("INFO")
    response = SimpleNamespace(
        status_code=200,
        json=lambda: {"status": "ERROR", "error": secret},
    )
    monkeypatch.setattr(php, "MASSIVE_API_KEY", "test-key")
    monkeypatch.setattr(php, "_http_get", lambda *_args, **_kwargs: response)

    assert price._fetch_with_massive_io("AAPL") is None
    assert secret not in caplog.text
    assert caplog.text.count("Massive.com 返回空数据或错误") == 1


def test_massive_historical_http_body_is_not_logged(monkeypatch, caplog):
    secret = "PRIVATE bearer=massive-history-body"
    caplog.set_level("INFO")
    response = SimpleNamespace(
        status_code=500,
        text=secret,
        json=lambda: {},
    )
    monkeypatch.setattr(php, "MASSIVE_API_KEY", "test-key")
    monkeypatch.setattr(php, "_http_get", lambda *_args, **_kwargs: response)

    assert price._fetch_with_massive_io("AAPL") is None
    assert secret not in caplog.text
    assert "Massive.com HTTP 错误: 500" in caplog.text


def test_massive_historical_http_json_error_is_not_logged(monkeypatch, caplog):
    secret = "PRIVATE account-id=massive-history-json"
    caplog.set_level("INFO")
    response = SimpleNamespace(
        status_code=403,
        text="",
        json=lambda: {"error": secret},
    )
    monkeypatch.setattr(php, "MASSIVE_API_KEY", "test-key")
    monkeypatch.setattr(php, "_http_get", lambda *_args, **_kwargs: response)

    assert price._fetch_with_massive_io("AAPL") is None
    assert secret not in caplog.text
    assert "Massive.com HTTP 错误: 403" in caplog.text


def test_alpha_vantage_historical_error_response_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE account-id=alpha-history-error"
    caplog.set_level("INFO")

    class _EmptyTicker:
        def __init__(self, *_args, **_kwargs):
            pass

        def history(self, **_kwargs):
            return SimpleNamespace(empty=True)

    response = SimpleNamespace(json=lambda: {"Error Message": secret})
    monkeypatch.setattr(price.yf, "Ticker", _EmptyTicker)
    monkeypatch.setattr(price, "ALPHA_VANTAGE_API_KEY", "test-key")
    monkeypatch.setattr(price, "_http_get", lambda *_args, **_kwargs: response)
    monkeypatch.setattr(price.time, "sleep", lambda _seconds: None)

    assert price.get_stock_historical_data("AAPL") == {"error": "No historical data for AAPL"}
    assert secret not in caplog.text
    assert "Alpha Vantage 返回错误" in caplog.text


def test_alpha_vantage_historical_rate_limit_log_is_redacted(monkeypatch, caplog):
    secret = "API call frequency exceeded PRIVATE account-id=alpha-rate"
    caplog.set_level("INFO")

    class _EmptyTicker:
        def __init__(self, *_args, **_kwargs):
            pass

        def history(self, **_kwargs):
            return SimpleNamespace(empty=True)

    response = SimpleNamespace(json=lambda: {"Note": secret})
    monkeypatch.setattr(price.yf, "Ticker", _EmptyTicker)
    monkeypatch.setattr(price, "ALPHA_VANTAGE_API_KEY", "test-key")
    monkeypatch.setattr(price, "_http_get", lambda *_args, **_kwargs: response)
    monkeypatch.setattr(price.time, "sleep", lambda _seconds: None)

    assert price.get_stock_historical_data("AAPL") == {"error": "No historical data for AAPL"}
    assert secret not in caplog.text
    assert "Alpha Vantage 速率限制" in caplog.text


def test_alpha_vantage_historical_note_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE account-id=alpha-history-note"
    caplog.set_level("INFO")

    class _EmptyTicker:
        def __init__(self, *_args, **_kwargs):
            pass

        def history(self, **_kwargs):
            return SimpleNamespace(empty=True)

    response = SimpleNamespace(json=lambda: {"Note": secret})
    monkeypatch.setattr(price.yf, "Ticker", _EmptyTicker)
    monkeypatch.setattr(price, "ALPHA_VANTAGE_API_KEY", "test-key")
    monkeypatch.setattr(price, "_http_get", lambda *_args, **_kwargs: response)
    monkeypatch.setattr(price.time, "sleep", lambda _seconds: None)

    assert price.get_stock_historical_data("AAPL") == {"error": "No historical data for AAPL"}
    assert secret not in caplog.text
    assert "Alpha Vantage 返回提示" in caplog.text


def test_fallback_price_search_branch_extracts_number(monkeypatch):
    r"""_fallback_price_value 搜索兜底：正则 r"\\d" 双反斜杠会编译成
    “字面反斜杠 + d”，永远匹配不到正常数字文本，整条搜索兜底失效。
    修复后应能从搜索结果中提取指数水平。"""
    monkeypatch.setattr(php, "_map_to_stooq_symbol", lambda _ticker: None)
    monkeypatch.setattr(
        php,
        "search",
        lambda _query: "benchmark index level today: 123,456 points",
    )

    assert php._fallback_price_value("^GSPC") == 123456.0


def test_provider_kline_loops_skip_poison_items(monkeypatch):
    """R112 回归：历史K线 provider 链的单条毒记录不得毁掉该 provider 整批。

    IEX/Tiingo/TwelveData/Marketstack/Massive 的解析循环里，非 dict 条目
    触发 .get AttributeError、date/datetime present-None 触发 None[:10]
    TypeError、Massive 的 item['t'] 裸索引触发 KeyError——全落进函数级
    except 使该 provider 返回 None，已解析的好行连同 provider 一起被弃
    （同 R107-R111 缺陷类）。坏行应被跳过，好行照常返回。"""
    valid_iex = {"date": "2026-09-23", "label": "Sep 23, 26",
                 "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100}
    valid_daily = {"date": "2026-09-23T00:00:00.000Z",
                   "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100}
    valid_twelve = {"datetime": "2026-09-23",
                    "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100}
    valid_massive = {"t": 1789689600000, "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 100}

    cases = [
        # (api_key 名, 函数, 响应 payload, 期望 time)
        ("IEX_CLOUD_API_KEY", php._fetch_with_iex_cloud,
         [valid_iex, "junk", None], "2026-09-23"),
        ("TIINGO_API_KEY", php._fetch_with_tiingo,
         [valid_daily, {"date": None}, None], "2026-09-23"),
        ("TWELVE_DATA_API_KEY", php._fetch_with_twelve_data,
         {"status": "ok", "values": [valid_twelve, "junk", {"datetime": None}]},
         "2026-09-23"),
        ("MARKETSTACK_API_KEY", php._fetch_with_marketstack,
         {"data": [valid_daily, 42, None]}, "2026-09-23"),
        ("MASSIVE_API_KEY", php._fetch_with_massive_io,
         {"status": "OK", "results": [valid_massive, "junk", {"t": None}, {}]},
         "2026-09-18"),
    ]

    for key_name, fn, payload, expected_time in cases:
        monkeypatch.setattr(php, key_name, "test-key")
        response = SimpleNamespace(status_code=200, json=lambda p=payload: p)
        monkeypatch.setattr(php, "_http_get", lambda *a, **k: response)

        result = fn("AAPL")

        assert result is not None, f"{fn.__name__} 被毒记录毁批"
        rows = result["kline_data"]
        assert len(rows) == 1, f"{fn.__name__} 毒行未被跳过: {rows}"
        assert rows[0]["time"] == expected_time
        assert rows[0]["close"] == 1.5


def test_alpha_vantage_historical_skips_poison_daily_rows(monkeypatch):
    """R119：AV Time Series (Daily) 混入非 dict 日行——day_data["1. open"]
    的 TypeError 落进函数级 except，让整段 AV 日线被弃走下游兜底
    （同 R107-R118 缺陷类）。毒行按条跳过，合法日照常解析。"""
    class _EmptyTicker:
        def __init__(self, *_args, **_kwargs):
            pass

        def history(self, **_kwargs):
            return SimpleNamespace(empty=True)

    def _day(open_, close):
        return {"1. open": open_, "2. high": open_, "3. low": open_,
                "4. close": close, "5. volume": "1000"}

    response = SimpleNamespace(json=lambda: {"Time Series (Daily)": {
        "2026-09-24": _day("100", "101"),
        "2026-09-23": "poison-row",
        "2026-09-22": None,
        "2026-09-21": _day("98", "99"),
    }})
    monkeypatch.setattr(price.yf, "Ticker", _EmptyTicker)
    monkeypatch.setattr(price, "ALPHA_VANTAGE_API_KEY", "test-key")
    monkeypatch.setattr(price, "FINNHUB_API_KEY", "")
    monkeypatch.setattr(price, "_http_get", lambda *_args, **_kwargs: response)
    monkeypatch.setattr(price.time, "sleep", lambda _seconds: None)
    for fn_name in (
        "_fetch_with_yahoo_scrape_historical", "_fetch_with_iex_cloud",
        "_fetch_with_tiingo", "_fetch_with_twelve_data",
        "_fetch_with_marketstack", "_fetch_with_massive_io",
        "_fetch_with_stooq_history",
    ):
        monkeypatch.setattr(price, fn_name, lambda *_args: None)

    result = price.get_stock_historical_data("AAPL", period="5d")

    rows = result["kline_data"]
    assert [r["time"] for r in rows] == ["2026-09-21", "2026-09-24"]
    assert rows[-1]["close"] == 101.0
