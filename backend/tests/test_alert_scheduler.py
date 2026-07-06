# -*- coding: utf-8 -*-
"""
Alert scheduler tests:
- pct threshold mode
- cooldown guard
- price_target one-shot mode
"""

from typing import List

import pytest

from backend.services import subscription_service as subs
from backend.services.alert_scheduler import PriceChangeScheduler, PriceSnapshot
from backend.services.subscription_service import SubscriptionService


@pytest.fixture
def subscription_service_tmp(tmp_path) -> SubscriptionService:
    """
    Point subscriptions to a tmp file and reset singleton for isolation.
    Restore globals after each test to avoid side effects.
    """
    original_path = subs.SUBSCRIPTIONS_FILE
    subs.SUBSCRIPTIONS_FILE = tmp_path / "subscriptions_scheduler.json"
    subs._subscription_service = None  # type: ignore[attr-defined]
    service = SubscriptionService()
    try:
        yield service
    finally:
        subs._subscription_service = None  # type: ignore[attr-defined]
        subs.SUBSCRIPTIONS_FILE = original_path


class FakeEmailService:
    def __init__(self) -> None:
        self.sent: List[dict] = []

    def send_stock_alert(
        self,
        to_email: str,
        ticker: str,
        alert_type: str,
        message: str,
        current_price=None,
        change_percent=None,
    ) -> tuple[bool, str, str | None]:
        self.sent.append(
            {
                "to_email": to_email,
                "ticker": ticker,
                "alert_type": alert_type,
                "message": message,
                "current_price": current_price,
                "change_percent": change_percent,
            }
        )
        return True, "none", None


def test_price_change_scheduler_triggers_when_threshold_met(subscription_service_tmp):
    service = subscription_service_tmp
    email = FakeEmailService()

    service.subscribe(
        email="user@example.com",
        ticker="AAPL",
        alert_types=["price_change"],
        price_threshold=5.0,
    )

    def fake_price_fetcher(_ticker: str):
        return PriceSnapshot(ticker=_ticker, price=105.0, change_percent=6.2)

    scheduler = PriceChangeScheduler(service, email, fake_price_fetcher)
    sent = scheduler.run_once()

    assert len(sent) == 1
    assert len(email.sent) == 1
    payload = sent[0]
    assert payload["email"] == "user@example.com"
    assert payload["ticker"] == "AAPL"
    assert payload["change_percent"] == 6.2

    # last_alert_at should be updated
    subs_list = service.get_subscriptions("user@example.com")
    assert subs_list[0].get("last_alert_at") is not None


def test_price_change_scheduler_skips_when_below_threshold(subscription_service_tmp):
    service = subscription_service_tmp
    email = FakeEmailService()

    service.subscribe(
        email="user@example.com",
        ticker="MSFT",
        alert_types=["price_change"],
        price_threshold=5.0,
    )

    def fake_price_fetcher(_ticker: str):
        return PriceSnapshot(ticker=_ticker, price=305.0, change_percent=2.0)

    scheduler = PriceChangeScheduler(service, email, fake_price_fetcher)
    sent = scheduler.run_once()

    assert sent == []
    assert email.sent == []

    subs_list = service.get_subscriptions("user@example.com")
    assert subs_list[0].get("last_alert_at") is None


def test_price_change_scheduler_respects_cooldown(subscription_service_tmp, monkeypatch):
    service = subscription_service_tmp
    email = FakeEmailService()
    monkeypatch.setenv("PRICE_ALERT_COOLDOWN_MINUTES", "120")

    service.subscribe(
        email="user@example.com",
        ticker="AAPL",
        alert_types=["price_change"],
        price_threshold=2.0,
        alert_mode="price_change_pct",
    )

    def fake_price_fetcher(_ticker: str):
        return PriceSnapshot(ticker=_ticker, price=110.0, change_percent=3.5)

    scheduler = PriceChangeScheduler(service, email, fake_price_fetcher)
    first = scheduler.run_once()
    second = scheduler.run_once()

    assert len(first) == 1
    assert second == []
    assert len(email.sent) == 1


def test_price_target_scheduler_triggers_once(subscription_service_tmp):
    service = subscription_service_tmp
    email = FakeEmailService()

    service.subscribe(
        email="user@example.com",
        ticker="AAPL",
        alert_types=["price_change"],
        alert_mode="price_target",
        price_target=100.0,
        direction="above",
    )

    def fake_price_fetcher(_ticker: str):
        return PriceSnapshot(ticker=_ticker, price=101.0, change_percent=0.2)

    scheduler = PriceChangeScheduler(service, email, fake_price_fetcher)
    first = scheduler.run_once()
    second = scheduler.run_once()

    assert len(first) == 1
    assert second == []
    assert len(email.sent) == 1
    stored = service.get_subscriptions("user@example.com")[0]
    assert stored.get("price_target_fired") is True


# ── C3 回归：新闻告警时间窗/去重统一 naive-UTC 基准 ──────────────────────────


def _utcnow_naive():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_c3_news_window_and_dedup_use_utc_basis(subscription_service_tmp):
    """三篇文章：晚于 last_news_at 的入选；早于它的去重；超 24h 窗的丢弃。
    last_news_at 与 published_at 均为 naive-UTC——本地时区机器上若任一侧
    仍是本地基准（旧 bug），窗口/去重边界会偏移导致断言失败。"""
    from datetime import timedelta

    from backend.services.alert_scheduler import NewsAlertScheduler

    service = subscription_service_tmp
    email = FakeEmailService()
    service.subscribe(email="user@example.com", ticker="AAPL", alert_types=["news"])

    now = _utcnow_naive()
    service.subscriptions["user@example.com"][0]["last_news_at"] = (now - timedelta(hours=2)).isoformat()

    def fake_news_fetcher(_ticker: str):
        return [
            {"title": "AAPL fresh news", "url": "u1", "source": "s",
             "published_at": now - timedelta(hours=1), "related_tickers": ["AAPL"]},
            {"title": "AAPL already alerted", "url": "u2", "source": "s",
             "published_at": now - timedelta(hours=3), "related_tickers": ["AAPL"]},
            {"title": "AAPL stale news", "url": "u3", "source": "s",
             "published_at": now - timedelta(hours=30), "related_tickers": ["AAPL"]},
        ]

    scheduler = NewsAlertScheduler(service, email, fake_news_fetcher)
    sent = scheduler.run_once()

    assert len(sent) == 1
    assert len(email.sent) == 1
    message = email.sent[0]["message"]
    assert "AAPL fresh news" in message
    assert "already alerted" not in message
    assert "stale news" not in message


def test_c3_last_news_at_written_as_utc(subscription_service_tmp):
    """发送成功后 last_news_at 须写 naive-UTC；本地时区机器上旧代码
    （裸 datetime.now()）写出的值会超前 UTC 数小时导致断言失败。"""
    from datetime import datetime, timedelta

    from backend.services.alert_scheduler import NewsAlertScheduler

    service = subscription_service_tmp
    email = FakeEmailService()
    service.subscribe(email="user@example.com", ticker="AAPL", alert_types=["news"])

    now = _utcnow_naive()

    def fake_news_fetcher(_ticker: str):
        return [{"title": "AAPL breaking", "url": "u", "source": "s",
                 "published_at": now - timedelta(minutes=30), "related_tickers": ["AAPL"]}]

    NewsAlertScheduler(service, email, fake_news_fetcher).run_once()

    stored = service.get_subscriptions("user@example.com")[0]["last_news_at"]
    assert stored is not None
    delta = abs(datetime.fromisoformat(stored) - _utcnow_naive())
    assert delta < timedelta(minutes=5)


def test_c3_aware_published_at_string_normalized(subscription_service_tmp):
    """published_at 为带时区 ISO 串时归一到 naive-UTC，不得抛 TypeError。"""
    from datetime import timedelta, timezone as tz

    from backend.services.alert_scheduler import NewsAlertScheduler

    service = subscription_service_tmp
    email = FakeEmailService()
    service.subscribe(email="user@example.com", ticker="AAPL", alert_types=["news"])

    aware_iso = (_utcnow_naive() - timedelta(hours=1)).replace(tzinfo=tz.utc).isoformat()

    def fake_news_fetcher(_ticker: str):
        return [{"title": "AAPL tz-aware", "url": "u", "source": "s",
                 "published_at": aware_iso, "related_tickers": ["AAPL"]}]

    sent = NewsAlertScheduler(service, email, fake_news_fetcher).run_once()
    assert len(sent) == 1


def test_c3_yfinance_epoch_converted_to_utc(monkeypatch):
    """fetch_news_articles 的 epoch→datetime 须按 UTC 基准转换；
    东八区机器上旧代码（裸 fromtimestamp）会偏 8h 导致断言失败。"""
    import sys
    import time
    import types
    from datetime import timedelta

    from backend.services.alert_scheduler import fetch_news_articles

    epoch = int(time.time()) - 3600  # 1 小时前

    class _FakeTicker:
        def __init__(self, _symbol):
            self.news = [{
                "title": "AAPL epoch news",
                "link": "u",
                "publisher": "s",
                "providerPublishTime": epoch,
                "relatedTickers": ["AAPL"],
            }]

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=_FakeTicker))

    articles = fetch_news_articles("AAPL")
    assert len(articles) == 1
    delta = abs(articles[0]["published_at"] - (_utcnow_naive() - timedelta(hours=1)))
    assert delta < timedelta(minutes=5)
