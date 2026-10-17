from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"


def _backend_env_value(text: str, key: str) -> str:
    match = re.search(rf"^      {re.escape(key)}:\s*(.+?)\s*$", text, re.MULTILINE)
    assert match, f"docker-compose.yml backend environment 缺少 {key}"
    return match.group(1)


def test_backend_persists_report_index_outside_tmpfs():
    """报告索引必须落在持久卷 /app/data，而不是重启即清空的 /app/backend/data。"""
    value = _backend_env_value(COMPOSE_PATH.read_text(encoding="utf-8"), "REPORT_INDEX_SQLITE_PATH")
    assert "/app/data/report_index.sqlite" in value
    assert "/app/backend/data" not in value


def test_backend_persists_langgraph_checkpoints_outside_tmpfs():
    """LangGraph checkpoint 必须落在持久卷 /app/data，否则重启后待确认/进行中的会话全部丢失。"""
    value = _backend_env_value(
        COMPOSE_PATH.read_text(encoding="utf-8"), "LANGGRAPH_CHECKPOINT_SQLITE_PATH"
    )
    assert "/app/data/langgraph/checkpoints.sqlite" in value
    assert "/app/backend/data" not in value


def test_compose_keeps_app_data_on_a_persistent_volume():
    text = COMPOSE_PATH.read_text(encoding="utf-8")
    assert "- backend_data:/app/data" in text
    # /app/backend/data 仍作为 tmpfs 存在（临时文件用），但不能承载上述持久化数据。
    assert "/app/backend/data" in text
