# -*- coding: utf-8 -*-
"""run_rag_quality._save_json 必须原子写——baseline.json 是漂移门控的持久参照，
truncate-write 中途崩溃会留下损坏基线，下一次 _load_json 直接炸掉整场评估。"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "tests" / "rag_quality" / "run_rag_quality.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_rag_quality", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # @dataclass 处理字符串注解时会按 cls.__module__ 反查 sys.modules，必须先注册
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_save_json_writes_content(tmp_path):
    module = _load_module()
    target = tmp_path / "baseline.json"
    module._save_json({"overall_metrics": {"faithfulness": 0.9}}, target)
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded["overall_metrics"]["faithfulness"] == 0.9


def test_save_json_replaces_existing_atomically(tmp_path):
    module = _load_module()
    target = tmp_path / "baseline.json"
    target.write_text('{"old": true}', encoding="utf-8")
    module._save_json({"new": 1}, target)
    assert json.loads(target.read_text(encoding="utf-8")) == {"new": 1}
    assert not list(tmp_path.glob("*.tmp"))


def test_save_json_mid_write_failure_keeps_original(tmp_path, monkeypatch):
    module = _load_module()
    target = tmp_path / "baseline.json"
    original = b'{"overall_metrics": {"faithfulness": 0.9}}'
    target.write_bytes(original)

    def flaky_dump(data, f, **kwargs):
        f.write('{"partial":')  # 半截内容落盘后才崩溃
        raise OSError("simulated disk failure")

    monkeypatch.setattr(module.json, "dump", flaky_dump)
    with pytest.raises(OSError):
        module._save_json({"new": 1}, target)
    assert target.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))
