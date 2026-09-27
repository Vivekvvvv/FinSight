# -*- coding: utf-8 -*-
"""eval runner 的 save_json 必须原子写——baseline_layer*.json 是各层
门控跨 run 的持久参照，截断写中途崩溃留下半截 JSON，下次 _load_json
直接抛异常炸掉整场评估且基线无法恢复。"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC_MODULES = {
    "run_layer2_retrieval": PROJECT_ROOT / "tests" / "rag_quality" / "run_layer2_retrieval.py",
    "run_layer3_e2e": PROJECT_ROOT / "tests" / "rag_quality" / "run_layer3_e2e.py",
}


def _load_spec_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # @dataclass 处理字符串注解时会按 cls.__module__ 反查 sys.modules，必须先注册
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_engine_v2():
    tests_root = str(PROJECT_ROOT / "tests")
    if tests_root not in sys.path:
        sys.path.insert(0, tests_root)
    import rag_qualityV2.engine_v2 as engine_v2

    return engine_v2


def _modules():
    yield pytest.param(_load_spec_module("run_layer2_retrieval", SPEC_MODULES["run_layer2_retrieval"]), id="layer2")
    yield pytest.param(_load_spec_module("run_layer3_e2e", SPEC_MODULES["run_layer3_e2e"]), id="layer3")
    yield pytest.param(_load_engine_v2(), id="engine_v2")


def _save(module, data, path: Path) -> None:
    fn = getattr(module, "save_json", None) or getattr(module, "_save_json")
    fn(data, path)


@pytest.mark.parametrize("module", list(_modules()))
def test_save_json_writes_content(module, tmp_path):
    target = tmp_path / "baseline.json"
    _save(module, {"overall_metrics": {"faithfulness": 0.9}}, target)
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded["overall_metrics"]["faithfulness"] == 0.9


@pytest.mark.parametrize("module", list(_modules()))
def test_save_json_replaces_existing_atomically(module, tmp_path):
    target = tmp_path / "baseline.json"
    target.write_text('{"old": true}', encoding="utf-8")
    _save(module, {"new": 1}, target)
    assert json.loads(target.read_text(encoding="utf-8")) == {"new": 1}
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("module", list(_modules()))
def test_save_json_mid_write_failure_keeps_original(module, tmp_path, monkeypatch):
    target = tmp_path / "baseline.json"
    original = b'{"overall_metrics": {"faithfulness": 0.9}}'
    target.write_bytes(original)

    def flaky_dump(data, f, **kwargs):
        f.write('{"partial":')  # 半截内容落盘后才崩溃
        raise OSError("simulated disk failure")

    monkeypatch.setattr(module.json, "dump", flaky_dump)
    with pytest.raises(OSError):
        _save(module, {"new": 1}, target)
    assert target.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))
