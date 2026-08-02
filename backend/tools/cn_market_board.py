from __future__ import annotations

import logging
import os

from backend.utils.env_config import env_int
from typing import Any

from backend.tools.http import _http_get
from backend.utils.quote import safe_float, safe_int

logger = logging.getLogger(__name__)

_EASTMONEY_USER_AGENT = os.getenv("EASTMONEY_USER_AGENT", "Mozilla/5.0 (FinSight)")
_EASTMONEY_TIMEOUT = env_int("EASTMONEY_TIMEOUT", 12, minimum=1)
_EASTMONEY_LIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
_EASTMONEY_DATA_CENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def _eastmoney_list(*, fs: str, fields: str, limit: int = 20) -> list[dict[str, Any]] | None:
    """返回行列表；上游请求失败/非 200/结构异常时返回 None（区别于"真的 0 行"）。"""
    params = {
        "pn": "1",
        "pz": str(max(1, min(safe_int(limit, 20) or 20, 200))),
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": "f3",
        "fs": fs,
        "fields": fields,
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
        data = payload.get("data") if isinstance(payload, dict) else None
        rows = data.get("diff") if isinstance(data, dict) else None
        return rows if isinstance(rows, list) else []
    except Exception as exc:
        logger.info('cn market board list failed')
        return None


def _fetch_failed(source: str) -> dict[str, Any]:
    # 上游故障不得伪装成 success=True + 0 行（"今日无数据"），否则调用方
    # （agent/前端）把数据源中断当成真实市况（R52）。保持字段形状兼容。
    return {
        "success": False,
        "error": "eastmoney fetch failed",
        "items": [],
        "count": 0,
        "source": source,
        "market": "CN",
    }


def fetch_limit_board(*, limit: int = 20) -> dict[str, Any]:
    """Fetch limit-up board style ranking from Eastmoney list endpoint."""
    rows = _eastmoney_list(
        fs="m:0+t:4,m:1+t:4",
        fields="f12,f14,f2,f3,f8,f10,f62",
        limit=limit,
    )
    if rows is None:
        return _fetch_failed("eastmoney_clist")
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get("f12") or "").strip()
        if not code:
            continue
        items.append(
            {
                "symbol": code,
                "name": str(row.get("f14") or "").strip() or code,
                "last_price": safe_float(row.get("f2")),
                "change_percent": safe_float(row.get("f3")),
                "turnover_rate": safe_float(row.get("f8")),
                "volume_ratio": safe_float(row.get("f10")),
                "main_net_inflow": safe_float(row.get("f62")),
            }
        )

    return {
        "success": True,
        "items": items,
        "count": len(items),
        "source": "eastmoney_clist",
        "market": "CN",
    }


def fetch_lhb(*, limit: int = 20) -> dict[str, Any]:
    """Fetch LongHuBang-like list from Eastmoney datacenter endpoint."""
    params = {
        "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
        "columns": "ALL",
        "pageNumber": "1",
        "pageSize": str(max(1, min(safe_int(limit, 20) or 20, 100))),
        "sortTypes": "-1",
        "sortColumns": "TRADE_DATE",
        "source": "WEB",
        "client": "WEB",
    }
    items: list[dict[str, Any]] = []
    fetch_ok = False
    try:
        resp = _http_get(
            _EASTMONEY_DATA_CENTER_URL,
            params=params,
            timeout=_EASTMONEY_TIMEOUT,
            headers={"User-Agent": _EASTMONEY_USER_AGENT},
        )
        if getattr(resp, "status_code", 0) == 200:
            payload = resp.json()
            if isinstance(payload, dict):
                # datacenter 接口 200 + dict 载荷视为已应答；result 为空是
                # 合法的"当日无龙虎榜"（周末/节假日），不算故障。
                fetch_ok = True
                result = payload.get("result")
                rows = result.get("data") if isinstance(result, dict) else None
                if isinstance(rows, list):
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        symbol = str(row.get("SECURITY_CODE") or "").strip()
                        if not symbol:
                            continue
                        items.append(
                            {
                                "symbol": symbol,
                                "name": str(row.get("SECURITY_NAME_ABBR") or "").strip() or symbol,
                                "trade_date": row.get("TRADE_DATE"),
                                "close_price": safe_float(row.get("CLOSE_PRICE")),
                                "change_percent": safe_float(row.get("CHANGE_RATE")),
                                "net_buy": safe_float(row.get("NET_BUY_AMT")),
                                "buy_amt": safe_float(row.get("BUY_AMT")),
                                "sell_amt": safe_float(row.get("SELL_AMT")),
                                "reason": row.get("EXPLAIN"),
                            }
                        )
    except Exception as exc:
        logger.info("fetch_lhb failed: %s", type(exc).__name__)

    if not fetch_ok:
        return _fetch_failed("eastmoney_datacenter")

    return {
        "success": True,
        "items": items,
        "count": len(items),
        "source": "eastmoney_datacenter",
        "market": "CN",
    }


__all__ = ["fetch_limit_board", "fetch_lhb"]
