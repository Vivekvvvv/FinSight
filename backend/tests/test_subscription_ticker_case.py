# -*- coding: utf-8 -*-
"""订阅 ticker 大小写分裂回归：

schema 不规范化 ticker；subscribe/unsubscribe/toggle/update_* 用
``sub['ticker'] == ticker`` 精确匹配，而 set_price_target_fired /
record_alert_event / alert_scheduler 已双侧 normalize。小写订阅落盘后：
- 大写 unsubscribe/toggle 找不到 → 幽灵订阅继续发信
- 调度器把 sub 复制成 normalized ticker 后 record_alert_attempt("AAPL")
  精确匹配不上存量 "aapl" → last_alert_at 永不写入 → cooldown 失效
  每轮重复发信；alert_failures 永不增长 → disabled 永不生效
- 大小写各订阅一次 → 同一标的重复告警 + 配额双计
"""

import pytest

from backend.services import subscription_service as subs
from backend.services.subscription_service import SubscriptionService


@pytest.fixture
def service(tmp_path) -> SubscriptionService:
    original_path = subs.SUBSCRIPTIONS_FILE
    subs.SUBSCRIPTIONS_FILE = tmp_path / "subscriptions.json"
    subs._subscription_service = None  # type: ignore[attr-defined]
    svc = SubscriptionService()
    try:
        yield svc
    finally:
        subs._subscription_service = None  # type: ignore[attr-defined]
        subs.SUBSCRIPTIONS_FILE = original_path


def test_subscribe_same_ticker_different_case_updates_not_duplicates(service):
    assert service.subscribe("a@b.co", "aapl") is True
    assert service.subscribe("a@b.co", "AAPL") is True

    entries = service.get_subscriptions("a@b.co")
    assert len(entries) == 1


def test_subscribe_normalizes_stored_ticker(service):
    service.subscribe("a@b.co", " aapl ")

    entry = service.get_subscriptions("a@b.co")[0]
    assert entry["ticker"] == "AAPL"


def test_unsubscribe_uppercase_removes_lowercase_entry(service):
    service.subscribe("a@b.co", "aapl")

    assert service.unsubscribe("a@b.co", "AAPL") is True
    assert service.get_subscriptions("a@b.co") == []


def test_toggle_uppercase_disables_lowercase_entry(service):
    service.subscribe("a@b.co", "aapl")

    assert service.toggle_subscription("a@b.co", "AAPL", enabled=False) is True
    assert service.get_subscriptions("a@b.co")[0]["disabled"] is True


def test_update_paths_match_lowercase_entry(service):
    """调度器 normalized-copy 路径会以 "AAPL" 回写；小写存量必须命中，
    否则 last_alert_at 永不更新 → cooldown 失效每轮重发、
    alert_failures 永不增长 → disabled 永不生效。"""
    service.subscribe("a@b.co", "aapl")

    service.update_last_alert("a@b.co", "AAPL")
    service.update_last_news("a@b.co", "AAPL")
    service.update_last_risk("a@b.co", "AAPL")
    service.record_alert_attempt("a@b.co", "AAPL", success=True)

    entry = service.get_subscriptions("a@b.co")[0]
    assert entry["last_alert_at"] is not None
    assert entry["last_news_at"] is not None
    assert entry["last_risk_at"] is not None
    assert entry["last_alert_attempt_at"] is not None


def test_get_subscribers_for_ticker_finds_lowercase_entry(service):
    service.subscribe("a@b.co", "aapl")

    subscribers = service.get_subscribers_for_ticker("AAPL")
    assert len(subscribers) == 1
