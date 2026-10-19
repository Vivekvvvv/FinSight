# -*- coding: utf-8 -*-
"""data/memory 测试夹具的清理必须真的清掉，不能把失败留给下一个用例。

背景：`backend/tests/conftest.py::_reset_api_memory_test_fixtures` 的 teardown
原先对每个 `test_api_user*.json` 直接 `unlink`。当某个用例让这些文件删不掉
（Windows 上改 chmod / 只读属性后就地删除会抛 PermissionError），异常是在
teardown 里抛的：带 tmp_path 的用例把该异常记成自己的 ERROR，而残留文件又让
**随机顺序下无关的下一个用例**继续挂——随机顺序每次挂的用例编号都不一样，
看着像随机 flake，实则是真实缺陷被静默跨用例传播（项目规则 2）。
"""
import ctypes
import os
from pathlib import Path

import pytest

from backend.services.memory import reset_profiles


def _set_readonly(path: Path) -> None:
    """把文件置为只读属性（等价于 chmod a-w 在 Windows 上的表现）。"""
    k32 = ctypes.windll.kernel32
    k32.SetFileAttributesW.restype = ctypes.c_int
    attrs = k32.GetFileAttributesW(str(path))
    assert k32.SetFileAttributesW(str(path), attrs | 0x1) != 0


def _restore_writable(path: Path) -> None:
    k32 = ctypes.windll.kernel32
    k32.SetFileAttributesW.restype = ctypes.c_int
    k32.SetFileAttributesW(str(path), 0x80)


def test_readonly_profile_cannot_be_deleted_in_place(tmp_path):
    """先钉死失败模式本身：只读文件就地 unlink 抛 PermissionError 且文件仍在。"""
    reset_profiles(str(tmp_path), {"test_api_user_ro": {"user_id": "test_api_user_ro"}})
    target = tmp_path / "test_api_user_ro.json"
    _set_readonly(target)
    try:
        with pytest.raises(PermissionError):
            target.unlink(missing_ok=True)
        assert target.exists()
    finally:
        _restore_writable(target)


def test_memory_fixture_teardown_reports_leftover_instead_of_leaking(tmp_path):
    """删不掉的文件必须让 teardown 明确报错，而不是把污染留给后续用例。

    这里直接复刻 conftest 的清理逻辑（夹具本身没法在被它清理的目录里自测），
    断言"删不掉时报告 leftover"，"删得掉时不报"。
    """
    reset_profiles(str(tmp_path), {"test_api_user_x": {"user_id": "test_api_user_x"}})
    target = tmp_path / "test_api_user_x.json"
    _set_readonly(target)
    try:
        leftovers = []
        for f in tmp_path.glob("test_api_user*.json"):
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass
            if f.exists():
                leftovers.append(str(f))
        assert leftovers == [str(target)]
    finally:
        _restore_writable(target)

    # 恢复可写后同样的循环不应再报 leftover——否则夹具会持续误报。
    leftovers = []
    for f in tmp_path.glob("test_api_user*.json"):
        try:
            f.unlink(missing_ok=True)
        except OSError:
            pass
        if f.exists():
            leftovers.append(str(f))
    assert leftovers == []
