# -*- coding: utf-8 -*-
"""Demo Mode 数据与状态。

Demo Mode 只负责无密钥、无本地数据时的只读展示兜底，不写入真实业务库。
"""

from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any


def _env_bool(name: str, default: str = "false") -> bool:
    raw = str(os.getenv(name, default) or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def is_demo_mode() -> bool:
    return _env_bool("FINSIGHT_DEMO_MODE", "false")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(days: int = 0, hours: int = 0) -> str:
    return (_now() + timedelta(days=days, hours=hours)).isoformat()


def demo_status() -> dict[str, Any]:
    missing = []
    for name in ("FMP_API_KEY", "OPENAI_COMPATIBLE_API_KEY", "JWT_SECRET", "API_AUTH_KEYS"):
        if not str(os.getenv(name, "")).strip():
            missing.append(name)
    return {
        "success": True,
        "demo_mode": is_demo_mode(),
        "data_source": "demo" if is_demo_mode() else "live_or_local",
        "missing_services": missing,
        "notes": [
            "Demo Mode 使用只读示例数据，不构成投资建议。",
            "配置真实 API key 后可切换到 live/local 数据。",
        ],
    }


DEMO_POSITIONS: list[dict[str, Any]] = [
    {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "shares": 8,
        "avg_cost": 182.0,
        "live_price": 195.5,
        "market_value": 1564.0,
        "cost_basis": 1456.0,
        "unrealized_pnl": 108.0,
        "price_source": "demo",
        "sector": "Technology",
        "currency": "USD",
        "tags": ["核心观察", "现金流"],
        "note": "演示持仓：用于展示组合与研究闭环。",
        "updated_at": _iso(hours=-2),
    },
    {
        "ticker": "NVDA",
        "name": "NVIDIA Corp.",
        "shares": 3,
        "avg_cost": 920.0,
        "live_price": 880.1,
        "market_value": 2640.3,
        "cost_basis": 2760.0,
        "unrealized_pnl": -119.7,
        "price_source": "demo",
        "sector": "Semiconductors",
        "currency": "USD",
        "tags": ["AI", "高波动"],
        "note": "演示持仓：亏损未超 5%，用于风险展示。",
        "updated_at": _iso(hours=-3),
    },
]

DEMO_WATCHLIST: list[dict[str, Any]] = [
    {
        "ticker": "MSFT",
        "name": "Microsoft Corp.",
        "tags": ["云", "AI"],
        "note": "观察 Azure 与 Copilot 收入兑现。",
        "group": "发现池",
        "priority": 4,
        "watch_reason": "重点复查云与 AI 资本开支回报。",
        "added_at": _iso(days=-2),
    },
    {
        "ticker": "GOOGL",
        "name": "Alphabet Inc.",
        "tags": ["广告", "AI"],
        "note": "观察搜索广告与 Gemini 相关投入。",
        "group": "发现池",
        "priority": 3,
        "watch_reason": "适合与 MSFT 做证据对比。",
        "added_at": _iso(days=-1),
    },
]

DEMO_REPORTS: list[dict[str, Any]] = [
    {
        "report_id": "demo_aapl_quality",
        "session_id": "demo",
        "ticker": "AAPL",
        "title": "AAPL 研究复查摘要",
        "summary": "服务收入与现金流仍是核心证据，硬件周期和监管是主要复查点。",
        "generated_at": _iso(days=-1),
        "confidence_score": 0.82,
        "is_favorite": True,
        "tags": ["demo", "cashflow", "risk"],
        "source_type": "demo",
        "quality_state": "pass",
        "publishable": True,
        "quality_reasons": [],
        "user_note": "下次复查服务收入增速与大中华区需求。",
        "citation_count": 6,
        "citation_quality": "high",
        "review_status": "watch",
        "as_of": _iso(days=-1),
        "freshness_status": "demo",
    },
    {
        "report_id": "demo_nvda_risk",
        "session_id": "demo",
        "ticker": "NVDA",
        "title": "NVDA 风险与证据缺口",
        "summary": "AI 需求仍强，但估值、供给周期和订单兑现需要持续核验。",
        "generated_at": _iso(days=-9),
        "confidence_score": 0.68,
        "is_favorite": False,
        "tags": ["demo", "ai", "stale"],
        "source_type": "demo",
        "quality_state": "warn",
        "publishable": True,
        "quality_reasons": [{"code": "demo_stale", "message": "演示旧报告，需要刷新"}],
        "user_note": "",
        "citation_count": 3,
        "citation_quality": "medium",
        "review_status": "new",
        "as_of": _iso(days=-9),
        "freshness_status": "stale",
    },
]

DEMO_NOTES: list[dict[str, Any]] = [
    {
        "note_id": "demo_note_aapl",
        "session_id": "demo",
        "user_id": "default_user",
        "ticker": "AAPL",
        "title": "AAPL 服务收入复查假设",
        "content": "假设：服务收入韧性可以抵消硬件周期压力。下一步核验最新财报分部收入。",
        "tags": ["demo", "hypothesis"],
        "created_at": _iso(days=-1),
        "updated_at": _iso(days=-1),
    },
    {
        "note_id": "demo_note_nvda",
        "session_id": "demo",
        "user_id": "default_user",
        "ticker": "NVDA",
        "title": "NVDA 订单兑现风险",
        "content": "观察点：订单、毛利率、供应链交付是否支持当前市场预期。",
        "tags": ["demo", "risk"],
        "created_at": _iso(hours=-8),
        "updated_at": _iso(hours=-8),
    },
]

DEMO_ALERTS: list[dict[str, Any]] = [
    {
        "id": "demo_alert_nvda",
        "ticker": "NVDA",
        "event_type": "risk_review",
        "severity": "high",
        "title": "NVDA 旧报告需要刷新",
        "message": "演示数据：报告已超过 7 天，建议重新生成研究摘要。",
        "triggered_at": _iso(hours=-5),
    }
]


def demo_portfolio_summary(session_id: str) -> dict[str, Any]:
    positions = deepcopy(DEMO_POSITIONS)
    total_value = round(sum(float(p["market_value"]) for p in positions), 2)
    total_cost = round(sum(float(p["cost_basis"]) for p in positions), 2)
    return {
        "success": True,
        "session_id": session_id,
        "positions": positions,
        "count": len(positions),
        "priced_count": len(positions),
        "total_value": total_value,
        "total_cost": total_cost,
        "total_pnl": round(total_value - total_cost, 2),
        "total_day_change": 0.0,
        "data_source": "demo",
    }


def demo_reports(session_id: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = deepcopy(DEMO_REPORTS[:limit])
    for row in rows:
        row["session_id"] = session_id
    return rows


def demo_notes(session_id: str, user_id: str, ticker: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    rows = deepcopy(DEMO_NOTES)
    for row in rows:
        row["session_id"] = session_id
        row["user_id"] = user_id
    if ticker:
        rows = [row for row in rows if row.get("ticker") == ticker.upper()]
    return rows[:limit]


def demo_timeline(symbol: str, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
    sym = symbol.upper()
    events = [
        {
            "id": f"demo_report_{sym}",
            "symbol": sym,
            "event_type": "report",
            "title": f"{sym} 演示报告生成",
            "summary": "演示数据：报告已进入研究库，可用于复查证据质量。",
            "occurred_at": _iso(days=-1),
            "severity": "medium",
            "source": "demo",
            "target_route": f"/reports?symbol={sym}",
            "evidence": {"confidence": 0.82, "citation_count": 6, "freshness_status": "demo", "quality_state": "pass"},
        },
        {
            "id": f"demo_note_{sym}",
            "symbol": sym,
            "event_type": "note",
            "title": f"{sym} 研究笔记更新",
            "summary": "演示数据：新增研究假设，建议与报告结论互相校验。",
            "occurred_at": _iso(hours=-8),
            "severity": "low",
            "source": "demo",
            "target_route": f"/notes?ticker={sym}",
            "evidence": {"confidence": 0.7, "citation_count": 0, "freshness_status": "demo", "quality_state": "pass"},
        },
    ]
    return events[:limit]


def demo_today_workspace(session_id: str) -> dict[str, Any]:
    portfolio = demo_portfolio_summary(session_id)
    reports = demo_reports(session_id, limit=3)
    return {
        "success": True,
        "as_of": _iso(),
        "freshness_status": "demo",
        "summary": "Demo Mode：2 只持仓、2 个观察标的、1 条待复查风险。",
        "portfolio_snapshot": {
            "total_value": portfolio["total_value"],
            "total_pnl": portfolio["total_pnl"],
            "total_cost": portfolio["total_cost"],
            "risk_positions": [],
            "position_count": portfolio["count"],
        },
        "watchlist_movers": deepcopy(DEMO_WATCHLIST),
        "alert_feed": deepcopy(DEMO_ALERTS),
        "reports_to_review": reports,
        "next_actions": [
            {
                "id": "demo_refresh_nvda",
                "type": "refresh_report",
                "title": "刷新 NVDA 旧报告",
                "reason": "演示报告已过期，适合验证报告刷新闭环。",
                "severity": "medium",
                "target_route": "/reports?highlight=demo_nvda_risk",
                "related_symbol": "NVDA",
            },
            {
                "id": "demo_review_aapl_note",
                "type": "review_note",
                "title": "复查 AAPL 服务收入假设",
                "reason": "笔记中存在待核验假设，建议与最新财报证据对齐。",
                "severity": "low",
                "target_route": "/notes?ticker=AAPL",
                "related_symbol": "AAPL",
            },
        ],
    }
