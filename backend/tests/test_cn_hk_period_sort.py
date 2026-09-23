# -*- coding: utf-8 -*-
"""_period_sort_key：年报 FY 必须按报告期末（12-31）排在当年 Q4 位置。

bug：FY 映射为 (year, 0)，在 reverse=True 排序下排在当年 Q1/Q2/Q3 之后——
年报（REPORT_DATE=12-31，晚于三季报 09-30）被排到同一年所有季报之后，
periods[0] 变成 Q3 而非 FY，最新年报被当成最旧一期；切片 [:target_periods]
还可能把 FY 挤出窗口。FY 是年度第 4 个报告期，应按 (year, 4) 参与排序。
"""
from __future__ import annotations

from backend.tools import cn_hk_market


def _income_row(report_date: str, report_type: str, revenue: float) -> dict:
    return {
        "REPORT_DATE": report_date,
        "REPORT_TYPE": report_type,
        "TOTAL_OPERATE_INCOME": revenue,
    }


def _rows_by_report_name(rows):
    def _fetch(report_name: str, secu_code: str, limit: int):
        if report_name == "RPT_F10_FINANCE_GINCOME":
            return rows
        return []
    return _fetch


def test_fy_sorts_as_latest_period(monkeypatch):
    """2025 年报(12-31)应排在 2025Q3/Q2/Q1 之前，成为 periods[0]。"""
    income_rows = [
        # 东财按 REPORT_DATE desc 返回：年报在前
        _income_row("2025-12-31 00:00:00", "年报", 1000.0),
        _income_row("2025-09-30 00:00:00", "三季报", 750.0),
        _income_row("2025-06-30 00:00:00", "中报", 500.0),
        _income_row("2025-03-31 00:00:00", "一季报", 250.0),
        _income_row("2024-12-31 00:00:00", "年报", 900.0),
    ]
    monkeypatch.setattr(
        cn_hk_market, "_fetch_finance_rows", _rows_by_report_name(income_rows)
    )

    result = cn_hk_market.fetch_cn_hk_financial_statements("600519.SS", periods=5)

    assert result is not None
    # 修复前：["2025Q3","2025Q2","2025Q1","2025FY","2024FY"] —— 年报垫底
    assert result["periods"][0] == "2025FY"
    assert result["periods"] == ["2025FY", "2025Q3", "2025Q2", "2025Q1", "2024FY"]
    # 指标数组与期间同序：最新值应是年报口径
    assert result["revenue"][0] == 1000.0


def test_fy_not_dropped_by_period_window(monkeypatch):
    """FY 不应因排错位置而被 [:periods] 窗口截掉。"""
    income_rows = [
        _income_row("2025-12-31 00:00:00", "年报", 100.0),
        _income_row("2025-09-30 00:00:00", "三季报", 90.0),
        _income_row("2025-06-30 00:00:00", "中报", 80.0),
        _income_row("2025-03-31 00:00:00", "一季报", 70.0),
        _income_row("2024-12-31 00:00:00", "年报", 60.0),
        _income_row("2024-09-30 00:00:00", "三季报", 50.0),
        _income_row("2024-06-30 00:00:00", "中报", 40.0),
        _income_row("2024-03-31 00:00:00", "一季报", 30.0),
    ]
    monkeypatch.setattr(
        cn_hk_market, "_fetch_finance_rows", _rows_by_report_name(income_rows)
    )

    result = cn_hk_market.fetch_cn_hk_financial_statements("600519.SS", periods=4)

    assert result is not None
    # 修复前 FY 排到 2025 三个季度之后，periods=4 窗口恰好把它挤出
    assert "2025FY" in result["periods"]
    assert result["periods"][0] == "2025FY"


def test_period_sort_key_orders():
    """排序键本身：FY 应等价于同年的第 4 报告期。"""
    keys = ["2025FY", "2025Q3", "2025Q2", "2025Q1", "2024FY", "2024Q4"]
    ordered = sorted(keys, key=cn_hk_market._period_sort_key, reverse=True)
    assert ordered[0] in {"2025FY", "2024Q4"} or ordered[0] == "2025FY"
    assert ordered.index("2025FY") < ordered.index("2025Q3")
    assert ordered.index("2025FY") < ordered.index("2025Q1")
