# -*- coding: utf-8 -*-
"""fetch_holidays.py 写回 cn_holiday.py 必须原子（规则1）：
该文件被 backend 运行时 import（historical_data_store/smart_cache），
原地 write_text 中途崩溃会留下截断的 .py → import 失败、后端起不来。"""
from __future__ import annotations

import builtins
import importlib.util
from datetime import date
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "fetch_holidays.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("fetch_holidays", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _make_cn_holiday_file(tmp_path: Path) -> Path:
    file_path = tmp_path / "cn_holiday.py"
    file_path.write_text(
        "from datetime import date\n"
        "\n"
        "CN_HOLIDAYS = {\n"
        '    date(2025, 1, 1): "元旦",\n'
        "}\n"
        "\n"
        "WORKDAY_OVERRIDES = {\n"
        '    date(2025, 1, 26): "春节前调休",\n'
        "}\n",
        encoding="utf-8",
    )
    return file_path


def test_update_cn_holiday_file_inserts_entries(tmp_path):
    module = _load_module()
    file_path = _make_cn_holiday_file(tmp_path)

    holidays = {date(2027, 10, 1): "国庆节", date(2027, 10, 2): "国庆节"}
    workdays = {date(2027, 9, 26): "国庆前调休"}
    module.update_cn_holiday_file(holidays, workdays, 2027, file_path=file_path)

    content = file_path.read_text(encoding="utf-8")
    # 原有条目保留
    assert 'date(2025, 1, 1): "元旦"' in content
    # 新节假日/调休块已插入
    assert 'date(2027, 10, 1): "国庆节"' in content
    assert 'date(2027, 10, 2): "国庆节"' in content
    assert 'date(2027, 9, 26): "国庆前调休"' in content
    # 结果仍是可编译的 Python（防止块位置错位产出坏文件）
    compile(content, str(file_path), "exec")


def test_update_cn_holiday_file_mid_write_failure_keeps_original(tmp_path, monkeypatch):
    """content 写入 temp 中途抛 OSError（磁盘满/被杀）时，原 .py 必须字节不变。"""
    module = _load_module()
    file_path = _make_cn_holiday_file(tmp_path)
    original = file_path.read_text(encoding="utf-8")

    real_open = builtins.open

    def flaky_open(file, mode="r", *args, **kwargs):
        if "w" in mode and str(file).endswith(".tmp"):
            real_handle = real_open(file, mode, *args, **kwargs)

            class _Wrapper:
                def __enter__(self):
                    return self

                def __exit__(self, *exc):
                    real_handle.close()
                    return False

                def write(self, data):
                    real_handle.write(data[:4])
                    real_handle.flush()
                    raise OSError("simulated mid-write failure")

                def flush(self):
                    real_handle.flush()

            return _Wrapper()
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", flaky_open)

    with pytest.raises(OSError):
        module.update_cn_holiday_file(
            {date(2027, 10, 1): "国庆节"}, {}, 2027, file_path=file_path
        )

    assert file_path.read_text(encoding="utf-8") == original
    # 失败路径不得把半截 temp 留在目标旁边（best-effort unlink）
    assert not list(tmp_path.glob("*.tmp"))
