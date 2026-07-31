# -*- coding: utf-8 -*-
import backend.tools.wayback as wayback_mod


class _MockResponse:
    def __init__(self, status_code=200, text="", payload=None, headers=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("no payload")
        return self._payload


def test_normalize_domain_drops_embedded_credentials_and_port():
    assert wayback_mod._normalize_domain("https://user:secret@www.example.com:8443/article") == "example.com"


def test_resolve_wayback_snapshot_via_available(monkeypatch):
    payload = {
        "archived_snapshots": {
            "closest": {
                "available": True,
                "status": "200",
                "url": "https://web.archive.org/web/20260210120000/https://www.reuters.com/test",
                "timestamp": "20260210120000",
            }
        }
    }
    monkeypatch.setattr(wayback_mod, "_http_get", lambda *_args, **_kwargs: _MockResponse(payload=payload))

    snapshot = wayback_mod.resolve_wayback_snapshot("https://www.reuters.com/test")

    assert snapshot is not None
    assert "web.archive.org/web/20260210120000" in str(snapshot.get("snapshot_url") or "")
    assert snapshot.get("status") == "200"


def test_fetch_via_wayback_extracts_html_text(monkeypatch):
    monkeypatch.setattr(
        wayback_mod,
        "resolve_wayback_snapshot",
        lambda *_args, **_kwargs: {
            "snapshot_url": "https://web.archive.org/web/20260210120000/https://www.wsj.com/test",
        },
    )
    html = "<html><body>" + ("Macro data release " * 20) + "</body></html>"
    monkeypatch.setattr(
        wayback_mod,
        "safe_pinned_request",
        lambda *_args, **_kwargs: _MockResponse(
            status_code=200,
            text=html,
            headers={"Content-Type": "text/html; charset=utf-8"},
        ),
    )

    text = wayback_mod.fetch_via_wayback("https://www.wsj.com/test")

    assert isinstance(text, str)
    assert "Macro data release" in text
    assert len(text) >= 80


def test_fetch_via_wayback_rejects_unsafe_snapshot_target(monkeypatch):
    monkeypatch.setattr(
        wayback_mod,
        "resolve_wayback_snapshot",
        lambda *_args, **_kwargs: {
            "snapshot_url": "http://127.0.0.1/private-metadata",
        },
    )
    captured = []

    def reject_target(method, url, **_kwargs):
        captured.append((method, url))
        return None

    monkeypatch.setattr(wayback_mod, "safe_pinned_request", reject_target)

    assert wayback_mod.fetch_via_wayback("https://www.wsj.com/test") is None
    assert captured == [("GET", "http://127.0.0.1/private-metadata")]


def test_resolve_wayback_rejects_embedded_url_credentials(monkeypatch):
    calls = []
    monkeypatch.setattr(wayback_mod, "_http_get", lambda *args, **kwargs: calls.append((args, kwargs)))

    assert wayback_mod.resolve_wayback_snapshot("https://user:secret@example.com/article") is None
    assert calls == []
