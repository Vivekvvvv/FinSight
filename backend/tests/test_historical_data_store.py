# -*- coding: utf-8 -*-
"""
tests/test_historical_data_store.py
单元测试：A股历史K线数据下载与缓存
"""
import pytest


# ── _to_bs_code 测试 ──────────────────────────────────────────────────────────

def test_to_bs_code_sh_600():
    from backend.services.historical_data_store import _to_bs_code
    assert _to_bs_code("600519.SS") == "sh.600519"


def test_to_bs_code_sh_601():
    from backend.services.historical_data_store import _to_bs_code
    assert _to_bs_code("601318.SS") == "sh.601318"


def test_to_bs_code_sh_688():
    from backend.services.historical_data_store import _to_bs_code
    assert _to_bs_code("688012.SS") == "sh.688012"


def test_to_bs_code_sz_000():
    from backend.services.historical_data_store import _to_bs_code
    assert _to_bs_code("000001.SZ") == "sz.000001"


def test_to_bs_code_sz_300():
    from backend.services.historical_data_store import _to_bs_code
    assert _to_bs_code("300750.SZ") == "sz.300750"


def test_to_bs_code_uppercase_suffix():
    from backend.services.historical_data_store import _to_bs_code
    assert _to_bs_code("600519.ss") == "sh.600519"


# ── _adjust_flag 测试 ─────────────────────────────────────────────────────────

def test_adjust_flag_qfq():
    from backend.services.historical_data_store import _adjust_flag
    assert _adjust_flag("qfq") == "2"


def test_adjust_flag_hfq():
    from backend.services.historical_data_store import _adjust_flag
    assert _adjust_flag("hfq") == "1"


def test_adjust_flag_none():
    from backend.services.historical_data_store import _adjust_flag
    assert _adjust_flag("none") == "3"


def test_adjust_flag_unknown_defaults_to_3():
    from backend.services.historical_data_store import _adjust_flag
    assert _adjust_flag("unknown") == "3"


# ── _clean 测试 ──────────────────────────────────────────────────────────────

def test_clean_removes_zero_close():
    from backend.services.historical_data_store import _clean
    rows = [
        {"date": "2024-01-02", "open": 10.0, "high": 11.0, "low": 9.0, "close": 0.0, "volume": 1000},
        {"date": "2024-01-03", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5, "volume": 1000},
    ]
    result = _clean(rows)
    assert all(r["close"] > 0 for r in result)
    assert len(result) == 1


def test_clean_removes_none_close():
    from backend.services.historical_data_store import _clean
    rows = [
        {"date": "2024-01-02", "open": 10.0, "high": 11.0, "low": 9.0, "close": None, "volume": 1000},
        {"date": "2024-01-03", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0, "volume": 1000},
    ]
    result = _clean(rows)
    assert len(result) == 1
    assert result[0]["close"] == 10.0


def test_clean_marks_suspicious_large_change():
    from backend.services.historical_data_store import _clean
    rows = [
        {"date": "2024-01-02", "open": 10.0, "high": 10.5, "low": 9.5, "close": 10.0, "volume": 1000},
        # 涨幅 >22%：10.0 → 12.5 = +25%
        {"date": "2024-01-03", "open": 12.0, "high": 13.0, "low": 11.5, "close": 12.5, "volume": 1000},
    ]
    result = _clean(rows)
    assert result[1]["is_suspicious"] is True


def test_clean_normal_change_not_suspicious():
    from backend.services.historical_data_store import _clean
    rows = [
        {"date": "2024-01-02", "open": 10.0, "high": 10.5, "low": 9.5, "close": 10.0, "volume": 1000},
        {"date": "2024-01-03", "open": 10.0, "high": 10.3, "low": 9.8, "close": 10.2, "volume": 1000},
    ]
    result = _clean(rows)
    assert result[1]["is_suspicious"] is False


def test_clean_empty_input():
    from backend.services.historical_data_store import _clean
    assert _clean([]) == []
