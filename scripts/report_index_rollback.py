#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_db_path(raw: str | None) -> Path:
    path = (raw or os.getenv("REPORT_INDEX_SQLITE_PATH") or "backend/data/report_index.sqlite").strip()
    return Path(path).expanduser().resolve()


def _safe_unlink(path: Path, *, attempts: int = 20, sleep_seconds: float = 0.05) -> None:
    if not path.exists():
        return
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            path.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(sleep_seconds)
    if last_error is not None:
        raise last_error


def run_rollback(db_path: Path, backup_path: Path | None = None) -> dict[str, Any]:
    if backup_path is None:
        backup_path = db_path.with_suffix(db_path.suffix + ".pre_migration.bak")

    if not backup_path.exists():
        raise FileNotFoundError(f"backup not found: {backup_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    restored_from_backup = False

    backup_bytes = backup_path.read_bytes()
    temp_path = Path(f"{db_path}.rollback-{os.getpid()}.tmp")
    last_error: Exception | None = None
    for _ in range(20):
        try:
            # 原子恢复（规则1）：temp+fsync+os.replace——原地 open('wb') 截断式
            # 写入一旦中途失败/崩溃（磁盘满等不会被重试兜住），db_path 留成
            # 部分残件，回滚工具自己把生产库打坏。
            with open(temp_path, "wb") as handle:
                handle.write(backup_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            # sidecar 先于换主库清掉：否则崩溃窗口内恢复体会与旧 WAL 配对，
            # 下次打开把旧 wal 帧回放进备份库，造出混合态。
            for suffix in ('-wal', '-shm', '-journal'):
                try:
                    _safe_unlink(Path(f"{db_path}{suffix}"), attempts=1)
                except PermissionError:
                    # best effort cleanup; rollback result should not fail for sidecar locks
                    pass
            os.replace(temp_path, db_path)
            restored_from_backup = True
            break
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.05)

    if not restored_from_backup:
        try:
            temp_path.unlink()
        except OSError:
            pass
        if last_error is not None:
            # 目标库被进程持有句柄时 os.replace 在 Windows 上恒被拒——此时大声失败
            # 是对的：旧实现原地截断会把 live 连接已缓存的库覆写成备份字节，
            # 造成混合态。提示先停服/断连再回滚。
            raise PermissionError(
                f"无法原子替换 {db_path}：目标文件可能被进程占用，请先停止占用该库的服务再回滚"
            ) from last_error

    return {
        "ok": True,
        "db_path": str(db_path),
        "backup_path": str(backup_path),
        "restored_from_backup": restored_from_backup,
        "rolled_back_at": _now_iso(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Rollback report_index sqlite schema")
    parser.add_argument("--db", dest="db", default=None, help="SQLite path (default: REPORT_INDEX_SQLITE_PATH)")
    parser.add_argument(
        "--backup",
        dest="backup",
        default=None,
        help="Backup sqlite file path (default: <db>.pre_migration.bak)",
    )
    args = parser.parse_args()

    db_path = _resolve_db_path(args.db)
    backup_path = Path(args.backup).expanduser().resolve() if args.backup else None
    result = run_rollback(db_path=db_path, backup_path=backup_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
