# -*- coding: utf-8 -*-
"""本次改动涉及的是 env 模板，不是代码：钉住"模板不再预置 DEV_MODE=1"。

浏览器/部署方照抄 .env.example 是主流用法（文件头第 2 行就写着 "Copy this
file to .env"），而该模板曾把 DEV_MODE=1 作为默认值发出去——照抄即等于
拿到"整站无鉴权 + dev_principal 给 admin 角色 + 跳过全部 7 个生产
SystemExit fail-fast"的一份配置，只在启动日志里有一行 WARNING。

.dev.server.example 侧本来就没有 DEV_MODE，本用例把两侧一起钉住，
避免哪天又被"补全"回去。
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _assigned_keys(text: str) -> dict[str, str]:
    """返回模板里所有 `KEY=value` 形式的赋值（KEY 统一大写）。"""
    assigned: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        assigned[key.strip()] = value.strip()
    return assigned


def test_dev_flow_example_does_not_enable_dev_mode_by_default():
    assigned = _assigned_keys((REPO_ROOT / ".env.example").read_text(encoding="utf-8"))
    assert "DEV_MODE" in assigned, ".env.example 应保留 DEV_MODE 行并附注释说明如何开启"
    assert assigned["DEV_MODE"] == "", (
        "本地开发模板不得预置 DEV_MODE=1：照抄即跳过鉴权/限流/生产 fail-fast"
    )


def test_server_env_example_never_defines_dev_mode():
    assigned = _assigned_keys((REPO_ROOT / ".env.server.example").read_text(encoding="utf-8"))
    assert "DEV_MODE" not in assigned, "生产模板不得出现 DEV_MODE（哪怕是 0）"


def test_empty_dev_mode_is_parsed_as_disabled():
    """模板留空后必须真的关闭：env_bool 只认 1/true/yes/on。"""
    import os

    from backend.security.auth import env_bool, is_dev_mode

    original = os.environ.get("DEV_MODE")
    try:
        os.environ["DEV_MODE"] = ""
        assert env_bool("DEV_MODE", "false") is False
        assert is_dev_mode() is False
    finally:
        if original is None:
            os.environ.pop("DEV_MODE", None)
        else:
            os.environ["DEV_MODE"] = original
