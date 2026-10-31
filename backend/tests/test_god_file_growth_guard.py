"""AGENTS.md 规则 4 的机器门禁：上帝文件只减不增。

规则 4 点名的 5 个上帝文件已在历史重构中瘦身（如 graph/nodes/synthesize.py
2718 -> 563 行）。本测试把它们的当前行数锁为硬顶，防止复杂度重新长回去。

复杂度同时转移到了三个规则 4 清单之外的新大文件（deep_search_agent /
execute_plan_stub / synthesize_render_vars），是下一个"上帝文件"的候选，
一并纳入监管。

超限时的正确动作：把新功能放进独立模块（AGENTS.md 规则 4），
不要改这里的数字来放行；确需上调基线，须在 PR 描述中给出拆分计划。
"""
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]

# 路径相对 backend/，值为允许的最大行数（含）。
# handlers/chat_handler.py 已在重构中删除：上限 0 意为"不许复活"。
_GROWTH_LIMITS = {
    # 规则 4 原名单（已瘦身，锁顶防回流）
    "graph/nodes/synthesize.py": 563,
    "graph/report_builder.py": 83,
    "tools/price.py": 334,
    "dashboard/data_service.py": 254,
    "handlers/chat_handler.py": 0,
    # 复杂度转移出的新大文件
    "agents/deep_search_agent.py": 1450,
    "graph/nodes/execute_plan_stub.py": 1118,
    "graph/nodes/synthesize_render_vars.py": 1056,
}


@pytest.mark.parametrize(
    "rel_path, max_lines", sorted(_GROWTH_LIMITS.items()), ids=list(_GROWTH_LIMITS)
)
def test_god_file_stays_within_limit(rel_path: str, max_lines: int) -> None:
    path = _BACKEND_ROOT / rel_path
    actual = len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0
    assert actual <= max_lines, (
        f"{rel_path} 增长到 {actual} 行，超过门禁上限 {max_lines}。"
        f"把新功能放进独立模块（AGENTS.md 规则 4：上帝文件只减不增）；"
        f"确需上调基线请在 PR 中给出拆分计划。"
    )
