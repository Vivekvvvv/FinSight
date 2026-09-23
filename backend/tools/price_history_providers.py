"""Historical price data provider functions.

Extracted from tools.price to keep the price module focused; price
re-exports every name here for backward compatibility.
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any, Optional

from .env import (
    IEX_CLOUD_API_KEY,
    MARKETSTACK_API_KEY,
    MASSIVE_API_KEY,
    TIINGO_API_KEY,
    TWELVE_DATA_API_KEY,
)
from .http import _http_get
from .search import search
from backend.utils.quote import safe_float


logger = logging.getLogger(__name__)


def _fetch_with_yahoo_scrape_historical(ticker: str, period: str = "1y") -> dict:
    """
    策略 4: 改进的 Yahoo Finance 网页抓取（2024最新方法）
    使用多个备用URL和更完善的请求头
    """
    try:
        logger.info("[get_stock_historical_data] 尝试从 Yahoo Finance 网页抓取...")
        
        # 根据 period 计算需要的天数
        period_days = {
            "1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180,
            "1y": 365, "2y": 730, "5y": 1825, "10y": 3650, "max": 10000
        }
        days = period_days.get(period, 365)
        
        # 改进的请求头（模拟真实浏览器）
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/csv,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": f"https://finance.yahoo.com/quote/{ticker}/history",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin"
        }
        
        # 尝试多个 Yahoo Finance URL（备用方案）
        urls = [
            f"https://query1.finance.yahoo.com/v7/finance/download/{ticker}",
            f"https://query2.finance.yahoo.com/v7/finance/download/{ticker}",
        ]
        
        for url in urls:
            try:
                params = {
                    "period1": int((datetime.now() - timedelta(days=days)).timestamp()),
                    "period2": int(datetime.now().timestamp()),
                    "interval": "1d",
                    "events": "history",
                    "includeAdjustedClose": "true"
                }
                
                response = _http_get(url, params=params, headers=headers, timeout=20, allow_redirects=True)
                
                if response.status_code == 200 and len(response.text) > 100:  # 确保有实际数据
                    # 解析 CSV 数据
                    import io
                    import csv
                    csv_data = io.StringIO(response.text)
                    reader = csv.DictReader(csv_data)
                    
                    kline_data = []
                    for row in reader:
                        try:
                            # 跳过无效行
                            if not row.get('Date') or not row.get('Close'):
                                continue
                            kline_data.append({
                                "time": row['Date'],
                                "open": _safe_float_value(row['Open']),
                                "high": _safe_float_value(row['High']),
                                "low": _safe_float_value(row['Low']),
                                "close": _safe_float_value(row['Close']),
                                "volume": _safe_float_value(row.get('Volume')) or 0.0,
                            })
                        except (ValueError, KeyError) as e:
                            continue  # 跳过无效行
                    
                    if kline_data:
                        logger.info("[get_stock_historical_data] Yahoo Finance 网页抓取成功")
                        return {"kline_data": kline_data, "period": period, "interval": "1d", "source": "yahoo_scrape"}
            except Exception as e:
                logger.info(
                    "[get_stock_historical_data] Yahoo Finance request failed: %s",
                    type(e).__name__,
                )
                continue
        
        return None
    except Exception as e:
        logger.info("[get_stock_historical_data] Yahoo Finance 网页抓取失败: %s", type(e).__name__)
        return None



def _fetch_with_iex_cloud(ticker: str, period: str = "1y") -> dict:
    """
    策略 5a: 使用 IEX Cloud API (免费额度: 50万次/月)
    文档: https://iexcloud.io/docs/api/
    """
    try:
        if not IEX_CLOUD_API_KEY:
            return None
            
        logger.info("[get_stock_historical_data] 尝试使用 IEX Cloud...")
        
        # IEX Cloud API 端点
        # 根据 period 计算时间范围
        period_days = {
            "1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180,
            "1y": 365, "2y": 730, "5y": 1825, "10y": 3650, "max": 10000
        }
        days = period_days.get(period, 365)
        
        # IEX Cloud 使用不同的时间范围参数
        if days <= 5:
            range_param = "5d"
        elif days <= 30:
            range_param = "1m"
        elif days <= 90:
            range_param = "3m"
        elif days <= 365:
            range_param = "1y"
        elif days <= 730:
            range_param = "2y"
        elif days <= 1825:
            range_param = "5y"
        else:
            range_param = "max"
        
        # IEX Cloud 不支持指数代码（如 ^IXIC），只支持股票代码
        # 如果ticker以^开头，跳过IEX Cloud
        if ticker.startswith('^'):
            return None
        
        url = f"https://cloud.iexapis.com/stable/stock/{ticker}/chart/{range_param}"
        params = {
            "token": IEX_CLOUD_API_KEY,
            "chartCloseOnly": "false"
        }
        
        response = _http_get(url, params=params, timeout=20)
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                kline_data = []
                for item in data:
                    kline_data.append({
                        "time": item.get('date', item.get('label', '')),
                        "open": _safe_float_value(item.get('open')),
                        "high": _safe_float_value(item.get('high')),
                        "low": _safe_float_value(item.get('low')),
                        "close": _safe_float_value(item.get('close')),
                        "volume": _safe_float_value(item.get('volume')),
                    })
                
                if kline_data:
                    logger.info("[get_stock_historical_data] IEX Cloud 成功获取数据")
                    return {"kline_data": kline_data, "period": period, "interval": "1d", "source": "iex_cloud"}
        
        return None
    except Exception as e:
        logger.info("[get_stock_historical_data] IEX Cloud 失败: %s", type(e).__name__)
        return None



def _fetch_with_tiingo(ticker: str, period: str = "1y") -> dict:
    """
    策略 5b: 使用 Tiingo API (免费额度: 每日500次)
    文档: https://api.tiingo.com/documentation/general/overview
    """
    try:
        if not TIINGO_API_KEY:
            return None
            
        logger.info("[get_stock_historical_data] 尝试使用 Tiingo...")
        
        # Tiingo API 端点
        period_days = {
            "1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180,
            "1y": 365, "2y": 730, "5y": 1825, "10y": 3650, "max": 10000
        }
        days = period_days.get(period, 365)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Tiingo 不支持指数代码（如 ^IXIC），需要特殊处理
        # 如果ticker以^开头，跳过Tiingo（因为Tiingo不支持指数）
        if ticker.startswith('^'):
            return None
        
        url = f"https://api.tiingo.com/tiingo/daily/{ticker}/prices"
        params = {
            "startDate": start_date.strftime('%Y-%m-%d'),
            "endDate": end_date.strftime('%Y-%m-%d'),
            "format": "json"
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Token {TIINGO_API_KEY}"
        }
        
        response = _http_get(url, params=params, headers=headers, timeout=20)
        
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                kline_data = []
                for item in data:
                    kline_data.append({
                        "time": item.get('date', '')[:10],  # 只取日期部分
                        "open": _safe_float_value(item.get('open')),
                        "high": _safe_float_value(item.get('high')),
                        "low": _safe_float_value(item.get('low')),
                        "close": _safe_float_value(item.get('close')),
                        "volume": _safe_float_value(item.get('volume')),
                    })
                
                if kline_data:
                    logger.info("[get_stock_historical_data] Tiingo 成功获取数据")
                    return {"kline_data": kline_data, "period": period, "interval": "1d", "source": "tiingo"}
        elif response.status_code == 404:
            # Tiingo 可能不支持该ticker（如指数），返回None让其他数据源处理
            logger.info("[get_stock_historical_data] Tiingo 不支持该证券，跳过")
            return None
        
        return None
    except Exception as e:
        logger.info("[get_stock_historical_data] Tiingo 失败: %s", type(e).__name__)
        return None



def _fetch_with_twelve_data(ticker: str, period: str = "1y") -> dict:
    """
    策略 5c: 使用 Twelve Data API (免费额度，轻量回退)
    文档: https://twelvedata.com/docs#time-series
    """
    try:
        if not TWELVE_DATA_API_KEY:
            return None

        # Twelve Data 对指数支持有限，避免 "^" 前缀的指数
        if ticker.startswith('^'):
            return None

        logger.info("[get_stock_historical_data] 尝试使用 Twelve Data...")

        period_days = {
            "1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180,
            "1y": 365, "2y": 730, "5y": 1825, "10y": 3650, "max": 10000
        }
        days = period_days.get(period, 365)
        outputsize = max(2, min(5000, days + 2))  # 轻量控制输出，兼顾免费额度

        params = {
            "symbol": ticker,
            "interval": "1day",
            "outputsize": outputsize,
            "apikey": TWELVE_DATA_API_KEY,
            "order": "desc",
        }
        response = _http_get("https://api.twelvedata.com/time_series", params=params, timeout=20)

        if response.status_code != 200:
            return None

        data = response.json()
        if data.get("status") != "ok":
            # status != ok 时通常返回 message
            message = data.get("message") or data.get("error")
            if message:
                logger.info("[get_stock_historical_data] Twelve Data 状态异常")
            return None

        values = data.get("values") or []
        if not values:
            return None

        kline_data = []
        for item in values:
            kline_data.append({
                "time": item.get("datetime", "")[:10],
                "open": _safe_float_value(item.get("open")),
                "high": _safe_float_value(item.get("high")),
                "low": _safe_float_value(item.get("low")),
                "close": _safe_float_value(item.get("close")),
                "volume": _safe_float_value(item.get("volume")),
            })

        if kline_data:
            # Twelve Data 默认倒序，翻转为时间正序
            kline_data = list(reversed(kline_data))
            as_of = values[0].get("datetime", "")[:19]
            logger.info("[get_stock_historical_data] Twelve Data 成功获取数据")
            return {"kline_data": kline_data, "period": period, "interval": "1d", "source": "twelve_data", "as_of": as_of}

        return None
    except Exception as e:
        logger.info("[get_stock_historical_data] Twelve Data 失败: %s", type(e).__name__)
        return None



def _fetch_with_marketstack(ticker: str, period: str = "1y") -> dict:
    """
    策略 5d: 使用 Marketstack API (免费额度: 1000次/月)
    文档: https://marketstack.com/documentation
    """
    try:
        if not MARKETSTACK_API_KEY:
            return None
            
        logger.info("[get_stock_historical_data] 尝试使用 Marketstack...")
        
        # Marketstack API 端点
        url = "http://api.marketstack.com/v1/eod"
        
        # Marketstack 不支持指数代码（如 ^IXIC），需要特殊处理
        # 如果ticker以^开头，跳过Marketstack（因为Marketstack不支持指数）
        if ticker.startswith('^'):
            return None
        
        # 计算日期范围
        period_days = {
            "1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180,
            "1y": 365, "2y": 730, "5y": 1825, "10y": 3650, "max": 10000
        }
        days = period_days.get(period, 365)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        params = {
            "access_key": MARKETSTACK_API_KEY,
            "symbols": ticker,
            "date_from": start_date.strftime('%Y-%m-%d'),
            "date_to": end_date.strftime('%Y-%m-%d'),
            "limit": 10000  # 最大限制
        }
        
        response = _http_get(url, params=params, timeout=20)
        
        if response.status_code == 200:
            data = response.json()
            if "error" in data:
                logger.info("[get_stock_historical_data] Marketstack 返回错误")
                return None
            
            if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
                kline_data = []
                for item in data["data"]:
                    kline_data.append({
                        "time": item.get('date', '')[:10],  # 只取日期部分
                        "open": _safe_float_value(item.get('open')),
                        "high": _safe_float_value(item.get('high')),
                        "low": _safe_float_value(item.get('low')),
                        "close": _safe_float_value(item.get('close')),
                        "volume": _safe_float_value(item.get('volume')),
                    })
                
                if kline_data:
                    logger.info("[get_stock_historical_data] Marketstack 成功获取数据")
                    return {"kline_data": kline_data, "period": period, "interval": "1d", "source": "marketstack"}
        
        return None
    except Exception as e:
        logger.info("[get_stock_historical_data] Marketstack 失败: %s", type(e).__name__)
        return None



def _fetch_with_massive_io(ticker: str, period: str = "1y") -> dict:
    """
    策略 5e: 使用 Massive.com (原 Polygon.io) API
    """
    try:
        if not MASSIVE_API_KEY:
            logger.info(f"[get_stock_historical_data] Massive.com API key 未配置")
            return None
            
        logger.info("[get_stock_historical_data] 尝试使用 Massive.com...")
        
        # Massive.com (原 Polygon.io) API 端点
        # 注意：Polygon.io 已更名为 Massive.com，但 API 端点仍为 api.polygon.io
        # API 格式: /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}
        # 日期必须作为路径参数，不能作为查询参数
        
        # 计算日期范围
        period_days = {
            "1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180,
            "1y": 365, "2y": 730, "5y": 1825, "10y": 3650, "max": 10000
        }
        days = period_days.get(period, 365)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # 日期作为路径参数
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
        
        params = {
            "adjusted": "true",
            "sort": "asc",
            "limit": 50000,
            "apikey": MASSIVE_API_KEY  # Massive.com API key 作为查询参数
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = _http_get(url, params=params, headers=headers, timeout=20)
        
        if response.status_code == 200:
            data = response.json()
            # Massive.com API 可能返回 'OK' 或 'DELAYED' 状态，只要 results 有数据就可以使用
            # DELAYED 状态表示数据有延迟，但仍然可以使用
            if data.get('status') in ('OK', 'DELAYED') and 'results' in data:
                results = data.get('results', [])
                if len(results) > 0:
                    kline_data = []
                    for item in results:
                        timestamp = item['t'] / 1000  # 转换为秒
                        date_str = datetime.fromtimestamp(timestamp, tz=UTC).strftime('%Y-%m-%d')  # UTC 取日，防本地时区偏一天
                        kline_data.append({
                            "time": date_str,
                            "open": _safe_float_value(item.get('o')),
                            "high": _safe_float_value(item.get('h')),
                            "low": _safe_float_value(item.get('l')),
                            "close": _safe_float_value(item.get('c')),
                            "volume": _safe_float_value(item.get('v')),
                        })
                    
                    if kline_data:
                        logger.info("[get_stock_historical_data] Massive.com 成功获取数据")
                        return {"kline_data": kline_data, "period": period, "interval": "1d", "source": "massive"}
            else:
                logger.info("[get_stock_historical_data] Massive.com 返回空数据或错误")
        else:
            logger.info(f"[get_stock_historical_data] Massive.com HTTP 错误: {response.status_code}")
        
        return None
    except Exception as e:
        logger.info("[get_stock_historical_data] Massive.com 失败: %s", type(e).__name__)
        return None



def _map_to_stooq_symbol(ticker: str) -> Optional[str]:
    """
    将 ticker 映射到 Stooq 格式。
    注意：Stooq 不支持加密货币和 A 股，返回 None 跳过。
    """
    upper = ticker.upper()

    # 不支持的 ticker 类型 - 返回 None 跳过
    # 加密货币
    if any(crypto in upper for crypto in ['BTC', 'ETH', 'USDT', 'BNB', 'XRP', 'SOL', 'DOGE', 'ADA']):
        return None
    # A 股指数和股票
    if upper.endswith('.SS') or upper.endswith('.SZ') or upper.startswith('000') or upper.startswith('600') or upper.startswith('300'):
        return None
    # 商品期货（Stooq 格式不同）
    if '=' in upper:
        return None

    # 已知的指数映射
    mapping = {
        "^IXIC": "^ndq",
        "^GSPC": "^spx",
        "^DJI": "^dji",
        "^RUT": "^rut",
        "^VIX": "^vix",
    }
    if upper in mapping:
        return mapping[upper]
    if upper.startswith("^"):
        return upper.lower()
    return f"{upper}.us"



def _fetch_with_stooq_history(ticker: str, period: str = "1y", interval: str = "1d") -> Optional[dict]:
    """
    免 Key 回退：使用 stooq 获取日线数据（支持部分指数和美股，代码带 .us）。
    """
    try:
        import requests  # type: ignore
        import csv
        from datetime import date, timedelta

        symbol = _map_to_stooq_symbol(ticker)
        if not symbol:
            return None

        days_map = {
            "1d": 5, "5d": 10, "1mo": 40, "3mo": 120, "6mo": 200,
            "1y": 365, "2y": 730, "5y": 1825, "10y": 3650, "max": 3650
        }
        days = days_map.get(period, 365)
        end = date.today()
        start = end - timedelta(days=days)
        url = f"https://stooq.pl/q/d/l/?s={symbol}&d1={start:%Y%m%d}&d2={end:%Y%m%d}&i=d"
        resp = _http_get(url, timeout=8)
        if resp.status_code != 200 or not resp.text:
            return None

        lines = resp.text.strip().splitlines()
        reader = csv.DictReader(lines)
        data = []
        for row in reader:
            try:
                date_key = "Date" if "Date" in row else ("Data" if "Data" in row else None)
                open_key = "Open" if "Open" in row else ("Otwarcie" if "Otwarcie" in row else None)
                high_key = "High" if "High" in row else ("Najwyzszy" if "Najwyzszy" in row else None)
                low_key = "Low" if "Low" in row else ("Najnizszy" if "Najnizszy" in row else None)
                close_key = "Close" if "Close" in row else ("Zamkniecie" if "Zamkniecie" in row else None)
                volume_key = "Volume" if "Volume" in row else ("Wolumen" if "Wolumen" in row else None)
                if not all([date_key, open_key, high_key, low_key, close_key]):
                    continue
                close_val = _safe_float_value(row[close_key])
                if close_val is None or close_val <= 0 or close_val > 1e8:
                    continue
                data.append(
                    {
                        "time": f"{row[date_key]} 00:00",
                        "open": _safe_float_value(row[open_key]),
                        "high": _safe_float_value(row[high_key]),
                        "low": _safe_float_value(row[low_key]),
                        "close": close_val,
                        "volume": _safe_float_value(row.get(volume_key)) or 0.0,
                    }
                )
            except Exception:
                continue

        if data:
            logger.info("[get_stock_historical_data] Stooq 成功获取数据")
            if interval.endswith("h"):
                # stooq 只有日线。此前用最近 10 日收盘伪造 OHLC 全等的"小时"平线
                # 冒充 1h 数据，下游波动率/振幅/量能指标会得到静默错误结果；
                # 如实返回 None 让降级链走真正的分时源或明确失败（R7）。
                return None
            return {"kline_data": data, "period": period, "interval": "1d", "source": "stooq"}
        return None
    except Exception as e:
        logger.info("[get_stock_historical_data] Stooq 失败: %s", type(e).__name__)
        return None



def _fallback_price_value(ticker: str) -> Optional[float]:
    """
    简单兜底：尝试用 stooq 价格接口或搜索提取一个最新价，用于生成平滑序列。
    """
    try:
        symbol = _map_to_stooq_symbol(ticker)
        if symbol:
            url = f"https://stooq.pl/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=json"
            resp = _http_get(url, timeout=6)
            if resp.status_code == 200:
                data = resp.json().get("symbols") or []
                if data:
                    close = data[0].get("close")
                    if close not in (None, "N/D"):
                        return _safe_float_value(close)
    except Exception as exc:
        logger.debug("historical stooq price fallback failed: %s", type(exc).__name__)

    # 搜索兜底
    try:
        search_result = search(f"{ticker} index level today")
        # r"\\d" 双反斜杠会编译成“字面反斜杠 + d”，永远匹配不到数字文本，
        # 整条搜索兜底失效（与 conversation/context.py 同类 bug）。
        m = re.search(r"(\d{3,6}(?:,\d{3})*(?:\.\d+)?)", search_result or "")
        if m:
            val = _safe_float_value(m.group(1).replace(",", ""))
            if val is None:
                return None
            if val <= 0 or val > 1e8:
                return None
            return val
    except Exception:
        pass
    return None



def _safe_float_value(value: Any) -> Optional[float]:
    return safe_float(value)

