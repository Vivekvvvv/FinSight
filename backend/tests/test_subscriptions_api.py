# -*- coding: utf-8 -*-
"""
P1 Alert subscription API smoke tests.
"""

import os
import sys
from typing import Any

import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.api.main import app  # noqa: E402
from backend.services import subscription_service as subs  # noqa: E402


def _configure_test_storage(tmp_path: Any) -> None:
    subs.SUBSCRIPTIONS_FILE = tmp_path / "subscriptions_test.json"
    subs._subscription_service = None  # type: ignore[attr-defined]


def test_subscribe_and_list_lifecycle(tmp_path):
    _configure_test_storage(tmp_path)
    with TestClient(app) as client:
        email = "user@example.com"
        ticker = "AAPL"

        resp = client.post(
            "/api/subscribe",
            json={
                "email": email,
                "ticker": ticker,
                "alert_types": ["price_change", "news"],
                "price_threshold": 5.0,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True
        assert data.get("email") == email
        assert data.get("ticker") == ticker

        resp = client.get(f"/api/subscriptions?email={email}")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True
        subs_list = data.get("subscriptions") or []
        assert len(subs_list) == 1
        sub = subs_list[0]
        assert sub["email"] == email
        assert sub["ticker"] == ticker
        assert sub["alert_types"] == ["price_change", "news"]
        assert sub["price_threshold"] == 5.0

        resp = client.post(
            "/api/unsubscribe",
            json={
                "email": email,
                "ticker": ticker,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True

        resp = client.get(f"/api/subscriptions?email={email}")
        assert resp.status_code == 200
        data = resp.json()
        subs_list = data.get("subscriptions") or []
        assert len(subs_list) == 0


def test_subscribe_validation_and_unsubscribe_missing(tmp_path):
    _configure_test_storage(tmp_path)
    with TestClient(app) as client:
        resp = client.post(
            "/api/subscribe",
            json={
                "ticker": "AAPL",
            },
        )
        assert resp.status_code in (400, 422)

        resp = client.post(
            "/api/unsubscribe",
            json={
                "ticker": "AAPL",
            },
        )
        assert resp.status_code in (400, 422)

        resp = client.post(
            "/api/unsubscribe",
            json={
                "email": "nobody@example.com",
                "ticker": "AAPL",
            },
        )
        assert resp.status_code == 404


def test_subscription_endpoints_reject_oversized_inputs(tmp_path):
    _configure_test_storage(tmp_path)
    with TestClient(app) as client:
        alert_types_resp = client.post(
            "/api/subscribe",
            json={
                "email": "user@example.com",
                "ticker": "AAPL",
                "alert_types": ["news"] * 5,
            },
        )
        ticker_resp = client.post(
            "/api/subscription/toggle",
            json={"email": "user@example.com", "ticker": "A" * 33, "enabled": True},
        )
        email_resp = client.get("/api/subscriptions", params={"email": "x" * 321})
        threshold_resp = client.post(
            "/api/subscribe",
            json={
                "email": "user@example.com",
                "ticker": "AAPL",
                "price_threshold": "inf",
            },
        )
        target_resp = client.post(
            "/api/subscribe",
            json={
                "email": "user@example.com",
                "ticker": "AAPL",
                "price_target": "nan",
            },
        )

    assert alert_types_resp.status_code == 422
    assert ticker_resp.status_code == 422
    assert email_resp.status_code == 422
    assert threshold_resp.status_code == 422
    assert target_resp.status_code == 422


def test_unsubscribe_unknown_ticker_returns_not_found_for_existing_email(tmp_path):
    _configure_test_storage(tmp_path)
    service = subs.get_subscription_service()
    email = "user@example.com"
    assert service.subscribe(email, "AAPL")
    before = service.subscriptions_file.read_bytes()

    with TestClient(app) as client:
        response = client.post("/api/unsubscribe", json={"email": email, "ticker": "TSLA"})

    assert response.status_code == 404
    assert service.subscriptions_file.read_bytes() == before


@pytest.mark.parametrize("ticker", ["   ", "BAD TICKER", ".AAPL", "A" * 21])
def test_subscribe_invalid_ticker_returns_bad_request_without_writing(tmp_path, ticker):
    _configure_test_storage(tmp_path)
    service = subs.get_subscription_service()
    email = "user@example.com"
    assert service.subscribe(email, "AAPL")
    before = service.subscriptions_file.read_bytes()

    with TestClient(app) as client:
        response = client.post("/api/subscribe", json={"email": email, "ticker": ticker})

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid ticker"
    assert service.subscriptions_file.read_bytes() == before


@pytest.mark.parametrize("existing_subscription", [False, True])
@pytest.mark.parametrize("settings", [
    {}, {"price_target": 120.0}, {"direction": "above"},
])
def test_incomplete_price_target_request_cannot_write_or_consume_quota(
    tmp_path, monkeypatch, settings, existing_subscription,
):
    from backend.services import entitlements

    _configure_test_storage(tmp_path)
    monkeypatch.setattr(entitlements, "PLANS_FILE", tmp_path / "plans.json")
    monkeypatch.setattr(entitlements, "_service_instance", entitlements.EntitlementsService())
    service = subs.get_subscription_service()
    email = "user@example.com"
    for ticker in ("AAPL", "MSFT"):
        assert service.subscribe(email, ticker)
    if existing_subscription:
        assert service.subscribe(
            email, "TSLA", alert_types=["price_change"],
            alert_mode="price_target", price_target=80.0, direction="below",
        )
    before = service.subscriptions_file.read_bytes()
    with TestClient(app) as client:
        invalid = client.post("/api/subscribe", json={
            "email": email, "ticker": "TSLA", "alert_types": ["price_change"],
            "alert_mode": "price_target", **settings,
        })

        assert invalid.status_code == 422
        assert service.subscriptions_file.read_bytes() == before
        valid = client.post("/api/subscribe", json={
            "email": email, "ticker": "TSLA", "alert_types": ["price_change"],
            "alert_mode": "price_target", "price_target": 120.0, "direction": "above",
        })

    assert valid.status_code == 200
    assert len(service.get_subscriptions(email)) == 3
    saved = next(item for item in service.get_subscriptions(email) if item["ticker"] == "TSLA")
    assert saved["price_target"] == 120.0
    assert saved["direction"] == "above"


def test_price_target_settings_are_optional_when_price_alerts_are_not_enabled():
    from backend.api.schemas import SubscriptionRequest

    request = SubscriptionRequest(
        email="user@example.com", ticker="AAPL", alert_types=["news"], alert_mode="price_target",
    )

    assert request.alert_types == ["news"]
    assert request.price_target is None


@pytest.mark.parametrize("alert_types", [[], False, 0, "", {}])
@pytest.mark.parametrize("existing_subscription", [False, True])
def test_empty_or_invalid_alert_types_cannot_create_default_alerts(tmp_path, alert_types, existing_subscription):
    _configure_test_storage(tmp_path)
    service = subs.get_subscription_service()
    email = "user@example.com"
    for ticker in ("AAPL", "MSFT"):
        assert service.subscribe(email, ticker, alert_types=["news"])
    before = service.subscriptions_file.read_bytes()
    ticker = "AAPL" if existing_subscription else "TSLA"

    with TestClient(app) as client:
        response = client.post("/api/subscribe", json={
            "email": email, "ticker": ticker, "alert_types": alert_types, "price_threshold": 3.0,
        })
        assert response.status_code == 422
        assert service.subscriptions_file.read_bytes() == before
        valid = client.post("/api/subscribe", json={"email": email, "ticker": "NVDA", "alert_types": ["news"]})

    assert valid.status_code == 200
    assert len(service.get_subscriptions(email)) == 3


@pytest.mark.parametrize("payload", [{}, {"alert_types": None}])
def test_unspecified_alert_types_keep_existing_defaults(tmp_path, payload):
    _configure_test_storage(tmp_path)
    with TestClient(app) as client:
        response = client.post("/api/subscribe", json={"email": "user@example.com", "ticker": "AAPL", **payload})

    assert response.status_code == 200
    saved = subs.get_subscription_service().get_subscriptions("user@example.com")[0]
    assert saved["alert_types"] == ["price_change", "news"]
