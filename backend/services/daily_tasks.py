"""智能任务生成器: 根据用户画像 + 市场数据 + 研报时效动态生成每日任务列表。"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from backend.utils.quote import safe_int, safe_float


# 研报过期阈值 (天)
REPORT_STALE_DAYS = 3


def _days_since(iso_str: str | None) -> int | None:
    """计算距离 ISO 时间字符串的天数差。"""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        # naive 存储值按本机时区还原归一 UTC：generated_at 可由
        # report_generator.py / report/ir.py / validator.py 以
        # datetime.now().isoformat()（本地时间）写入——直接 aware-naive
        # 相减抛 TypeError 被吞后返回 None，过期研报被误判"近期"，
        # 与 task_router / reports_to_review 的修复一致。
        if dt.tzinfo is None:
            dt = dt.astimezone(timezone.utc)
        days = (datetime.now(timezone.utc) - dt).days
        return days if days >= 0 else None
    except Exception:
        return None


def _stable_task_id(*, ticker: str = "", category: str, date_str: str = "") -> str:
    """生成稳定的任务 ID (基于 ticker + category + date 的 hash)。

    同一天、同一 ticker、同一类别的任务总是返回相同的 ID，
    避免前端在轮询刷新时重新挂载组件。
    """
    today = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    material = f"{ticker}|{category}|{today}".encode("utf-8")
    return f"task_{hashlib.sha256(material).hexdigest()[:12]}"


def generate_daily_tasks(
    *,
    watchlist: list[str],
    reports: list[dict[str, Any]],
    news_count: int = 0,
    risk_preference: str = "balanced",
) -> list[dict[str, Any]]:
    """根据输入信号生成个性化每日任务列表。

    Args:
        watchlist: 用户关注的 ticker 列表
        reports: 最近的研报列表 (来自 report_index)
        news_count: 未读新闻条数
        risk_preference: 投资者类型 (conservative / balanced / aggressive)

    Returns:
        任务列表, 每条含 id / title / category / priority / action_url / icon / execution_params
    """
    tasks: list[dict[str, Any]] = []
    watchlist = list(dict.fromkeys(ticker.strip().upper() for ticker in watchlist if isinstance(ticker, str) and ticker.strip()))

    # --- 1. 研报时效检查 ---
    ticker_last_report: dict[str, dict[str, Any]] = {}
    ticker_last_time: dict[str, datetime | None] = {}
    for r in reports:
        if (not isinstance(r, dict) or r.get("error") or r.get("success") is False
            or str(r.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            continue
        raw_ticker = r.get("ticker")
        t = raw_ticker.strip().upper() if isinstance(raw_ticker, str) else ""
        symbol = r.get("symbol")
        if symbol is not None and (not isinstance(symbol, str) or symbol.strip().upper() != t):
            continue
        report_time = None
        try:
            report_time = datetime.fromisoformat(r.get("generated_at").replace("Z", "+00:00")).astimezone(timezone.utc)
            if report_time > datetime.now(timezone.utc):
                report_time = None
        except (AttributeError, TypeError, ValueError, OverflowError):
            pass
        if t and (t not in ticker_last_report or report_time is not None
                  and (ticker_last_time[t] is None or report_time > ticker_last_time[t])):
            ticker_last_report[t] = r
            ticker_last_time[t] = report_time

    for ticker in watchlist:
        last = ticker_last_report.get(ticker)
        if last:
            days = _days_since(last.get("generated_at"))
            if days is None or days >= REPORT_STALE_DAYS:
                # 过期研报 → 重新分析
                tasks.append({
                    "id": _stable_task_id(ticker=ticker, category="reanalyze"),
                    "title": f"{ticker} 研报更新时间未知 — 建议刷新" if days is None else f"{ticker} 研报已 {days} 天未更新 — 建议刷新",
                    "category": "reanalyze",
                    "priority": 1 if days is not None and days >= 7 else 2,
                    "action_url": f"/chat?query=分析 {ticker} 最新情况",
                    "icon": "AlertTriangle",
                    "execution_params": {
                        "query": f"重新分析 {ticker} 最新情况",
                        "tickers": [ticker],
                        "output_mode": "investment_report",
                    },
                })
            else:
                # 近期研报 → 查看 (无需执行)
                raw_report_id = last.get("report_id")
                report_id = raw_report_id.strip() if isinstance(raw_report_id, str) else ""
                generated = last.get("generated_at", "")[:10]
                tasks.append({
                    "id": _stable_task_id(ticker=ticker, category="review"),
                    "title": f"查看 {ticker} 最新研报 (生成于 {generated})",
                    "category": "review",
                    "priority": 3,
                    "action_url": f"/chat?report_id={report_id}" if report_id else f"/workbench?ticker={ticker}",
                    "icon": "FileSearch",
                    "execution_params": None,
                })
        else:
            # 关注但无研报 → 生成首份分析
            tasks.append({
                "id": _stable_task_id(ticker=ticker, category="generate"),
                "title": f"为 {ticker} 生成首份深度分析",
                "category": "generate",
                "priority": 2,
                "action_url": f"/chat?query=深度分析 {ticker}",
                "icon": "Sparkles",
                "execution_params": {
                    "query": f"深度分析 {ticker}",
                    "tickers": [ticker],
                    "output_mode": "investment_report",
                },
            })

    # --- 2. 新闻任务 (导航型，无需执行) ---
    parsed_count = safe_int(news_count, 0) or 0
    news_count = parsed_count if safe_float(news_count) == parsed_count else 0
    if news_count > 0:
        tickers_str = ", ".join(watchlist[:3]) if watchlist else "市场"
        tasks.append({
            "id": _stable_task_id(category="news"),
            "title": f"{news_count} 条未读快讯 ({tickers_str})",
            "category": "news",
            "priority": 2,
            "action_url": "/dashboard",
            "icon": "Newspaper",
            "execution_params": None,
        })

    # --- 3. 风险偏好特定任务 ---
    risk_preference = risk_preference.strip().lower() if isinstance(risk_preference, str) else "balanced"
    if risk_preference == "conservative":
        tasks.append({
            "id": _stable_task_id(category="risk"),
            "title": "检查持仓风险敞口 — 关注防御性配置",
            "category": "risk",
            "priority": 2,
            "action_url": "/chat?query=分析我的持仓风险敞口",
            "icon": "Shield",
            "execution_params": {
                "query": "分析我的持仓风险敞口",
                "output_mode": "chat",
            },
        })
    elif risk_preference == "aggressive":
        tasks.append({
            "id": _stable_task_id(category="opportunity"),
            "title": "扫描高波动标的机会 — 事件驱动策略",
            "category": "opportunity",
            "priority": 2,
            "action_url": "/chat?query=近期有哪些高波动投资机会",
            "icon": "TrendingUp",
            "execution_params": {
                "query": "近期有哪些高波动投资机会",
                "output_mode": "chat",
            },
        })
    else:
        tasks.append({
            "id": _stable_task_id(category="rebalance"),
            "title": "组合再平衡检查 — 评估配置偏离度",
            "category": "rebalance",
            "priority": 3,
            "action_url": "/chat?query=我的持仓需要再平衡吗",
            "icon": "BarChart2",
            "execution_params": {
                "query": "我的持仓需要再平衡吗",
                "output_mode": "chat",
            },
        })

    # 按 priority 排序 (1=高, 3=低), 最多 5 条
    tasks.sort(key=lambda t: t["priority"])
    return tasks[:5]
