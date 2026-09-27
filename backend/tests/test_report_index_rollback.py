# -*- coding: utf-8 -*-
"""rollback 恢复必须原子：原地 open('wb') 截断写入在中途失败时把
db_path 留成部分残件——回滚工具自身成为打坏生产库的源头（规则1）。"""
from __future__ import annotations

import builtins
import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "report_index_rollback.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("report_index_rollback", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_rollback_restores_backup_bytes(tmp_path):
    module = _load_module()
    db_path = tmp_path / "report_index.sqlite"
    backup = tmp_path / "report_index.sqlite.pre_migration.bak"
    db_path.write_bytes(b"new-schema-bytes")
    backup.write_bytes(b"old-schema-bytes")

    result = module.run_rollback(db_path=db_path, backup_path=backup)

    assert result["ok"] is True
    assert db_path.read_bytes() == b"old-schema-bytes"


def test_rollback_write_failure_leaves_db_intact(tmp_path, monkeypatch):
    """写入中途抛非 PermissionError（磁盘满/IO 错不会被重试循环兜住）时，
    原 db 必须保持完整——原地截断写入会在异常点留下部分残件。"""
    module = _load_module()
    db_path = tmp_path / "report_index.sqlite"
    backup = tmp_path / "report_index.sqlite.pre_migration.bak"
    db_path.write_bytes(b"original-live-db")
    backup.write_bytes(b"full-backup-bytes")

    real_open = builtins.open

    def flaky_open(file, mode="r", *args, **kwargs):
        name = str(file)
        if "w" in mode and (name.endswith(".sqlite") or ".tmp" in name):
            real_handle = real_open(file, mode, *args, **kwargs)

            class _Wrapper:
                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    real_handle.close()
                    return False

                def write(self, data):
                    # 写前 4 字节再炸——落盘残件，证明真实文件被污染路径
                    real_handle.write(bytes(data)[:4])
                    real_handle.flush()
                    raise OSError("simulated mid-write failure")

            return _Wrapper()
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", flaky_open)

    with pytest.raises(OSError):
        module.run_rollback(db_path=db_path, backup_path=backup)

    assert db_path.read_bytes() == b"original-live-db"
