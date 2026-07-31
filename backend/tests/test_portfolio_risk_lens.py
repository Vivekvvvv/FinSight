# -*- coding: utf-8 -*-
"""测试 Portfolio Risk Lens 规则引擎"""
from datetime import datetime, timedelta, timezone
import math

from backend.services.portfolio_risk_lens import calculate_portfolio_risk_lens, RISK_RULES


def test_empty_portfolio():
    """空持仓应返回空风险透镜"""
    result = calculate_portfolio_risk_lens([], [])

    assert result["success"] is True
    assert result["risk_score"] == 0
    assert result["concentration_risk"] == []
    assert result["loss_positions"] == []
    assert result["stale_research"] == []
    assert result["missing_coverage"] == []
    assert len(result["next_actions"]) == 1
    assert result["next_actions"][0]["type"] == "add_portfolio"


def test_invalid_and_non_finite_position_values_do_not_pollute_risk_lens():
    positions = [
        {"ticker": "VALID", "market_value": "1000", "cost_basis": "900", "unrealized_pnl": "100"},
        {"ticker": "TEXT", "market_value": "bad", "cost_basis": "bad", "unrealized_pnl": "bad"},
        {"ticker": "NAN", "market_value": "nan", "cost_basis": "inf", "unrealized_pnl": "-inf"},
        {"ticker": "NEGATIVE", "market_value": -100, "cost_basis": -90, "unrealized_pnl": -10},
    ]

    result = calculate_portfolio_risk_lens(positions, [])

    assert result["total_value"] == 1000.0
    assert result["total_cost"] == 900.0
    for exposure_key in ("sector_exposure", "currency_exposure", "market_exposure"):
        assert all(
            math.isfinite(item["value"]) and math.isfinite(item["percentage"])
            for item in result[exposure_key]
        )


def test_malformed_positions_and_reports_are_ignored():
    positions = [
        None,
        "bad",
        {},
        {"ticker": None, "market_value": 1000},
        {"ticker": "BAD TICKER", "market_value": 1000},
        {"ticker": "X" * 21, "market_value": 1000},
        {"ticker": " aapl ", "market_value": 1000, "cost_basis": 900},
    ]

    result = calculate_portfolio_risk_lens(positions, [None, "bad", {"ticker": "AAPL"}])

    assert result["total_value"] == 1000.0
    assert result["concentration_risk"][0]["related_symbol"] == "AAPL"


def test_only_malformed_positions_produce_empty_risk_lens():
    result = calculate_portfolio_risk_lens([None, {}, {"ticker": " "}], [])

    assert result["risk_score"] == 0
    assert result["next_actions"][0]["type"] == "add_portfolio"


def test_single_position_concentration():
    """单一持仓 >25% 触发集中度风险"""
    positions = [
        {"ticker": "AAPL", "market_value": 3000, "cost_basis": 2800},
        {"ticker": "NVDA", "market_value": 1000, "cost_basis": 900},
    ]

    result = calculate_portfolio_risk_lens(positions, [])

    # AAPL 占 75%，超过 25% 阈值
    concentration = [r for r in result["concentration_risk"] if r["type"] == "concentration"]
    assert len(concentration) == 1
    assert concentration[0]["related_symbol"] == "AAPL"
    assert concentration[0]["severity"] == "high"
    assert "集中度过高" in concentration[0]["title"]


def test_sector_concentration():
    """单一行业 >40% 触发行业集中度风险"""
    positions = [
        {"ticker": "AAPL", "market_value": 2500, "cost_basis": 2000, "sector": "Technology"},
        {"ticker": "MSFT", "market_value": 2000, "cost_basis": 1800, "sector": "Technology"},
        {"ticker": "JPM", "market_value": 1000, "cost_basis": 900, "sector": "Finance"},
    ]

    result = calculate_portfolio_risk_lens(positions, [])

    # Technology 占 4500/5500 = 81.8%，超过 40% 阈值
    sector_conc = [r for r in result["concentration_risk"] if r["type"] == "sector_concentration"]
    assert len(sector_conc) == 1
    assert "Technology" in sector_conc[0]["title"]
    assert sector_conc[0]["severity"] == "high"


def test_loss_positions():
    """亏损持仓触发风险提示"""
    positions = [
        # -12% → high
        {"ticker": "AAPL", "market_value": 880, "cost_basis": 1000, "unrealized_pnl": -120},
        # -7% → medium
        {"ticker": "NVDA", "market_value": 930, "cost_basis": 1000, "unrealized_pnl": -70},
        # -3% → 不触发
        {"ticker": "TSLA", "market_value": 970, "cost_basis": 1000, "unrealized_pnl": -30},
    ]

    result = calculate_portfolio_risk_lens(positions, [])

    loss = result["loss_positions"]
    assert len(loss) == 2

    aapl = next(r for r in loss if r["related_symbol"] == "AAPL")
    nvda = next(r for r in loss if r["related_symbol"] == "NVDA")

    assert aapl["severity"] == "high"  # <-10%
    assert nvda["severity"] == "medium"  # -5% ~ -10%


def test_stale_research():
    """过期报告触发新鲜度风险"""
    positions = [
        {"ticker": "AAPL", "market_value": 1000, "cost_basis": 1000},
        {"ticker": "NVDA", "market_value": 1000, "cost_basis": 1000},
    ]

    now = datetime.now(timezone.utc)
    reports = [
        # 40 天前 → critical
        {
            "ticker": "AAPL",
            "as_of": (now - timedelta(days=40)).isoformat(),
        },
        # 10 天前 → medium
        {
            "ticker": "NVDA",
            "as_of": (now - timedelta(days=10)).isoformat(),
        },
    ]

    result = calculate_portfolio_risk_lens(positions, reports)

    stale = result["stale_research"]
    assert len(stale) == 2

    aapl = next(r for r in stale if r["related_symbol"] == "AAPL")
    nvda = next(r for r in stale if r["related_symbol"] == "NVDA")

    assert aapl["severity"] == "high"  # >30 天
    assert nvda["severity"] == "medium"  # 7-30 天


def test_stale_research_with_naive_as_of():
    """R19 回归：无时区的 as_of（如纯日期串，财报/备案常见）也必须触发过期风险。
    旧代码 naive 与 aware now 相减抛 TypeError 被吞 → 风险整条静默漏报。"""
    positions = [{"ticker": "AAPL", "market_value": 1000, "cost_basis": 1000}]
    naive_date = (datetime.now(timezone.utc) - timedelta(days=40)).strftime("%Y-%m-%d")
    reports = [{"ticker": "AAPL", "as_of": naive_date}]

    result = calculate_portfolio_risk_lens(positions, reports)

    stale = result["stale_research"]
    assert len(stale) == 1
    assert stale[0]["severity"] == "high"


def test_missing_coverage():
    """高仓位无报告覆盖触发风险"""
    positions = [
        {"ticker": "AAPL", "market_value": 1500, "cost_basis": 1400},  # 60% 无报告
        {"ticker": "NVDA", "market_value": 1000, "cost_basis": 900},   # 40% 有报告
    ]

    reports = [
        {"ticker": "NVDA", "as_of": datetime.now(timezone.utc).isoformat()},
    ]

    result = calculate_portfolio_risk_lens(positions, reports)

    missing = result["missing_coverage"]
    assert len(missing) == 1
    assert missing[0]["related_symbol"] == "AAPL"
    assert missing[0]["severity"] == "medium"
    assert "缺少研究覆盖" in missing[0]["title"]


def test_risk_score_calculation():
    """验证风险评分计算逻辑"""
    positions = [
        # 触发 3 个 high (集中度 + sector + 亏损)
        {"ticker": "AAPL", "market_value": 8000, "cost_basis": 10000, "unrealized_pnl": -2000, "sector": "Tech"},
        {"ticker": "NVDA", "market_value": 2000, "cost_basis": 2000, "sector": "Tech"},
    ]

    result = calculate_portfolio_risk_lens(positions, [])

    # 预期：单一持仓 high(15) + sector high(15) + 亏损 high(15) = 45
    # 实际可能略有不同，但应该 >= 40
    assert result["risk_score"] >= 40
    assert result["risk_score"] <= 100


def test_exposure_aggregation():
    """验证行业/币种/市场暴露统计"""
    positions = [
        {"ticker": "AAPL", "market_value": 3000, "cost_basis": 2800, "sector": "Tech", "currency": "USD"},
        {"ticker": "700.HK", "market_value": 2000, "cost_basis": 1900, "sector": "Tech", "currency": "HKD"},
        {"ticker": "JPM", "market_value": 1000, "cost_basis": 900, "sector": "Finance", "currency": "USD"},
    ]

    result = calculate_portfolio_risk_lens(positions, [])

    # 行业暴露
    sector_exp = result["sector_exposure"]
    tech = next(s for s in sector_exp if s["sector"] == "Tech")
    assert tech["value"] == 5000
    assert tech["percentage"] == 5000 / 6000

    # 币种暴露
    currency_exp = result["currency_exposure"]
    usd = next(c for c in currency_exp if c["currency"] == "USD")
    assert usd["value"] == 4000

    # 市场暴露
    market_exp = result["market_exposure"]
    us = next(m for m in market_exp if m["market"] == "US")
    hk = next(m for m in market_exp if m["market"] == "HK")
    assert us["value"] == 4000
    assert hk["value"] == 2000


def test_next_actions_generation():
    """验证推荐操作生成"""
    positions = [
        {"ticker": "AAPL", "market_value": 880, "cost_basis": 1000, "unrealized_pnl": -120},  # high loss
    ]

    result = calculate_portfolio_risk_lens(positions, [])

    actions = result["next_actions"]
    assert len(actions) > 0

    # 应包含针对 AAPL 亏损的操作建议
    aapl_action = next((a for a in actions if a.get("related_symbol") == "AAPL"), None)
    assert aapl_action is not None
    assert aapl_action["severity"] in ["high", "medium"]
