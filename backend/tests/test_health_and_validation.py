# -*- coding: utf-8 -*-
"""
P0 稳定性回归测试：健康检查与基本请求校验。

目标：
- / 与 /health 端点始终可用，用于监控与存活检查；
- /chat/supervisor 在收到空 query 时由 Pydantic 校验层直接返回 422，
  避免空请求进入主链路。
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from backend.api.main import app  # noqa: E402


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_root_health_endpoint(client):
    """根路径应返回 healthy 状态和时间戳。"""
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "healthy"
    assert "timestamp" in data
    assert "message" in data


def test_health_endpoint(client):
    """/health 端点应只返回公开存活信息。"""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "ok"
    assert "version" in data
    assert "uptime_seconds" in data
    assert "components" not in data
    assert "recent_runs" not in data
    assert "query_text" not in str(data)
    assert "timestamp" in data


def test_chat_empty_query_validation(client):
    """
    空 query 应在进入处理函数前被 Pydantic 拦截，返回 422。
    这样可以避免空请求进入主链路，提升稳健性。
    """
    resp = client.post("/chat/supervisor", json={"query": ""})
    assert resp.status_code == 422


def test_legacy_chat_endpoint_removed(client):
    """旧 /chat 端点应已移除，返回 404。"""
    resp = client.post("/chat", json={"query": "AAPL 现在多少钱"})
    assert resp.status_code == 404
