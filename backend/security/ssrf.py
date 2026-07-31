# -*- coding: utf-8 -*-
"""
SSRF guard helpers shared across agents/tools.
"""

from __future__ import annotations

from urllib.parse import urlparse
import ipaddress
import socket


def _parsed_url_has_credentials(parsed) -> bool:
    try:
        return parsed.username is not None or parsed.password is not None
    except (TypeError, ValueError):
        return True


def url_has_credentials(url: str) -> bool:
    """Return True for embedded URL credentials or malformed URLs."""
    try:
        return _parsed_url_has_credentials(urlparse(url))
    except (TypeError, ValueError):
        return True


def _ip_is_blocked(ip: ipaddress._BaseAddress) -> bool:
    """内网/环回/链路本地/保留/组播地址一律拦截。"""
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
    )


def _host_is_blocked_literal(lowered: str) -> bool:
    """按主机名字面量拦截明显的本地/内网别名。"""
    if lowered in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return True
    if lowered.endswith(".local") or lowered.endswith(".internal"):
        return True
    return False


def is_safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if _parsed_url_has_credentials(parsed):
        return False
    host = parsed.hostname
    if not host:
        return False
    lowered = host.lower()
    if _host_is_blocked_literal(lowered):
        return False
    try:
        ip = ipaddress.ip_address(lowered)
        return not _ip_is_blocked(ip)
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if _ip_is_blocked(ip):
                return False
    except Exception:
        return False
    return True


def resolve_safe_target(url: str) -> tuple[str, int, str] | None:
    """解析 url 的 host，校验其**所有**解析 IP 均为公网，返回 (host, port, pinned_ip)。

    用于 IP pinning：调用方拿到已校验的 pinned_ip 后强制连接到它，避免
    is_safe_url 校验与 requests 连接之间 DNS 被重解析（DNS rebinding / TOCTOU）。
    不安全（非 http/s、localhost/.local/.internal、任一解析 IP 私网/环回/链路
    本地/保留/组播）返回 None。

    - 静态 IP 字面量：校验后 pinned_ip = 该 IP。
    - 域名：getaddrinfo 解析，全部 IP 必须公网，pinned_ip 取第一个。
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    if _parsed_url_has_credentials(parsed):
        return None
    host = parsed.hostname
    if not host:
        return None
    lowered = host.lower()
    if _host_is_blocked_literal(lowered):
        return None

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return None

    # 静态 IP 字面量
    try:
        ip = ipaddress.ip_address(lowered)
        if _ip_is_blocked(ip):
            return None
        return (host, port, str(ip))
    except ValueError:
        pass

    # 域名：解析全部 IP，任一非公网即拒；pinned_ip 取第一个安全 IP。
    try:
        infos = socket.getaddrinfo(host, port)
    except Exception:
        return None
    first_ip: str | None = None
    for info in infos:
        raw_ip = info[4][0]
        try:
            ip = ipaddress.ip_address(raw_ip)
        except ValueError:
            return None
        if _ip_is_blocked(ip):
            return None
        if first_ip is None:
            first_ip = raw_ip
    if first_ip is None:
        return None
    return (host, port, first_ip)
