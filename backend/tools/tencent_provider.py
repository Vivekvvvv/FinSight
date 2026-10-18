from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from backend.tools.http import _http_get
from backend.utils.quote import safe_float

logger = logging.getLogger(__name__)

from backend.tools.tencent_history_providers import (
    _wan_to_yuan,
    to_tencent_code,
    fetch_cn_top_list_history,
    fetch_north_flow_history,
    fetch_margin_trading_history,
)

from backend.tools.tencent_market_providers import (
    _fetch_top_list_seats,
    _is_recent_eastmoney_date,
    _parse_eastmoney_date,
    fetch_cn_top_list,
    fetch_margin_trading,
    fetch_north_flow,
)




def is_cn_symbol(symbol: str) -> bool:
    """判断是否为A股代码（.SS/.SZ/.BJ后缀）"""
    text = str(symbol or "").strip().upper()
    return text.endswith((".SS", ".SZ", ".BJ"))


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
    # 时延是区间计时，必须用单调钟：time.time() 随系统时钟跳变——
    # 上游往返途中后跳会把 (now-start) 拉成负值，负 response_time_ms
    # 被 record_success 的 >0 门槛静默丢弃（成功调用丢计时样本）；
    # 前跳则一条样本灌入数小时级值，avg_response_time_ms 被污染数据
    # 支配到滚出 100 样本窗口。该值仅入监控统计、无 epoch 语义消费者。
    start_time = time.monotonic()

    try:
        resp = _http_get(url, timeout=(3, 6))
        response_time_ms = (time.monotonic() - start_time) * 1000

        if resp.status_code != 200:
            logger.info("[Tencent] quote HTTP %d", resp.status_code)
            monitor.record_failure("tencent", f"HTTP {resp.status_code}")
            return None

        # 解析响应：v_sh600519="51~贵州茅台~600519~2086.00~2080.00~..."
        text = resp.text.strip()
        if not text or "~" not in text:
            monitor.record_failure("tencent", "empty or invalid response")
            return None

        parts = text.split('"')[1].split("~") if '"' in text else []
        if len(parts) < 34:
            logger.info("[Tencent] quote 字段不足: %d fields", len(parts))
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
        logger.info("[Tencent] quote 获取失败: %s", type(exc).__name__)
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
            logger.info("[Tencent] K线 HTTP %d", resp.status_code)
            return None

        data = resp.json()
        if data.get("code") != 0:
            logger.info("[Tencent] K线返回错误")
            return None

        # 解析K线数据
        stock_data = data.get("data", {}).get(code, {})
        kline_key = f"qfq{kline_type}"  # qfqday / qfqweek / qfqmonth
        raw_lines = stock_data.get(kline_key, [])

        if not raw_lines:
            logger.info("[Tencent] K线数据为空")
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
        logger.info("[Tencent] K线获取失败: %s", type(exc).__name__)
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
            logger.info("[Tencent] 分时 HTTP %d", resp.status_code)
            return None

        data = resp.json()
        if data.get("code") != 0:
            logger.info("[Tencent] 分时返回错误")
            return None

        # 解析分时数据
        stock_data = data.get("data", {}).get(code, {})
        minute_container = stock_data.get("data", {})

        # 分时数据在 minute_container['data'] 中
        if not isinstance(minute_container, dict):
            logger.info("[Tencent] 分时数据格式错误")
            return None

        raw_lines = minute_container.get("data", [])
        date_str = minute_container.get("date", "")

        if not raw_lines:
            logger.info("[Tencent] 分时数据为空")
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

        # as_of 必须是最后一条分时点的时间；取数时刻在盘后会让昨天的旧图
        # 看起来是刚更新的（同 us_market 分时的口径）。腾讯日期常为 20261017。
        last_time = times[-1] if times else ""
        day = str(date_str or "").strip()
        if len(day) == 8 and day.isdigit():
            day = f"{day[:4]}-{day[4:6]}-{day[6:]}"
        if day and last_time:
            as_of = f"{day}T{last_time}"
        else:
            as_of = last_time or datetime.now(timezone.utc).isoformat()

        return {
            "intraday_data": intraday_data,
            "times": times,
            "prices": prices,
            "volumes": volumes,
            "date": date_str,
            "source": "tencent",
            "as_of": as_of,
            "freshness_status": "live",
            "fallback_level": 1,
        }
    except Exception as exc:
        logger.info("[Tencent] 分时获取失败: %s", type(exc).__name__)
        return None




__all__ = ["is_cn_symbol", "to_tencent_code", "fetch_cn_quote", "fetch_cn_kline", "fetch_cn_intraday", "fetch_cn_top_list", "fetch_cn_top_list_history", "fetch_north_flow", "fetch_north_flow_history", "fetch_margin_trading", "fetch_margin_trading_history"]
