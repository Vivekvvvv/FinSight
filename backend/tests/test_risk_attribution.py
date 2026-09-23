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


def test_fetch_returns_filters_non_finite_closes():
    from backend.services.risk_attribution import _fetch_returns

    rows = [
        {"close": value}
        for value in ([100 + index for index in range(31)] + ["nan", "inf"])
    ]
    with patch(
        "backend.tools.get_stock_historical_data",
        return_value={"kline_data": rows},
    ):
        returns = _fetch_returns("AAPL")

    assert returns is not None
    assert len(returns) == 30
    assert all(np.isfinite(value) for value in returns)


def test_fetch_returns_rejects_oversized_ticker_before_provider():
    from backend.services.risk_attribution import _fetch_returns

    with patch("backend.tools.get_stock_historical_data") as provider:
        assert _fetch_returns("A" * 33) is None

    provider.assert_not_called()


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


def test_risk_attribution_handles_invalid_and_non_finite_market_values():
    from backend.services.risk_attribution import calculate_risk_attribution

    positions = [
        {"ticker": "VALID", "market_value": 1000},
        {"ticker": "TEXT", "market_value": "bad"},
        {"ticker": "NAN", "market_value": "nan"},
        {"ticker": "INF", "market_value": "inf"},
        {"ticker": "NEGATIVE", "market_value": -100},
    ]
    with patch("backend.services.risk_attribution._fetch_returns", return_value=None):
        result = calculate_risk_attribution(positions)

    weights = {item["ticker"]: item["weight"] for item in result["positions"]}
    assert weights["VALID"] == 1.0
    assert all(np.isfinite(item["weight"]) for item in result["positions"])
    assert all(weights[ticker] == 0.0 for ticker in ("TEXT", "NAN", "INF", "NEGATIVE"))


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


def test_stored_position_shape_derives_market_value():
    """集成回归：get_positions 实际返回 shares/avg_cost，没有 market_value。
    /api/portfolio/risk-attribution 端点把存储行直接喂进来——字段缺失恒 0
    会让 total_val<=0 永远返回 no_data"持仓数据不足"。应按 shares*avg_cost
    兜底（与 portfolio_risk_lens 同一口径）。"""
    from backend.services.risk_attribution import calculate_risk_attribution
    positions = [
        {"ticker": "AAPL", "shares": 30, "avg_cost": 100, "sector": "科技"},
        {"ticker": "NVDA", "shares": 10, "avg_cost": 100, "sector": "科技"},
    ]
    with patch("backend.services.risk_attribution._fetch_returns", return_value=None):
        result = calculate_risk_attribution(positions)
    assert result["method"] == "simplified"
    weights = {item["ticker"]: item["weight"] for item in result["positions"]}
    assert weights["AAPL"] == 0.75
    assert weights["NVDA"] == 0.25


def test_market_value_field_takes_precedence_over_shares_avg_cost():
    """显式 market_value 不被 shares*avg_cost 兜底覆盖。"""
    from backend.services.risk_attribution import calculate_risk_attribution
    positions = [
        {"ticker": "AAPL", "shares": 10, "avg_cost": 50, "market_value": 900},
        {"ticker": "NVDA", "market_value": 100},
    ]
    with patch("backend.services.risk_attribution._fetch_returns", return_value=None):
        result = calculate_risk_attribution(positions)
    weights = {item["ticker"]: item["weight"] for item in result["positions"]}
    assert weights["AAPL"] == 0.9
    assert weights["NVDA"] == 0.1


def test_sector_attribution_duplicate_detail_rows_use_own_sector():
    """R85: 行业归因用 positions[pos_details.index(p)] 反查 sector——index()
    按值相等找第一个匹配，两条明细 dict 完全相同（同 ticker+同权重+同 beta，
    如券商重复导入的相同持仓行但 sector 标注不同）时第二条恒返回第一条的
    下标，其风险被错记到第一条的 sector：一边虚增一边漏计。"""
    from backend.services.risk_attribution import calculate_risk_attribution

    market_returns = [0.01, -0.005, 0.008, -0.002, 0.012] * 8  # σ>0 才有非零风险贡献

    def fake_fetch(ticker, period="1y"):
        if ticker == "000300.SS":
            return market_returns
        return None

    positions = [
        {"ticker": "DUP", "market_value": 5000, "sector": "科技"},
        {"ticker": "DUP", "market_value": 5000, "sector": "金融"},  # 与上行产出完全相同的明细 dict
        {"ticker": "OTHER", "market_value": 10000, "sector": "金融"},
    ]
    with patch("backend.services.risk_attribution._fetch_returns", side_effect=fake_fetch):
        result = calculate_risk_attribution(positions)

    contrib_by_ticker = {
        p["ticker"]: p["market_risk_contrib"] + p["idio_risk_contrib"]
        for p in result["positions"]
    }
    dup = contrib_by_ticker["DUP"]
    other = contrib_by_ticker["OTHER"]
    assert dup > 0 and other > 0

    contrib = {s["sector"]: s["risk_contribution"] for s in result["sector_attribution"]}
    # 正确归属：科技=第一条 DUP；金融=第二条 DUP + OTHER。
    # buggy: 科技=两条 DUP（第二条被 index() 撞回第一条），金融只剩 OTHER。
    assert contrib["科技"] == pytest.approx(dup)
    assert contrib["金融"] == pytest.approx(dup + other)
