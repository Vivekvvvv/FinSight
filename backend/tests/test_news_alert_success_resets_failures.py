# -*- coding: utf-8 -*-
"""
NewsAlertScheduler 成功路径回归测试：

成功发送新闻提醒后必须调用 record_alert_attempt(success=True)，与
PriceChangeScheduler / RiskAlertScheduler 一致。该调用负责把
alert_failures 清零并清除 last_alert_error；缺失时新闻订阅的失败
计数只增不减，累计达到 ALERT_FAILURE_LIMIT 后订阅被自动 disabled
——即使期间有成功发送，用户也会静默丢订阅。
"""

from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from backend.services import subscription_service as subs
from backend.services.alert_scheduler import NewsAlertScheduler
from backend.services.subscription_service import SubscriptionService


@pytest.fixture
def subscription_service_tmp(tmp_path) -> SubscriptionService:
    """Point subscriptions to a tmp file and reset singleton for isolation."""
    original_path = subs.SUBSCRIPTIONS_FILE
    subs.SUBSCRIPTIONS_FILE = tmp_path / "subscriptions_news_reset.json"
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
            }
        )
        return True, "none", None


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_news_success_resets_alert_failures(subscription_service_tmp):
    """失败计数 2 + 一次成功发送后 alert_failures 必须清零。

    失败路径会累加同一计数器（record_alert_attempt(success=False)），
    成功路径不对称地跳过重置就是 bug。"""
    service = subscription_service_tmp
    email = FakeEmailService()
    service.subscribe(email="user@example.com", ticker="AAPL", alert_types=["news"])

    sub = service.subscriptions["user@example.com"][0]
    sub["alert_failures"] = 2
    sub["last_alert_error"] = "delivery_error"
    with service._lock:
        service._save_subscriptions()

    def fake_news_fetcher(_ticker: str):
        return [
            {
                "title": "AAPL fresh news",
                "url": "u1",
                "source": "s",
                "published_at": _utcnow_naive() - timedelta(minutes=30),
                "related_tickers": ["AAPL"],
            }
        ]

    sent = NewsAlertScheduler(service, email, fake_news_fetcher).run_once()

    assert len(sent) == 1
    assert len(email.sent) == 1
    stored = service.get_subscriptions("user@example.com")[0]
    assert stored["alert_failures"] == 0
    assert stored["last_alert_error"] is None
    assert stored["last_alert_attempt_at"] is not None
    # 成功路径原有副作用不能丢：去重时间戳仍须更新
    assert stored["last_news_at"] is not None
