# -*- coding: utf-8 -*-
import json
import os
from pathlib import Path

import pytest

# Keep test runtime deterministic and avoid async sqlite destructor noise in
# short-lived TestClient lifecycles unless a test explicitly overrides backend.
os.environ.setdefault("LANGGRAPH_CHECKPOINTER_BACKEND", "memory")
os.environ.setdefault("LANGGRAPH_CHECKPOINTER_ALLOW_MEMORY_FALLBACK", "true")
os.environ.setdefault("DEV_MODE", "1")
# MemoryService 默认相对路径 data/memory 随进程 CWD 解析——pytest 从
# backend/ 运行时应用读写 backend/data/memory，而下方重置 fixture 固定写
# repo_root/data/memory（parents[2]），两侧根本不是同一目录：fixture 重置
# 从未触及应用真实文件，test_api_user* 残留上一轮写入让首轮之后每轮必挂。
# 统一指到 repo_root/data/memory（= 生产从 repo 根运行的解析结果）。
os.environ.setdefault(
    "MEMORY_STORAGE_PATH",
    str(Path(__file__).resolve().parents[2] / "data" / "memory"),
)


@pytest.fixture(autouse=True)
def _force_langgraph_deterministic_defaults(monkeypatch):
    """
    Tests must be deterministic and must NOT call external LLMs/tools by default.

    Individual tests can override these env vars when explicitly testing LLM/tool modes.
    """

    monkeypatch.setenv("LANGGRAPH_PLANNER_MODE", "stub")
    monkeypatch.setenv("LANGGRAPH_SYNTHESIZE_MODE", "stub")
    monkeypatch.setenv("LANGGRAPH_EXECUTE_LIVE_TOOLS", "false")
    monkeypatch.setenv("ENABLE_LANGSMITH", "false")


@pytest.fixture(autouse=True)
def _reset_api_memory_test_fixtures():
    """
    Some API tests persist user profiles/watchlists to `data/memory/*.json`.
    Reset them before each test to avoid order-dependence and dirty working trees.
    Teardown removes ALL test_api_user* files to prevent pollution.
    """

    repo_root = Path(__file__).resolve().parents[2]
    memory_dir = repo_root / "data" / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)

    _default_profile = {
        "risk_tolerance": "medium",
        "investment_style": "balanced",
        "watchlist": [],
        "preferences": {},
        "last_active": "2026-02-03T00:00:00Z",
    }

    for uid in ("test_api_user", "test_api_user_wl", "test_api_user_agent_prefs"):
        (memory_dir / f"{uid}.json").write_text(
            json.dumps({**_default_profile, "user_id": uid}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    yield

    # Teardown: remove ALL test_api_user* files to prevent pollution
    for f in memory_dir.glob("test_api_user*.json"):
        f.unlink(missing_ok=True)
