# -*- coding: utf-8 -*-
"""_extract_metric_series：完整行名匹配必须优先于子串命中。

bug：行匹配用 ``any(candidate in row_name_lower ...)`` 按 index 顺序取第一个
子串命中行。operating_income 的候选含 "ebit" —— yfinance income_stmt 的
reconciliation 区块（Normalized EBITDA/Normalized Income 等）排在主表之前，
"normalized ebitda" 包含 "ebit" → 营业利润指标被 EBITDA 行劫持（数值系统性
偏高）。同理 "Cost Of Revenue" 若排在 "Total Revenue" 之前会劫持营收。

修复：第一遍只认规范化行名全等（strip+lower 后 == 候选词），宽松子串降为
第二遍兜底——与 data_providers._match_report_value 的修法同型。
"""
from __future__ import annotations

from backend.agents.fundamental_agent import FundamentalAgent

_COLUMNS = ["2025-09-30", "2025-06-30", "2025-03-31", "2024-12-31", "2024-09-30"]


def _row(*values):
    return {col: val for col, val in zip(_COLUMNS, values)}


def _agent() -> FundamentalAgent:
    return FundamentalAgent(llm=None, cache=None, tools_module=None)


def _normalized(index, data):
    financials = {
        "financials": {"columns": list(_COLUMNS), "index": index, "data": data},
        "balance_sheet": None,
        "cashflow": None,
    }
    return _agent()._build_normalized_metrics(financials)


def test_ebitda_row_before_operating_income_does_not_hijack_metric():
    """Normalized EBITDA 排在 Operating Income 前时，operating_income 仍取后者。"""
    index = [
        "Normalized EBITDA",          # 含 "ebit"，bug 下先命中
        "Operating Income",
        "Total Revenue",
        "Net Income",
    ]
    data = [
        _row(999.0, 990.0, 980.0, 970.0, 960.0),   # EBITDA（明显偏大）
        _row(100.0, 95.0, 90.0, 85.0, 80.0),       # Operating Income
        _row(500.0, 480.0, 460.0, 440.0, 420.0),
        _row(60.0, 55.0, 50.0, 45.0, 40.0),
    ]
    metrics = _normalized(index, data)["metrics"]
    # 修复前：latest=999.0（EBITDA 行被当作营业利润）
    assert metrics["operating_income"]["latest"] == 100.0


def test_cost_of_revenue_before_total_revenue_does_not_hijack_metric():
    """Cost Of Revenue 排在 Total Revenue 前时，revenue 仍取合计行。"""
    index = [
        "Cost Of Revenue",            # 含 "revenue"，bug 下先命中
        "Total Revenue",
        "Operating Income",
        "Net Income",
    ]
    data = [
        _row(300.0, 290.0, 280.0, 270.0, 260.0),   # 成本（负指标被当营收）
        _row(500.0, 480.0, 460.0, 440.0, 420.0),   # Total Revenue
        _row(100.0, 95.0, 90.0, 85.0, 80.0),
        _row(60.0, 55.0, 50.0, 45.0, 40.0),
    ]
    metrics = _normalized(index, data)["metrics"]
    # 修复前：latest=300.0（成本行被当作营收）
    assert metrics["revenue"]["latest"] == 500.0


def test_substring_fallback_still_matches_variant_row_names():
    """无全等行名时仍靠子串兜底（行为保持，不回退成找不到）。"""
    index = ["Operating Income Loss", "Total Revenue", "Net Income"]
    data = [
        _row(77.0, 70.0, 65.0, 60.0, 55.0),   # "operating income loss" 含 "operating income"
        _row(500.0, 480.0, 460.0, 440.0, 420.0),
        _row(60.0, 55.0, 50.0, 45.0, 40.0),
    ]
    metrics = _normalized(index, data)["metrics"]
    assert metrics["operating_income"]["latest"] == 77.0


def test_exact_ebit_row_still_matches():
    """无 Operating Income 行、存在独立 EBIT 行时仍可命中。"""
    index = ["Normalized EBITDA", "EBIT", "Total Revenue"]
    data = [
        _row(999.0, 990.0, 980.0, 970.0, 960.0),
        _row(88.0, 84.0, 80.0, 76.0, 72.0),    # 独立 "EBIT" 行应被全等命中
        _row(500.0, 480.0, 460.0, 440.0, 420.0),
    ]
    metrics = _normalized(index, data)["metrics"]
    assert metrics["operating_income"]["latest"] == 88.0
