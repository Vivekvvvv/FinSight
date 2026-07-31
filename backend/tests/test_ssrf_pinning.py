# -*- coding: utf-8 -*-
"""SSRF IP pinning 回归：resolve_safe_target + safe_pinned_request。

核心防护：is_safe_url 校验与 requests 连接之间 DNS 被重解析（DNS rebinding /
TOCTOU）。pinned_http 把 URL host 改写为校验时锁定的 IP，连接不再重解析域名，
HTTPS 的 SNI/证书验证仍用域名；重定向禁自动、逐跳校验。
"""
from __future__ import annotations

import backend.security.ssrf as ssrf
import backend.security.pinned_http as ph


def _addrinfo(ip: str, port: int):
    return [(2, 1, 6, "", (ip, port))]


class _Resp:
    def __init__(self, status_code=200, headers=None, text="ok"):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text


# ── resolve_safe_target ─────────────────────────────────────────


def test_resolve_public_returns_pinned_ip(monkeypatch):
    monkeypatch.setattr(ssrf.socket, "getaddrinfo", lambda h, p, *a, **k: _addrinfo("93.184.216.34", p))
    assert ssrf.resolve_safe_target("https://example.com/x") == ("example.com", 443, "93.184.216.34")


def test_resolve_private_blocked(monkeypatch):
    monkeypatch.setattr(ssrf.socket, "getaddrinfo", lambda h, p, *a, **k: _addrinfo("169.254.169.254", p))
    assert ssrf.resolve_safe_target("https://evil.com/x") is None


def test_resolve_any_private_ip_blocks_whole_host(monkeypatch):
    # 多个解析 IP，只要有一个内网即整体拒绝
    monkeypatch.setattr(ssrf.socket, "getaddrinfo",
                        lambda h, p, *a, **k: _addrinfo("93.184.216.34", p) + _addrinfo("10.0.0.5", p))
    assert ssrf.resolve_safe_target("https://evil.com/x") is None


def test_resolve_static_loopback_blocked():
    assert ssrf.resolve_safe_target("http://127.0.0.1/admin") is None
    assert ssrf.resolve_safe_target("http://localhost/x") is None


def test_resolve_non_http_scheme_blocked():
    assert ssrf.resolve_safe_target("file:///etc/passwd") is None


def test_resolve_invalid_port_is_rejected():
    assert ssrf.resolve_safe_target("https://example.com:not-a-port/path") is None


def test_embedded_url_credentials_are_rejected(monkeypatch):
    monkeypatch.setattr(ssrf.socket, "getaddrinfo", lambda h, p, *a, **k: _addrinfo("93.184.216.34", p or 443))

    target = "https://user:secret@example.com/path"

    assert ssrf.url_has_credentials(target) is True
    assert ssrf.is_safe_url(target) is False
    assert ssrf.resolve_safe_target(target) is None


# ── safe_pinned_request：pin 生效 ───────────────────────────────


def _capture_request(monkeypatch, responder):
    """monkeypatch Session.request，把每次调用的 url/headers 记下来并用 responder 决定返回。"""
    calls = []

    def fake_request(self, method, url, **kwargs):
        calls.append(
            {
                "method": method,
                "url": url,
                "headers": kwargs.get("headers", {}),
                "auth": kwargs.get("auth"),
                "cookies": kwargs.get("cookies"),
            }
        )
        return responder(len(calls))

    monkeypatch.setattr(ph.requests.Session, "request", fake_request)
    return calls


def test_connects_to_pinned_ip_not_domain(monkeypatch):
    monkeypatch.setattr(ph, "resolve_safe_target", lambda url: ("example.com", 443, "93.184.216.34"))
    calls = _capture_request(monkeypatch, lambda n: _Resp(200))

    resp = ph.safe_pinned_get("https://example.com/path?q=1", timeout=5)

    assert resp.status_code == 200
    # 连接目标是 pinned IP，而非域名（域名不再交给 requests 重新解析）
    assert "93.184.216.34" in calls[0]["url"]
    assert "example.com" not in calls[0]["url"]
    # Host header 仍是域名（HTTP 语义 + 证书验证）
    assert calls[0]["headers"]["Host"] == "example.com"


def test_rebinding_uses_validated_ip_not_reresolved(monkeypatch):
    """核心：getaddrinfo 校验时返回公网、之后翻转成内网（rebinding），
    但连接用校验时锁定的公网 IP，翻转无效。"""
    state = {"n": 0}

    def flipping(host, port, *a, **k):
        state["n"] += 1
        ip = "93.184.216.34" if state["n"] == 1 else "169.254.169.254"
        return _addrinfo(ip, port)

    monkeypatch.setattr(ssrf.socket, "getaddrinfo", flipping)
    calls = _capture_request(monkeypatch, lambda n: _Resp(200))

    resp = ph.safe_pinned_get("https://evil.com/x", timeout=5)

    assert resp is not None
    assert "93.184.216.34" in calls[0]["url"]   # 用第 1 次校验的公网 IP
    assert "169.254" not in calls[0]["url"]      # 第 2 次内网翻转无效


# ── 重定向逐跳校验 ──────────────────────────────────────────────


def test_redirect_to_internal_blocked_without_connecting(monkeypatch):
    def getaddrinfo(host, port, *a, **k):
        if host == "example.com":
            return _addrinfo("93.184.216.34", port)
        return _addrinfo("10.0.0.5", port)  # 内网

    monkeypatch.setattr(ssrf.socket, "getaddrinfo", getaddrinfo)
    # 第 1 跳（公网）返回 302 指向内网
    calls = _capture_request(
        monkeypatch,
        lambda n: _Resp(302, headers={"Location": "http://internal.evil.com/metadata"}),
    )

    resp = ph.safe_pinned_get("https://example.com/x", timeout=5)

    assert resp is None                       # 内网重定向被逐跳校验拦截
    assert len(calls) == 1                    # 只连了第 1 跳公网，未连内网
    assert "93.184.216.34" in calls[0]["url"]


def test_too_many_redirects_returns_none(monkeypatch):
    monkeypatch.setattr(ph, "resolve_safe_target", lambda url: ("example.com", 443, "93.184.216.34"))
    calls = _capture_request(
        monkeypatch,
        lambda n: _Resp(302, headers={"Location": "https://example.com/next"}),
    )

    resp = ph.safe_pinned_get("https://example.com/x", timeout=5, max_redirects=2)

    assert resp is None
    assert len(calls) == 3  # 初次 + 2 跳后超限


def test_cross_origin_redirect_strips_sensitive_credentials(monkeypatch):
    def resolve(url):
        host = ph.urlparse(url).hostname
        if host == "example.com":
            return host, 443, "93.184.216.34"
        return host, 443, "93.184.216.35"

    monkeypatch.setattr(ph, "resolve_safe_target", resolve)
    calls = _capture_request(
        monkeypatch,
        lambda n: _Resp(
            302,
            headers={"Location": "https://other.example/next"},
        )
        if n == 1
        else _Resp(200),
    )

    response = ph.safe_pinned_get(
        "https://example.com/start",
        timeout=5,
        headers={
            "Authorization": "Bearer private",
            "Cookie": "session=private",
            "X-API-Key": "private",
            "X-Custom": "safe",
        },
        auth=("user", "private"),
        cookies={"session": "private"},
    )

    assert response is not None
    assert calls[0]["headers"]["Authorization"] == "Bearer private"
    assert calls[0]["auth"] == ("user", "private")
    assert "Authorization" not in calls[1]["headers"]
    assert "Cookie" not in calls[1]["headers"]
    assert "X-API-Key" not in calls[1]["headers"]
    assert calls[1]["headers"]["X-Custom"] == "safe"
    assert calls[1]["auth"] is None
    assert calls[1]["cookies"] is None


def test_blocked_target_log_redacts_url_query(monkeypatch, caplog):
    import logging

    secret = "PRIVATE_QUERY_TOKEN"
    monkeypatch.setattr(ph, "resolve_safe_target", lambda _url: None)
    caplog.set_level(logging.INFO, logger="backend.security.pinned_http")

    response = ph.safe_pinned_get(
        f"https://example.com/path?token={secret}",
        timeout=5,
    )

    assert response is None
    assert "example.com" in caplog.text
    assert secret not in caplog.text


def test_unsafe_first_url_returns_none(monkeypatch):
    monkeypatch.setattr(ph, "resolve_safe_target", lambda url: None)
    calls = _capture_request(monkeypatch, lambda n: _Resp(200))

    assert ph.safe_pinned_get("http://127.0.0.1/x", timeout=5) is None
    assert len(calls) == 0  # 校验失败，从未发起连接
