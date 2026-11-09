import pytest

from backend.services.smart_cache import TradingHoursCache


@pytest.mark.parametrize("market, instant", [("cn", "2026-11-07T02:00:00+00:00"),
                                           ("cn", "2026-10-01T02:00:00+00:00"),
                                           ("hk", "2026-11-07T02:00:00+00:00"),
                                           ("us", "2026-11-07T15:00:00+00:00")])
def test_weekend_and_mainland_holiday_hours_cannot_be_declared_trading(market, instant):
    from datetime import datetime
    assert TradingHoursCache._is_trading_hours(market, datetime.fromisoformat(instant)) is False


@pytest.mark.parametrize("market, instant", [("cn", "2026-11-09T03:30:00+00:00"),
                                           ("cn", "2026-11-09T07:00:00+00:00"),
                                           ("hk", "2026-11-09T04:00:00+00:00"),
                                           ("hk", "2026-11-09T08:00:00+00:00")])
def test_close_boundaries_are_outside_trading_time(market, instant):
    from datetime import datetime
    assert TradingHoursCache._is_trading_hours(market, datetime.fromisoformat(instant)) is False


@pytest.mark.parametrize("ticker", ["600519.SH", "000001.SH", " 600519.sh "])
def test_sh_alias_uses_mainland_trading_hours(ticker):
    assert TradingHoursCache.detect_market(ticker) == "cn"


@pytest.mark.parametrize("ticker, market", [("600519.SS", "cn"), ("000001.SZ", "cn"), ("0700.HK", "hk"), ("AAPL", "us")])
def test_existing_market_suffixes_remain_supported(ticker, market):
    assert TradingHoursCache.detect_market(ticker) == market


@pytest.mark.parametrize("instant,expected_ttl", [
    ("2026-06-01T20:30:00+00:00", 1800),
    ("2026-01-05T13:45:00+00:00", 1800),
    ("2026-06-01T13:30:00+00:00", 30),
    ("2026-01-05T14:30:00+00:00", 30),
    ("2026-06-01T20:00:00+00:00", 1800),
    ("2026-01-05T21:00:00+00:00", 1800),
])
def test_us_cache_hours_follow_new_york_daylight_saving(monkeypatch, instant, expected_ttl):
    from datetime import datetime
    from backend.services import smart_cache

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat(instant)

    monkeypatch.setattr(smart_cache, "datetime", Clock)
    assert TradingHoursCache.get_smart_ttl("us", "quote") == expected_ttl


@pytest.mark.parametrize("market,instant,expected_ttl", [
    ("cn", "2026-11-08T15:00:00+00:00", 37800),
    ("hk", "2026-11-08T15:00:00+00:00", 37800),
    ("us", "2026-11-08T23:00:00+00:00", 55800),
    ("cn", "2026-11-09T01:25:00+00:00", 300),
    ("cn", "2026-11-09T04:55:00+00:00", 300),
    ("hk", "2026-11-09T04:55:00+00:00", 300),
    ("us", "2026-11-09T14:25:00+00:00", 300),
    ("cn", "2026-10-07T15:00:00+00:00", 37800),
])
def test_closed_cache_entries_expire_by_the_next_open(monkeypatch, market, instant, expected_ttl):
    from datetime import datetime
    from backend.services import smart_cache

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat(instant)

    monkeypatch.setattr(smart_cache, "datetime", Clock)
    assert TradingHoursCache.get_smart_ttl(market, "quote") == expected_ttl


@pytest.mark.parametrize("ticker", ["BTC-USD", "ETH-USDT", "ETH-BTC"])
@pytest.mark.parametrize("data_type,ttl", [("quote", 30), ("kline", 300), ("intraday", 60)])
def test_crypto_cache_stays_short_during_stock_market_weekends(monkeypatch, ticker, data_type, ttl):
    from datetime import datetime
    from backend.services import smart_cache

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat("2026-11-07T15:00:00+00:00")

    monkeypatch.setattr(smart_cache, "datetime", Clock)
    assert smart_cache.get_smart_cache_ttl(ticker, data_type) == ttl
