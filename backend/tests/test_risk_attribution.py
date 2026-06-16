# -*- coding: utf-8 -*-
"""
tests/test_risk_attribution.py
单元测试：组合风险归因（OLS beta 回归）
"""
from unittest.mock import patch

import numpy as np
import pytest


# ── _ols_beta 测试 ────────────────────────────────────────────────────────────

def test_ols_beta_perfect_correlation():
    """完全正相关时 beta 应接近 1"""
    from backend.services.risk_attribution import _ols_beta
    rm = np.array([0.01, -0.02, 0.03, -0.01, 0.02] * 10, dtype=float)
    beta, idio = _ols_beta(rm, rm)
    assert abs(beta - 1.0) < 0.01
    assert idio < 1e-9


def test_ols_beta_zero_market_variance():
    """市场方差为零时不抛异常，beta 返回 1.0"""
    from backend.services.risk_attribution import _ols_beta
    rm_flat = np.zeros(50, dtype=float)
    rs = np.random.default_rng(42).normal(0, 0.01, 50)
    beta, idio = _ols_beta(rs, rm_flat)
    assert beta == 1.0


def test_ols_beta_double_return():
    """股票收益率是市场的 2 倍时，beta 应接近 2.0"""
    from backend.services.risk_attribution import _ols_beta
    rng = np.random.default_rng(0)
    rm = rng.normal(0, 0.01, 200)
    rs = 2.0 * rm
    beta, idio = _ols_beta(rs, rm)
    assert abs(beta - 2.0) < 0.05
    assert idio < 1e-9


# ── calculate_risk_attribution 测试 ──────────────────────────────────────────

def test_risk_attribution_empty_positions():
    """空持仓应返回 no_data 结果，不崩溃"""
    from backend.services.risk_attribution import calculate_risk_attribution
    result = calculate_risk_attribution([])
    assert result["method"] == "no_data"
    assert result["total_portfolio_vol"] == 0.0


def test_risk_attribution_zero_market_value():
    """市值均为0时应返回 no_data"""
    from backend.services.risk_attribution import calculate_risk_attribution
    result = calculate_risk_attribution([{"ticker": "AAPL", "market_value": 0}])
    assert result["method"] == "no_data"


def test_risk_attribution_simplified_when_no_market_data():
    """拉不到市场数据时应使用 simplified 方法，不抛异常"""
    from backend.services.risk_attribution import calculate_risk_attribution
    positions = [
        {"ticker": "600519.SS", "market_value": 100000, "sector": "消费"},
        {"ticker": "000858.SZ", "market_value": 50000, "sector": "消费"},
    ]
    with patch("backend.services.risk_attribution._fetch_returns", return_value=None):
        result = calculate_risk_attribution(positions)
    assert result["method"] == "simplified"
    assert isinstance(result["total_portfolio_vol"], float)
    assert len(result["positions"]) == 2


def test_risk_attribution_result_structure():
    """返回结构包含所有必需字段"""
    from backend.services.risk_attribution import calculate_risk_attribution
    positions = [{"ticker": "AAPL", "market_value": 10000, "sector": "科技"}]
    with patch("backend.services.risk_attribution._fetch_returns", return_value=None):
        result = calculate_risk_attribution(positions)
    for key in ("total_portfolio_vol", "market_risk_pct", "idiosyncratic_risk_pct",
                "positions", "sector_attribution", "method"):
        assert key in result


def test_risk_attribution_pct_sums_to_100():
    """市场风险% + 特质风险% 应等于 100"""
    from backend.services.risk_attribution import calculate_risk_attribution
    positions = [{"ticker": "AAPL", "market_value": 50000}]
    with patch("backend.services.risk_attribution._fetch_returns", return_value=None):
        result = calculate_risk_attribution(positions)
    total = round(result["market_risk_pct"] + result["idiosyncratic_risk_pct"], 1)
    assert abs(total - 100.0) < 0.2


def test_risk_attribution_sector_attribution():
    """行业归因包含对应的 sector 名"""
    from backend.services.risk_attribution import calculate_risk_attribution
    positions = [
        {"ticker": "A", "market_value": 60000, "sector": "金融"},
        {"ticker": "B", "market_value": 40000, "sector": "科技"},
    ]
    with patch("backend.services.risk_attribution._fetch_returns", return_value=None):
        result = calculate_risk_attribution(positions)
    sectors = {s["sector"] for s in result["sector_attribution"]}
    assert "金融" in sectors
    assert "科技" in sectors
