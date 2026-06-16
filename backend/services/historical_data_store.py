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
from datetime import date, timedelta
from typing import Any

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
                "open": float(row[1]) if row[1] else None,
                "high": float(row[2]) if row[2] else None,
                "low": float(row[3]) if row[3] else None,
                "close": float(row[4]) if row[4] else None,
                "volume": float(row[5]) if row[5] else None,
            })
        bs.logout()
        return rows
    except ImportError:
        logger.warning("baostock 未安装")
        return []
    except Exception as e:
        logger.warning("baostock 拉取失败 %s: %s", ticker, e)
        try:
            import baostock as bs
            bs.logout()
        except Exception:
            pass
        return []


def _clean(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """数据清洗：去异常行，ffill缺失，标记涨跌幅>22%的行"""
    # 过滤 close 为空或为0
    valid = [r for r in rows if r.get("close") and float(r["close"]) > 0]
    if not valid:
        return []

    # 排序
    valid.sort(key=lambda x: x["date"])

    # ffill：用前一天 close 填充缺失的 open/high/low
    for i, r in enumerate(valid):
        if r.get("open") is None or r.get("open", 0) <= 0:
            r["open"] = valid[i - 1]["close"] if i > 0 else r["close"]
        if r.get("high") is None or r.get("high", 0) <= 0:
            r["high"] = r["close"]
        if r.get("low") is None or r.get("low", 0) <= 0:
            r["low"] = r["close"]

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


def _read_cache(ticker: str, start: str, end: str, adjust: str) -> list[dict[str, Any]] | None:
    _ensure_table()
    with _lock, _conn() as c:
        rows = c.execute("""
            SELECT date, open, high, low, close, volume, is_suspicious
            FROM kline_cache
            WHERE ticker=? AND adjust=? AND date>=? AND date<=?
            ORDER BY date
        """, (ticker.upper(), adjust, start, end)).fetchall()

    if not rows:
        return None

    # 验证范围覆盖：首/末日期与请求基本吻合
    cached_start = rows[0][0]
    cached_end = rows[-1][0]
    if cached_start > start or cached_end < end:
        return None   # 缓存不覆盖请求范围，需重新拉取

    return [
        {"date": r[0], "open": r[1], "high": r[2], "low": r[3],
         "close": r[4], "volume": r[5], "is_suspicious": bool(r[6])}
        for r in rows
    ]


def _write_cache(ticker: str, rows: list[dict[str, Any]], adjust: str) -> None:
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
             int(r.get("is_suspicious", False)))
            for r in rows
        ])


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
        except Exception:
            return []

    cleaned = _clean(rows)
    if cleaned:
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
