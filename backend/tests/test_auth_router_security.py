from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.auth_router import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_mock_login_is_hidden_outside_dev_mode(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "false")

    with _client() as client:
        response = client.post(
            "/api/auth/login",
            json={"email": "admin@finsight.local", "password": "admin123"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Not found"


def test_mock_login_remains_available_in_dev_mode(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")

    with _client() as client:
        response = client.post(
            "/api/auth/login",
            json={"email": "admin@finsight.local", "password": "admin123"},
        )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert response.json()["token"]


def test_mock_login_rejects_invalid_password_in_dev_mode(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")

    with _client() as client:
        response = client.post(
            "/api/auth/login",
            json={"email": "admin@finsight.local", "password": "wrong"},
        )

    assert response.status_code == 401


def test_mock_login_rejects_oversized_credentials_before_hashing(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "true")

    with _client() as client:
        email_response = client.post(
            "/api/auth/login",
            json={"email": "x" * 321, "password": "password"},
        )
        password_response = client.post(
            "/api/auth/login",
            json={"email": "admin@finsight.local", "password": "x" * 129},
        )

    assert email_response.status_code == 422
    assert password_response.status_code == 422
