from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient


def _set_prod_env(monkeypatch, *, role: str = "user") -> None:
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_BASE", "https://example.invalid/v1")
    monkeypatch.setenv("POSTGRES_DB", "test")
    monkeypatch.setenv("POSTGRES_USER", "test")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
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
    assert event["metadata"] == {}


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
    assert loaded["metadata"] == {}
    assert "unexpected" not in loaded


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
