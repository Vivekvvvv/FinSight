# -*- coding: utf-8 -*-
"""get_financial_statements_summary 必须能按 str(列名) 取到 data 记录里的值。

bug：_to_payload 把 columns/index 字符串化，但 data 记录保留原始列标签
（yfinance 报表列是 pd.Timestamp）。summary 里 data[idx].get(latest_year)
拿字符串列名查 Timestamp 键——hash 不同永远命中默认值 'N/A'，所有指标行
被静默跳过，摘要只剩表头和日期。SEC 兜底 _build_table_payload 的键本来
就是字符串列名，说明 _to_payload 缺同一归一。

修复后 NaN 单元格也必须被 safe_float 挡掉，否则解禁的查找会输出 "$nanM"。
"""
from __future__ import annotations

import pandas as pd
import pytest

from backend.tools import financial


class _FakeTicker:
    """模拟 yfinance 报表：列是 DatetimeIndex（Timestamp），与生产一致。"""

    def __init__(self):
        cols = pd.DatetimeIndex([pd.Timestamp("2025-06-30"), pd.Timestamp("2024-06-30")])
        self.financials = pd.DataFrame(
            [[100e9, 90e9], [20e9, 18e9]],
            index=["Total Revenue", "Net Income"],
            columns=cols,
        )
        self.balance_sheet = pd.DataFrame(
            [[300e9, 280e9]],
            index=["Total Assets"],
            columns=cols,
        )
        self.cashflow = pd.DataFrame(
            [[30e9, 28e9]],
            index=["Operating Cash Flow"],
            columns=cols,
        )
        # quarterly_* 属性不存在 → getattr 抛 AttributeError 被候选循环捕获


def test_summary_renders_metric_rows_for_timestamp_columns(monkeypatch):
    monkeypatch.setattr(financial.yf, "Ticker", lambda _t: _FakeTicker())

    summary = financial.get_financial_statements_summary("FAKE")

    assert "Total Revenue" in summary
    # 最新年份 Total Revenue = 100e9 → "$100.00B"；键不匹配时整行缺失
    assert "$100.00B" in summary
    assert "$300.00B" in summary  # Total Assets
    assert "$30.00B" in summary   # Operating Cash Flow


def test_summary_skips_nan_cells(monkeypatch):
    """NaN 单元格不得输出 "$nanM"（解禁查找后否则会漏出脏文本）。"""

    class _NanTicker(_FakeTicker):
        def __init__(self):
            super().__init__()
            cols = self.financials.columns
            self.cashflow = pd.DataFrame(
                [[float("nan"), 28e9]],
                index=["Operating Cash Flow"],
                columns=cols,
            )

    monkeypatch.setattr(financial.yf, "Ticker", lambda _t: _NanTicker())

    summary = financial.get_financial_statements_summary("FAKE")

    assert "nan" not in summary.lower()
    # 其余表仍正常输出
    assert "$100.00B" in summary
