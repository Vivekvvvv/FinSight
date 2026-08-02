from __future__ import annotations

import logging

import pytest

from backend.tools import web


@pytest.mark.parametrize(
    "failure",
    [
        None,
        TimeoutError,
    ],
)
def test_fetch_url_content_does_not_log_query_credentials(monkeypatch, caplog, failure):
    secret = "PRIVATE_QUERY_TOKEN_123"
    url = f"https://example.com/article?access_token={secret}"

    if failure is None:
        monkeypatch.setattr(web, "safe_pinned_request", lambda *_args, **_kwargs: None)
    else:
        def fail_request(*_args, **_kwargs):
            raise web.requests.exceptions.Timeout(secret)

        monkeypatch.setattr(web, "safe_pinned_request", fail_request)

    caplog.set_level(logging.INFO, logger="backend.tools.web")

    assert web.fetch_url_content(url) is None
    assert secret not in caplog.text
    assert "access_token" not in caplog.text
    assert "example.com" not in caplog.text
