import sys
from types import SimpleNamespace

from backend.tools import price


class _UnformattableTicker:
    def __init__(self, secret: str) -> None:
        self.secret = secret

    def __format__(self, _format_spec: str) -> str:
        raise RuntimeError(self.secret)


class _UnformattableString(str):
    def __new__(cls, value: str, secret: str):
        instance = super().__new__(cls, value)
        instance.secret = secret
        return instance

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
    monkeypatch.setattr(price, "MASSIVE_API_KEY", "test-key")

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

    monkeypatch.setattr(price, "_http_get", _fail_get)

    assert price._fetch_with_yahoo_scrape_historical("AAPL") is None
    assert secret not in caplog.text
    assert caplog.text.count("RuntimeError") == 2


def test_iex_historical_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE postgres://price:secret@db/iex"
    caplog.set_level("INFO")
    monkeypatch.setattr(price, "IEX_CLOUD_API_KEY", "test-key")

    assert price._fetch_with_iex_cloud(_UnformattableTicker(secret)) is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_tiingo_historical_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE postgres://price:secret@db/tiingo"
    caplog.set_level("INFO")
    monkeypatch.setattr(price, "TIINGO_API_KEY", "test-key")

    assert price._fetch_with_tiingo(_UnformattableTicker(secret)) is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_twelve_data_historical_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE postgres://price:secret@db/twelve"
    caplog.set_level("INFO")
    monkeypatch.setattr(price, "TWELVE_DATA_API_KEY", "test-key")

    assert price._fetch_with_twelve_data(_UnformattableString("AAPL", secret)) is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_marketstack_historical_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE postgres://price:secret@db/marketstack"
    caplog.set_level("INFO")
    monkeypatch.setattr(price, "MARKETSTACK_API_KEY", "test-key")

    assert price._fetch_with_marketstack(_UnformattableString("AAPL", secret)) is None
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_stooq_historical_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE postgres://price:secret@db/stooq"
    caplog.set_level("INFO")

    def _fail_mapping(_ticker):
        raise RuntimeError(secret)

    monkeypatch.setattr(price, "_map_to_stooq_symbol", _fail_mapping)

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
    monkeypatch.setattr(price, "TWELVE_DATA_API_KEY", "test-key")
    monkeypatch.setattr(price, "_http_get", lambda *_args, **_kwargs: response)

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
    monkeypatch.setattr(price, "MARKETSTACK_API_KEY", "test-key")
    monkeypatch.setattr(price, "_http_get", lambda *_args, **_kwargs: response)

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
    monkeypatch.setattr(price, "MASSIVE_API_KEY", "test-key")
    monkeypatch.setattr(price, "_http_get", lambda *_args, **_kwargs: response)

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
    monkeypatch.setattr(price, "MASSIVE_API_KEY", "test-key")
    monkeypatch.setattr(price, "_http_get", lambda *_args, **_kwargs: response)

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
    monkeypatch.setattr(price, "MASSIVE_API_KEY", "test-key")
    monkeypatch.setattr(price, "_http_get", lambda *_args, **_kwargs: response)

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
    monkeypatch.setattr(price, "MASSIVE_API_KEY", "test-key")
    monkeypatch.setattr(price, "_http_get", lambda *_args, **_kwargs: response)

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
