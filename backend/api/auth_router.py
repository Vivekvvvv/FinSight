# -*- coding: utf-8 -*-
"""认证路由：登录/登出"""

import hashlib
import secrets
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.security.auth import is_dev_mode, secure_secret_matches

router = APIRouter(tags=["Auth"])

# Mock 用户表（内存）
MOCK_USERS = {
    "admin@finsight.local": {
        "password_hash": hashlib.sha256("admin123".encode()).hexdigest(),
        "user_id": "admin_user",
        "role": "admin",
    },
    "user@finsight.local": {
        "password_hash": hashlib.sha256("user123".encode()).hexdigest(),
        "user_id": "regular_user",
        "role": "user",
    },
}


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=1, max_length=128)


class LoginResponse(BaseModel):
    success: bool
    token: str
    user_id: str
    role: str
    email: str


@router.post("/api/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest) -> dict[str, Any]:
    if not is_dev_mode():
        raise HTTPException(status_code=404, detail="Not found")

    email = req.email.strip().lower()
    user = MOCK_USERS.get(email)
    if not user:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    password_hash = hashlib.sha256(req.password.encode()).hexdigest()
    if not secure_secret_matches(password_hash, user["password_hash"]):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    # 生成 JWT-like token（Mock，实际应用应使用 JWT 库）
    token = secrets.token_urlsafe(32)

    return {
        "success": True,
        "token": token,
        "user_id": user["user_id"],
        "role": user["role"],
        "email": email,
    }


@router.post("/api/auth/logout")
async def logout() -> dict[str, Any]:
    return {"success": True, "message": "已登出"}

# 注：GET /api/me 由 entitlements_router 提供（走规范的 get_current_user 依赖）。
# 此处曾有一份重复注册的同名路由，靠挂载顺序抢先生效，已删除。
