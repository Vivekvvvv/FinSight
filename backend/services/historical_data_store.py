# -*- coding: utf-8 -*-
"""
A股历史K线数据下载与缓存服务

- 使用 baostock 拉取日线数据（前复权/后复权/不复权）
- 结果缓存到 SQLite，避免重复请求
- 数据清洗：去停牌异常、ffill缺失、标记涨跌幅异常（>22%）
- baostock 不可用时 fallback 到现有 get_stock_historical_data
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Any

from backend.services.cn_holiday import is_cn_holiday
from backend.utils.quote import safe_float, safe_int

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(os.path.dirname(__file__), "../../data/historical_kline.db")
_lock = threading.RLock()
_table_ready = False


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    c = sqlite3.connect(_DB_PATH, timeout=30, isolation_level=None)
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _ensure_table() -> None:
    global _table_ready
    if _table_ready:
        return
    with _lock, _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS kline_cache (
                ticker     TEXT NOT NULL,
                date       TEXT NOT NULL,
                open       REAL,
                high       REAL,
                low        REAL,
                close      REAL,
                volume     REAL,
                adjust     TEXT NOT NULL DEFAULT 'qfq',
                is_suspicious INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (ticker, date, adjust)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_kline_ticker_date ON kline_cache(ticker, adjust, date)")
        # 记录每次成功拉取的“声明区间”（审计 C2）：命中判定依据声明区间而非 bar 实际首末，
        # 否则 start 落在休市日（如默认 2020-01-01 元旦）时恒判未覆盖、缓存永不命中。
        c.execute("""
            CREATE TABLE IF NOT EXISTS kline_fetch_meta (
                ticker        TEXT NOT NULL,
                adjust        TEXT NOT NULL,
                fetched_start TEXT NOT NULL,
                fetched_end   TEXT NOT NULL,
                updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (ticker, adjust)
            )
        """)
    _table_ready = True


# ── baostock 工具 ──────────────────────────────────────────────────────────────

def _to_bs_code(ticker: str) -> str:
    """600519.SS → sh.600519  |  000001.SZ → sz.000001"""
    t = ticker.upper().replace(".SS", "").replace(".SZ", "").replace(".SH", "")
    prefix = t[:3]
    if prefix in ("600", "601", "603", "605", "688", "900"):
        return f"sh.{t}"
    elif prefix[:2] in ("00", "30", "20", "39"):
        return f"sz.{t}"
    elif ticker.upper().endswith(".SS"):
        return f"sh.{t}"
    return f"sz.{t}"


def _adjust_flag(adjust: str) -> str:
    return {"qfq": "2", "hfq": "1", "none": "3"}.get(adjust.lower(), "3")


def _fetch_baostock(ticker: str, start: str, end: str, adjust: str) -> list[dict[str, Any]]:
    """用 baostock 拉取日线，返回清洗后的列表"""
    try:
        import baostock as bs
        bs.login()
        rs = bs.query_history_k_data_plus(
            code=_to_bs_code(ticker),
            fields="date,open,high,low,close,volume",
            start_date=start,
            end_date=end,
            frequency="d",
            adjustflag=_adjust_flag(adjust),
        )
        rows = []
        while rs.error_code == "0" and rs.next():
            row = rs.get_row_data()
            rows.append({
                "date": row[0],
                "open": safe_float(row[1]),
                "high": safe_float(row[2]),
                "low": safe_float(row[3]),
                "close": safe_float(row[4]),
                "volume": safe_float(row[5]),
            })
        bs.logout()
        return rows
    except ImportError:
        logger.warning("baostock 未安装")
        return []
    except Exception as e:
        logger.warning("baostock 拉取失败 %s: %s", ticker, type(e).__name__)
        try:
            import baostock as bs
            bs.logout()
        except Exception as logout_exc:
            logger.debug("baostock logout failed: %s", type(logout_exc).__name__)
        return []


def _clean(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """数据清洗：去异常行，ffill缺失，标记涨跌幅>22%的行"""
    # 过滤 close 为空、不可解析、非有限或非正的行。
    valid = []
    for row in rows:
        close = safe_float(row.get("close"))
        if close is None:
            continue
        if close > 0:
            row["close"] = close
            valid.append(row)
    if not valid:
        return []

    # 排序
    valid.sort(key=lambda x: x["date"])

    # ffill：用前一天 close 填充缺失的 open/high/low
    for i, r in enumerate(valid):
        for field in ("open", "high", "low"):
            value = safe_float(r.get(field))
            if value is None or value <= 0:
                value = valid[i - 1]["close"] if field == "open" and i > 0 else r["close"]
            r[field] = value

        volume = safe_float(r.get("volume"))
        r["volume"] = volume if volume is not None and volume >= 0 else 0.0

    # 标记异常（涨跌幅 > 22%）
    for i, r in enumerate(valid):
        if i == 0:
            r["is_suspicious"] = False
            continue
        prev = float(valid[i - 1]["close"])
        curr = float(r["close"])
        pct = abs(curr - prev) / prev if prev > 0 else 0
        r["is_suspicious"] = pct > 0.22

    return valid


# 复权价随分红除权回溯变化，命中还须最近拉取过；超期强制重拉刷新复权因子
_ADJUSTED_REFRESH_TTL_DAYS = 7
# baostock 日线约在收盘后傍晚发布；北京时间 20 点前不要求当日 bar，否则盘中恒判未覆盖
_EOD_PUBLISH_HOUR_BJ = 20


def _required_end(end_d: date, now_bj: datetime | None = None) -> date:
    """尾部覆盖要求的最晚日期：不晚于“日线应已发布”的最后一个交易日。"""
    if now_bj is None:
        now_bj = datetime.now(timezone(timedelta(hours=8)))
    latest = now_bj.date()
    if now_bj.hour < _EOD_PUBLISH_HOUR_BJ:
        latest -= timedelta(days=1)
    required = min(end_d, latest)
    # 回退到最近交易日（节假日表覆盖 2024+；表外年份仅周末回退，方向安全——只会多拉不会漏）
    for _ in range(12):
        if not is_cn_holiday(required):
            break
        required -= timedelta(days=1)
    return required


def _read_cache(ticker: str, start: str, end: str, adjust: str) -> list[dict[str, Any]] | None:
    _ensure_table()
    with _lock, _conn() as c:
        meta = c.execute(
            "SELECT fetched_start, fetched_end, updated_at FROM kline_fetch_meta WHERE ticker=? AND adjust=?",
            (ticker.upper(), adjust),
        ).fetchone()
        if not meta:
            return None  # 无拉取记录（存量库/新标的），重拉一次即建立声明区间
        rows = c.execute("""
            SELECT date, open, high, low, close, volume, is_suspicious
            FROM kline_cache
            WHERE ticker=? AND adjust=? AND date>=? AND date<=?
            ORDER BY date
        """, (ticker.upper(), adjust, start, end)).fetchall()

    if not rows:
        return None

    try:
        start_d = date.fromisoformat(start)
        end_d = date.fromisoformat(end)
        fetched_start_d = date.fromisoformat(meta[0])
        fetched_end_d = date.fromisoformat(meta[1])
    except ValueError:
        return None

    # 覆盖判定（审计 C2）：对比“声明区间”，与请求边界是否为交易日无关
    if fetched_start_d > start_d or fetched_end_d < _required_end(end_d):
        return None

    if adjust != "none":
        stale_before = (
            datetime.now(timezone.utc) - timedelta(days=_ADJUSTED_REFRESH_TTL_DAYS)
        ).strftime("%Y-%m-%d %H:%M:%S")
        if str(meta[2] or "") < stale_before:  # updated_at 为 SQLite datetime('now')，UTC 同格式
            return None

    return [
        {"date": r[0], "open": r[1], "high": r[2], "low": r[3],
         "close": r[4], "volume": r[5], "is_suspicious": bool(r[6])}
        for r in rows
    ]


def _write_cache(
    ticker: str,
    rows: list[dict[str, Any]],
    adjust: str,
    declared_start: str | None = None,
    declared_end: str | None = None,
) -> None:
    """写入 bar 数据并更新声明区间。

    declared_start/end 为本次实际请求过的日历区间（baostock 成功路径传入）；
    缺省时退化为 bar 实际首末（fallback 路径，无法确认请求区间是否被完整覆盖）。
    """
    _ensure_table()
    if not rows:
        return
    with _lock, _conn() as c:
        c.executemany("""
            INSERT OR REPLACE INTO kline_cache
              (ticker, date, open, high, low, close, volume, adjust, is_suspicious)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, [
            (ticker.upper(), r["date"], r.get("open"), r.get("high"),
             r.get("low"), r["close"], r.get("volume"), adjust,
             safe_int(r.get("is_suspicious"), 0) or 0)
            for r in rows
        ])

        new_start = declared_start or min(r["date"] for r in rows)
        new_end = declared_end or max(r["date"] for r in rows)
        old = c.execute(
            "SELECT fetched_start, fetched_end FROM kline_fetch_meta WHERE ticker=? AND adjust=?",
            (ticker.upper(), adjust),
        ).fetchone()
        if old:
            try:
                old_s, old_e = date.fromisoformat(old[0]), date.fromisoformat(old[1])
                new_s, new_e = date.fromisoformat(new_start), date.fromisoformat(new_end)
                # 仅重叠/相邻区间才合并；不连续则弃旧取新（中间的洞未拉取过，合并会造成假命中）
                if new_s <= old_e + timedelta(days=1) and new_e >= old_s - timedelta(days=1):
                    new_start = min(old[0], new_start)
                    new_end = max(old[1], new_end)
            except ValueError:
                pass
        c.execute(
            """INSERT OR REPLACE INTO kline_fetch_meta
               (ticker, adjust, fetched_start, fetched_end, updated_at)
               VALUES (?,?,?,?,datetime('now'))""",
            (ticker.upper(), adjust, new_start, new_end),
        )


# ── 公共接口 ──────────────────────────────────────────────────────────────────

def fetch_and_cache_kline(
    ticker: str,
    start_date: str = "2020-01-01",
    end_date: str | None = None,
    adjust: str = "qfq",
) -> list[dict[str, Any]]:
    """
    获取历史K线（带缓存 & 清洗）。

    优先级：SQLite缓存 → baostock → 现有工具降级

    Returns:
        list of {date, open, high, low, close, volume, is_suspicious}
    """
    if end_date is None:
        end_date = date.today().isoformat()

    # 检查缓存
    cached = _read_cache(ticker, start_date, end_date, adjust)
    if cached:
        logger.debug("kline cache hit: %s %s~%s", ticker, start_date, end_date)
        return cached

    # 从 baostock 拉取
    rows = _fetch_baostock(ticker, start_date, end_date, adjust)
    from_baostock = bool(rows)

    if not rows:
        # fallback：现有工具
        try:
            from backend.tools import get_stock_historical_data
            payload = get_stock_historical_data(ticker, period="5y", interval="1d")
            kdata = (payload or {}).get("kline_data") or []
            rows = [
                {"date": p.get("time", "")[:10], "open": p.get("open"),
                 "high": p.get("high"), "low": p.get("low"),
                 "close": p.get("close"), "volume": p.get("volume")}
                for p in kdata if p.get("close")
            ]
        except Exception as exc:
            logger.warning("historical fallback failed for %s: %s", ticker, type(exc).__name__)
            return []

    cleaned = _clean(rows)
    if cleaned:
        if from_baostock:
            # baostock 按请求区间返回，声明 [start_date, end_date] 已拉取；
            # 末端收敛到“应已发布的最后交易日”——end_date 是未来/当日时，
            # 数据只到最新 bar，照单全声明会让后续新交易日假命中。
            try:
                declared_end = min(end_date, _required_end(date.fromisoformat(end_date)).isoformat())
            except ValueError:
                declared_end = max(r["date"] for r in cleaned)
            _write_cache(ticker, cleaned, adjust, declared_start=start_date, declared_end=declared_end)
        else:
            # fallback 固定拉 5y，不能确认覆盖请求区间，仅声明 bar 实际首末
            _write_cache(ticker, cleaned, adjust)

    # 过滤日期范围
    return [r for r in cleaned if start_date <= r["date"] <= end_date]


def get_cached_tickers() -> list[str]:
    """返回已有缓存的股票列表"""
    _ensure_table()
    with _lock, _conn() as c:
        rows = c.execute("SELECT DISTINCT ticker FROM kline_cache").fetchall()
    return [r[0] for r in rows]


def clear_expired_cache(days: int = 365) -> int:
    """清理超过 N 天未访问的旧缓存，返回删除行数"""
    _ensure_table()
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    with _lock, _conn() as c:
        cur = c.execute("DELETE FROM kline_cache WHERE created_at < ?", (cutoff,))
        return cur.rowcount
