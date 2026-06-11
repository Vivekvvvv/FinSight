# -*- coding: utf-8 -*-
"""Demo Mode 状态接口。"""

from __future__ import annotations

from fastapi import APIRouter

from backend.demo_mode import demo_status


demo_router = APIRouter(tags=["Demo"])


@demo_router.get("/api/demo/status")
async def get_demo_status() -> dict:
    """返回当前 Demo Mode 状态与缺失服务配置。"""
    return demo_status()
