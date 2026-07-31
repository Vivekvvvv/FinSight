# -*- coding: utf-8 -*-
"""持久化损坏保护回归测试（CLAUDE.md 规则 2）。

读到损坏的 JSON 存储文件时，必须先备份为 *.corrupt 再回退默认值，
禁止静默回退导致下一次写入把用户数据永久覆盖。
参照 backend/services/memory.py 的同类修复。
"""
from __future__ import annotations

import pytest


def test_subscription_store_backs_up_corrupt_file(tmp_path, monkeypatch):
    from backend.services import subscription_service as mod

    corrupt_file = tmp_path / "subscriptions.json"
    corrupt_file.write_text("{ not valid json", encoding="utf-8")
    monkeypatch.setattr(mod, "SUBSCRIPTIONS_FILE", corrupt_file)

    svc = mod.SubscriptionService()
    assert svc.subscriptions == {}

    backups = list(tmp_path.glob("subscriptions.json.*.corrupt"))
    assert len(backups) == 1
    backup = backups[0]
    assert backup.read_text(encoding="utf-8") == "{ not valid json"

    # 后续写入生成新文件，损坏原文保留在备份里可人工恢复
    assert svc.subscribe("user@example.com", "AAPL") is True
    assert backup.read_text(encoding="utf-8") == "{ not valid json"
    assert svc.get_subscriptions("user@example.com")


@pytest.mark.parametrize(
    "corrupt_payload",
    ["[[[ broken", '{"alice":{"plan":"pro","weight":NaN}}'],
)
def test_entitlements_store_backs_up_corrupt_file(tmp_path, corrupt_payload):
    from backend.services import entitlements as ent

    original_path = ent.PLANS_FILE
    try:
        corrupt_file = tmp_path / "user_plans_test.json"
        corrupt_file.write_text(corrupt_payload, encoding="utf-8")
        ent.PLANS_FILE = corrupt_file
        ent.reset_entitlements_service_for_tests()

        svc = ent.get_entitlements_service()
        assert svc.get_plan("alice") == "free"

        backups = list(tmp_path.glob("user_plans_test.json.*.corrupt"))
        assert len(backups) == 1
        backup = backups[0]
        assert backup.read_text(encoding="utf-8") == corrupt_payload

        # 写入新 plan 不触碰备份
        svc.set_plan("alice", "pro", source="test")
        assert backup.read_text(encoding="utf-8") == corrupt_payload
        assert svc.get_plan("alice") == "pro"
    finally:
        ent.PLANS_FILE = original_path
        ent.reset_entitlements_service_for_tests()
