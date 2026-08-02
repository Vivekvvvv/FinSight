from __future__ import annotations

import logging

from backend.tools import jina_reader


def test_jina_reader_does_not_log_url_query_credentials(monkeypatch, caplog):
    secret = "PRIVATE_JINA_QUERY_TOKEN"
    url = f"https://example.com/article?access_token={secret}"

    def fail_request(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(jina_reader, "_http_get", fail_request)
    caplog.set_level(logging.DEBUG, logger="backend.tools.jina_reader")

    assert jina_reader.fetch_via_jina(url) is None
    assert secret not in caplog.text
    assert "access_token" not in caplog.text
    assert "example.com" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_jina_reader_rejects_embedded_url_credentials(monkeypatch, caplog):
    secret = "PRIVATE_JINA_PASSWORD"
    calls = []
    monkeypatch.setattr(jina_reader, "_http_get", lambda *args, **kwargs: calls.append((args, kwargs)))
    caplog.set_level(logging.DEBUG, logger="backend.tools.jina_reader")

    assert jina_reader.fetch_via_jina(f"https://user:{secret}@example.com/article") is None
    assert calls == []
    assert secret not in caplog.text
