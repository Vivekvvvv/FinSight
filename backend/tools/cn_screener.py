# -*- coding: utf-8 -*-
"""A股/港股全市场筛选 —— 东方财富公开列表接口（免 key）。

股票发现页此前 CN/HK 只有 15 只硬编码热门票（FMP 付费筛选器不覆盖
CN/HK，直接走 fallback 链）。本模块用 Eastmoney clist 排行接口提供
全市场真实数据：A股约 5000+ 只（沪深主板+创业板+科创板）、港股主板，
支持服务端排序 + 分页，数值筛选在本地应用。

上游故障返回 None，由 screener.screen_stocks 回落既有 fallback 链
（Alpha Vantage / yfinance 热门票 / 静态演示），不改变原有降级语义。
"""
from __future__ import annotations

import logging
import os

from backend.utils.env_config import env_int
from typing import Any

from backend.tools.http import _http_get
from backend.utils.quote import safe_float

logger = logging.getLogger(__name__)

_EASTMONEY_USER_AGENT = os.getenv("EASTMONEY_USER_AGENT", "Mozilla/5.0 (FinSight)")
_EASTMONEY_TIMEOUT = env_int("EASTMONEY_TIMEOUT", 12, minimum=1)
_EASTMONEY_LIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"

# 市场 → Eastmoney fs 板块过滤：沪主板+科创板 / 深主板+创业板；港股主板
_MARKET_FS = {
    "CN": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
    "HK": "m:116",
}

# screen_stocks 契约的 sort_by → Eastmoney fid 排序字段。
# beta / lastAnnualDividend 无对应字段，退化为按总市值排（capability_note 说明）。
_SORT_FID = {
    "marketCap": "f20",
    "price": "f2",
    "volume": "f5",
    "changesPercentage": "f3",
    "beta": "f20",
    "lastAnnualDividend": "f20",
}

# f12 代码 f13 市场 f14 名称 f2 现价 f3 涨跌% f5 成交量 f6 成交额
# f8 换手% f9 PE(TTM) f20 总市值 f21 流通市值 f23 PB f62 主力净流入 f100 行业
_FIELDS = "f12,f13,f14,f2,f3,f5,f6,f8,f9,f20,f21,f23,f62,f100"

_PAGE_SIZE = 100
_MAX_PAGES = 10  # 本地过滤最多扫 10 页（1000 行），防止苛刻条件深翻页打爆上游


def _fetch_page(*, fs: str, fid: str, po: int, page: int) -> list[dict[str, Any]] | None:
    """拉一页排行。请求失败/非 200/载荷异常返回 None（区别于"没有更多行"的 []）。"""
    params = {
        "pn": str(page),
        "pz": str(_PAGE_SIZE),
        "po": str(po),
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": fid,
        "fs": fs,
        "fields": _FIELDS,
    }
    try:
        resp = _http_get(
            _EASTMONEY_LIST_URL,
            params=params,
            timeout=_EASTMONEY_TIMEOUT,
            headers={"User-Agent": _EASTMONEY_USER_AGENT},
        )
        if getattr(resp, "status_code", 0) != 200:
            return None
        payload = resp.json()
        if not isinstance(payload, dict):
            return None
        data = payload.get("data")
        diff = data.get("diff") if isinstance(data, dict) else None
        if isinstance(diff, list):
            return [row for row in diff if isinstance(row, dict)]
        return []
    except Exception as exc:
        logger.info("eastmoney screener page %s failed: %s", page, type(exc).__name__)
        return None


def _to_symbol(code: str, market_id: str, market: str) -> str:
    """转项目通用 Yahoo 后缀：600519.SS / 000001.SZ / 0700.HK。"""
    if market == "HK":
        digits = code.lstrip("0") or "0"
        return f"{digits.zfill(4)}.HK"
    if market_id == "1":
        return f"{code}.SS"
    return f"{code}.SZ"


def _build_item(row: dict[str, Any], market: str) -> dict[str, Any] | None:
    code = str(row.get("f12") or "").strip()
    if not code:
        return None
    symbol = _to_symbol(code, str(row.get("f13") or "").strip(), market)
    volume = safe_float(row.get("f5"))
    if market == "CN" and volume is not None:
        volume *= 100  # A股 f5 单位是手（100 股），统一转股数与美股口径一致
    sector = str(row.get("f100") or "").strip() or None
    return {
        "symbol": symbol,
        "name": str(row.get("f14") or "").strip() or symbol,
        "sector": sector,
        "industry": sector,
        "country": market,
        "exchange": "HKEX" if market == "HK" else ("Shanghai" if symbol.endswith(".SS") else "Shenzhen"),
        "price": safe_float(row.get("f2")),
        "market_cap": safe_float(row.get("f20")),
        "volume": volume,
        "beta": None,
        "dividend": None,
        "change_percent": safe_float(row.get("f3")),
        "pe": safe_float(row.get("f9")),
        "pb": safe_float(row.get("f23")),
        "turnover_rate": safe_float(row.get("f8")),
        "main_net_inflow": safe_float(row.get("f62")),
    }


def _passes_filters(item: dict[str, Any], filters: dict[str, Any]) -> bool:
    """与 screener._yfinance_popular_stocks 同语义：字段缺失时不排除该行。"""
    price = item.get("price")
    market_cap = item.get("market_cap")
    volume = item.get("volume")

    checks = (
        ("priceMoreThan", price, lambda v, t: v < t),
        ("priceLowerThan", price, lambda v, t: v > t),
        ("marketCapMoreThan", market_cap, lambda v, t: v < t),
        ("marketCapLowerThan", market_cap, lambda v, t: v > t),
        ("volumeMoreThan", volume, lambda v, t: v < t),
    )
    for key, value, violates in checks:
        threshold = safe_float(filters.get(key))
        if threshold is None or value is None:
            continue
        if violates(value, threshold):
            return False
    return True


def eastmoney_screen_stocks(
    *,
    market: str,
    filters: dict[str, Any] | None,
    limit: int,
    page: int,
    sort_by: str,
    sort_order: str,
) -> dict[str, Any] | None:
    """全市场筛选。上游故障返回 None（调用方回落既有 fallback 链）。"""
    market_norm = str(market or "").strip().upper()
    fs = _MARKET_FS.get(market_norm)
    if not fs:
        return None

    fid = _SORT_FID.get(sort_by, "f20")
    po = 0 if str(sort_order or "").strip().lower() == "asc" else 1
    active_filters = {k: v for k, v in (filters or {}).items() if v is not None}
    target = max(1, limit) * max(1, page)

    collected: list[dict[str, Any]] = []
    for pn in range(1, _MAX_PAGES + 1):
        rows = _fetch_page(fs=fs, fid=fid, po=po, page=pn)
        if rows is None:
            if pn == 1:
                return None  # 首页即故障：整体降级
            break  # 已有部分页成功，用已收集数据
        if not rows:
            break
        for row in rows:
            item = _build_item(row, market_norm)
            if item is None or not _passes_filters(item, active_filters):
                continue
            collected.append(item)
        if len(collected) >= target:
            break
        if len(rows) < _PAGE_SIZE:
            break  # 已到最后一页

    start = (max(1, page) - 1) * max(1, limit)
    sliced = collected[start : start + max(1, limit)]

    note = "A股/港股全市场数据来自东方财富公开列表接口（免 key）。"
    if sort_by in {"beta", "lastAnnualDividend"}:
        note += "该数据源不支持 beta/股息排序，已按总市值排序代替。"

    return {
        "success": True,
        "market": market_norm,
        "filters": filters if isinstance(filters, dict) else {},
        "sort": {"by": sort_by, "order": sort_order},
        "items": sliced,
        "count": len(sliced),
        "results": sliced,
        "source": "eastmoney_clist_screener",
        "warning": None,
        "capability_note": note,
    }


__all__ = ["eastmoney_screen_stocks"]
