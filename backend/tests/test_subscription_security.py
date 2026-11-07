from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient


def _set_prod_env(monkeypatch, *, role: str = "user") -> None:
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_BASE", "https://llm.test/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "test-model")
    monkeypatch.setenv("POSTGRES_DB", "test")
    monkeypatch.setenv("POSTGRES_USER", "test")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test")
    monkeypatch.setenv("JWT_SECRET", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("API_AUTH_KEYS", "release-key-1")
    monkeypatch.setenv(
        "API_AUTH_PRINCIPALS",
        '{"release-key-1":{"user_id":"alice","email":"alice@example.invalid","role":"' + role + '"}}',
    )


def test_subscription_list_without_email_uses_principal_email(monkeypatch, tmp_path):
    from backend.api import main
    from backend.services import subscription_service as subs

    _set_prod_env(monkeypatch)
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", tmp_path / "subscriptions.json")
    subs._subscription_service = None  # type: ignore[attr-defined]
    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))

    with TestClient(main.app) as client:
        response = client.get("/api/subscriptions", headers={"x-api-key": "release-key-1"})

    assert response.status_code == 200
    assert response.json()["subscriptions"] == []


def test_admin_subscription_list_requires_admin(monkeypatch, tmp_path):
    from backend.api import main
    from backend.services import subscription_service as subs

    _set_prod_env(monkeypatch, role="user")
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", tmp_path / "subscriptions.json")
    subs._subscription_service = None  # type: ignore[attr-defined]
    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))

    with TestClient(main.app) as client:
        response = client.get("/api/admin/subscriptions", headers={"x-api-key": "release-key-1"})

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("POST", "/api/subscribe", {"email": "alice@example.invalid", "ticker": "AAPL"}),
        ("POST", "/api/unsubscribe", {"email": "alice@example.invalid", "ticker": "AAPL"}),
        ("GET", "/api/subscriptions", None),
        (
            "POST",
            "/api/subscription/toggle",
            {"email": "alice@example.invalid", "ticker": "AAPL", "enabled": True},
        ),
        ("GET", "/api/admin/subscriptions", None),
    ],
)
def test_subscription_internal_errors_are_redacted(monkeypatch, method, path, payload, caplog, capsys):
    from backend.api import main
    from backend.services import subscription_service as subs

    class FailingSubscriptionService:
        @staticmethod
        def is_valid_email(_email):
            return True

        @staticmethod
        def is_valid_ticker(_ticker):
            return True

        @staticmethod
        def fail(*_args, **_kwargs):
            raise RuntimeError("private subscription storage detail")

        subscribe = fail
        unsubscribe = fail
        get_subscriptions = fail
        toggle_subscription = fail

    _set_prod_env(monkeypatch, role="admin")
    monkeypatch.setattr(subs, "get_subscription_service", lambda: FailingSubscriptionService())
    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))
    caplog.set_level(logging.ERROR, logger="backend.api.subscription_router")

    with TestClient(main.app) as client:
        response = client.request(
            method,
            path,
            headers={"x-api-key": "release-key-1"},
            json=payload,
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert "private subscription storage detail" not in response.text
    assert "private subscription storage detail" not in capsys.readouterr().err
    assert "private subscription storage detail" not in caplog.text
    assert "[subscription/" in caplog.text


@pytest.mark.parametrize(
    ("payload", "error_type"),
    [
        ("{invalid json", "JSONDecodeError"),
        ('["not-an-object"]', "ValueError"),
        ('{"alice@example.invalid": "not-a-list"}', "ValueError"),
        ('{"alice@example.invalid": ["not-an-object"]}', "ValueError"),
        ('{"alice@example.invalid": [{"price_target": NaN}]}', "ValueError"),
    ],
)
def test_subscription_service_backs_up_corrupt_storage(
    monkeypatch, tmp_path, caplog, payload, error_type
):
    from backend.services import subscription_service as subs

    storage_path = tmp_path / "subscriptions.json"
    storage_path.write_text(payload, encoding="utf-8")
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", storage_path)

    with caplog.at_level(logging.WARNING, logger="backend.services.subscription_service"):
        service = subs.SubscriptionService()

    backups = list(tmp_path.glob("*.corrupt"))
    assert service.subscriptions == {}
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == payload
    assert not storage_path.exists()
    assert error_type in caplog.text
    assert payload not in caplog.text


def test_subscription_service_does_not_report_success_when_save_fails(
    monkeypatch, tmp_path, caplog
):
    from backend.services import subscription_service as subs

    storage_path = tmp_path / "subscriptions.json"
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", storage_path)
    service = subs.SubscriptionService()

    def fail_replace(_source, _target):
        raise OSError("private subscription write detail")

    monkeypatch.setattr(subs.os, "replace", fail_replace)
    with caplog.at_level(logging.ERROR, logger="backend.services.subscription_service"):
        with pytest.raises(OSError, match="private subscription write detail"):
            service.subscribe("alice@example.invalid", "AAPL")

    assert not storage_path.exists()
    assert "private subscription write detail" not in caplog.text
    assert "OSError" in caplog.text


@pytest.mark.parametrize("field", ["price_threshold", "price_target"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_subscription_service_rejects_non_finite_numeric_values(
    monkeypatch, tmp_path, field, value
):
    from backend.services import subscription_service as subs

    storage_path = tmp_path / "subscriptions.json"
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", storage_path)
    service = subs.SubscriptionService()

    with pytest.raises(ValueError, match=f"{field} must be finite"):
        service.subscribe("alice@example.invalid", "AAPL", **{field: value})

    assert service.get_subscriptions("alice@example.invalid") == []
    assert not storage_path.exists()


@pytest.mark.parametrize("field", ["price_threshold", "price_target"])
@pytest.mark.parametrize("value", [True, False])
def test_subscription_service_rejects_boolean_numeric_values(
    monkeypatch, tmp_path, field, value
):
    from backend.services import subscription_service as subs

    storage_path = tmp_path / "subscriptions.json"
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", storage_path)
    service = subs.SubscriptionService()

    with pytest.raises(ValueError, match=f"{field} must be finite"):
        service.subscribe("alice@example.invalid", "AAPL", **{field: value})

    assert service.get_subscriptions("alice@example.invalid") == []
    assert not storage_path.exists()


@pytest.mark.parametrize("field", ["price_threshold", "price_target"])
@pytest.mark.parametrize("value", [0, -1, "0", "-1"])
@pytest.mark.parametrize("existing_subscription", [False, True])
def test_subscription_service_rejects_non_positive_prices_without_using_quota(
    monkeypatch, tmp_path, field, value, existing_subscription,
):
    from backend.services import subscription_service as subs

    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", tmp_path / "subscriptions.json")
    service = subs.SubscriptionService()
    email = "alice@example.invalid"
    assert service.subscribe(email, "AAPL", alert_types=["news"], max_subscriptions=2)
    before = service.subscriptions_file.read_bytes()
    ticker = "AAPL" if existing_subscription else "MSFT"

    with pytest.raises(ValueError, match=f"{field} must be positive"):
        service.subscribe(email, ticker, max_subscriptions=2, **{field: value})

    assert service.subscriptions_file.read_bytes() == before
    assert service.subscribe(email, "NVDA", price_threshold=3.0, max_subscriptions=2)
    assert len(service.get_subscriptions(email)) == 2


@pytest.mark.parametrize("settings", [
    {}, {"price_target": 220.0}, {"direction": "above"},
    {"price_target": 220.0, "direction": "sideways"},
])
@pytest.mark.parametrize("existing_subscription", [False, True])
def test_incomplete_price_target_cannot_overwrite_subscription_or_claim_quota(
    monkeypatch, tmp_path, settings, existing_subscription,
):
    from backend.services import subscription_service as subs

    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", tmp_path / "subscriptions.json")
    service = subs.SubscriptionService()
    email = "alice@example.invalid"
    assert service.subscribe(email, "AAPL", alert_types=["news"], max_subscriptions=2)
    before = service.subscriptions_file.read_bytes()
    ticker = "AAPL" if existing_subscription else "MSFT"

    with pytest.raises(ValueError, match="price_target alerts require price_target and direction"):
        service.subscribe(email, ticker, alert_types=["price_change"], alert_mode="price_target", **settings)

    assert service.subscriptions_file.read_bytes() == before
    assert service.subscribe(email, "NVDA", price_threshold=3.0, max_subscriptions=2)
    assert len(service.get_subscriptions(email)) == 2


def test_non_price_subscription_does_not_require_target_settings(monkeypatch, tmp_path):
    from backend.services import subscription_service as subs

    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", tmp_path / "subscriptions.json")
    service = subs.SubscriptionService()

    assert service.subscribe("alice@example.invalid", "AAPL", alert_types=["news"], alert_mode="price_target")
    assert service.get_subscriptions("alice@example.invalid")[0]["price_target"] is None


@pytest.mark.parametrize("alert_types", [[], ["unknown"], ["news", "unknown"], "news", {}, True, [["news"]]])
@pytest.mark.parametrize("existing_subscription", [False, True])
def test_invalid_alert_types_cannot_overwrite_subscription_or_claim_quota(
    monkeypatch, tmp_path, alert_types, existing_subscription,
):
    from backend.services import subscription_service as subs

    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", tmp_path / "subscriptions.json")
    service = subs.SubscriptionService()
    email = "alice@example.invalid"
    assert service.subscribe(email, "AAPL", alert_types=["news", "risk"], max_subscriptions=2)
    before = service.subscriptions_file.read_bytes()
    ticker = "AAPL" if existing_subscription else "MSFT"

    with pytest.raises(ValueError, match="alert_types must contain supported alert types"):
        service.subscribe(email, ticker, alert_types=alert_types, max_subscriptions=2)

    assert service.subscriptions_file.read_bytes() == before
    assert service.subscribe(email, "NVDA", price_threshold=3.0, max_subscriptions=2)
    assert len(service.get_subscriptions(email)) == 2


@pytest.mark.parametrize("email", ["alice@example.invalid\n", "alice@example.invalid\r\n"])
def test_malformed_email_cannot_create_subscription_or_claim_quota(monkeypatch, tmp_path, email):
    from backend.api import main
    from backend.services import subscription_service as subs

    monkeypatch.setenv("DEV_MODE", "1")
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", tmp_path / "subscriptions.json")
    service = subs.SubscriptionService()
    monkeypatch.setattr(subs, "get_subscription_service", lambda: service)
    assert service.subscribe("alice@example.invalid", "AAPL")
    before = service.subscriptions_file.read_bytes()

    assert service.is_valid_email(email) is False
    assert service.subscribe(email, "MSFT", max_subscriptions=1) is False
    with TestClient(main.app) as client:
        response = client.post("/api/subscribe", json={"email": email, "ticker": "MSFT"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid email"
    assert service.subscriptions_file.read_bytes() == before


def test_subscription_storage_key_controls_delivery_email(monkeypatch, tmp_path):
    from backend.services import subscription_service as subs

    storage_path = tmp_path / "subscriptions.json"
    storage_path.write_text(
        json.dumps(
            {
                "alice@example.invalid": [
                    {
                        "email": "bob@example.invalid",
                        "ticker": "AAPL",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", storage_path)

    service = subs.SubscriptionService()

    loaded = service.get_subscriptions("alice@example.invalid")
    assert loaded[0]["email"] == "alice@example.invalid"
    persisted = json.loads(storage_path.read_text(encoding="utf-8"))
    assert persisted["alice@example.invalid"][0]["email"] == "alice@example.invalid"


def test_record_alert_attempt_recovers_invalid_failure_counter(monkeypatch, tmp_path):
    from backend.services import subscription_service as subs

    storage_path = tmp_path / "subscriptions.json"
    email = "alice@example.invalid"
    storage_path.write_text(
        json.dumps({email: [{"ticker": "AAPL", "alert_failures": "bad"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", storage_path)
    service = subs.SubscriptionService()

    service.record_alert_attempt(email, "AAPL", success=False, error="delivery failed")

    saved = json.loads(storage_path.read_text(encoding="utf-8"))
    assert saved[email][0]["alert_failures"] == 1


def test_successful_delivery_cannot_reenable_subscription_disabled_during_send(monkeypatch, tmp_path):
    from backend.services import subscription_service as subs

    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", tmp_path / "subscriptions.json")
    service = subs.SubscriptionService()
    email = "alice@example.invalid"
    assert service.subscribe(email, "AAPL")
    stale_service = subs.SubscriptionService()
    service.record_alert_attempt(email, "AAPL", success=False, error="delivery failed")
    assert service.toggle_subscription(email, "AAPL", enabled=False)

    stale_service.record_alert_attempt(email, "AAPL", success=True)

    saved = service.get_subscriptions(email)[0]
    assert saved["disabled"] is True
    assert saved["alert_failures"] == 0
    assert saved["last_alert_error"] is None
    assert saved["last_alert_at"] is not None


def test_unsubscribe_missing_ticker_does_not_report_success_or_rewrite_storage(monkeypatch, tmp_path):
    from backend.services import subscription_service as subs

    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", tmp_path / "subscriptions.json")
    service = subs.SubscriptionService()
    email = "alice@example.invalid"
    assert service.subscribe(email, "AAPL")
    before = service.subscriptions_file.read_bytes()

    assert service.unsubscribe(email, "TSLA") is False
    assert service.subscriptions_file.read_bytes() == before
    assert [item["ticker"] for item in service.get_subscriptions(email)] == ["AAPL"]


@pytest.mark.parametrize("ticker", [None, "", "   ", "BAD TICKER", ".AAPL", "A" * 21])
def test_invalid_subscription_ticker_cannot_claim_remaining_slot(monkeypatch, tmp_path, ticker):
    from backend.services import subscription_service as subs

    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", tmp_path / "subscriptions.json")
    service = subs.SubscriptionService()
    email = "alice@example.invalid"
    assert service.subscribe(email, "AAPL", max_subscriptions=2)
    before = service.subscriptions_file.read_bytes()

    assert service.subscribe(email, ticker, max_subscriptions=2) is False
    assert service.subscriptions_file.read_bytes() == before
    assert service.subscribe(email, "MSFT", max_subscriptions=2)


@pytest.mark.parametrize("ticker", [" aapl ", "000001.SZ", "BRK.B", "BTC-USD", "^GSPC", "EURUSD=X", "A" * 20])
def test_subscription_ticker_validation_keeps_scheduler_supported_symbols(monkeypatch, tmp_path, ticker):
    from backend.services import subscription_service as subs
    from backend.services.alert_scheduler import _subscription_ticker

    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", tmp_path / "subscriptions.json")
    service = subs.SubscriptionService()
    assert service.subscribe("alice@example.invalid", ticker)
    saved = service.get_subscriptions("alice@example.invalid")[0]
    assert _subscription_ticker(saved) == ticker.strip().upper()


def test_record_alert_event_bounds_persisted_content(monkeypatch, tmp_path):
    from backend.services import subscription_service as subs

    storage_path = tmp_path / "subscriptions.json"
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", storage_path)
    service = subs.SubscriptionService()
    assert service.subscribe("alice@example.invalid", "AAPL") is True

    assert service.record_alert_event(
        "alice@example.invalid",
        "AAPL",
        "news",
        title="t" * 1000,
        message="m" * 10_000,
        metadata={"blob": "x" * (16 * 1024)},
    ) is True

    event = service.list_alert_events("alice@example.invalid")[0]
    assert len(event["title"]) == 512
    assert len(event["message"]) == 4096
    # 超限 metadata 被丢弃，但必须留下降级标记而不是伪装成"没有 metadata"。
    assert event["metadata"] == {"_metadata_unavailable": "oversized"}


def test_legacy_alert_events_are_bounded_when_loaded(monkeypatch, tmp_path):
    from datetime import datetime, timezone
    from backend.services import subscription_service as subs

    storage_path = tmp_path / "subscriptions.json"
    email = "alice@example.invalid"
    event = {
        "id": "i" * 100,
        "email": "e" * 500,
        "ticker": "a" * 50,
        "event_type": "n" * 100,
        "severity": "s" * 100,
        "title": "t" * 1000,
        "message": "m" * 10_000,
        "triggered_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {"blob": "x" * (16 * 1024)},
        "unexpected": "x" * 10_000,
    }
    storage_path.write_text(
        json.dumps({email: [{"ticker": "AAPL", "recent_events": [event]}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", storage_path)

    loaded = subs.SubscriptionService().list_alert_events(email)[0]

    assert len(loaded["id"]) == 64
    assert len(loaded["email"]) == 320
    assert len(loaded["ticker"]) == 20
    assert len(loaded["event_type"]) == 64
    assert len(loaded["severity"]) == 32
    assert len(loaded["title"]) == 512
    assert len(loaded["message"]) == 4096
    # 16 KiB blob 序列化后（含 {"blob": ...} 的外壳）必然越过上限，被丢弃并留标记。
    assert loaded["metadata"] == {"_metadata_unavailable": "oversized"}
    assert "unexpected" not in loaded


@pytest.mark.parametrize("same_subscription", [False, True])
def test_alert_retention_and_feed_use_time_instead_of_iso_text(monkeypatch, tmp_path, same_subscription):
    from datetime import datetime, timedelta, timezone
    from backend.services import subscription_service as subs

    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", tmp_path / "subscriptions.json")
    monkeypatch.setattr(subs, "ALERT_EVENTS_PER_SUB", 1)
    service = subs.SubscriptionService()
    email = "alice@example.invalid"
    assert service.subscribe(email, "AAPL")
    other_ticker = "AAPL" if same_subscription else "MSFT"
    if not same_subscription:
        assert service.subscribe(email, other_ticker)
    now = datetime.now(timezone.utc)
    older = (now - timedelta(hours=2)).astimezone(timezone(timedelta(hours=8)))
    newer = now - timedelta(hours=1)
    assert service.record_alert_event(email, "AAPL", "news", title="older", triggered_at=older.isoformat())
    assert service.record_alert_event(email, other_ticker, "news", title="newer", triggered_at=newer.isoformat())

    latest = service.list_alert_events(email, limit=1)

    assert [event["title"] for event in latest] == ["newer"]
    assert latest[0]["triggered_at"] == newer.isoformat()
    if same_subscription:
        assert service.get_subscriptions(email)[0]["recent_events"][0]["title"] == "newer"


def test_subscription_instances_do_not_overwrite_new_subscribers(monkeypatch, tmp_path):
    from backend.services import subscription_service as subs

    storage_path = tmp_path / "subscriptions.json"
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", storage_path)
    first = subs.SubscriptionService()
    second = subs.SubscriptionService()

    assert first.subscribe("alice@example.invalid", "AAPL") is True
    assert second.subscribe("bob@example.invalid", "MSFT") is True

    reloaded = subs.SubscriptionService()
    assert len(reloaded.get_subscriptions("alice@example.invalid")) == 1
    assert len(reloaded.get_subscriptions("bob@example.invalid")) == 1


def test_stale_subscription_instance_does_not_erase_newer_data(monkeypatch, tmp_path):
    from backend.services import subscription_service as subs

    storage_path = tmp_path / "subscriptions.json"
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", storage_path)
    first = subs.SubscriptionService()
    assert first.subscribe("alice@example.invalid", "AAPL") is True
    stale = subs.SubscriptionService()
    assert first.subscribe("bob@example.invalid", "MSFT") is True

    assert stale.unsubscribe("alice@example.invalid", "AAPL") is True

    reloaded = subs.SubscriptionService()
    assert reloaded.get_subscriptions("alice@example.invalid") == []
    assert len(reloaded.get_subscriptions("bob@example.invalid")) == 1


def test_stale_toggle_does_not_erase_newer_subscriptions(monkeypatch, tmp_path):
    from backend.services import subscription_service as subs

    storage_path = tmp_path / "subscriptions.json"
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", storage_path)
    first = subs.SubscriptionService()
    assert first.subscribe("alice@example.invalid", "AAPL") is True
    stale = subs.SubscriptionService()
    assert first.subscribe("bob@example.invalid", "MSFT") is True

    assert stale.toggle_subscription("alice@example.invalid", "AAPL", False) is True

    reloaded = subs.SubscriptionService()
    assert reloaded.get_subscriptions("alice@example.invalid")[0]["disabled"] is True
    assert len(reloaded.get_subscriptions("bob@example.invalid")) == 1


def test_stale_alert_attempt_does_not_erase_newer_subscriptions(monkeypatch, tmp_path):
    from backend.services import subscription_service as subs

    storage_path = tmp_path / "subscriptions.json"
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", storage_path)
    first = subs.SubscriptionService()
    assert first.subscribe("alice@example.invalid", "AAPL") is True
    stale = subs.SubscriptionService()
    assert first.subscribe("bob@example.invalid", "MSFT") is True

    stale.record_alert_attempt("alice@example.invalid", "AAPL", success=True)

    reloaded = subs.SubscriptionService()
    alice = reloaded.get_subscriptions("alice@example.invalid")[0]
    assert alice["last_alert_at"] is not None
    assert len(reloaded.get_subscriptions("bob@example.invalid")) == 1


def test_stale_last_alert_update_does_not_erase_newer_subscriptions(
    monkeypatch, tmp_path
):
    from backend.services import subscription_service as subs

    storage_path = tmp_path / "subscriptions.json"
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", storage_path)
    first = subs.SubscriptionService()
    assert first.subscribe("alice@example.invalid", "AAPL") is True
    stale = subs.SubscriptionService()
    assert first.subscribe("bob@example.invalid", "MSFT") is True

    stale.update_last_alert("alice@example.invalid", "AAPL")

    reloaded = subs.SubscriptionService()
    assert reloaded.get_subscriptions("alice@example.invalid")[0]["last_alert_at"]
    assert len(reloaded.get_subscriptions("bob@example.invalid")) == 1


@pytest.mark.parametrize(
    ("method_name", "expected_field"),
    [
        ("update_last_news", "last_news_at"),
        ("update_last_risk", "last_risk_at"),
        ("set_price_target_fired", "price_target_fired"),
        ("record_alert_event", "recent_events"),
    ],
)
def test_remaining_stale_writes_do_not_erase_newer_subscriptions(
    monkeypatch, tmp_path, method_name, expected_field
):
    from backend.services import subscription_service as subs

    storage_path = tmp_path / "subscriptions.json"
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", storage_path)
    first = subs.SubscriptionService()
    assert first.subscribe("alice@example.invalid", "AAPL") is True
    stale = subs.SubscriptionService()
    assert first.subscribe("bob@example.invalid", "MSFT") is True

    method = getattr(stale, method_name)
    if method_name == "record_alert_event":
        method("alice@example.invalid", "AAPL", "price_change")
    else:
        method("alice@example.invalid", "AAPL")

    reloaded = subs.SubscriptionService()
    alice = reloaded.get_subscriptions("alice@example.invalid")[0]
    assert alice[expected_field]
    assert len(reloaded.get_subscriptions("bob@example.invalid")) == 1


def test_stale_subscription_reads_refresh_from_storage(monkeypatch, tmp_path):
    from backend.services import subscription_service as subs

    storage_path = tmp_path / "subscriptions.json"
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", storage_path)
    writer = subs.SubscriptionService()
    stale = subs.SubscriptionService()
    assert writer.subscribe("alice@example.invalid", "AAPL") is True
    assert writer.record_alert_event(
        "alice@example.invalid", "AAPL", "price_change"
    ) is True

    assert len(stale.get_subscriptions("alice@example.invalid")) == 1
    assert len(stale.get_subscribers_for_ticker("AAPL")) == 1
    assert len(stale.list_alert_events("alice@example.invalid")) == 1


def test_subscription_limit_is_atomic_and_allows_existing_ticker_updates(monkeypatch, tmp_path):
    from backend.services import subscription_service as subs

    storage_path = tmp_path / "subscriptions.json"
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", storage_path)
    service = subs.SubscriptionService()

    assert service.subscribe("alice@example.invalid", "AAPL", max_subscriptions=1) is True
    assert service.subscribe("alice@example.invalid", "AAPL", alert_types=["news"], max_subscriptions=1) is True

    with pytest.raises(subs.SubscriptionLimitExceeded) as exc_info:
        service.subscribe("alice@example.invalid", "MSFT", max_subscriptions=1)

    assert exc_info.value.limit == 1
    assert exc_info.value.current == 1
    assert [item["ticker"] for item in service.get_subscriptions("alice@example.invalid")] == ["AAPL"]


@pytest.mark.parametrize("preserve_existing_alerts", [False, True])
def test_subscription_update_can_preserve_latest_alert_settings(monkeypatch, tmp_path, preserve_existing_alerts):
    from backend.services import subscription_service as subs

    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", tmp_path / "subscriptions.json")
    writer = subs.SubscriptionService()
    email = "alice@example.invalid"
    assert writer.subscribe(email, "AAPL", alert_types=["news"], risk_threshold="medium")
    stale = subs.SubscriptionService()
    assert writer.subscribe(email, "AAPL", alert_types=["news", "risk"], risk_threshold="critical")

    options = {"preserve_existing_alerts": True} if preserve_existing_alerts else {}
    assert stale.subscribe(
        email, "AAPL", alert_types=["price_change"], risk_threshold="low", max_subscriptions=1,
        **options,
    )

    saved = writer.get_subscriptions(email)[0]
    expected_types = ["news", "price_change", "risk"] if preserve_existing_alerts else ["price_change"]
    assert sorted(saved["alert_types"]) == expected_types
    assert saved["risk_threshold"] == ("critical" if preserve_existing_alerts else "low")
    assert len(writer.get_subscriptions(email)) == 1


def test_dropped_alert_event_metadata_is_marked_not_silently_empty(monkeypatch, tmp_path):
    """metadata 被丢弃时必须留下标记，不能和"本来就没有 metadata"同形。

    alert_scheduler 会把 change_percent / current_price 塞进 metadata，行情
    缺失时这些值可能是 NaN——json allow_nan=False 直接抛 ValueError，此前
    被压成 `{}`：事件流里该条告警看着和"没有元数据"完全一样（项目规则 2）。
    """
    from backend.services import subscription_service as subs

    storage_path = tmp_path / "subscriptions.json"
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", storage_path)
    service = subs.SubscriptionService()
    assert service.subscribe("alice@example.invalid", "AAPL") is True

    assert service.record_alert_event(
        "alice@example.invalid",
        "AAPL",
        "price_change",
        metadata={"change_percent": float("nan"), "current_price": 1.0},
    ) is True

    event = service.list_alert_events("alice@example.invalid")[0]
    assert event["metadata"] == {"_metadata_unavailable": "unserializable"}


def test_oversized_alert_event_metadata_is_marked_not_silently_empty(monkeypatch, tmp_path):
    """超限 metadata 同样要留标记（体积原因与不可序列化原因可区分）。"""
    from backend.services import subscription_service as subs

    storage_path = tmp_path / "subscriptions.json"
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", storage_path)
    service = subs.SubscriptionService()
    assert service.subscribe("alice@example.invalid", "AAPL") is True

    assert service.record_alert_event(
        "alice@example.invalid",
        "AAPL",
        "news",
        metadata={"blob": "x" * (17 * 1024)},
    ) is True

    event = service.list_alert_events("alice@example.invalid")[0]
    assert event["metadata"] == {"_metadata_unavailable": "oversized"}


def test_absent_alert_event_metadata_stays_empty(monkeypatch, tmp_path):
    """真的没有 metadata 的事件仍是 `{}`——不能给正常事件乱打降级标记。"""
    from backend.services import subscription_service as subs

    storage_path = tmp_path / "subscriptions.json"
    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", storage_path)
    service = subs.SubscriptionService()
    assert service.subscribe("alice@example.invalid", "AAPL") is True

    assert service.record_alert_event(
        "alice@example.invalid",
        "AAPL",
        "news",
    ) is True

    event = service.list_alert_events("alice@example.invalid")[0]
    assert event["metadata"] == {}
