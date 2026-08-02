# -*- coding: utf-8 -*-
"""IP-pinned HTTP requests —— 抵御 DNS rebinding / SSRF TOCTOU。

resolve_safe_target 解析并锁定安全公网 IP 后，这里把 URL 的 host 改写为该
pinned IP 强制连接（requests 不再重新解析域名），HTTPS 的 SNI 与证书验证
hostname 仍用原域名（经 Host header + adapter 的 server_hostname/assert_hostname）。
禁止自动重定向，手动逐跳——每跳都重新 resolve_safe_target，使攻击者无法在
"校验"与"连接"之间翻转 DNS（rebinding）。

线程安全：per-request Session/adapter，绝不 monkey-patch 全局 socket.getaddrinfo
（项目大量 to_thread/ThreadPoolExecutor 多线程）。
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from backend.security.ssrf import resolve_safe_target

logger = logging.getLogger(__name__)

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_SENSITIVE_REDIRECT_HEADERS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "x-api-key",
    "api-key",
    "x-auth-token",
    "x-access-token",
}


class _PinnedIPAdapter(HTTPAdapter):
    """URL 中的 host 已被改写为 pinned IP（连接目标）；本 adapter 让 HTTPS 的
    TLS SNI 与证书验证 hostname 用原域名，从而"连 IP、验域名"。

    只对 https 注入 server_hostname/assert_hostname——HTTPConnectionPool（明文
    HTTP）不接受这两个参数，注入会 TypeError。
    """

    def __init__(self, server_hostname: str, **kwargs: Any) -> None:
        self._server_hostname = server_hostname
        super().__init__(**kwargs)

    def send(self, request: Any, **kwargs: Any) -> Any:
        if str(getattr(request, "url", "")).lower().startswith("https"):
            pool_kw = self.poolmanager.connection_pool_kw
            pool_kw["server_hostname"] = self._server_hostname   # TLS SNI = 域名
            pool_kw["assert_hostname"] = self._server_hostname   # 证书验证 = 域名
        return super().send(request, **kwargs)


def _ip_netloc(pinned_ip: str, port: int) -> str:
    if ":" in pinned_ip:  # IPv6
        return f"[{pinned_ip}]:{port}"
    return f"{pinned_ip}:{port}"


def _host_header(host: str, port: int, scheme: str) -> str:
    default_port = 443 if scheme == "https" else 80
    return host if port == default_port else f"{host}:{port}"


def _origin(url: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlparse(url)
        host = str(parsed.hostname or "").lower()
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return None
    if not host:
        return None
    return parsed.scheme.lower(), host, port


def _safe_log_host(url: str) -> str:
    try:
        return str(urlparse(url).hostname or "invalid")
    except ValueError:
        return "invalid"


def _build_retry() -> Retry:
    return Retry(
        total=1,
        backoff_factor=0.2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD", "POST"],
        raise_on_status=False,
    )


def safe_pinned_request(
    method: str,
    url: str,
    *,
    headers: Optional[dict] = None,
    timeout: Any,
    max_redirects: int = 3,
    **kwargs: Any,
) -> Optional[requests.Response]:
    """对用户可控 URL 做 IP-pinned、逐跳校验的出站请求。

    返回 requests.Response；任一跳的 URL（含重定向目标）不安全、或重定向超过
    max_redirects → 返回 None（调用方按"unsafe/失败"处理，与旧的 is_safe_url
    拦截语义一致）。绝不对内网地址发起过连接（先 resolve_safe_target 校验，
    通过才连接到 pinned IP）。
    """
    base_headers = dict(headers or {})
    retry = _build_retry()
    current_url = url
    forward_sensitive_credentials = True

    for _hop in range(max_redirects + 1):
        target = resolve_safe_target(current_url)
        if target is None:
            logger.info("[pinned_http] blocked unsafe target")
            return None
        host, port, pinned_ip = target

        parsed = urlparse(current_url)
        ip_url = urlunparse((
            parsed.scheme,
            _ip_netloc(pinned_ip, port),
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        ))
        req_headers = dict(base_headers)
        request_kwargs = dict(kwargs)
        if not forward_sensitive_credentials:
            req_headers = {
                key: value
                for key, value in req_headers.items()
                if str(key).lower() not in _SENSITIVE_REDIRECT_HEADERS
            }
            request_kwargs.pop("auth", None)
            request_kwargs.pop("cookies", None)
        req_headers["Host"] = _host_header(host, port, parsed.scheme)

        session = requests.Session()
        adapter = _PinnedIPAdapter(server_hostname=host, max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        try:
            resp = session.request(
                method,
                ip_url,
                headers=req_headers,
                timeout=timeout,
                allow_redirects=False,
                **request_kwargs,
            )
        finally:
            session.close()

        if resp.status_code in _REDIRECT_STATUSES:
            location = resp.headers.get("Location")
            if not location:
                return resp
            next_url = urljoin(current_url, location)
            if _origin(next_url) != _origin(current_url):
                forward_sensitive_credentials = False
            current_url = next_url  # 相对 Location → 绝对
            continue
        return resp

    logger.info("[pinned_http] too many redirects")
    return None


def safe_pinned_get(url: str, **kwargs: Any) -> Optional[requests.Response]:
    """GET 便捷封装。"""
    return safe_pinned_request("GET", url, **kwargs)


__all__ = ["safe_pinned_request", "safe_pinned_get"]
