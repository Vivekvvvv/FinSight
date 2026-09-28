# -*- coding: utf-8 -*-
"""纯 ASGI 的 API 指标中间件。

为什么不用 backend.monitoring.prometheus_exporter.PrometheusMiddleware：
1) 那是 BaseHTTPMiddleware——每个请求过一条 anyio 内存流，对 SSE
   (chat/execution/rebalance 三处 StreamingResponse) 是逐块代理的开销；
   纯 ASGI 只包 send，无缓冲，并把流式全程耗时计入 duration。
2) 它用 request.url.path 做 endpoint 标签——/api/quote/{ticker} 这类
   路径参数路由会让序列基数随 ticker/note_id/user_id 无限膨胀
   （prometheus 客户端内存常驻）。此处取路由匹配后的 scope["route"].path
   （路由模板），标签有界；未匹配路径归入 __unmatched__。
3) PrometheusMiddleware 自始未被注册，alerts.yml 的
   HighAPIErrorRate / SlowAPIResponse / HighActiveRequests
   三条告警因此永远缺序列——本中间件是它们唯一的数据源。
"""
from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from backend.monitoring.prometheus_exporter import (
    record_api_error,
    record_api_request,
    update_active_requests,
)

logger = logging.getLogger(__name__)

_UNMATCHED = "__unmatched__"


def _endpoint_label(scope: dict) -> str:
    """路由匹配后 scope["route"] 携带路由模板；未匹配路径不原样落标签。"""
    route = scope.get("route")
    path = getattr(route, "path", None) if route is not None else None
    if isinstance(path, str) and path:
        return path
    return _UNMATCHED


def _record(scope: dict, status: int, duration: float, error_type: str | None) -> None:
    method = str(scope.get("method") or "")
    endpoint = _endpoint_label(scope)
    record_api_request(method, endpoint, status, duration)
    if error_type is not None:
        record_api_error(method, endpoint, error_type)
    elif status >= 500:
        # 路由内异常已被框架 ExceptionMiddleware 转成 500 响应，逃逸不到
        # 本层——按状态码补记，否则 errors_total 恒 0、HighAPIErrorRate 假阴性。
        record_api_error(method, endpoint, "http_5xx")


class ApiMetricsMiddleware:
    """统计每个 HTTP 请求的请求数/耗时/错误/并发——喂给 alerts.yml 的
    HighAPIErrorRate / SlowAPIResponse / HighActiveRequests。"""

    def __init__(self, app: Callable[..., Awaitable[Any]]) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        update_active_requests(1)
        start = time.monotonic()
        status = 500

        async def send_wrapper(message: dict) -> None:
            nonlocal status
            if message.get("type") == "http.response.start":
                status = int(message.get("status") or 500)
            await send(message)

        error_type: str | None = None
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            error_type = type(exc).__name__
            raise
        finally:
            duration = time.monotonic() - start
            update_active_requests(-1)
            try:
                _record(scope, status, duration, error_type)
            except Exception as exc:
                # 指标写失败不能反过来弄断请求
                logger.debug("api metrics record failed: %s", type(exc).__name__)
