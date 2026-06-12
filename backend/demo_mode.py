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
    demo_mode = is_demo_mode()
    market_keys = ("FMP_API_KEY", "ALPHA_VANTAGE_API_KEY", "FINNHUB_API_KEY", "TWELVE_DATA_API_KEY", "EODHD_API_KEY")
    has_market_key = any(str(os.getenv(name, "")).strip() for name in market_keys)
    has_llm_key = bool(str(os.getenv("OPENAI_COMPATIBLE_API_KEY", "")).strip())
    has_auth_keys = bool(str(os.getenv("JWT_SECRET", "")).strip() and str(os.getenv("API_AUTH_KEYS", "")).strip())
    market_status = "demo" if demo_mode else ("live_ready" if has_market_key else "fallback_ready")
    market_detail = (
        "当前使用内置演示行情。"
        if demo_mode
        else (
            "已检测到外部行情 key，优先使用真实外部源。"
            if has_market_key
            else "未配置付费行情 key；US/HK 使用 yfinance，A 股使用 BaoStock 免密兜底。"
        )
    )
    components = [
        {
            "key": "market_data",
            "label": "行情与股票筛选",
            "status": market_status,
            "detail": market_detail,
            "required_action": None if demo_mode or has_market_key else "如需更完整筛选覆盖，可配置 FMP_API_KEY。",
        },
        {
            "key": "llm",
            "label": "AI 研究生成",
            "status": "demo" if demo_mode else ("live_ready" if has_llm_key else "missing_key"),
            "detail": "Demo Mode 下可使用模板化研究输出。" if demo_mode else ("已检测到 LLM key。" if has_llm_key else "未检测到 LLM key。"),
            "required_action": None if demo_mode or has_llm_key else "配置 OPENAI_COMPATIBLE_API_KEY。",
        },
        {
            "key": "auth",
            "label": "访问控制",
            "status": "demo" if demo_mode else ("live_ready" if has_auth_keys else "missing_key"),
            "detail": "本地演示身份已启用。" if demo_mode else ("JWT 与 API key 已配置。" if has_auth_keys else "JWT 或 API key 未完整配置。"),
            "required_action": None if demo_mode or has_auth_keys else "配置 JWT_SECRET 和 API_AUTH_KEYS。",
        },
    ]
    return {
        "success": True,
        "demo_mode": demo_mode,
        "data_source": "demo" if demo_mode else "live_or_local",
        "overall_status": "demo" if demo_mode else ("live_ready" if not missing else "needs_config"),
        "missing_services": missing,
        "components": components,
        "notes": [
            "Demo Mode 使用只读示例数据，不构成投资建议。",
            "未配置行情 key 时，系统会尝试 yfinance 与 BaoStock 免密兜底。",
        ],
    }


DEMO_MARKET_PROFILES: dict[str, dict[str, Any]] = {
    "AAPL": {
        "name": "Apple Inc.",
        "market": "US",
        "exchange": "NASDAQ",
        "sector": "Technology",
        "currency": "USD",
        "base_price": 195.5,
        "change": 2.3,
        "change_percent": 1.19,
        "trend": [0.0, 0.7, 1.2, 0.8, 1.6, 2.1, 2.8, 2.4, 3.0, 3.6, 4.1, 3.8],
        "volume": 52_000_000,
        "market_cap": 3_000_000_000_000,
        "trailingPE": 30.4,
        "priceToBook": 44.2,
        "trailingEps": 6.43,
        "beta": 1.2,
    },
    "MSFT": {
        "name": "Microsoft Corp.",
        "market": "US",
        "exchange": "NASDAQ",
        "sector": "Technology",
        "currency": "USD",
        "base_price": 430.2,
        "change": 1.8,
        "change_percent": 0.42,
        "trend": [0.0, 1.4, 2.2, 3.8, 4.7, 4.1, 5.2, 6.4, 7.1, 7.6, 8.4, 9.3],
        "volume": 24_000_000,
        "market_cap": 3_200_000_000_000,
        "trailingPE": 36.8,
        "priceToBook": 12.6,
        "trailingEps": 11.7,
        "beta": 0.9,
    },
    "NVDA": {
        "name": "NVIDIA Corp.",
        "market": "US",
        "exchange": "NASDAQ",
        "sector": "Semiconductors",
        "currency": "USD",
        "base_price": 880.1,
        "change": -7.1,
        "change_percent": -0.8,
        "trend": [0.0, 5.6, 13.4, 8.2, 16.8, 24.0, 19.5, 31.0, 27.2, 22.4, 29.6, 25.1],
        "volume": 41_000_000,
        "market_cap": 2_200_000_000_000,
        "trailingPE": 72.5,
        "priceToBook": 47.8,
        "trailingEps": 12.1,
        "beta": 1.7,
    },
    "GOOGL": {
        "name": "Alphabet Inc.",
        "market": "US",
        "exchange": "NASDAQ",
        "sector": "Communication Services",
        "currency": "USD",
        "base_price": 175.4,
        "change": 0.8,
        "change_percent": 0.48,
        "trend": [0.0, -0.4, 0.2, 1.1, 1.5, 0.9, 1.8, 2.0, 1.6, 2.5, 2.9, 3.4],
        "volume": 28_000_000,
        "market_cap": 2_100_000_000_000,
        "trailingPE": 27.1,
        "priceToBook": 7.4,
        "trailingEps": 6.47,
        "beta": 1.0,
    },
    "0700.HK": {
        "name": "Tencent Holdings Limited",
        "market": "HK",
        "exchange": "HKEX",
        "sector": "Communication Services",
        "currency": "HKD",
        "base_price": 381.0,
        "change": 2.2,
        "change_percent": 0.58,
        "trend": [0.0, -1.8, -0.6, 1.2, 2.7, 1.9, 3.4, 4.8, 4.1, 5.6, 6.2, 7.0],
        "volume": 20_800_000,
        "market_cap": 3_560_000_000_000,
        "trailingPE": 22.6,
        "priceToBook": 4.1,
        "trailingEps": 16.9,
        "beta": 1.0,
    },
    "9988.HK": {
        "name": "Alibaba Group Holding Limited",
        "market": "HK",
        "exchange": "HKEX",
        "sector": "Consumer Discretionary",
        "currency": "HKD",
        "base_price": 81.2,
        "change": 0.25,
        "change_percent": 0.31,
        "trend": [0.0, 0.6, -0.2, -1.0, -0.4, 0.1, 0.9, 1.3, 0.7, 1.8, 2.1, 1.5],
        "volume": 73_000_000,
        "market_cap": 1_520_000_000_000,
        "trailingPE": 13.8,
        "priceToBook": 1.6,
        "trailingEps": 5.88,
        "beta": 1.2,
    },
    "600519.SS": {
        "name": "Kweichow Moutai Co., Ltd.",
        "market": "CN",
        "exchange": "Shanghai",
        "sector": "Consumer Staples",
        "currency": "CNY",
        "base_price": 1702.0,
        "change": 7.1,
        "change_percent": 0.42,
        "trend": [0.0, -8.0, -15.0, -6.0, 4.0, 12.0, 8.0, 19.0, 25.0, 18.0, 31.0, 39.0],
        "volume": 2_100_000,
        "market_cap": 2_138_000_000_000,
        "trailingPE": 27.9,
        "priceToBook": 9.6,
        "trailingEps": 61.0,
        "beta": 0.7,
    },
    "300750.SZ": {
        "name": "Contemporary Amperex Technology Co., Ltd.",
        "market": "CN",
        "exchange": "Shenzhen",
        "sector": "Industrials",
        "currency": "CNY",
        "base_price": 193.6,
        "change": -0.68,
        "change_percent": -0.35,
        "trend": [0.0, 2.4, 1.1, -1.8, -3.2, -2.1, -4.8, -3.6, -5.2, -6.1, -4.9, -7.0],
        "volume": 15_200_000,
        "market_cap": 852_000_000_000,
        "trailingPE": 21.4,
        "priceToBook": 4.9,
        "trailingEps": 9.05,
        "beta": 1.1,
    },
}


def _demo_market_profile(symbol: str) -> dict[str, Any] | None:
    return DEMO_MARKET_PROFILES.get(str(symbol or "").strip().upper())


def _demo_source_meta() -> dict[str, Any]:
    return {
        "source": "demo",
        "freshness_status": "demo",
        "fallback_level": 2,
        "as_of": _iso(),
    }


def demo_quote(symbol: str) -> dict[str, Any] | None:
    profile = _demo_market_profile(symbol)
    if not profile:
        return None
    price = float(profile["base_price"])
    change = float(profile["change"])
    change_percent = float(profile["change_percent"])
    day_low = round(price - max(abs(change) * 1.4, price * 0.006), 2)
    day_high = round(price + max(abs(change) * 1.6, price * 0.007), 2)
    return {
        **_demo_source_meta(),
        "symbol": str(symbol).upper(),
        "shortName": profile["name"],
        "longName": profile["name"],
        "price": price,
        "currentPrice": price,
        "regularMarketPrice": price,
        "change": change,
        "regularMarketChange": change,
        "change_percent": change_percent,
        "regularMarketChangePercent": change_percent,
        "regularMarketDayLow": day_low,
        "regularMarketDayHigh": day_high,
        "regularMarketVolume": profile["volume"],
        "marketCap": profile["market_cap"],
        "beta": profile["beta"],
        "currency": profile["currency"],
        "exchange": profile["exchange"],
        "sector": profile["sector"],
        "fiftyTwoWeekLow": round(price * 0.72, 2),
        "fiftyTwoWeekHigh": round(price * 1.18, 2),
    }


def demo_kline(symbol: str, period: str = "1mo", interval: str = "1d") -> dict[str, Any] | None:
    profile = _demo_market_profile(symbol)
    if not profile:
        return None
    base_price = float(profile["base_price"])
    trend = list(profile["trend"])
    end = _now().date()
    rows: list[dict[str, Any]] = []
    dates: list[str] = []
    values: list[list[float]] = []
    previous_close = base_price - float(trend[-1])
    for index, offset in enumerate(trend):
        day = end - timedelta(days=len(trend) - index)
        close = round(base_price - float(trend[-1]) + float(offset), 2)
        open_price = round(previous_close + (float(offset) - float(trend[index - 1] if index else 0)) * 0.35, 2)
        spread = max(base_price * 0.006, abs(close - open_price) * 0.8)
        high = round(max(open_price, close) + spread, 2)
        low = round(min(open_price, close) - spread, 2)
        volume = float(profile["volume"]) * (0.72 + (index % 5) * 0.08)
        time_value = day.strftime("%Y-%m-%d")
        rows.append({
            "time": f"{time_value} 00:00",
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": round(volume, 0),
        })
        dates.append(time_value)
        values.append([open_price, close, low, high])
        previous_close = close
    return {
        **_demo_source_meta(),
        "symbol": str(symbol).upper(),
        "period": period,
        "interval": interval,
        "kline_data": rows,
        "dates": dates,
        "values": values,
    }


def demo_financials(symbol: str) -> dict[str, Any] | None:
    profile = _demo_market_profile(symbol)
    if not profile:
        return None
    market_cap = float(profile["market_cap"])
    pe = float(profile["trailingPE"])
    eps = float(profile["trailingEps"])
    revenue = market_cap / max(pe, 1.0) * 1.65
    net_income = eps * max(market_cap / max(float(profile["base_price"]), 1.0), 1.0)
    return {
        "ticker": str(symbol).upper(),
        "data": {
            **_demo_source_meta(),
            "shortName": profile["name"],
            "sector": profile["sector"],
            "currency": profile["currency"],
            "marketCap": market_cap,
            "trailingPE": pe,
            "priceToBook": profile["priceToBook"],
            "trailingEps": eps,
            "beta": profile["beta"],
            "totalRevenue": round(revenue, 2),
            "netIncome": round(net_income, 2),
            "grossMargins": 0.43 if profile["market"] == "US" else 0.36,
            "returnOnEquity": 0.32 if profile["market"] != "CN" else 0.24,
        },
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
