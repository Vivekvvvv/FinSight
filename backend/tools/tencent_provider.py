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


def is_cn_symbol(symbol: str) -> bool:
    """判断是否为A股代码（.SS/.SZ/.BJ后缀）"""
    text = str(symbol or "").strip().upper()
    return text.endswith((".SS", ".SZ", ".BJ"))


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


def fetch_cn_quote(symbol: str) -> dict[str, Any] | None:
    """
    从腾讯财经获取A股实时行情。
    API: https://qt.gtimg.cn/q=sh600519,sz000001
    返回格式: v_sh600519="51~贵州茅台~600519~2086.00~2080.00~2085.00~..."
    """
    from backend.services.datasource_monitor import get_monitor
    import time

    code = to_tencent_code(symbol)
    if code is None:
        return None

    url = f"https://qt.gtimg.cn/q={code}"
    monitor = get_monitor()
    start_time = time.time()

    try:
        resp = _http_get(url, timeout=(3, 6))
        response_time_ms = (time.time() - start_time) * 1000

        if resp.status_code != 200:
            logger.info("[Tencent] HTTP %d for %s", resp.status_code, symbol)
            monitor.record_failure("tencent", f"HTTP {resp.status_code}")
            return None

        # 解析响应：v_sh600519="51~贵州茅台~600519~2086.00~2080.00~..."
        text = resp.text.strip()
        if not text or "~" not in text:
            monitor.record_failure("tencent", "empty or invalid response")
            return None

        parts = text.split('"')[1].split("~") if '"' in text else []
        if len(parts) < 34:
            logger.info("[Tencent] 字段不足 for %s: %d fields", symbol, len(parts))
            monitor.record_failure("tencent", f"insufficient fields: {len(parts)}")
            return None

        # 字段映射（腾讯接口字段索引）:
        # 3=现价, 4=昨收, 5=开盘, 6=成交量(手), 7=外盘, 8=内盘
        # 9=买一, 10=买一量, ..., 30=日期, 31=时间
        # 39=市盈率PE, 43=振幅, 44=流通市值(亿), 45=总市值(亿), 46=市净率PB, 52=换手率
        price = safe_float(parts[3])
        prev_close = safe_float(parts[4])
        if price is None or prev_close is None or prev_close == 0:
            return None

        change = price - prev_close
        change_percent = (change / prev_close) * 100
        volume = safe_float(parts[6])  # 成交量(手)
        if volume:
            volume = volume * 100  # 转换为股

        # 基本面数据（字段39-52）
        pe_ratio = safe_float(parts[39]) if len(parts) > 39 else None  # 市盈率
        pb_ratio = safe_float(parts[46]) if len(parts) > 46 else None  # 市净率
        market_cap = safe_float(parts[45]) if len(parts) > 45 else None  # 总市值(亿)
        circulating_cap = safe_float(parts[44]) if len(parts) > 44 else None  # 流通市值(亿)
        turnover_rate = safe_float(parts[52]) if len(parts) > 52 else None  # 换手率(%)

        # 转换市值单位：亿 → 元
        if market_cap:
            market_cap = market_cap * 100_000_000
        if circulating_cap:
            circulating_cap = circulating_cap * 100_000_000

        # 拼接时间戳
        date_str = parts[30] if len(parts) > 30 else ""  # 20260614
        time_str = parts[31] if len(parts) > 31 else ""  # 150000
        as_of = datetime.now(timezone.utc).isoformat()
        if date_str and len(date_str) == 8:
            try:
                as_of = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                if time_str and len(time_str) == 6:
                    as_of += f"T{time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}+08:00"
            except Exception:
                pass

        # 记录成功
        monitor.record_success("tencent", response_time_ms)

        return {
            "symbol": symbol.upper(),
            "currentPrice": price,
            "regularMarketPrice": price,
            "price": price,
            "regularMarketChange": change,
            "change": change,
            "regularMarketChangePercent": change_percent,
            "change_percent": change_percent,
            "regularMarketVolume": volume,
            "volume": volume,
            "regularMarketPreviousClose": prev_close,
            "previousClose": prev_close,
            # 基本面数据
            "pe_ratio": pe_ratio,
            "trailingPE": pe_ratio,
            "pb_ratio": pb_ratio,
            "priceToBook": pb_ratio,
            "market_cap": market_cap,
            "marketCap": market_cap,
            "circulating_cap": circulating_cap,
            "turnover_rate": turnover_rate,
            # 元数据
            "source": "tencent",
            "as_of": as_of,
            "freshness_status": "live",
            "fallback_level": 1,
            "modelGenerated": False,
        }
    except Exception as exc:
        logger.info("[Tencent] 获取失败 %s: %s", symbol, type(exc).__name__)
        monitor.record_failure("tencent", type(exc).__name__)
        return None


def fetch_cn_kline(symbol: str, *, period: str = "1mo", interval: str = "1d") -> dict[str, Any] | None:
    """
    从腾讯财经获取A股K线历史数据。
    API: https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,,,320,qfq

    参数:
        period: 时间周期 (5d/1mo/3mo/6mo/1y/2y)
        interval: K线类型 (1d=日K, 1wk=周K, 1mo=月K)

    返回格式:
        "2026-01-12 1419.100 1423.230 1431.000 1417.100 36083.000"
        格式为: 日期 开盘 收盘 最高 最低 成交量(手)
    """
    code = to_tencent_code(symbol)
    if code is None:
        return None

    # 根据period计算需要的K线数量
    period_to_count = {
        "5d": 10,
        "1mo": 30,
        "3mo": 90,
        "6mo": 150,
        "1y": 280,
        "2y": 520,
        "5y": 1300,
    }
    count = period_to_count.get(period, 90)

    # 根据interval选择K线类型
    interval_map = {
        "1d": "day",
        "1wk": "week",
        "1mo": "month",
    }
    kline_type = interval_map.get(interval, "day")

    # 腾讯接口参数: param=代码,类型,开始日期,结束日期,数量,复权方式
    # qfq=前复权, hfq=后复权, 空=不复权
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},{kline_type},,,{count},qfq"

    try:
        resp = _http_get(url, timeout=(3, 8))
        if resp.status_code != 200:
            logger.info("[Tencent] K线 HTTP %d for %s", resp.status_code, symbol)
            return None

        data = resp.json()
        if data.get("code") != 0:
            logger.info("[Tencent] K线返回错误 for %s: %s", symbol, data.get("msg"))
            return None

        # 解析K线数据
        stock_data = data.get("data", {}).get(code, {})
        kline_key = f"qfq{kline_type}"  # qfqday / qfqweek / qfqmonth
        raw_lines = stock_data.get(kline_key, [])

        if not raw_lines:
            logger.info("[Tencent] K线数据为空 for %s", symbol)
            return None

        # 解析每条K线: ['2026-04-29', '1405.000', '1401.170', '1409.750', '1400.280', '34813.000']
        # 格式: [日期, 开盘, 收盘, 最高, 最低, 成交量(手)]
        kline_data = []
        dates = []
        values = []

        for line in raw_lines:
            # 腾讯返回的是列表，不是字符串
            if not isinstance(line, list) or len(line) < 6:
                continue

            date_str = str(line[0])  # 2026-04-29
            open_price = safe_float(line[1])
            close_price = safe_float(line[2])
            high_price = safe_float(line[3])
            low_price = safe_float(line[4])
            volume = safe_float(line[5])

            if close_price is None:
                continue

            # 成交量从手转为股
            if volume:
                volume = volume * 100

            kline_data.append({
                "time": date_str,
                "open": open_price,
                "close": close_price,
                "high": high_price,
                "low": low_price,
                "volume": volume,
            })

            dates.append(date_str)
            values.append([open_price, close_price, low_price, high_price])

        if not kline_data:
            return None

        return {
            "kline_data": kline_data,
            "dates": dates,
            "values": values,
            "period": period,
            "interval": interval,
            "source": "tencent",
            "as_of": dates[-1] if dates else datetime.now(timezone.utc).isoformat(),
            "freshness_status": "live",
            "fallback_level": 1,
        }
    except Exception as exc:
        logger.info("[Tencent] K线获取失败 %s: %s", symbol, type(exc).__name__)
        return None


def fetch_cn_intraday(symbol: str) -> dict[str, Any] | None:
    """
    从腾讯财经获取A股分时数据（当日逐分钟）。
    API: https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=sh600519

    返回格式:
        data: ['0930 1271.18 415 52753970.34', '0931 1268.20 1156 146919161.70', ...]
        格式为: 时间 价格 累计成交量(手) 累计成交额
    """
    code = to_tencent_code(symbol)
    if code is None:
        return None

    url = f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?code={code}"

    try:
        resp = _http_get(url, timeout=(3, 8))
        if resp.status_code != 200:
            logger.info("[Tencent] 分时 HTTP %d for %s", resp.status_code, symbol)
            return None

        data = resp.json()
        if data.get("code") != 0:
            logger.info("[Tencent] 分时返回错误 for %s: %s", symbol, data.get("msg"))
            return None

        # 解析分时数据
        stock_data = data.get("data", {}).get(code, {})
        minute_container = stock_data.get("data", {})

        # 分时数据在 minute_container['data'] 中
        if not isinstance(minute_container, dict):
            logger.info("[Tencent] 分时数据格式错误 for %s", symbol)
            return None

        raw_lines = minute_container.get("data", [])
        date_str = minute_container.get("date", "")

        if not raw_lines:
            logger.info("[Tencent] 分时数据为空 for %s", symbol)
            return None

        # 解析每条分时数据: '0930 1271.18 415 52753970.34'
        # 格式: 时间 价格 累计成交量(手) 累计成交额
        intraday_data = []
        times = []
        prices = []
        volumes = []

        for line in raw_lines:
            parts = str(line).split()
            if len(parts) < 4:
                continue

            time_str = parts[0]  # 0930
            price = safe_float(parts[1])
            cum_volume = safe_float(parts[2])  # 累计成交量(手)
            cum_amount = safe_float(parts[3])  # 累计成交额

            if price is None:
                continue

            # 转换为标准时间格式
            if len(time_str) == 4:
                formatted_time = f"{time_str[:2]}:{time_str[2:]}"
            else:
                formatted_time = time_str

            # 成交量从手转为股
            volume_shares = cum_volume * 100 if cum_volume else None

            intraday_data.append({
                "time": formatted_time,
                "price": price,
                "volume": volume_shares,
                "amount": cum_amount,
            })

            times.append(formatted_time)
            prices.append(price)
            if volume_shares:
                volumes.append(volume_shares)

        if not intraday_data:
            return None

        return {
            "intraday_data": intraday_data,
            "times": times,
            "prices": prices,
            "volumes": volumes,
            "date": date_str,
            "source": "tencent",
            "as_of": datetime.now(timezone.utc).isoformat(),
            "freshness_status": "live",
            "fallback_level": 1,
        }
    except Exception as exc:
        logger.info("[Tencent] 分时获取失败 %s: %s", symbol, type(exc).__name__)
        return None


def fetch_cn_top_list(symbol: str, include_seats: bool = True, max_age_days: int = 90) -> dict[str, Any] | None:
    """
    从东方财富获取A股龙虎榜数据（大额交易、机构席位）。

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
                trade_date = record.get("TRADE_DATE")
                if not _is_recent_eastmoney_date(trade_date, max_age_days=max_age_days):
                    logger.info("[Eastmoney] top list record is stale for %s: %s", symbol, trade_date)
                    return None
                result = {
                    "symbol": symbol.upper(),
                    "stock_code": stock_code,
                    "stock_name": record.get("SECURITY_NAME_ABBR", ""),
                    "date": trade_date or datetime.now(timezone.utc).date().isoformat(),
                    "reason": record.get("EXPLANATION") or record.get("EXPLAIN") or "龙虎榜",
                    "close_price": safe_float(record.get("CLOSE_PRICE")),
                    "change_percent": safe_float(record.get("CHANGE_RATE")),
                    "buy_amount": safe_float(record.get("BILLBOARD_BUY_AMT") or record.get("SUM_BUY_AMT")) or 0.0,
                    "sell_amount": safe_float(record.get("BILLBOARD_SELL_AMT") or record.get("SUM_SELL_AMT")) or 0.0,
                    "net_buy": safe_float(record.get("BILLBOARD_NET_AMT") or record.get("NET_BS_AMT")) or 0.0,
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
        logger.info("[Eastmoney] new top list lookup failed %s: %s", symbol, type(exc).__name__)

    # 提取纯数字代码（如sh600519 → 600519）
    stock_code = code[2:] if len(code) > 2 else code

    # 东方财富龙虎榜API
    url = f"http://data.eastmoney.com/DataCenter_V3/stock2016/TradeDetail/pagesize=50,page=1,sortRule=-1,sortType=,startDate=,endDate=,gpfw=0,js=var%20data_tab_1.html?code={stock_code}"

    try:
        resp = _http_get(url, timeout=(5, 10))
        if resp.status_code != 200:
            logger.info("[东方财富] 龙虎榜 HTTP %d for %s", resp.status_code, symbol)
            return None

        text = resp.text.strip()

        # 提取JSON数据
        import re
        match = re.search(r'var\s+data_tab_1\s*=\s*(\[.*?\]);?', text, re.DOTALL)
        if not match:
            logger.info("[东方财富] 龙虎榜数据解析失败 for %s", symbol)
            return None

        import json
        data_list = json_loads_strict(match.group(1))

        if not data_list:
            logger.info("[东方财富] 龙虎榜无数据 for %s", symbol)
            return None

        # 查找匹配的股票记录
        record = None
        for item in data_list:
            if item.get("SCode") == stock_code:
                record = item
                break

        if not record:
            logger.info("[东方财富] 龙虎榜未找到 %s 的记录", symbol)
            return None

        # 解析龙虎榜基础数据
        buy_amount = _wan_to_yuan(record.get("Bmoney", 0))  # 万元转元
        sell_amount = _wan_to_yuan(record.get("Smoney", 0))
        net_buy = _wan_to_yuan(record.get("JmMoney", 0))

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
        logger.info("[东方财富] 龙虎榜获取失败 %s: %s", symbol, type(exc).__name__)
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
            logger.debug("[东方财富] 席位明细 HTTP %d for %s", resp.status_code, stock_code)
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
            for idx, seat in enumerate(buy_data[:5], 1):  # 前5席位
                buy_amt = _wan_to_yuan(seat.get("Bmoney", 0))  # 万元转元
                sell_amt = _wan_to_yuan(seat.get("Smoney", 0))
                seat_name = seat.get("SName", "未知席位")
                is_institution = "机构" in seat_name or "专用" in seat_name

                buy_seats.append({
                    "rank": idx,
                    "seat_name": seat_name,
                    "buy_amount": buy_amt,
                    "sell_amount": sell_amt,
                    "net_amount": buy_amt - sell_amt,
                    "is_institution": is_institution
                })

        if sell_match:
            sell_data = json_loads_strict(sell_match.group(1))
            for idx, seat in enumerate(sell_data[:5], 1):
                buy_amt = _wan_to_yuan(seat.get("Bmoney", 0))
                sell_amt = _wan_to_yuan(seat.get("Smoney", 0))
                seat_name = seat.get("SName", "未知席位")
                is_institution = "机构" in seat_name or "专用" in seat_name

                sell_seats.append({
                    "rank": idx,
                    "seat_name": seat_name,
                    "buy_amount": buy_amt,
                    "sell_amount": sell_amt,
                    "net_amount": buy_amt - sell_amt,
                    "is_institution": is_institution
                })

        return {
            "buy_seats": buy_seats,
            "sell_seats": sell_seats
        }

    except Exception as exc:
        logger.debug("[东方财富] 席位明细获取失败 %s: %s", stock_code, type(exc).__name__)
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

    try:
        resp = _http_get(
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            params={
                "reportName": "RPT_DAILYBILLBOARD_DETAILSNEW",
                "columns": "ALL",
                "filter": f'(SECURITY_CODE="{stock_code}")',
                "pageNumber": "1",
        "pageSize": str(max(1, min(safe_int(days, 30), 100))),
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
        logger.info("[Eastmoney] new top list history lookup failed %s: %s", symbol, type(exc).__name__)

    # 东方财富历史龙虎榜API
    url = f"http://data.eastmoney.com/DataCenter_V3/stock2016/TradeDetail/pagesize=200,page=1,sortRule=-1,sortType=,startDate={start_date},endDate={end_date},gpfw=0,code={stock_code},js=var%20data_tab_1.html"

    try:
        resp = _http_get(url, timeout=(5, 10))
        if resp.status_code != 200:
            logger.info("[东方财富] 龙虎榜历史 HTTP %d for %s", resp.status_code, symbol)
            return []

        text = resp.text.strip()

        import re
        import json

        match = re.search(r'var\s+data_tab_1\s*=\s*(\[.*?\]);?', text, re.DOTALL)
        if not match:
            logger.info("[东方财富] 龙虎榜历史数据解析失败 for %s", symbol)
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
        logger.info("[东方财富] 龙虎榜历史获取失败 %s: %s", symbol, type(exc).__name__)
        return []


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

        # 头部标量取最新有效分时点的累计值，万元转元
        north_total = last_north * 10000 if last_north is not None else 0.0
        sh_total = last_sh * 10000 if last_sh is not None else 0.0
        sz_total = last_sz * 10000 if last_sz is not None else 0.0

        return {
            "date": date,
            "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "north_flow": north_total or 0.0,
            "sh_flow": sh_total or 0.0,
            "sz_flow": sz_total or 0.0,
            "data_points": data_points,
            "source": "eastmoney",
            "unit": "元"
        }
    except Exception as exc:
        logger.info("[东方财富] 北向资金获取失败: %s", type(exc).__name__)
        return None


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
            if rows:
                latest = rows[0]
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
                    "margin_balance": margin_balance or 0.0,
                    "margin_buy": margin_buy or 0.0,
                    "margin_repay": margin_repay or 0.0,
                    "short_balance": short_balance or 0.0,
                    "short_sell": short_sell or 0.0,
                    "short_repay": short_repay or 0.0,
                    "margin_buy_ratio": margin_buy_ratio,
                    "total_balance": total_balance or 0.0,
                    "source": "eastmoney",
                    "unit": "融资单位=元，融券单位=股",
                }
    except Exception as exc:
        logger.info("[Eastmoney] new margin trading lookup failed %s: %s", symbol, type(exc).__name__)

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
            logger.info("[东方财富] 融资融券 HTTP %d for %s", resp.status_code, symbol)
            return None

        data = resp.json()

        if data.get("code") != 0 or not data.get("result"):
            logger.info("[东方财富] 融资融券返回错误 for %s", symbol)
            return None

        records = data["result"].get("data", [])
        if not records:
            logger.info("[东方财富] 融资融券无数据 for %s", symbol)
            return None

        # 取最新一条记录
        latest = records[0]

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

        return {
            "symbol": symbol.upper(),
            "stock_code": stock_code,
            "date": latest.get("TRADE_DATE", datetime.now(timezone.utc).date().isoformat()),
            "margin_balance": margin_balance or 0.0,
            "margin_buy": margin_buy or 0.0,
            "margin_repay": margin_repay or 0.0,
            "short_balance": short_balance or 0.0,
            "short_sell": short_sell or 0.0,
            "short_repay": short_repay or 0.0,
            "margin_buy_ratio": margin_buy_ratio,
            "total_balance": total_balance or 0.0,
            "source": "eastmoney",
            "unit": "融资单位=元，融券单位=股"
        }
    except Exception as exc:
        logger.info("[东方财富] 融资融券获取失败 %s: %s", symbol, type(exc).__name__)
        return None


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
        logger.info("[Eastmoney] new margin trading history lookup failed %s: %s", symbol, type(exc).__name__)

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
            logger.info("[东方财富] 融资融券历史 HTTP %d for %s", resp.status_code, symbol)
            return []

        data = resp.json()

        if data.get("code") != 0 or not data.get("result"):
            logger.info("[东方财富] 融资融券历史返回错误 for %s", symbol)
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
        logger.info("[东方财富] 融资融券历史获取失败 %s: %s", symbol, type(exc).__name__)
        return []


__all__ = ["is_cn_symbol", "to_tencent_code", "fetch_cn_quote", "fetch_cn_kline", "fetch_cn_intraday", "fetch_cn_top_list", "fetch_cn_top_list_history", "fetch_north_flow", "fetch_north_flow_history", "fetch_margin_trading", "fetch_margin_trading_history"]
