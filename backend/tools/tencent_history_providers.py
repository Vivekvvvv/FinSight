"""Eastmoney history data provider functions.

Extracted from tools.tencent_provider so the provider module can stay focused
on real-time quote/kline/intraday/top-list access; tencent_provider re-exports
every name here for backward compatibility.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from backend.tools.http import _http_get
from backend.utils.quote import safe_float, safe_int
from backend.utils.strict_json import json_loads_strict


logger = logging.getLogger(__name__)


def _wan_to_yuan(value: Any) -> float | None:
    """万元转元。safe_float 对空串/"-"/None 返回 None，此前 `safe_float(x) * 10000`
    会 `None * 10000` 抛 TypeError，在循环里被外层 except 吞掉 → 整个多日/多股
    数据集丢弃（如北向资金历史一行停牌占位就返回 []）。无法解析时返回 None，
    只让该字段缺失，不牵连整批数据（R53）。"""
    parsed = safe_float(value)
    return parsed * 10000 if parsed is not None else None


def to_tencent_code(symbol: str) -> str | None:
    """将 Yahoo 格式（600519.SS）转换为腾讯格式（sh600519）"""
    text = str(symbol or "").strip().upper()
    if text.endswith(".SS"):
        return f"sh{text[:-3]}"
    if text.endswith(".SZ"):
        return f"sz{text[:-3]}"
    if text.endswith(".BJ"):
        return f"bj{text[:-3]}"
    return None


def fetch_cn_top_list_history(
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
    days: int = 7
) -> list[dict[str, Any]]:
    """
    获取龙虎榜历史记录

    参数:
        symbol: 股票代码（如 600519.SS）
        start_date: 开始日期（YYYY-MM-DD），优先级高于days
        end_date: 结束日期（YYYY-MM-DD），默认今天
        days: 查询天数（默认7天），当start_date为None时生效

    返回:
        [
            {
                "symbol": "600519.SS",
                "date": "2026-06-14",
                "reason": "涨跌幅偏离值7%",
                "buy_amount": 123456789.0,
                ...
            },
            ...
        ]
    """
    from datetime import timedelta

    code = to_tencent_code(symbol)
    if code is None:
        return []

    stock_code = code[2:] if len(code) > 2 else code

    # 计算日期范围
    if end_date is None:
        end_date = datetime.now(timezone.utc).date().isoformat()

    if start_date is None:
        end_dt = datetime.fromisoformat(end_date).date()
        start_dt = end_dt - timedelta(days=days)
        start_date = start_dt.isoformat()

    # pageSize 须覆盖请求的日期窗口：旧代码恒取 days（默认 7），调用方显式
    # 传 start_date/end_date 的更长区间会被静默截断（文档写明 start_date
    # 优先级高于 days，/api/stock/top-list/{ticker}/history 受影响）。
    try:
        window_days = (
            datetime.fromisoformat(str(end_date)[:10]).date()
            - datetime.fromisoformat(str(start_date)[:10]).date()
        ).days + 1
    except Exception:
        window_days = safe_int(days, 30)
    page_size = max(1, min(max(safe_int(days, 30), window_days), 100))

    try:
        resp = _http_get(
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            params={
                "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
                "columns": "ALL",
                "filter": f'(SECURITY_CODE="{stock_code}")',
                "pageNumber": "1",
        "pageSize": str(page_size),
                "sortTypes": "-1",
                "sortColumns": "TRADE_DATE",
                "source": "WEB",
                "client": "WEB",
            },
            timeout=(5, 10),
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code == 200:
            payload = resp.json()
            rows = ((payload.get("result") or {}).get("data") or []) if isinstance(payload, dict) else []
            results = []
            for record in rows:
                item = {
                    "symbol": symbol.upper(),
                    "stock_code": stock_code,
                    "stock_name": record.get("SECURITY_NAME_ABBR", ""),
                    "date": record.get("TRADE_DATE", ""),
                    "reason": record.get("EXPLANATION") or record.get("EXPLAIN") or "龙虎榜",
                    "close_price": safe_float(record.get("CLOSE_PRICE")),
                    "change_percent": safe_float(record.get("CHANGE_RATE")),
                    "buy_amount": safe_float(record.get("BILLBOARD_BUY_AMT") or record.get("SUM_BUY_AMT")) or 0.0,
                    "sell_amount": safe_float(record.get("BILLBOARD_SELL_AMT") or record.get("SUM_SELL_AMT")) or 0.0,
                    "net_buy": safe_float(record.get("BILLBOARD_NET_AMT") or record.get("NET_BS_AMT")) or 0.0,
                    "turnover_rate": safe_float(record.get("TURNOVERRATE")),
                    "source": "eastmoney_datacenter",
                }
                date_key = str(item.get("date") or "")[:10]
                if start_date and date_key < start_date:
                    continue
                if end_date and date_key > end_date:
                    continue
                results.append(item)
            if results:
                return sorted(results, key=lambda x: x["date"], reverse=True)
    except Exception as exc:
        logger.info("[Eastmoney] new top list history lookup failed: %s", type(exc).__name__)

    # 东方财富历史龙虎榜API
    url = f"http://data.eastmoney.com/DataCenter_V3/stock2016/TradeDetail/pagesize=200,page=1,sortRule=-1,sortType=,startDate={start_date},endDate={end_date},gpfw=0,code={stock_code},js=var%20data_tab_1.html"

    try:
        resp = _http_get(url, timeout=(5, 10))
        if resp.status_code != 200:
            logger.info("[东方财富] 龙虎榜历史 HTTP %d", resp.status_code)
            return []

        text = resp.text.strip()

        import re
        import json

        match = re.search(r'var\s+data_tab_1\s*=\s*(\[.*?\]);?', text, re.DOTALL)
        if not match:
            logger.info("[东方财富] 龙虎榜历史数据解析失败")
            return []

        data_list = json_loads_strict(match.group(1))

        if not data_list:
            return []

        # 解析每条记录
        results = []
        for record in data_list:
            if record.get("SCode") != stock_code:
                continue

            buy_amount = _wan_to_yuan(record.get("Bmoney", 0))
            sell_amount = _wan_to_yuan(record.get("Smoney", 0))
            net_buy = _wan_to_yuan(record.get("JmMoney", 0))

            results.append({
                "symbol": symbol.upper(),
                "stock_code": stock_code,
                "stock_name": record.get("SName", ""),
                "date": record.get("Tdate", ""),
                "reason": record.get("Ctypedes", "上榜"),
                "close_price": safe_float(record.get("ClosePrice")),
                "change_percent": safe_float(record.get("Chgradio")),
                "buy_amount": buy_amount,
                "sell_amount": sell_amount,
                "net_buy": net_buy,
                "turnover_rate": safe_float(record.get("TurnoverRate")),
                "source": "eastmoney"
            })

        # 按日期降序排列
        results.sort(key=lambda x: x["date"], reverse=True)

        return results

    except Exception as exc:
        logger.info("[东方财富] 龙虎榜历史获取失败: %s", type(exc).__name__)
        return []


def fetch_north_flow_history(days: int = 30) -> list[dict[str, Any]]:
    """
    获取北向资金历史数据（批量查询）

    参数:
        days: 查询天数（默认30天，最大90天）

    返回:
        [
            {
                "date": "2026-06-14",
                "north_flow": 12345678900.0,
                "sh_flow": 8000000000.0,
                "sz_flow": 4345678900.0
            },
            ...
        ]
    """
    from datetime import timedelta

    # 计算日期范围
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days)

    # 东方财富北向资金历史API
    # 数据中心：沪深港通资金流向
    url = "http://push2his.eastmoney.com/api/qt/kamt.kline/get"
    params = {
        "fields1": "f1,f2,f3,f4",
        "fields2": "f51,f52,f53,f54,f55,f56",
        "klt": "101",  # 日线
        "lmt": days,
        "ut": "b2884a393a59ad64002292a3e90d46a5"
    }

    try:
        resp = _http_get(url, params=params, timeout=(5, 10))
        if resp.status_code != 200:
            logger.info("[东方财富] 北向资金历史 HTTP %d", resp.status_code)
            return []

        import json
        data = json_loads_strict(resp.text)

        if data.get("rc") != 0 or not data.get("data"):
            logger.info("[东方财富] 北向资金历史返回错误")
            return []

        result_data = data["data"]

        # 解析K线数据
        # klines格式：["日期,北向,沪股通,深股通", ...]
        klines = result_data.get("klines", [])

        results = []
        for kline in klines:
            parts = kline.split(",")
            if len(parts) >= 4:
                date_str = parts[0]  # YYYY-MM-DD
                north = _wan_to_yuan(parts[1])  # 万元转元
                sh = _wan_to_yuan(parts[2])
                sz = _wan_to_yuan(parts[3])

                results.append({
                    "date": date_str,
                    "north_flow": north,
                    "sh_flow": sh,
                    "sz_flow": sz,
                    "source": "eastmoney"
                })

        # 按日期降序排列
        results.sort(key=lambda x: x["date"], reverse=True)

        return results

    except Exception as exc:
        logger.info("[东方财富] 北向资金历史获取失败: %s", type(exc).__name__)
        return []


def fetch_margin_trading_history(symbol: str, days: int = 90) -> list[dict[str, Any]]:
    """
    获取融资融券历史数据

    参数:
        symbol: 股票代码（如 600519.SS）
        days: 查询天数（默认90天，最大180天）

    返回:
        [
            {
                "date": "2026-06-14",
                "margin_balance": 1234567890.0,
                "margin_buy": 50000000.0,
                "margin_repay": 30000000.0,
                "short_balance": 123456.0,
                "short_sell": 10000.0,
                "short_repay": 5000.0,
                "total_balance": 1234691346.0
            },
            ...
        ]
    """
    code = to_tencent_code(symbol)
    if code is None:
        return []

    stock_code = code[2:] if len(code) > 2 else code

    try:
        resp = _http_get(
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            params={
                "reportName": "RPTA_WEB_RZRQ_GGMX",
                "columns": "ALL",
                "filter": f'(SCODE="{stock_code}")',
                "pageNumber": "1",
        "pageSize": str(max(1, min(safe_int(days, 90), 200))),
                "sortTypes": "-1",
                "sortColumns": "DATE",
                "source": "WEB",
                "client": "WEB",
            },
            timeout=(5, 10),
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code == 200:
            payload = resp.json()
            rows = ((payload.get("result") or {}).get("data") or []) if isinstance(payload, dict) else []
            results = [
                {
                    "symbol": symbol.upper(),
                    "stock_code": stock_code,
                    "date": record.get("DATE", ""),
                    "margin_balance": safe_float(record.get("RZYE")) or 0.0,
                    "margin_buy": safe_float(record.get("RZMRE")) or 0.0,
                    "margin_repay": safe_float(record.get("RZCHE")) or 0.0,
                    "short_balance": safe_float(record.get("RQYL")) or 0.0,
                    "short_sell": safe_float(record.get("RQMCL")) or 0.0,
                    "short_repay": safe_float(record.get("RQCHL")) or 0.0,
                    "total_balance": safe_float(record.get("RZRQYE")) or 0.0,
                    "source": "eastmoney",
                }
                for record in rows
            ]
            if results:
                return sorted(results, key=lambda x: x["date"], reverse=True)
    except Exception as exc:
        logger.info("[Eastmoney] new margin trading history lookup failed: %s", type(exc).__name__)

    # 东方财富融资融券历史API
    url = "http://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "reportName": "RPT_RZRQ_LSHJ",
        "columns": "TRADE_DATE,SECURITY_CODE,RZYE,RZMRE,RZCHE,RQYL,RQMCL,RQCHL,RZRQYE",
        "quoteColumns": "",
        "filter": f'(SECURITY_CODE="{stock_code}")',
        "pageNumber": "1",
        "pageSize": str(days),
        "sortTypes": "-1",
        "sortColumns": "TRADE_DATE",
        "source": "WEB",
        "client": "WEB"
    }

    try:
        resp = _http_get(url, params=params, timeout=(5, 10))
        if resp.status_code != 200:
            logger.info("[东方财富] 融资融券历史 HTTP %d", resp.status_code)
            return []

        data = resp.json()

        if data.get("code") != 0 or not data.get("result"):
            logger.info("[东方财富] 融资融券历史返回错误")
            return []

        records = data["result"].get("data", [])
        if not records:
            return []

        # 解析历史记录
        results = []
        for record in records:
            results.append({
                "symbol": symbol.upper(),
                "stock_code": stock_code,
                "date": record.get("TRADE_DATE", ""),
                "margin_balance": safe_float(record.get("RZYE")) or 0.0,
                "margin_buy": safe_float(record.get("RZMRE")) or 0.0,
                "margin_repay": safe_float(record.get("RZCHE")) or 0.0,
                "short_balance": safe_float(record.get("RQYL")) or 0.0,
                "short_sell": safe_float(record.get("RQMCL")) or 0.0,
                "short_repay": safe_float(record.get("RQCHL")) or 0.0,
                "total_balance": safe_float(record.get("RZRQYE")) or 0.0,
                "source": "eastmoney"
            })

        # 按日期降序排列
        results.sort(key=lambda x: x["date"], reverse=True)

        return results

    except Exception as exc:
        logger.info("[东方财富] 融资融券历史获取失败: %s", type(exc).__name__)
        return []
