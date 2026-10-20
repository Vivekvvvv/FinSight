"""Eastmoney market fetchers extracted from tools.tencent_provider.

龙虎榜/席位明细、北向资金、融资融券的东财抓取簇及东财日期助手，逐字搬自
``tencent_provider``；父模块经 re-export 维持既有导入路径与 ``__all__`` 不变。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from backend.tools._item import iter_dict_items
from backend.tools.http import _http_get
from backend.utils.quote import safe_float, safe_int
from backend.utils.strict_json import json_loads_strict
from backend.tools.tencent_history_providers import _wan_to_yuan, to_tencent_code

logger = logging.getLogger(__name__)

def _parse_eastmoney_date(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        pass
    try:
        return datetime.fromisoformat(text[:10])
    except Exception:
        return None


def _is_recent_eastmoney_date(value: Any, *, max_age_days: int, now: datetime | None = None) -> bool:
    parsed = _parse_eastmoney_date(value)
    if parsed is None:
        return False
    today = (now or datetime.now(timezone.utc)).date()
    age_days = max(1, safe_int(max_age_days, 90))
    return parsed.date() >= today - timedelta(days=age_days)


def _mark_top_list_failure(diagnostics: dict[str, Any] | None, reason: str) -> None:
    if diagnostics is not None:
        diagnostics["fallback_reason"] = reason


def fetch_cn_top_list(
    symbol: str,
    include_seats: bool = True,
    max_age_days: int = 90,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    从东方财富获取A股龙虎榜数据（大额交易、机构席位）。

    返回 None 有两种含义，调用方无法从返回值区分：该股近期没有上榜记录，
    或者上游取数失败/解析失败。传入 ``diagnostics`` 时，后者会写入
    ``fallback_reason``，避免"数据源挂了"被渲染成"这只票没上榜"（项目规则 2）。

    API:
    - 基础数据: http://data.eastmoney.com/DataCenter_V3/stock2016/TradeDetail/...
    - 席位明细: http://data.eastmoney.com/DataCenter_V3/stock2016/TradeDetail/pagesize=200,page=1,...

    参数:
        symbol: 股票代码（如 600519.SS）
        include_seats: 是否包含席位明细（默认True）

    返回格式:
        {
            "symbol": "600519.SS",
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "date": "2026-06-14",
            "reason": "涨跌幅偏离值7%",
            "close_price": 1580.50,
            "change_percent": 5.32,
            "buy_amount": 123456789.0,
            "sell_amount": 98765432.0,
            "net_buy": 24691357.0,
            "turnover_rate": 1.23,
            "buy_seats": [
                {
                    "rank": 1,
                    "seat_name": "机构专用",
                    "buy_amount": 50000000.0,
                    "sell_amount": 0.0,
                    "net_amount": 50000000.0,
                    "is_institution": True
                },
                ...
            ],
            "sell_seats": [...],
            "source": "eastmoney"
        }
    """
    code = to_tencent_code(symbol)
    if code is None:
        return None
    stock_code = code[2:] if len(code) > 2 else code

    try:
        resp = _http_get(
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            params={
                "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
                "columns": "ALL",
                "filter": f'(SECURITY_CODE="{stock_code}")',
                "pageNumber": "1",
                "pageSize": "5",
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
            if rows:
                record = rows[0]
                # 非 dict 毒记录跳过新版解析落旧版兜底（此前靠 AttributeError
                # 碰巧落过去）。TRADE_DATE 缺失/畸形时 _is_recent_eastmoney_date
                # 返回 False，但不可解析≠过期——直接 return None 会跳过旧版
                # 兜底；且无法验证新旧就采用该记录会让过期短路形同虚设。
                # 仅日期可解析时才进入新版判定：超龄→return None，近期→采用（同 R107 缺陷类）
                if isinstance(record, dict) and _parse_eastmoney_date(record.get("TRADE_DATE")) is not None:
                    trade_date = record.get("TRADE_DATE")
                    if not _is_recent_eastmoney_date(trade_date, max_age_days=max_age_days):
                        logger.info("[Eastmoney] top list record is stale")
                        # 上过榜但记录超龄：不是"上游挂了"，也不等于"从没上榜"，
                        # 单独标注让路由层能说清是哪一种。
                        _mark_top_list_failure(diagnostics, "stale_record")
                        return None
                    result = {
                        "symbol": symbol.upper(),
                        "stock_code": stock_code,
                        "stock_name": record.get("SECURITY_NAME_ABBR", ""),
                        "date": trade_date or datetime.now(timezone.utc).date().isoformat(),
                        "reason": record.get("EXPLANATION") or record.get("EXPLAIN") or "龙虎榜",
                        "close_price": safe_float(record.get("CLOSE_PRICE")),
                        "change_percent": safe_float(record.get("CHANGE_RATE")),
                        "buy_amount": safe_float(record.get("BILLBOARD_BUY_AMT") or record.get("SUM_BUY_AMT")),
                        "sell_amount": safe_float(record.get("BILLBOARD_SELL_AMT") or record.get("SUM_SELL_AMT")),
                        # 上游没回净买入额时不能折成 0：下游会渲染成"机构净买入
                        # 0.00 亿元"（研究路由 prompt）。缺失必须是 None。
                        "net_buy": safe_float(record.get("BILLBOARD_NET_AMT") or record.get("NET_BS_AMT")),
                        "turnover_rate": safe_float(record.get("TURNOVERRATE")),
                        "buy_seats": [],
                        "sell_seats": [],
                        "source": "eastmoney_datacenter",
                    }
                    if include_seats:
                        seats = _fetch_top_list_seats(stock_code, record.get("TRADE_DATE"))
                        if seats:
                            result["buy_seats"] = seats.get("buy_seats", [])
                            result["sell_seats"] = seats.get("sell_seats", [])
                    return result
    except Exception as exc:
        logger.info("[Eastmoney] new top list lookup failed: %s", type(exc).__name__)

    # 提取纯数字代码（如sh600519 → 600519）
    stock_code = code[2:] if len(code) > 2 else code

    # 东方财富龙虎榜API
    url = f"http://data.eastmoney.com/DataCenter_V3/stock2016/TradeDetail/pagesize=50,page=1,sortRule=-1,sortType=,startDate=,endDate=,gpfw=0,js=var%20data_tab_1.html?code={stock_code}"

    try:
        resp = _http_get(url, timeout=(5, 10))
        if resp.status_code != 200:
            logger.info("[东方财富] 龙虎榜 HTTP %d", resp.status_code)
            _mark_top_list_failure(diagnostics, "upstream_error")
            return None

        text = resp.text.strip()

        # 提取JSON数据
        import re
        match = re.search(r'var\s+data_tab_1\s*=\s*(\[.*?\]);?', text, re.DOTALL)
        if not match:
            logger.info("[东方财富] 龙虎榜数据解析失败")
            _mark_top_list_failure(diagnostics, "upstream_error")
            return None

        import json
        data_list = json_loads_strict(match.group(1))

        if not isinstance(data_list, list):
            # 解析出来不是列表（null/对象）：上游回包异常，不是"没有记录"。
            logger.info("[东方财富] 龙虎榜数据解析失败")
            _mark_top_list_failure(diagnostics, "upstream_error")
            return None

        if not data_list:
            logger.info("[东方财富] 龙虎榜无数据")
            return None

        # 查找匹配的股票记录；非 dict 毒条目按条跳过——item.get 的
        # AttributeError 会落进外层 except 让整个旧版查询返回 None（同 R107）
        record = None
        for item in iter_dict_items(data_list):
            if item.get("SCode") == stock_code:
                record = item
                break

        if not record:
            logger.info("[东方财富] 龙虎榜未找到记录")
            return None

        # 解析龙虎榜基础数据
        buy_amount = _wan_to_yuan(record.get("Bmoney"))  # 万元转元
        sell_amount = _wan_to_yuan(record.get("Smoney"))
        # 旧代码给缺失字段补 0（而非 0 元成交），下游读成"净买入 0.00 亿元"。
        net_buy = _wan_to_yuan(record.get("JmMoney"))

        result = {
            "symbol": symbol.upper(),
            "stock_code": stock_code,
            "stock_name": record.get("SName", ""),
            "date": record.get("Tdate", datetime.now(timezone.utc).date().isoformat()),
            "reason": record.get("Ctypedes", "上榜"),
            "close_price": safe_float(record.get("ClosePrice")),
            "change_percent": safe_float(record.get("Chgradio")),
            "buy_amount": buy_amount,
            "sell_amount": sell_amount,
            "net_buy": net_buy,
            "turnover_rate": safe_float(record.get("TurnoverRate")),
            "buy_seats": [],
            "sell_seats": [],
            "source": "eastmoney"
        }

        # 获取席位明细
        if include_seats:
            seats = _fetch_top_list_seats(stock_code, record.get("Tdate"))
            if seats:
                result["buy_seats"] = seats.get("buy_seats", [])
                result["sell_seats"] = seats.get("sell_seats", [])

        return result

    except Exception as exc:
        logger.info("[东方财富] 龙虎榜获取失败: %s", type(exc).__name__)
        _mark_top_list_failure(diagnostics, "upstream_error")
        return None


def _fetch_top_list_seats(stock_code: str, trade_date: str | None = None) -> dict[str, Any] | None:
    """
    获取龙虎榜席位明细（买入/卖出前5席位）

    参数:
        stock_code: 纯数字代码（如 600519）
        trade_date: 交易日期（YYYY-MM-DD）

    返回:
        {
            "buy_seats": [
                {"rank": 1, "seat_name": "机构专用", "buy_amount": 50000000.0, "sell_amount": 0.0, "net_amount": 50000000.0, "is_institution": True},
                ...
            ],
            "sell_seats": [...]
        }
    """
    if trade_date is None:
        trade_date = datetime.now(timezone.utc).date().isoformat()

    # 东方财富席位明细API
    # 返回买入前5席位和卖出前5席位
    url = f"http://data.eastmoney.com/DataCenter_V3/stock2016/TradeDetail/pagesize=200,page=1,sortRule=-1,sortType=,startDate={trade_date},endDate={trade_date},gpfw=0,code={stock_code},js=var%20data_tab_2.html"

    try:
        resp = _http_get(url, timeout=(5, 10))
        if resp.status_code != 200:
            logger.debug("[东方财富] 席位明细 HTTP %d", resp.status_code)
            return None

        text = resp.text.strip()

        # 提取JSON数据
        import re
        import json

        # 买入席位：var data_tab_2
        buy_match = re.search(r'var\s+data_tab_2\s*=\s*(\[.*?\]);?', text, re.DOTALL)
        # 卖出席位：var data_tab_3
        sell_match = re.search(r'var\s+data_tab_3\s*=\s*(\[.*?\]);?', text, re.DOTALL)

        buy_seats = []
        sell_seats = []

        if buy_match:
            buy_data = json_loads_strict(buy_match.group(1))
            if not isinstance(buy_data, list):
                buy_data = []  # 非 list 时 [:5] TypeError 会吞掉全部席位
            for idx, seat in enumerate(buy_data[:5], 1):  # 前5席位
                if not isinstance(seat, dict):
                    continue  # 毒席位按条跳过（同 R107）
                buy_amt = _wan_to_yuan(seat.get("Bmoney", 0))  # 万元转元
                sell_amt = _wan_to_yuan(seat.get("Smoney", 0))
                seat_name = seat.get("SName", "未知席位")
                is_institution = "机构" in seat_name or "专用" in seat_name

                buy_seats.append({
                    "rank": idx,
                    "seat_name": seat_name,
                    "buy_amount": buy_amt,
                    "sell_amount": sell_amt,
                    # _wan_to_yuan 对 "-"/null 返回 None：None-None 抛 TypeError
                    # 会被外层 except 吞成整个席位明细 None（R53 同类）
                    "net_amount": buy_amt - sell_amt if buy_amt is not None and sell_amt is not None else None,
                    "is_institution": is_institution
                })

        if sell_match:
            sell_data = json_loads_strict(sell_match.group(1))
            if not isinstance(sell_data, list):
                sell_data = []
            for idx, seat in enumerate(sell_data[:5], 1):
                if not isinstance(seat, dict):
                    continue  # 毒席位按条跳过（同 R107）
                buy_amt = _wan_to_yuan(seat.get("Bmoney", 0))
                sell_amt = _wan_to_yuan(seat.get("Smoney", 0))
                seat_name = seat.get("SName", "未知席位")
                is_institution = "机构" in seat_name or "专用" in seat_name

                sell_seats.append({
                    "rank": idx,
                    "seat_name": seat_name,
                    "buy_amount": buy_amt,
                    "sell_amount": sell_amt,
                    "net_amount": buy_amt - sell_amt if buy_amt is not None and sell_amt is not None else None,
                    "is_institution": is_institution
                })

        return {
            "buy_seats": buy_seats,
            "sell_seats": sell_seats
        }

    except Exception as exc:
        logger.debug("[东方财富] 席位明细获取失败: %s", type(exc).__name__)
        return None


def fetch_north_flow(date: str | None = None) -> dict[str, Any] | None:
    """
    从东方财富获取北向资金流向数据（沪股通+深股通）。
    API: http://push2.eastmoney.com/api/qt/kamt.rtmin/get

    参数:
        date: 查询日期（YYYY-MM-DD），默认为今天

    返回格式:
        {
            "date": "2026-06-14",
            "time": "15:00:00",
            "north_flow": 12345678900.0,  # 北向资金净流入（元）
            "sh_flow": 8000000000.0,      # 沪股通净流入
            "sz_flow": 4345678900.0,      # 深股通净流入
            "north_balance": 520000000000.0,  # 北向资金余额
            "sh_balance": 308000000000.0,
            "sz_balance": 212000000000.0,
            "sz_balance": 212000000000.0,
            "data_points": [
                {"time": "09:30", "north": 123456789, "sh": 80000000, "sz": 43456789},
                ...
            ],
            "source": "eastmoney"
        }
    """
    if date is None:
        date = datetime.now(timezone.utc).date().isoformat()

    # 东方财富北向资金API
    # fields1: hk2sh(沪股通),hk2sz(深股通),s2n(北向)
    # fields2: 各时间点数据
    url = "http://push2.eastmoney.com/api/qt/kamt.rtmin/get"
    params = {
        "fields1": "f1,f2,f3,f4",
        "fields2": "f51,f52,f53,f54,f56",
        "ut": "b2884a393a59ad64002292a3e90d46a5",
        "cb": "jQuery"
    }

    try:
        resp = _http_get(url, params=params, timeout=(5, 10))
        if resp.status_code != 200:
            logger.info("[东方财富] 北向资金 HTTP %d", resp.status_code)
            return None

        # 返回格式：jQuery({"rc":0,"rt":6,"svr":...,"data":{...}})
        text = resp.text.strip()

        # 提取JSON数据
        import re
        match = re.search(r'jQuery\((.*)\)', text)
        if not match:
            logger.info("[东方财富] 北向资金数据解析失败")
            return None

        import json
        data = json_loads_strict(match.group(1))

        if data.get("rc") != 0 or not data.get("data"):
            logger.info("[东方财富] 北向资金返回错误")
            return None

        result_data = data["data"]

        # kamt.rtmin 的 s2n 是字符串列表，每行对应 fields2=f51,f52,f53,f54,f56：
        # "HH:MM,沪股通净流入,沪股通余额,深股通净流入,北向合计"（万元，未开盘时段为 "-"）。
        # 旧代码把 s2n 当标量 float 又当 dict 解析，两个分支互斥且都不成立，
        # 返回体恒为 north_flow=0 + data_points=[]。
        s2n_rows = result_data.get("s2n") or []
        if not isinstance(s2n_rows, list):
            s2n_rows = []

        data_points = []
        last_sh = last_sz = last_north = None
        for row in s2n_rows:
            if not isinstance(row, str):
                continue
            parts = row.split(",")
            if len(parts) < 5:
                continue
            time_str = parts[0].strip()
            if len(time_str) == 4 and ":" not in time_str:
                time_str = f"{time_str[:2]}:{time_str[2:]}"
            north_v = safe_float(parts[4])
            if north_v is None:
                continue  # 未开盘时段
            last_sh = safe_float(parts[1])
            last_sz = safe_float(parts[3])
            last_north = north_v
            if len(data_points) < 30:
                data_points.append({"time": time_str, "north": north_v * 10000})

        if last_north is None:
            # 分时行全部是未开盘的 "-"（或没有行）：一处真实数据都没解析到，
            # 此时 north_flow=0 会被下游当成"今日北向净流入 0 元"这一事实结论
            # （研究路由把 0 渲染成"净流入 0.00 亿元"喂进 prompt），
            # 必须与"确实收盘/平盘"区分开（项目规则 2）。
            logger.info("[东方财富] 北向资金无有效分时点")
            return None

        # 头部标量取最新有效分时点的累计值，万元转元
        north_total = last_north * 10000
        sh_total = last_sh * 10000
        sz_total = last_sz * 10000

        return {
            "date": date,
            "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            # 有有效分时点即为真实累计值：不再 `or 0.0`——0 元是合法净流入
            # （持平），把"取数失败"和"持平"折成同一个 0 会让失败伪装成结论。
            "north_flow": north_total,
            "sh_flow": sh_total,
            "sz_flow": sz_total,
            "data_points": data_points,
            "source": "eastmoney",
            "unit": "元"
        }
    except Exception as exc:
        logger.info("[东方财富] 北向资金获取失败: %s", type(exc).__name__)
        return None


def fetch_margin_trading(symbol: str) -> dict[str, Any] | None:
    """
    从东方财富获取A股融资融券数据。
    API: http://datacenter-web.eastmoney.com/api/data/v1/get

    参数:
        symbol: 股票代码（如 600519.SS）

    返回格式:
        {
            "symbol": "600519.SS",
            "date": "2026-06-14",
            "margin_balance": 1234567890.0,     # 融资余额（元）
            "margin_buy": 50000000.0,           # 融资买入额
            "margin_repay": 30000000.0,         # 融资偿还额
            "short_balance": 123456.0,          # 融券余量（股）
            "short_sell": 10000.0,              # 融券卖出量
            "short_repay": 5000.0,              # 融券偿还量
            "margin_buy_ratio": 5.23,           # 融资买入占比(%)
            "total_balance": 1234691346.0,      # 融资融券余额
            "source": "eastmoney"
        }
    """
    code = to_tencent_code(symbol)
    if code is None:
        return None
    stock_code = code[2:] if len(code) > 2 else code

    try:
        resp = _http_get(
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            params={
                "reportName": "RPTA_WEB_RZRQ_GGMX",
                "columns": "ALL",
                "filter": f'(SCODE="{stock_code}")',
                "pageNumber": "1",
                "pageSize": "10",
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
            # 非 dict 毒行按条跳过取首个有效行——rows[0].get 的 AttributeError
            # 只是碰巧落进外层 except 降级到旧版报表（margin_buy_ratio 硬编
            # 0.0 丢真实占比）；同 fetch_cn_top_list 新版分支的 R107 口径。
            latest = next(iter_dict_items(rows), None)
            if latest is not None:
                margin_balance = safe_float(latest.get("RZYE"))
                margin_buy = safe_float(latest.get("RZMRE"))
                margin_repay = safe_float(latest.get("RZCHE"))
                short_balance = safe_float(latest.get("RQYL"))
                short_sell = safe_float(latest.get("RQMCL"))
                short_repay = safe_float(latest.get("RQCHL"))
                total_balance = safe_float(latest.get("RZRQYE"))
                market_value = safe_float(latest.get("SZ"))
                margin_buy_ratio = (
                    round((margin_buy / market_value) * 100, 4)
                    if margin_buy is not None and market_value
                    else 0.0
                )
                return {
                    "symbol": symbol.upper(),
                    "stock_code": stock_code,
                    "date": latest.get("DATE", datetime.now(timezone.utc).date().isoformat()),
                    # `or 0.0` 把"该行没回这个字段"折成"融资余额 0 元"这一事实：
                    # 下游 `bal/1e8` 会把它渲染成"融资余额 0.00 亿元"写进 /qa 的
                    # prompt。真实 0 是合法值（safe_float 保留），缺失必须是 None。
                    "margin_balance": margin_balance,
                    "margin_buy": margin_buy,
                    "margin_repay": margin_repay,
                    "short_balance": short_balance,
                    "short_sell": short_sell,
                    "short_repay": short_repay,
                    "margin_buy_ratio": margin_buy_ratio,
                    "total_balance": total_balance,
                    "source": "eastmoney",
                    "unit": "融资单位=元，融券单位=股",
                }
    except Exception as exc:
        logger.info("[Eastmoney] new margin trading lookup failed: %s", type(exc).__name__)

    # 提取纯数字代码
    stock_code = code[2:] if len(code) > 2 else code

    # 东方财富融资融券API
    # reportName: RPT_RZRQ_LSHJ (融资融券历史汇总)
    # columns: TRADE_DATE,RZYE,RZMRE,RZCHE,RQYL,RQMCL,RQCHL,RZRQYE
    url = "http://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "reportName": "RPT_RZRQ_LSHJ",
        "columns": "TRADE_DATE,SECURITY_CODE,RZYE,RZMRE,RZCHE,RQYL,RQMCL,RQCHL,RZRQYE,RZMRE_CHG,RQMCL_CHG",
        "quoteColumns": "",
        "filter": f'(SECURITY_CODE="{stock_code}")',
        "pageNumber": "1",
        "pageSize": "10",
        "sortTypes": "-1",
        "sortColumns": "TRADE_DATE",
        "source": "WEB",
        "client": "WEB"
    }

    try:
        resp = _http_get(url, params=params, timeout=(5, 10))
        if resp.status_code != 200:
            logger.info("[东方财富] 融资融券 HTTP %d", resp.status_code)
            return None

        data = resp.json()

        if data.get("code") != 0 or not data.get("result"):
            logger.info("[东方财富] 融资融券返回错误")
            return None

        records = data["result"].get("data", [])

        # 取最新一条有效记录——非 dict 毒行按条跳过；records[0].get 的
        # AttributeError 落进外层 except 后此处再无兜底，整个融资融券
        # 查询被一条毒记录打成 None（同 R107/上方新版分支口径）。
        latest = next(iter_dict_items(records), None)
        if latest is None:
            logger.info("[东方财富] 融资融券无数据")
            return None

        # 字段说明（东方财富API）：
        # TRADE_DATE: 交易日期
        # RZYE: 融资余额（元）
        # RZMRE: 融资买入额（元）
        # RZCHE: 融资偿还额（元）
        # RQYL: 融券余量（股）
        # RQMCL: 融券卖出量（股）
        # RQCHL: 融券偿还量（股）
        # RZRQYE: 融资融券余额（元）

        margin_balance = safe_float(latest.get("RZYE"))  # 融资余额
        margin_buy = safe_float(latest.get("RZMRE"))      # 融资买入额
        margin_repay = safe_float(latest.get("RZCHE"))    # 融资偿还额
        short_balance = safe_float(latest.get("RQYL"))    # 融券余量（股）
        short_sell = safe_float(latest.get("RQMCL"))      # 融券卖出量
        short_repay = safe_float(latest.get("RQCHL"))     # 融券偿还量
        total_balance = safe_float(latest.get("RZRQYE"))  # 融资融券余额

        # 计算融资买入占比（需要获取当日成交额）
        # 这里返回0，实际需要调用额外API获取成交额
        margin_buy_ratio = 0.0

        # 同上：`or 0.0` 让"上游没回该字段"伪装成"余额 0 元"这一事实结论。
        return {
            "symbol": symbol.upper(),
            "stock_code": stock_code,
            "date": latest.get("TRADE_DATE", datetime.now(timezone.utc).date().isoformat()),
            "margin_balance": margin_balance,
            "margin_buy": margin_buy,
            "margin_repay": margin_repay,
            "short_balance": short_balance,
            "short_sell": short_sell,
            "short_repay": short_repay,
            "margin_buy_ratio": margin_buy_ratio,
            "total_balance": total_balance,
            "source": "eastmoney",
            "unit": "融资单位=元，融券单位=股"
        }
    except Exception as exc:
        logger.info("[东方财富] 融资融券获取失败: %s", type(exc).__name__)
        return None
