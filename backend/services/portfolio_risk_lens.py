# -*- coding: utf-8 -*-
"""Portfolio Risk Lens - 持仓风险透镜

把 Portfolio 从"持仓列表"升级成"风险解释器"。
不做买卖建议，只解释暴露、集中度、亏损、相关风险。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

# 风险规则配置（可参数化）
RISK_RULES = {
    "single_position_high": 0.25,       # 单一持仓 > 25% 高集中度
    "single_sector_high": 0.40,         # 单一行业 > 40% 高集中
    "loss_medium_threshold": -0.05,     # -5% 中风险
    "loss_high_threshold": -0.10,       # -10% 高风险
    "stale_days_warning": 7,            # 7 天数据过期警告
    "stale_days_critical": 30,          # 30 天数据过期严重
    "low_quality_rate_threshold": 0.30, # 低质量报告占比 > 30%
    "high_position_no_research": 0.10,  # 高仓位 > 10% 但无报告覆盖
}


def calculate_portfolio_risk_lens(
    positions: list[dict[str, Any]],
    reports: list[dict[str, Any]] = None,
) -> dict[str, Any]:
    """计算 Portfolio 风险透镜

    Args:
        positions: 持仓列表（从 portfolio_store.get_positions 获取）
        reports: 相关报告列表（从 report_index 获取，可选）

    Returns:
        PortfolioRiskLens 结构
    """
    if not positions:
        return _empty_risk_lens()

    reports = reports or []

    # 计算总市值和成本
    total_value = sum(p.get("market_value") or 0 for p in positions)
    total_cost = sum(p.get("cost_basis") or 0 for p in positions)

    # 初始化风险项列表
    concentration_risks = []
    sector_exposure = {}
    currency_exposure = {}
    market_exposure = {}
    stale_research = []
    loss_positions = []
    missing_coverage = []

    # 规则 1: 单一持仓集中度风险
    for pos in positions:
        if total_value > 0:
            weight = (pos.get("market_value") or 0) / total_value
            if weight > RISK_RULES["single_position_high"]:
                concentration_risks.append({
                    "id": f"concentration_{pos['ticker']}",
                    "type": "concentration",
                    "severity": "high",
                    "title": f"{pos['ticker']} 持仓集中度过高",
                    "reason": f"占总仓位 {weight*100:.1f}%，超过 {RISK_RULES['single_position_high']*100:.0f}% 阈值",
                    "target_route": f"/dashboard/{pos['ticker']}",
                    "related_symbol": pos["ticker"],
                    "metric_value": weight,
                })

    # 规则 2: 行业集中度风险
    for pos in positions:
        sector = pos.get("sector") or "Unknown"
        sector_exposure[sector] = sector_exposure.get(sector, 0) + (pos.get("market_value") or 0)

    for sector, value in sector_exposure.items():
        if total_value > 0:
            weight = value / total_value
            if weight > RISK_RULES["single_sector_high"]:
                concentration_risks.append({
                    "id": f"sector_{sector}",
                    "type": "sector_concentration",
                    "severity": "high",
                    "title": f"{sector} 行业集中度过高",
                    "reason": f"占总仓位 {weight*100:.1f}%，超过 {RISK_RULES['single_sector_high']*100:.0f}% 阈值",
                    "target_route": "/portfolio",
                    "related_symbol": None,
                    "metric_value": weight,
                })

    # 规则 3: 币种暴露统计
    for pos in positions:
        currency = pos.get("currency") or "USD"
        currency_exposure[currency] = currency_exposure.get(currency, 0) + (pos.get("market_value") or 0)

    # 规则 4: 市场暴露（根据 ticker 前缀推断）
    for pos in positions:
        ticker = pos["ticker"]
        market = "US"  # 默认美股
        if ticker.endswith(".HK"):
            market = "HK"
        elif ticker.endswith(".SS") or ticker.endswith(".SZ"):
            market = "CN"
        market_exposure[market] = market_exposure.get(market, 0) + (pos.get("market_value") or 0)

    # 规则 5: 亏损持仓风险
    for pos in positions:
        unrealized_pnl = pos.get("unrealized_pnl")
        cost_basis = pos.get("cost_basis")
        if unrealized_pnl is not None and cost_basis and cost_basis > 0:
            pnl_pct = unrealized_pnl / cost_basis
            if pnl_pct < RISK_RULES["loss_medium_threshold"]:
                severity = "high" if pnl_pct < RISK_RULES["loss_high_threshold"] else "medium"
                loss_positions.append({
                    "id": f"loss_{pos['ticker']}",
                    "type": "loss",
                    "severity": severity,
                    "title": f"{pos['ticker']} 持仓亏损",
                    "reason": f"当前亏损 {pnl_pct*100:.1f}%",
                    "target_route": f"/dashboard/{pos['ticker']}",
                    "related_symbol": pos["ticker"],
                    "metric_value": pnl_pct,
                })

    # 规则 6: 数据新鲜度风险（基于报告 as_of）
    report_dict = {r.get("ticker"): r for r in reports if r.get("ticker")}
    now = datetime.now(timezone.utc)

    for pos in positions:
        ticker = pos["ticker"]
        report = report_dict.get(ticker)
        if report:
            as_of = report.get("as_of")
            if as_of:
                try:
                    as_of_dt = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
                    days_old = (now - as_of_dt).days

                    if days_old > RISK_RULES["stale_days_warning"]:
                        severity = "high" if days_old > RISK_RULES["stale_days_critical"] else "medium"
                        stale_research.append({
                            "id": f"stale_{ticker}",
                            "type": "stale_research",
                            "severity": severity,
                            "title": f"{ticker} 研究数据过期",
                            "reason": f"报告数据截至 {days_old} 天前",
                            "target_route": f"/reports?ticker={ticker}",
                            "related_symbol": ticker,
                            "metric_value": days_old,
                        })
                except (ValueError, TypeError):
                    pass

    # 规则 7: 低质量报告覆盖风险
    low_quality_count = sum(1 for r in reports if r.get("quality_state") in ["warn", "block"])
    if reports and low_quality_count / len(reports) > RISK_RULES["low_quality_rate_threshold"]:
        concentration_risks.append({
            "id": "low_quality_coverage",
            "type": "quality",
            "severity": "medium",
            "title": "研究质量覆盖不足",
            "reason": f"{low_quality_count}/{len(reports)} 份报告存在质量问题（{low_quality_count/len(reports)*100:.0f}%）",
            "target_route": "/reports",
            "related_symbol": None,
            "metric_value": low_quality_count / len(reports),
        })

    # 规则 8: 高仓位缺少研究覆盖
    for pos in positions:
        if total_value > 0:
            weight = (pos.get("market_value") or 0) / total_value
            ticker = pos["ticker"]
            if weight > RISK_RULES["high_position_no_research"] and ticker not in report_dict:
                missing_coverage.append({
                    "id": f"missing_{ticker}",
                    "type": "missing_coverage",
                    "severity": "medium",
                    "title": f"{ticker} 缺少研究覆盖",
                    "reason": f"持仓占比 {weight*100:.1f}%，但无研究报告",
                    "target_route": f"/chat?prefill=深度分析 {ticker}",
                    "related_symbol": ticker,
                    "metric_value": weight,
                })

    # 计算总风险评分（0-100）
    risk_score = _calculate_risk_score(
        concentration_risks,
        loss_positions,
        stale_research,
        missing_coverage,
    )

    # 生成 next_actions
    next_actions = _generate_risk_actions(
        concentration_risks,
        loss_positions,
        stale_research,
        missing_coverage,
    )

    return {
        "success": True,
        "as_of": now.isoformat(),
        "total_value": total_value,
        "total_cost": total_cost,
        "risk_score": risk_score,
        "concentration_risk": concentration_risks,
        "sector_exposure": [
            {"sector": k, "value": v, "percentage": v / total_value if total_value > 0 else 0}
            for k, v in sorted(sector_exposure.items(), key=lambda x: -x[1])
        ],
        "currency_exposure": [
            {"currency": k, "value": v, "percentage": v / total_value if total_value > 0 else 0}
            for k, v in sorted(currency_exposure.items(), key=lambda x: -x[1])
        ],
        "market_exposure": [
            {"market": k, "value": v, "percentage": v / total_value if total_value > 0 else 0}
            for k, v in sorted(market_exposure.items(), key=lambda x: -x[1])
        ],
        "stale_research": stale_research,
        "loss_positions": loss_positions,
        "missing_coverage": missing_coverage,
        "next_actions": next_actions,
    }


def _empty_risk_lens() -> dict[str, Any]:
    """空 Portfolio 的风险透镜"""
    return {
        "success": True,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "total_value": 0,
        "total_cost": 0,
        "risk_score": 0,
        "concentration_risk": [],
        "sector_exposure": [],
        "currency_exposure": [],
        "market_exposure": [],
        "stale_research": [],
        "loss_positions": [],
        "missing_coverage": [],
        "next_actions": [{
            "id": "add_portfolio",
            "type": "add_portfolio",
            "title": "录入持仓组合",
            "reason": "录入持仓后可查看风险分析",
            "severity": "low",
            "target_route": "/portfolio",
            "related_symbol": None,
        }],
    }


def _calculate_risk_score(
    concentration_risks: list,
    loss_positions: list,
    stale_research: list,
    missing_coverage: list,
) -> int:
    """计算总风险评分（0-100，数值越高风险越大）

    评分规则：
    - 基础分 0
    - 每个 high severity 风险 +15 分
    - 每个 medium severity 风险 +8 分
    - 每个 low severity 风险 +3 分
    - 最高 100 分
    """
    score = 0
    all_risks = concentration_risks + loss_positions + stale_research + missing_coverage

    for risk in all_risks:
        severity = risk.get("severity", "low")
        if severity == "high":
            score += 15
        elif severity == "medium":
            score += 8
        elif severity == "low":
            score += 3

    return min(score, 100)


def _generate_risk_actions(
    concentration_risks: list,
    loss_positions: list,
    stale_research: list,
    missing_coverage: list,
) -> list[dict[str, Any]]:
    """从风险项生成推荐操作（最多 10 条）"""
    actions = []

    # 优先处理 high severity 风险
    all_risks = concentration_risks + loss_positions + stale_research + missing_coverage
    all_risks.sort(key=lambda r: {"high": 0, "medium": 1, "low": 2}.get(r.get("severity", "low"), 99))

    for risk in all_risks[:10]:
        actions.append({
            "id": f"action_{risk['id']}",
            "type": risk["type"],
            "title": risk["title"],
            "reason": risk["reason"],
            "severity": risk["severity"],
            "target_route": risk["target_route"],
            "related_symbol": risk.get("related_symbol"),
        })

    return actions
