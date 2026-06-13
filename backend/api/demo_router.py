# -*- coding: utf-8 -*-
"""Demo 与数据源状态接口。"""

from __future__ import annotations

from fastapi import APIRouter

from backend.demo_mode import demo_status
from backend.services.data_source_status import get_data_source_status


demo_router = APIRouter(tags=["Demo"])


@demo_router.get("/api/demo/status")
async def get_demo_status() -> dict:
    """返回当前 Demo Mode 状态，保留旧接口兼容。"""
    return demo_status()


@demo_router.get("/api/data-sources/status")
async def get_data_sources_status() -> dict:
    """返回 US/CN/HK、LLM、RAG、Auth 的可用性与降级说明。"""
    return get_data_source_status()
