from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.memory import MemoryService
from backend.services.portfolio_store import save_suggestion, update_position
from backend.services.report_index import ReportIndexStore
from backend.services.research_notes import create_note, list_notes
from backend.services.subscription_service import SubscriptionService


USER_ID = "default_user"
SESSION_ID = "user:default_user:vue-shadow"
EMAIL = "local-researcher@example.com"


def iso(days: int = 0, hours: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days, hours=hours)).isoformat()


def seed_portfolio() -> None:
    positions = [
        {
            "ticker": "AAPL",
            "shares": 18,
            "avg_cost": 182.4,
            "name": "Apple Inc.",
            "tags": ["核心持仓", "消费电子"],
            "note": "关注换机周期、服务收入增速和回购节奏。",
            "sector": "Technology",
            "currency": "USD",
            "opened_at": iso(-96),
        },
        {
            "ticker": "MSFT",
            "shares": 9,
            "avg_cost": 408.6,
            "name": "Microsoft",
            "tags": ["云计算", "AI"],
            "note": "Azure 增速和 AI Copilot 商业化是主要观察点。",
            "sector": "Technology",
            "currency": "USD",
            "opened_at": iso(-72),
        },
        {
            "ticker": "NVDA",
            "shares": 6,
            "avg_cost": 116.2,
            "name": "NVIDIA",
            "tags": ["半导体", "高波动"],
            "note": "仓位较小，重点看数据中心订单和毛利率韧性。",
            "sector": "Semiconductors",
            "currency": "USD",
            "opened_at": iso(-54),
        },
        {
            "ticker": "600519.SS",
            "shares": 2,
            "avg_cost": 1508.0,
            "name": "贵州茅台",
            "tags": ["A股", "消费"],
            "note": "观察批价、渠道库存和现金分红稳定性。",
            "sector": "Consumer Staples",
            "currency": "CNY",
            "opened_at": iso(-36),
        },
        {
            "ticker": "0700.HK",
            "shares": 100,
            "avg_cost": 375.0,
            "name": "腾讯控股",
            "tags": ["港股", "互联网"],
            "note": "重点跟踪游戏流水、广告恢复和回购力度。",
            "sector": "Communication Services",
            "currency": "HKD",
            "opened_at": iso(-28),
        },
    ]
    for pos in positions:
        update_position(SESSION_ID, **pos)

    save_suggestion(
        "seed_rebalance_20260630",
        SESSION_ID,
        {
            "title": "月底仓位复盘",
            "summary": "组合偏科技成长，建议把单一高波动敞口控制在可承受范围内，并保留现金缓冲。",
            "actions": [
                {"ticker": "NVDA", "action": "trim_watch", "reason": "涨跌幅弹性较大，等待财报后再决定是否加仓。"},
                {"ticker": "600519.SS", "action": "hold", "reason": "防御属性强，但需继续观察消费数据。"},
                {"ticker": "0700.HK", "action": "hold_watch", "reason": "回购提供支撑，等待港股流动性确认。"},
            ],
            "created_by": "local_seed",
        },
    )


def seed_watchlist() -> None:
    memory = MemoryService()
    items = [
        ("AAPL", "Apple Inc.", ["核心", "财报"], "等待下一次业绩电话会验证服务收入质量。", "核心跟踪", 1, "active"),
        ("MSFT", "Microsoft", ["云", "AI"], "关注 Azure 与 Copilot 的增长拆分。", "核心跟踪", 2, "active"),
        ("NVDA", "NVIDIA", ["半导体", "波动"], "只做小仓观察，等待供需边际变化。", "高波动", 3, "reviewing"),
        ("600519.SS", "贵州茅台", ["A股", "消费"], "看批价、库存和分红预期。", "A股观察", 2, "active"),
        ("0700.HK", "腾讯控股", ["港股", "互联网"], "关注回购、广告、游戏流水。", "港股观察", 2, "active"),
        ("9988.HK", "阿里巴巴", ["港股", "电商"], "观察云业务和股东回报变化。", "港股观察", 4, "new"),
    ]
    for ticker, name, tags, note, group, priority, status in items:
        memory.add_to_watchlist(
            USER_ID,
            ticker,
            name=name,
            tags=tags,
            note=note,
            group=group,
            priority=priority,
            watch_reason=note,
            research_status=status,
        )
    memory.set_preference(USER_ID, "default_symbol", "AAPL")
    memory.set_preference(USER_ID, "market_focus", ["US", "CN", "HK"])
    memory.set_preference(USER_ID, "risk_style", "balanced")


def seed_notes() -> None:
    existing = list_notes(SESSION_ID, USER_ID, limit=200)
    existing_titles = {item.get("title") for item in existing}
    notes = [
        (
            "AAPL 服务收入复查",
            "AAPL",
            ["财报", "现金流"],
            "假设：硬件周期放缓时，服务收入和回购仍能托住每股收益。\n\n待验证：\n- 服务收入增速是否继续高于硬件。\n- 大中华区收入是否稳定。\n- 回购规模是否继续抵消股本稀释。",
        ),
        (
            "NVDA 风险边界",
            "NVDA",
            ["半导体", "风险"],
            "当前更适合把 NVDA 视为高波动资产。\n\n观察点：数据中心订单能见度、毛利率、客户集中度、出口限制带来的不确定性。",
        ),
        (
            "600519.SS 消费防御观察",
            "600519.SS",
            ["A股", "消费"],
            "茅台不是看短期弹性，而是看渠道价格、库存和分红稳定性。\n\n如果批价连续走弱，需要下调防御权重。",
        ),
        (
            "0700.HK 港股互联网复盘",
            "0700.HK",
            ["港股", "互联网"],
            "腾讯的观察重点：游戏流水、视频号广告、金融科技恢复、回购节奏。\n\n港股整体流动性改善时，估值弹性可能放大。",
        ),
    ]
    for title, ticker, tags, content in notes:
        if title not in existing_titles:
            create_note(SESSION_ID, USER_ID, title=title, ticker=ticker, tags=tags, content=content)


def report_payload(report_id: str, ticker: str, title: str, summary: str, tags: list[str], confidence: float, days: int) -> dict:
    generated_at = iso(days)
    return {
        "report_id": report_id,
        "session_id": SESSION_ID,
        "ticker": ticker,
        "title": title,
        "summary": summary,
        "tags": tags,
        "generated_at": generated_at,
        "as_of": generated_at,
        "freshness_status": "cached",
        "confidence_score": confidence,
        "source_type": "ai_generated",
        "quality_state": "pass",
        "meta": {
            "source_type": "ai_generated",
            "analysis_depth": "report",
            "source_trigger": "seeded_local_usage",
            "as_of": generated_at,
        },
        "sections": [
            {"heading": "核心结论", "content": summary},
            {"heading": "后续动作", "content": "继续观察真实行情、财报与新闻证据，不把本地记录当作实时价格来源。"},
        ],
        "citations": [
            {
                "title": f"{ticker} 公司资料",
                "url": f"https://example.com/research/{ticker.lower()}",
                "snippet": "本地种子数据仅用于展示报告库使用痕迹。",
                "published_date": generated_at[:10],
                "confidence": 0.7,
            },
            {
                "title": "组合复盘记录",
                "url": f"https://example.com/portfolio/{ticker.lower()}",
                "snippet": "结合持仓、笔记和关注列表生成的本地复盘摘要。",
                "published_date": generated_at[:10],
                "confidence": 0.68,
            },
        ],
    }


def seed_reports() -> None:
    store = ReportIndexStore()
    reports = [
        report_payload(
            "seed_report_aapl_quality_202606",
            "AAPL",
            "AAPL 质量与现金流复盘",
            "服务收入、回购和生态粘性仍是主要支撑，短期需要验证硬件需求是否拖累整体增速。",
            ["质量", "现金流", "核心持仓"],
            0.82,
            -2,
        ),
        report_payload(
            "seed_report_msft_ai_cloud_202606",
            "MSFT",
            "MSFT 云与 AI 商业化观察",
            "Azure 与 Copilot 是增长主线，估值需要持续的企业端付费证据来支撑。",
            ["云计算", "AI", "财报"],
            0.79,
            -4,
        ),
        report_payload(
            "seed_report_cn_hk_watch_202606",
            "0700.HK",
            "港股互联网与回购线索",
            "腾讯回购和广告恢复提供下限，仍需跟踪港股流动性和游戏流水。",
            ["港股", "互联网", "回购"],
            0.74,
            -6,
        ),
    ]
    for report in reports:
        store.upsert_report(session_id=SESSION_ID, report=report, include_blocked=True)


def seed_subscriptions() -> None:
    service = SubscriptionService()
    service.subscribe(EMAIL, "AAPL", ["price_change", "news", "report"], price_threshold=3.0, risk_threshold="medium")
    service.subscribe(EMAIL, "NVDA", ["price_change", "risk"], price_threshold=5.0, risk_threshold="high")
    service.subscribe(EMAIL, "600519.SS", ["news", "report"], risk_threshold="medium")
    service.record_alert_event(
        EMAIL,
        "NVDA",
        "price_change",
        title="NVDA 波动提醒",
        message="本地记录：高波动持仓需要复查仓位上限。",
        metadata={"source": "local_seed"},
    )


def main() -> None:
    os.chdir(ROOT)
    seed_portfolio()
    seed_watchlist()
    seed_notes()
    seed_reports()
    seed_subscriptions()
    print(json.dumps({
        "ok": True,
        "session_id": SESSION_ID,
        "user_id": USER_ID,
        "message": "local usage data seeded",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
