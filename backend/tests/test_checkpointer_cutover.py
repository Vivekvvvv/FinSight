from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.services import checkpointer_cutover


def test_sqlite_precheck_error_is_redacted(monkeypatch):
    secret = "PRIVATE C:/secret/checkpointer.sqlite"
    monkeypatch.setattr(
        checkpointer_cutover,
        "_probe_backend",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    result = checkpointer_cutover.run_checkpointer_cutover_drill(
        sqlite_path="state.sqlite",
        postgres_dsn="postgresql://example.invalid/db",
    )

    assert result["steps"][0]["error"] == "RuntimeError"
    assert secret not in str(result)


def test_postgres_cutover_error_is_redacted(monkeypatch):
    secret = "PRIVATE postgresql connection detail"

    def _probe_backend(**kwargs):
        if kwargs["backend"] == "postgres":
            raise RuntimeError(secret)
        return {"backend": kwargs["backend"]}

    monkeypatch.setattr(checkpointer_cutover, "_probe_backend", _probe_backend)

    result = checkpointer_cutover.run_checkpointer_cutover_drill(
        sqlite_path="state.sqlite",
        postgres_dsn="postgresql://example.invalid/db",
    )

    postgres_step = next(step for step in result["steps"] if step["step"] == "postgres_cutover")
    assert postgres_step["error"] == "RuntimeError"
    assert secret not in str(result)


def test_sqlite_rollback_error_is_redacted(monkeypatch):
    secret = "PRIVATE C:/secret/rollback.sqlite"
    sqlite_calls = {"count": 0}

    def _probe_backend(**kwargs):
        if kwargs["backend"] == "sqlite":
            sqlite_calls["count"] += 1
            if sqlite_calls["count"] == 2:
                raise RuntimeError(secret)
        return {"backend": kwargs["backend"]}

    monkeypatch.setattr(checkpointer_cutover, "_probe_backend", _probe_backend)

    result = checkpointer_cutover.run_checkpointer_cutover_drill(
        sqlite_path="state.sqlite",
        postgres_dsn="postgresql://example.invalid/db",
    )

    rollback_step = next(step for step in result["steps"] if step["step"] == "sqlite_rollback")
    assert rollback_step["error"] == "RuntimeError"
    assert secret not in str(result)


def test_run_checkpointer_cutover_drill_success(monkeypatch):
    calls: list[str] = []

    def fake_probe_backend(*, backend: str, sqlite_path: str, postgres_dsn: str, pipeline: bool, allow_fallback: bool):
        calls.append(backend)
        return {
            'backend': backend,
            'persistent': backend in {'sqlite', 'postgres'},
            'fallback_used': False,
            'fallback_reason': None,
            'location': sqlite_path if backend == 'sqlite' else 'postgresql://***@localhost:5432/finsight',
        }

    monkeypatch.setattr(checkpointer_cutover, '_probe_backend', fake_probe_backend)

    result = checkpointer_cutover.run_checkpointer_cutover_drill(
        sqlite_path='data/langgraph/checkpoints.sqlite',
        postgres_dsn='postgresql://user:pass@localhost:5432/finsight',
        pipeline=True,
        allow_fallback=False,
    )

    assert result['ok'] is True
    assert calls == ['sqlite', 'postgres', 'sqlite']
    assert [step['status'] for step in result['steps']] == ['pass', 'pass', 'pass']
    assert result['config']['postgres_dsn'].startswith('postgresql://***@')


def test_run_checkpointer_cutover_drill_postgres_failure(monkeypatch):
    calls: list[str] = []

    def fake_probe_backend(*, backend: str, sqlite_path: str, postgres_dsn: str, pipeline: bool, allow_fallback: bool):
        calls.append(backend)
        if backend == 'postgres':
            raise RuntimeError('postgres unavailable')
        return {
            'backend': backend,
            'persistent': True,
            'fallback_used': False,
            'fallback_reason': None,
            'location': sqlite_path,
        }

    monkeypatch.setattr(checkpointer_cutover, '_probe_backend', fake_probe_backend)

    result = checkpointer_cutover.run_checkpointer_cutover_drill(
        sqlite_path='data/langgraph/checkpoints.sqlite',
        postgres_dsn='postgresql://user:pass@localhost:5432/finsight',
    )

    assert result['ok'] is False
    assert calls == ['sqlite', 'postgres', 'sqlite']
    assert result['steps'][1]['step'] == 'postgres_cutover'
    assert result['steps'][1]['status'] == 'failed'
    assert result['steps'][1]['error'] == 'RuntimeError'


def test_write_checkpointer_drill_evidence(tmp_path: Path):
    payload = {
        'ok': True,
        'steps': [{'step': 'sqlite_precheck', 'status': 'pass'}],
    }
    out = tmp_path / 'evidence' / 'checkpointer_switch_drill.json'

    actual = checkpointer_cutover.write_checkpointer_drill_evidence(payload, out)

    assert actual == out.resolve()
    loaded = json.loads(actual.read_text(encoding='utf-8'))
    assert loaded['ok'] is True
    assert loaded['steps'][0]['step'] == 'sqlite_precheck'
    # 原子替换（审计 D4）：不留 .tmp 残留，且覆盖已有文件时同样干净
    assert not list(out.parent.glob('*.tmp'))
    checkpointer_cutover.write_checkpointer_drill_evidence({'ok': False}, out)
    assert json.loads(out.read_text(encoding='utf-8'))['ok'] is False
    assert not list(out.parent.glob('*.tmp'))


def test_write_checkpointer_drill_evidence_preserves_existing_file_on_replace_failure(
    tmp_path: Path,
    monkeypatch,
):
    out = tmp_path / "evidence.json"
    out.write_text('{"ok": true}', encoding="utf-8")

    def fail_replace(_source, _target):
        raise OSError("replace failed")

    monkeypatch.setattr(checkpointer_cutover.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        checkpointer_cutover.write_checkpointer_drill_evidence({"ok": False}, out)

    assert json.loads(out.read_text(encoding="utf-8"))["ok"] is True
    assert not list(tmp_path.glob("*.tmp"))


def test_write_checkpointer_drill_evidence_rejects_non_finite_payload(
    tmp_path: Path,
):
    out = tmp_path / "evidence.json"
    out.write_text('{"ok": true}', encoding="utf-8")

    with pytest.raises(ValueError, match="Out of range float values"):
        checkpointer_cutover.write_checkpointer_drill_evidence(
            {"latency_ms": float("nan")},
            out,
        )

    assert out.read_text(encoding="utf-8") == '{"ok": true}'
    assert not list(tmp_path.glob("*.tmp"))
