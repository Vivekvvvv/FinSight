# -*- coding: utf-8 -*-
"""
Alert scheduler tests:
- pct threshold mode
- cooldown guard
- price_target one-shot mode
"""

from types import SimpleNamespace
from typing import List

import pytest

from backend.services import subscription_service as subs
from backend.services import alert_scheduler as alert_scheduler_module
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


class FailingEmailService(FakeEmailService):
    def send_stock_alert(self, *args, **kwargs) -> tuple[bool, str, str | None]:
        super().send_stock_alert(*args, **kwargs)
        return False, "transient", "PRIVATE provider failure"


@pytest.mark.parametrize("value", [None, "", " ", ".AAPL", "BAD TICKER", "A" * 21])
def test_subscription_ticker_rejects_invalid_stored_values(value):
    assert alert_scheduler_module._subscription_ticker({"ticker": value}) is None


def test_subscription_ticker_normalizes_valid_stored_value():
    assert alert_scheduler_module._subscription_ticker({"ticker": " aapl "}) == "AAPL"


@pytest.mark.parametrize("value", ["", "bad", "1.5"])
def test_invalid_cooldown_environment_uses_default(monkeypatch, value):
    monkeypatch.setenv("PRICE_ALERT_COOLDOWN_MINUTES", value)
    assert alert_scheduler_module._positive_env_int("PRICE_ALERT_COOLDOWN_MINUTES", 60) == 60


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


@pytest.mark.parametrize("threshold", ["nan", "inf", "-inf", 0, -1])
def test_price_change_scheduler_rejects_invalid_stored_threshold(
    subscription_service_tmp,
    threshold,
):
    service = subscription_service_tmp
    email = FakeEmailService()
    service.subscribe(
        email="user@example.com",
        ticker="AAPL",
        alert_types=["price_change"],
        price_threshold=5.0,
    )
    service.subscriptions["user@example.com"][0]["price_threshold"] = threshold
    service._save_subscriptions()

    scheduler = PriceChangeScheduler(
        service,
        email,
        lambda ticker: PriceSnapshot(ticker=ticker, price=105.0, change_percent=6.0),
    )

    assert scheduler.run_once() == []
    assert email.sent == []


@pytest.mark.parametrize(
    "snapshot",
    [
        PriceSnapshot(ticker="AAPL", price=float("nan"), change_percent=1.0),
        PriceSnapshot(ticker="AAPL", price=100.0, change_percent=float("inf")),
    ],
)
def test_price_change_scheduler_rejects_non_finite_snapshot(subscription_service_tmp, snapshot):
    service = subscription_service_tmp
    email = FakeEmailService()
    service.subscribe(
        email="user@example.com",
        ticker="AAPL",
        alert_types=["price_change"],
        price_threshold=1.0,
    )
    scheduler = PriceChangeScheduler(service, email, lambda _ticker: snapshot)

    assert scheduler.run_once() == []
    assert email.sent == []


def test_price_scheduler_isolates_fetch_failure_per_subscription(subscription_service_tmp, monkeypatch):
    service = subscription_service_tmp
    email = FakeEmailService()
    messages = []
    monkeypatch.setattr(
        alert_scheduler_module,
        "logger",
        SimpleNamespace(
            warning=lambda message, *args: messages.append(message % args),
            info=lambda *_args, **_kwargs: None,
        ),
    )
    for ticker in ("AAPL", "MSFT"):
        service.subscribe(
            email="user@example.com",
            ticker=ticker,
            alert_types=["price_change"],
            price_threshold=1.0,
        )
    secret = "PRIVATE price provider failure"

    def fetcher(ticker):
        if ticker == "AAPL":
            raise RuntimeError(secret)
        return PriceSnapshot(ticker=ticker, price=105.0, change_percent=5.0)

    sent = PriceChangeScheduler(service, email, fetcher).run_once()

    assert [item["ticker"] for item in sent] == ["MSFT"]
    log_text = "\n".join(messages)
    assert secret not in log_text
    assert "Price fetch failed" in log_text


def test_price_scheduler_isolates_email_exception(subscription_service_tmp, monkeypatch):
    class _RaisingEmailService(FakeEmailService):
        def send_stock_alert(self, *args, **kwargs):
            if kwargs["ticker"] == "AAPL":
                raise RuntimeError("PRIVATE email failure")
            return super().send_stock_alert(*args, **kwargs)

    service = subscription_service_tmp
    email = _RaisingEmailService()
    messages = []
    monkeypatch.setattr(
        alert_scheduler_module,
        "logger",
        SimpleNamespace(
            warning=lambda message, *args: messages.append(message % args),
            info=lambda *_args, **_kwargs: None,
        ),
    )
    for ticker in ("AAPL", "MSFT"):
        service.subscribe(
            email="user@example.com",
            ticker=ticker,
            alert_types=["price_change"],
            price_threshold=1.0,
        )

    sent = PriceChangeScheduler(
        service,
        email,
        lambda ticker: PriceSnapshot(ticker=ticker, price=105.0, change_percent=5.0),
    ).run_once()

    assert [item["ticker"] for item in sent] == ["MSFT"]
    aapl = next(item for item in service.get_subscriptions("user@example.com") if item["ticker"] == "AAPL")
    assert aapl["last_alert_error"] == "delivery_error"
    log_text = "\n".join(messages)
    assert "PRIVATE email failure" not in log_text
    assert "Email send raised" in log_text


def test_alert_failure_log_omits_email_and_error_message(subscription_service_tmp, monkeypatch):
    service = subscription_service_tmp
    private_email = "private-alert-recipient@example.com"
    messages = []
    monkeypatch.setattr(
        alert_scheduler_module,
        "logger",
        SimpleNamespace(
            warning=lambda message, *args: messages.append(message % args),
            info=lambda *_args, **_kwargs: None,
        ),
    )
    service.subscribe(
        email=private_email,
        ticker="AAPL",
        alert_types=["price_change"],
        price_threshold=1.0,
    )
    scheduler = PriceChangeScheduler(
        service,
        FailingEmailService(),
        lambda ticker: PriceSnapshot(ticker=ticker, price=105.0, change_percent=5.0),
    )
    scheduler.run_once()

    log_text = "\n".join(messages)
    assert private_email not in log_text
    assert "PRIVATE provider failure" not in log_text
    assert "AAPL" not in log_text
    assert "Email send failed" in log_text
    assert "transient" not in log_text


def test_alert_failure_normalizes_untrusted_error_fields(subscription_service_tmp, monkeypatch):
    class _UntrustedErrorEmailService(FakeEmailService):
        def send_stock_alert(self, *args, **kwargs):
            super().send_stock_alert(*args, **kwargs)
            return False, "PRIVATE provider category", "PRIVATE provider detail"

    service = subscription_service_tmp
    messages = []
    monkeypatch.setattr(
        alert_scheduler_module,
        "logger",
        SimpleNamespace(
            warning=lambda message, *args: messages.append(message % args),
            info=lambda *_args, **_kwargs: None,
        ),
    )
    service.subscribe(
        email="user@example.com",
        ticker="AAPL",
        alert_types=["price_change"],
        price_threshold=1.0,
    )
    scheduler = PriceChangeScheduler(
        service,
        _UntrustedErrorEmailService(),
        lambda ticker: PriceSnapshot(ticker=ticker, price=105.0, change_percent=5.0),
    )

    scheduler.run_once()

    log_text = "\n".join(messages)
    stored = service.get_subscriptions("user@example.com")[0]
    assert "PRIVATE" not in log_text
    assert "AAPL" not in log_text
    assert "Email send failed" in log_text
    assert "unknown" not in log_text
    assert stored["last_alert_error"] == "delivery_error"


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
    with service._lock:
        service._save_subscriptions()

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


def test_news_scheduler_ignores_invalid_stored_last_news_at(subscription_service_tmp):
    from datetime import timedelta
    from backend.services.alert_scheduler import NewsAlertScheduler

    service = subscription_service_tmp
    email = FakeEmailService()
    service.subscribe(email="user@example.com", ticker="AAPL", alert_types=["news"])
    service.subscriptions["user@example.com"][0]["last_news_at"] = "not-a-date"
    service._save_subscriptions()

    sent = NewsAlertScheduler(
        service,
        email,
        lambda _ticker: [{
            "title": "AAPL fresh news",
            "url": "u",
            "source": "s",
            "published_at": _utcnow_naive() - timedelta(minutes=30),
            "related_tickers": ["AAPL"],
        }],
    ).run_once()

    assert len(sent) == 1
    assert len(email.sent) == 1


def test_news_scheduler_filters_malformed_and_bounds_article_fields(subscription_service_tmp):
    from datetime import timedelta
    from backend.services.alert_scheduler import NewsAlertScheduler

    service = subscription_service_tmp
    email = FakeEmailService()
    service.subscribe(email="user@example.com", ticker="AAPL", alert_types=["news"])
    now = _utcnow_naive()
    long_title = "AAPL " + "t" * 1000

    sent = NewsAlertScheduler(
        service,
        email,
        lambda _ticker: [
            None,
            "bad",
            {"title": 123, "published_at": now},
            {"title": "AAPL bad date", "published_at": 123},
            {
                "title": long_title,
                "source": "s" * 1000,
                "url": "u" * 5000,
                "published_at": now - timedelta(minutes=30),
                "related_tickers": "AAPL",
            },
        ],
    ).run_once()

    assert len(sent) == 1
    message = email.sent[0]["message"]
    assert long_title not in message
    assert "t" * 507 in message
    assert "s" * 129 not in message
    assert "u" * 2049 not in message


def test_news_scheduler_isolates_fetch_failure_per_subscription(subscription_service_tmp, monkeypatch):
    from datetime import timedelta
    from backend.services.alert_scheduler import NewsAlertScheduler

    messages = []
    monkeypatch.setattr(
        alert_scheduler_module,
        "logger",
        SimpleNamespace(
            warning=lambda message, *args: messages.append(message % args),
            info=lambda *_args, **_kwargs: None,
        ),
    )
    service = subscription_service_tmp
    email = FakeEmailService()
    service.subscribe(email="first@example.com", ticker="AAPL", alert_types=["news"])
    service.subscribe(email="second@example.com", ticker="MSFT", alert_types=["news"])
    secret = "PRIVATE provider failure"

    def fetcher(ticker):
        if ticker == "AAPL":
            raise RuntimeError(secret)
        return [{
            "title": "MSFT fresh news",
            "published_at": _utcnow_naive() - timedelta(minutes=30),
            "related_tickers": ["MSFT"],
        }]

    sent = NewsAlertScheduler(service, email, fetcher).run_once()

    assert [item["ticker"] for item in sent] == ["MSFT"]
    log_text = "\n".join(messages)
    assert secret not in log_text
    assert "News fetch failed" in log_text


def test_news_scheduler_isolates_email_exception(subscription_service_tmp, monkeypatch):
    from datetime import timedelta
    from backend.services.alert_scheduler import NewsAlertScheduler

    class _RaisingEmailService(FakeEmailService):
        def send_stock_alert(self, *args, **kwargs):
            if kwargs["ticker"] == "AAPL":
                raise RuntimeError("PRIVATE news email failure")
            return super().send_stock_alert(*args, **kwargs)

    service = subscription_service_tmp
    email = _RaisingEmailService()
    messages = []
    monkeypatch.setattr(
        alert_scheduler_module,
        "logger",
        SimpleNamespace(
            warning=lambda message, *args: messages.append(message % args),
            info=lambda *_args, **_kwargs: None,
        ),
    )
    for ticker in ("AAPL", "MSFT"):
        service.subscribe(email="user@example.com", ticker=ticker, alert_types=["news"])

    def fetcher(ticker):
        return [{
            "title": f"{ticker} fresh news",
            "published_at": _utcnow_naive() - timedelta(minutes=30),
            "related_tickers": [ticker],
        }]

    sent = NewsAlertScheduler(service, email, fetcher).run_once()

    assert [item["ticker"] for item in sent] == ["MSFT"]
    aapl = next(item for item in service.get_subscriptions("user@example.com") if item["ticker"] == "AAPL")
    assert aapl["last_alert_error"] == "delivery_error"
    log_text = "\n".join(messages)
    assert "PRIVATE news email failure" not in log_text
    assert "News email send raised" in log_text


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


def test_stooq_snapshot_change_uses_previous_close_not_open(monkeypatch):
    """R31 回归：告警快照的 change_percent 必须相对真昨收。旧代码用当日开盘
    近似，隔夜跳空 +6% 盘中平走会被算成 ~0% 而漏报。"""
    import requests as requests_module
    from datetime import datetime, timezone

    from backend.services.alert_scheduler import _fetch_with_stooq

    today = datetime.now(timezone.utc).date().isoformat()

    class _SnapResp:
        status_code = 200

        def json(self):
            return {"symbols": [{"close": "105.0", "open": "104.9"}]}

    class _HistResp:
        status_code = 200
        text = (
            "Date,Open,High,Low,Close,Volume\n"
            "2026-07-03,99,101,98,100.0,1000\n"
            f"{today},104.9,106,104,105.0,900\n"  # 当日行须被排除
        )

    def _fake_get(url, *args, **kwargs):
        return _HistResp() if "/q/d/l/" in url else _SnapResp()

    monkeypatch.setattr(requests_module, "get", _fake_get)

    snap = _fetch_with_stooq("AAPL")
    assert snap is not None
    assert snap.price == 105.0
    # 相对昨收 100 → +5%；旧代码相对开盘 104.9 → ~+0.1%
    assert abs(snap.change_percent - 5.0) < 0.01


def test_stooq_snapshot_change_none_when_history_unavailable(monkeypatch):
    import requests as requests_module

    from backend.services.alert_scheduler import _fetch_with_stooq

    class _SnapResp:
        status_code = 200

        def json(self):
            return {"symbols": [{"close": "105.0", "open": "104.9"}]}

    class _FailResp:
        status_code = 500
        text = ""

    def _fake_get(url, *args, **kwargs):
        return _FailResp() if "/q/d/l/" in url else _SnapResp()

    monkeypatch.setattr(requests_module, "get", _fake_get)

    snap = _fetch_with_stooq("AAPL")
    assert snap is not None
    assert snap.price == 105.0
    assert snap.change_percent is None  # 宁缺毋错：调度器会跳过本轮


def test_parse_pub_datetime_accepts_epoch_and_iso():
    from datetime import datetime

    from backend.services.alert_scheduler import _parse_pub_datetime

    # epoch 秒 → naive-UTC
    assert _parse_pub_datetime(0) == datetime(1970, 1, 1)
    assert _parse_pub_datetime("86400") == datetime(1970, 1, 2)
    # ISO 串（新版 yfinance content.pubDate）→ naive-UTC
    assert _parse_pub_datetime("2026-07-06T12:00:00Z") == datetime(2026, 7, 6, 12, 0)
    assert _parse_pub_datetime("2026-07-06T20:00:00+08:00") == datetime(2026, 7, 6, 12, 0)
    # 垃圾输入 → None
    assert _parse_pub_datetime(None) is None
    assert _parse_pub_datetime("not-a-date") is None


def test_fetch_news_parses_new_yfinance_content_structure(monkeypatch):
    """yfinance >=0.2.5x 的 news 为 ncp 流结构（字段嵌在 content 下），
    旧解析拿到全空值逐条丢弃 → 主路径静默失效。"""
    import sys
    import types
    from datetime import timedelta

    from backend.services.alert_scheduler import fetch_news_articles

    pub_iso = (_utcnow_naive() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    class _FakeTicker:
        def __init__(self, _symbol):
            self.news = [{
                "id": "n1",
                "content": {
                    "title": "AAPL ncp-style news",
                    "pubDate": pub_iso,
                    "canonicalUrl": {"url": "https://finance.example/apple"},
                    "provider": {"displayName": "Reuters"},
                },
            }]

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=_FakeTicker))

    articles = fetch_news_articles("AAPL")
    assert len(articles) == 1
    art = articles[0]
    assert art["title"] == "AAPL ncp-style news"
    assert art["url"] == "https://finance.example/apple"
    assert art["source"] == "Reuters"
    delta = abs(art["published_at"] - (_utcnow_naive() - timedelta(hours=1)))
    assert delta < timedelta(minutes=5)


def test_fetch_news_skips_malformed_items_and_bounds_fields(monkeypatch):
    import sys
    import types
    from datetime import timedelta

    from backend.services.alert_scheduler import fetch_news_articles

    pub_iso = (_utcnow_naive() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    class _FakeTicker:
        def __init__(self, _symbol):
            self.news = [
                None,
                "bad",
                {"content": {"canonicalUrl": "bad", "provider": "bad"}},
                {
                    "title": "AAPL " + "t" * 1000,
                    "link": "u" * 5000,
                    "publisher": "s" * 1000,
                    "pubDate": pub_iso,
                    "relatedTickers": ["AAPL"] * 100,
                },
            ]

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=_FakeTicker))

    articles = fetch_news_articles("AAPL")

    assert len(articles) == 1
    assert len(articles[0]["title"]) == 512
    assert len(articles[0]["url"]) == 2048
    assert len(articles[0]["source"]) == 128
    assert len(articles[0]["related_tickers"]) == 50
