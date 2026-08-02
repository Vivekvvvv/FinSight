# -*- coding: utf-8 -*-
"""Daily Risk Snapshot Scheduler

每日定时任务：为所有活跃用户的 Portfolio 生成风险快照。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from backend.services.portfolio_store import get_all_active_sessions
from backend.services.portfolio_risk_lens import calculate_portfolio_risk_lens
from backend.services.risk_snapshots import save_risk_snapshot

logger = logging.getLogger(__name__)


def take_daily_risk_snapshot() -> None:
    """执行每日快照任务

    遍历所有有持仓数据的 session，计算风险透镜并保存快照。
    """
    logger.info("Starting daily risk snapshot job")

    try:
        # 获取所有活跃会话（有持仓数据的 session）
        sessions = get_all_active_sessions()
        logger.info("Active sessions loaded")

        snapshot_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        success_count = 0
        error_count = 0

        for session_id, user_id in sessions:
            try:
                # 获取持仓数据
                from backend.services.portfolio_store import get_positions
                positions = get_positions(session_id)

                if not positions:
                    continue

                # 获取相关报告（用于质量评估）
                from backend.services.report_index import get_report_index_store
                store = get_report_index_store()
                tickers = [p["ticker"] for p in positions if p.get("ticker")]
                reports = []
                for ticker in tickers:
                    # list_reports 返回 list[dict]，不是 {"items": [...]}
                    ticker_reports = store.list_reports(
                        session_id=session_id,
                        ticker=ticker,
                        limit=1,
                    )
                    reports.extend(ticker_reports)

                # 计算风险透镜
                risk_lens = calculate_portfolio_risk_lens(positions, reports)

                # 保存快照
                save_risk_snapshot(session_id, user_id, risk_lens, snapshot_date)
                success_count += 1

            except Exception as e:
                logger.error(
                    "Failed to snapshot portfolio: %s",
                    type(e).__name__,
                )
                error_count += 1

        logger.info("Daily risk snapshot completed")

    except Exception as e:
        logger.error("Daily risk snapshot job failed: %s", type(e).__name__)


def start_risk_snapshot_scheduler() -> BackgroundScheduler:
    """启动风险快照调度器

    每日 UTC 16:00 执行（北京时间 00:00）。

    Returns:
        BackgroundScheduler 实例
    """
    scheduler = BackgroundScheduler()

    # 每天 UTC 16:00 执行（北京时间 00:00）
    scheduler.add_job(
        take_daily_risk_snapshot,
        trigger="cron",
        hour=16,
        minute=0,
        timezone="UTC",
        id="daily_risk_snapshot",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Risk snapshot scheduler started (daily at UTC 16:00)")

    return scheduler
