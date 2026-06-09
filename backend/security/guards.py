# -*- coding: utf-8 -*-
"""权限守卫装饰器"""

from functools import wraps
from typing import Callable

from fastapi import HTTPException, Request


def require_user(endpoint: Callable) -> Callable:
    """拒绝 guest，要求已登录用户"""
    @wraps(endpoint)
    async def wrapper(*args, **kwargs):
        request: Request | None = kwargs.get("http_request") or kwargs.get("request")
        if not request:
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
        if not request:
            raise HTTPException(status_code=500, detail="require_user: no Request found")

        principal = getattr(request.state, "principal", None)
        if not principal or getattr(principal, "role", None) == "guest":
            raise HTTPException(status_code=401, detail="需要登录才能访问此资源")

        return await endpoint(*args, **kwargs)
    return wrapper


def require_admin(endpoint: Callable) -> Callable:
    """仅 admin 可访问"""
    @wraps(endpoint)
    async def wrapper(*args, **kwargs):
        request: Request | None = kwargs.get("http_request") or kwargs.get("request")
        if not request:
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
        if not request:
            raise HTTPException(status_code=500, detail="require_admin: no Request found")

        principal = getattr(request.state, "principal", None)
        if not principal or not getattr(principal, "is_admin", False):
            raise HTTPException(status_code=403, detail="需要管理员权限")

        return await endpoint(*args, **kwargs)
    return wrapper
