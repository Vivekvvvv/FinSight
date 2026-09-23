# -*- coding: utf-8 -*-
"""_match_report_value：完整 concept 名匹配必须优先于子串命中。

bug：concept 分支用 ``term in concept`` 子串匹配——concept_terms=("assets",)
会命中 us-gaap_OtherAssetsCurrent / us-gaap_AssetsCurrent 等分项概念。
Finnhub financials-reported 的 bs 行按报表呈现顺序排列（分项恒在合计之前），
first-match 使 total_assets/total_liabilities 返回分项小计值而非合计。

修复：第一遍只认标签子串或规范化 concept 全等（剥掉 us-gaap_ 等命名空间），
宽松子串降为第二遍兜底，保留 salesrevenuenet / revenuefromcontract…tax 等
无关键词标签变体的既有命中。
"""
from __future__ import annotations

from backend.dashboard import data_providers

# 按真实分类资产负债表呈现顺序：分项在前、合计在后
_BS_ROWS = [
    {"concept": "us-gaap_CashAndCashEquivalentsAtCarryingValue", "label": "Cash and cash equivalents", "value": 30.0},
    {"concept": "us-gaap_ShortTermInvestments", "label": "Marketable securities", "value": 20.0},
    {"concept": "us-gaap_OtherAssetsCurrent", "label": "Other current assets", "value": 10.0},
    {"concept": "us-gaap_AssetsCurrent", "label": "Total current assets", "value": 90.0},
    {"concept": "us-gaap_PropertyPlantAndEquipmentNet", "label": "Property, plant and equipment, net", "value": 40.0},
    {"concept": "us-gaap_OtherAssetsNoncurrent", "label": "Other non-current assets", "value": 20.0},
    {"concept": "us-gaap_Assets", "label": "Total assets", "value": 150.0},
    {"concept": "us-gaap_LiabilitiesCurrent", "label": "Total current liabilities", "value": 60.0},
    {"concept": "us-gaap_LongTermDebt", "label": "Long-term debt", "value": 30.0},
    {"concept": "us-gaap_Liabilities", "label": "Total liabilities", "value": 90.0},
    {"concept": "us-gaap_LiabilitiesAndStockholdersEquity", "label": "Total liabilities and equity", "value": 150.0},
]

_IC_ROWS = [
    {"concept": "us-gaap_Revenues", "label": "Revenues", "value": 200.0},
    {"concept": "us-gaap_GrossProfit", "label": "Gross profit", "value": 80.0},
    {"concept": "us-gaap_OperatingIncomeLoss", "label": "Operating income", "value": 40.0},
    {"concept": "us-gaap_NetIncomeLoss", "label": "Net income", "value": 30.0},
    {"concept": "us-gaap_EarningsPerShareBasic", "label": "Earnings per share, basic", "value": 1.5},
    {"concept": "us-gaap_EarningsPerShareDiluted", "label": "Earnings per share, diluted", "value": 1.4},
]

_CF_ROWS = [
    {"concept": "us-gaap_NetCashProvidedByUsedInOperatingActivities", "label": "Net cash provided by operating activities", "value": 35.0},
    {"concept": "us-gaap_PaymentsToAcquirePropertyPlantAndEquipment", "label": "Payments to acquire property, plant and equipment", "value": -8.0},
]


def _payload() -> dict:
    return {
        "data": [
            {
                "year": 2025,
                "quarter": 3,
                "report": {"bs": _BS_ROWS, "ic": _IC_ROWS, "cf": _CF_ROWS},
            }
        ]
    }


def test_bs_totals_return_total_not_component(monkeypatch):
    """分项行在合计行之前时，total_assets/total_liabilities 必须取合计。"""
    monkeypatch.setattr(data_providers, "_finnhub_request", lambda *a, **k: _payload())
    result = data_providers._fetch_financial_statements_from_finnhub("AAPL")
    assert result is not None
    # 修复前：total_assets=10.0 (OtherAssetsCurrent)、total_liabilities=60.0 (LiabilitiesCurrent)
    assert result["total_assets"] == [150.0]
    assert result["total_liabilities"] == [90.0]
    # 回归：标签匹配与完整 concept 名匹配不受影响
    assert result["revenue"] == [200.0]          # "us-gaap_Revenues" 经 label 命中
    assert result["gross_profit"] == [80.0]
    assert result["operating_income"] == [40.0]
    assert result["net_income"] == [30.0]
    assert result["operating_cash_flow"] == [35.0]
    assert result["free_cash_flow"] == [27.0]    # 35 + (-8)，capex<0 → ocf+capex


def test_match_report_value_exact_concept_beats_earlier_substring():
    """行间优先级：后出现的完整 concept 命中 > 先出现的子串命中。"""
    rows = [
        {"concept": "us-gaap_OtherAssetsCurrent", "label": "", "value": 10.0},
        {"concept": "us-gaap_AssetsCurrent", "label": "", "value": 90.0},
        {"concept": "us-gaap_Assets", "label": "", "value": 150.0},
    ]
    assert data_providers._match_report_value(rows, concept_terms=("assets",)) == 150.0


def test_match_report_value_substring_fallback_for_variant_concepts():
    """无关键词标签 + 变体 concept 名仍靠子串兜底命中（行为保持）。"""
    rows = [
        {"concept": "us-gaap_SalesRevenueNet", "label": "Turnover", "value": 77.0},
    ]
    assert data_providers._match_report_value(
        rows,
        label_terms=("net sales", "total revenue", "revenue"),
        concept_terms=("revenue", "salesrevenue"),
    ) == 77.0


def test_match_report_value_namespaced_exact_concept():
    rows = [{"concept": "ifrs-full_Liabilities", "label": "", "value": 5.0}]
    assert data_providers._match_report_value(rows, concept_terms=("liabilities",)) == 5.0
