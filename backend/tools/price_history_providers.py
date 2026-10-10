"""Historical price data provider functions.

Extracted from tools.price to keep the price module focused; price
re-exports every name here for backward compatibility.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import UTC, date, datetime, timedelta
from typing import Any, Optional

import yfinance as yf

from ._item import iter_dict_items
from .env import (
    ALPHA_VANTAGE_API_KEY,
    FINNHUB_API_KEY,
    IEX_CLOUD_API_KEY,
    MARKETSTACK_API_KEY,
    MASSIVE_API_KEY,
    TIINGO_API_KEY,
    TWELVE_DATA_API_KEY,
    finnhub_client,
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
                for item in iter_dict_items(data):
                    # 非 dict 毒行由 iter_dict_items 按条跳过——否则 .get
                    # AttributeError 落进函数级 except，该 provider 整批返回 None（同 R107）
                    time_str = str(item.get('date') or item.get('label') or '')
                    if not time_str:
                        continue  # 无日期K线柱无意义，丢弃
                    kline_data.append({
                        "time": time_str,
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
                for item in iter_dict_items(data):
                    # 毒行按条跳过（同 R107）；date present-None 也跳过切片
                    time_str = str(item.get('date') or '')[:10]
                    if not time_str:
                        continue  # 无日期K线柱无意义，丢弃
                    kline_data.append({
                        "time": time_str,  # 只取日期部分
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
        for item in iter_dict_items(values):
            # 毒行按条跳过（同 R107）
            time_str = str(item.get("datetime") or "")[:10]
            if not time_str:
                continue  # 无日期K线柱无意义，丢弃
            kline_data.append({
                "time": time_str,
                "open": _safe_float_value(item.get("open")),
                "high": _safe_float_value(item.get("high")),
                "low": _safe_float_value(item.get("low")),
                "close": _safe_float_value(item.get("close")),
                "volume": _safe_float_value(item.get("volume")),
            })

        if kline_data:
            # Twelve Data 默认倒序，翻转为时间正序
            kline_data = list(reversed(kline_data))
            as_of = str(values[0].get("datetime") or "")[:19] if isinstance(values[0], dict) else ""
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
                for item in iter_dict_items(data["data"]):
                    # 毒行按条跳过（同 R107）
                    time_str = str(item.get('date') or '')[:10]
                    if not time_str:
                        continue  # 无日期K线柱无意义，丢弃
                    kline_data.append({
                        "time": time_str,  # 只取日期部分
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
                    for item in iter_dict_items(results):
                        # 毒行按条跳过；item['t'] 裸索引 KeyError/TypeError
                        # 会让整个 provider 返回 None（同 R107）
                        ts = _safe_float_value(item.get('t'))
                        if ts is None:
                            continue
                        timestamp = ts / 1000  # 转换为秒
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
    # 加密货币：必须是「crypto 代码 + USD/USDT/-/结尾」形态（BTC-USD、SOLUSD）。
    # 裸子串会把合法美股误判成 crypto："SOL"⊂"SOLV"、"ETH"⊂"ETHO"、
    # "BTC"⊂"BTCT"、"ADA"⊂"ADAG" —— 这些 ticker 直接失去 stooq 兜底源。
    if re.match(r"^(?:BTC|ETH|USDT|BNB|XRP|SOL|DOGE|ADA)(?:USD|USDT|-|$)", upper):
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
        # 但首个数字命中还可能是指数名里的数字（"S&P 500"→500）、
        # 年份或编号——优先带千分位/小数的匹配、跳过裸年份，否则错误数字
        # 会被 _fetch_index_price 直接当现价展示给用户。注意千分位形态
        # 前段允许 1-3 位（"5,900"），旧的 \d{3,6} 会把 "5,900" 拆成裸
        # "900" 而丢掉分隔符信息。
        matches = list(
            re.finditer(r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{3,6}(?:\.\d+)?)", search_result or "")
        )
        matches.sort(key=lambda m: "," not in m.group(1) and "." not in m.group(1))
        for m in matches:
            token = m.group(1)
            val = _safe_float_value(token.replace(",", ""))
            if val is None or val <= 0 or val > 1e8:
                continue
            if "," not in token and "." not in token and 1900 <= val <= 2100:
                continue  # 裸年份不是价格
            return val
    except Exception:
        pass
    return None



def _safe_float_value(value: Any) -> Optional[float]:
    return safe_float(value)



# ============================================
# 公司信息获取
# ============================================

def get_stock_historical_data(ticker: str, period: str = "1y", interval: str = "1d") -> dict:
    """
    获取股票的历史数据，用于K线图。
    返回的数据格式专门为 ECharts 优化。
    使用多源回退策略：yfinance (优先，最可靠) → Alpha Vantage → Finnhub → Yahoo 网页抓取 → IEX Cloud → Tiingo → Twelve Data → Marketstack → Massive.com → Stooq
    
    Args:
        ticker: 股票代码
        period: 时间周期 ("1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max")
        interval: 数据间隔 ("1d", "1wk", "1mo")
    
    Returns:
        dict: {"kline_data": [...]} 或 {"error": "..."}
    """
    # 指数优先尝试 Stooq（免 Key，避免 yfinance 速率限制）
    is_index = ticker.startswith("^")
    if is_index:
        stooq_result = _fetch_with_stooq_history(ticker, period, interval)
        if stooq_result and stooq_result.get("kline_data"):
            logger.info("[get_stock_historical_data] Stooq 指数兜底命中，返回日线数据")
            return stooq_result

    # 策略 0: 优先使用 yfinance（最可靠，支持股票和指数）
    # 使用 session 和重试机制，避免速率限制
    max_retries = 1  # 限流严重时快速跳过
    for attempt in range(max_retries):
        try:
            logger.info("[get_stock_historical_data] 尝试使用 yfinance...")
            
            # 创建新的 session，避免缓存问题
            import yfinance as yf_local
            stock = yf_local.Ticker(ticker, session=None)  # 不使用缓存
            
            # 对于指数，使用不同的参数
            include_time = interval.endswith('h') or interval.endswith('m')
            if ticker.startswith('^'):
                hist = stock.history(period=period, interval=interval, timeout=5, raise_errors=True)
            else:
                hist = stock.history(period=period, interval=interval, timeout=5, raise_errors=True)
            
            if not hist.empty and len(hist) > 0:
                data = []
                for index, row in hist.iterrows():
                    # 处理日期/时间格式
                    if include_time and hasattr(index, 'to_pydatetime'):
                        time_str = index.to_pydatetime().strftime('%Y-%m-%d %H:%M')
                    elif hasattr(index, 'strftime'):
                        time_str = index.strftime('%Y-%m-%d')
                    elif hasattr(index, 'date'):
                        time_str = index.date().strftime('%Y-%m-%d')
                    else:
                        time_str = str(index)[:10]
                    
                    time_value = time_str if include_time else f"{time_str} 00:00"
                    data.append({
                        "time": time_value,
                    "open": _safe_float_value(row['Open']),
                    "high": _safe_float_value(row['High']),
                    "low": _safe_float_value(row['Low']),
                    "close": _safe_float_value(row['Close']),
                    "volume": _safe_float_value(row.get('Volume')),
                    })
                
                if data:
                    logger.info("[get_stock_historical_data] yfinance 成功获取数据")
                    return {"kline_data": data, "period": period, "interval": interval, "source": "yfinance"}
        except Exception as e:
            error_msg = str(e)
            if "Too Many Requests" in error_msg or "Rate limited" in error_msg:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.info("[get_stock_historical_data] yfinance 速率限制，等待后重试...")
                    import time as time_module
                    time_module.sleep(wait_time)
                    continue
            logger.info("[get_stock_historical_data] yfinance 失败: %s", type(e).__name__)
            if attempt == max_retries - 1:
                break
    
    # 策略 1: 尝试使用 Alpha Vantage
    # 注意：Alpha Vantage 不支持指数代码（如 ^IXIC），对于指数直接跳过
    if ALPHA_VANTAGE_API_KEY and not ticker.startswith('^'):
        try:
            # 对于指数代码，移除^符号
            ticker_for_av = ticker.lstrip('^')
            url = f"https://www.alphavantage.co/query"
            params = {
                "function": "TIME_SERIES_DAILY",
                "symbol": ticker_for_av,
                "apikey": ALPHA_VANTAGE_API_KEY,
                "outputsize": "full"
            }
            response = _http_get(url, params=params, timeout=15)
            data = response.json()
            
            # 检查是否有错误信息
            if "Error Message" in data:
                error_msg = data.get('Error Message', 'Unknown error')
                logger.info("[get_stock_historical_data] Alpha Vantage 返回错误")
                raise Exception(f"Alpha Vantage API error: {error_msg}")
            
            # 检查是否有速率限制提示
            if "Note" in data:
                note = data.get('Note', '')
                if "API call frequency" in note or "rate limit" in note.lower():
                    logger.info("[get_stock_historical_data] Alpha Vantage 速率限制")
                    raise Exception("Alpha Vantage rate limit")
                else:
                    logger.info("[get_stock_historical_data] Alpha Vantage 返回提示")
                    raise Exception(f"Alpha Vantage note: {note}")
            
            if "Time Series (Daily)" in data:
                time_series = data["Time Series (Daily)"]
                # 根据 period 确定需要的数据量
                period_days = {
                    "1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180,
                    "1y": 252, "2y": 504, "5y": 1260, "10y": 2520, "max": 10000
                }
                max_days = period_days.get(period, 252)
                
                sorted_dates = sorted(time_series.keys(), reverse=True)[:max_days]
                
                kline_data = []
                for date_str in sorted_dates:
                    day_data = time_series[date_str]
                    # 毒行按条跳过——非 dict 的 day_data["1. open"] TypeError
                    # 落进函数级 except 让整段 AV 日线被弃走下游兜底（同 R107-R118）
                    if not isinstance(day_data, dict):
                        continue
                    kline_data.append({
                        "time": date_str,
                        "open": _safe_float_value(day_data["1. open"]),
                        "high": _safe_float_value(day_data["2. high"]),
                        "low": _safe_float_value(day_data["3. low"]),
                        "close": _safe_float_value(day_data["4. close"]),
                        "volume": _safe_float_value(day_data.get("5. volume")) or 0.0,
                    })
                
                # 按时间正序排列
                kline_data.reverse()
                logger.info("[get_stock_historical_data] Alpha Vantage 成功获取数据")
                return {"kline_data": kline_data, "period": period, "interval": interval}
        except Exception as e:
            logger.info("[get_stock_historical_data] Alpha Vantage 失败: %s，尝试 yfinance...", type(e).__name__)
    
    # 策略 2: 回退到 yfinance（支持多时间周期，带重试）
    # 注意：yfinance 已在文件顶部导入，这里直接使用
    # yfinance 支持指数代码（如 ^IXIC, ^GSPC），这是获取指数数据的主要方法
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # yfinance 支持指数代码，直接使用
            stock = yf.Ticker(ticker)
            
            # 根据 period 和 interval 获取数据
            # yfinance 支持的 period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
            # yfinance 支持的 interval: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
            # 对于指数，yfinance 通常能正常工作
            hist = stock.history(period=period, interval=interval, timeout=5)
            
            if hist.empty:
                if attempt < max_retries - 1:
                    logger.info("[get_stock_historical_data] yfinance 返回空数据，准备重试...")
                    time.sleep(2 ** attempt)  # 指数退避
                    continue
                configured_fallback = any((
                    FINNHUB_API_KEY,
                    IEX_CLOUD_API_KEY,
                    TIINGO_API_KEY,
                    TWELVE_DATA_API_KEY,
                    MARKETSTACK_API_KEY,
                    MASSIVE_API_KEY,
                ))
                if configured_fallback:
                    break
                return {"error": f"No historical data for {ticker}"}

            # 转换格式以匹配 ECharts 的要求
            include_time = interval.endswith('h') or interval.endswith('m')
            data = []
            for index, row in hist.iterrows():
                # Normalize timestamp for chart rows
                if include_time and hasattr(index, 'to_pydatetime'):
                    time_str = index.to_pydatetime().strftime('%Y-%m-%d %H:%M')
                elif hasattr(index, 'strftime'):
                    time_str = index.strftime('%Y-%m-%d')
                elif hasattr(index, 'date'):
                    time_str = index.date().strftime('%Y-%m-%d')
                else:
                    time_str = str(index)[:10]
                time_value = time_str if include_time else f"{time_str} 00:00"
                data.append({
                    "time": time_value,
                    "open": _safe_float_value(row['Open']),
                    "high": _safe_float_value(row['High']),
                    "low": _safe_float_value(row['Low']),
                    "close": _safe_float_value(row['Close']),
                    "volume": _safe_float_value(row.get('Volume')),
                })

            logger.info("[get_stock_historical_data] yfinance fallback success")
            return {"kline_data": data, "period": period, "interval": interval}
        except Exception as e:
            error_msg = str(e)
            if "Too Many Requests" in error_msg or "Rate limited" in error_msg:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.info("[get_stock_historical_data] yfinance fallback 速率限制，等待后重试...")
                    import time as time_module
                    time_module.sleep(wait_time)
                    continue
            # 如果不是速率限制错误，或者已经重试完，继续到下一个策略
            logger.info("[get_stock_historical_data] yfinance fallback 失败: %s", type(e).__name__)
            if attempt == max_retries - 1:
                break  # 最后一次尝试失败，继续到下一个策略
    
    # 策略 3: 尝试使用 Finnhub（如果有 API key）
    if FINNHUB_API_KEY and finnhub_client:
        try:
            from datetime import datetime, timedelta
            
            # 根据 period 计算天数
            period_days = {
                "1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180,
                "1y": 365, "2y": 730, "5y": 1825, "10y": 3650, "max": 10000
            }
            days = period_days.get(period, 365)
            
            end_date = int(time.time())
            start_date = int((datetime.now() - timedelta(days=days)).timestamp())
            
            res = finnhub_client.stock_candles(ticker, 'D', start_date, end_date)
            
            if res['s'] == 'ok' and len(res['c']) > 0:
                kline_data = []
                for i in range(len(res['t'])):
                    timestamp = res['t'][i]
                    date_str = datetime.fromtimestamp(timestamp, tz=UTC).strftime('%Y-%m-%d')  # UTC 取日，防本地时区偏一天
                    kline_data.append({
                        "time": date_str,
                        "open": _safe_float_value(res['o'][i]),
                        "high": _safe_float_value(res['h'][i]),
                        "low": _safe_float_value(res['l'][i]),
                        "close": _safe_float_value(res['c'][i]),
                        "volume": _safe_float_value(res.get('v', [0] * len(res['t']))[i]) if 'v' in res else 0.0,
                    })
                logger.info("[get_stock_historical_data] Finnhub 成功获取数据")
                return {"kline_data": kline_data, "period": period, "interval": interval}
        except Exception as e2:
            logger.info("[get_stock_historical_data] Finnhub 也失败: %s", type(e2).__name__)
    
    # 策略 4: 尝试从 Yahoo Finance 网页直接抓取（对指数代码特别有效）
    try:
        result = _fetch_with_yahoo_scrape_historical(ticker, period)
        if result and "kline_data" in result and len(result["kline_data"]) > 0:
            return result
    except Exception as e3:
        logger.info("[get_stock_historical_data] Yahoo Finance 网页抓取失败: %s", type(e3).__name__)
    
    # 对于指数代码，优先使用 yfinance（即使之前失败，再试一次，因为指数可能支持）
    if ticker.startswith('^'):
        logger.info("[get_stock_historical_data] 检测到指数代码，尝试使用 yfinance 专门获取指数数据...")
        try:
            # 对于指数，yfinance 通常支持，但可能需要特殊处理
            stock = yf.Ticker(ticker)
            hist = stock.history(period=period, interval=interval, timeout=5)
            
            if not hist.empty:
                include_time = interval.endswith('h') or interval.endswith('m')
                data = []
                for index, row in hist.iterrows():
                    if include_time and hasattr(index, 'to_pydatetime'):
                        time_str = index.to_pydatetime().strftime('%Y-%m-%d %H:%M')
                    elif hasattr(index, 'strftime'):
                        time_str = index.strftime('%Y-%m-%d')
                    elif hasattr(index, 'date'):
                        time_str = index.date().strftime('%Y-%m-%d')
                    else:
                        time_str = str(index)[:10]
                    
                    time_value = time_str if include_time else f"{time_str} 00:00"
                    data.append({
                        "time": time_value,
                        "open": _safe_float_value(row['Open']),
                        "high": _safe_float_value(row['High']),
                        "low": _safe_float_value(row['Low']),
                        "close": _safe_float_value(row['Close']),
                        "volume": _safe_float_value(row.get('Volume')),
                    })
                
                if data:
                    logger.info("[get_stock_historical_data] yfinance 成功获取指数数据")
                    return {"kline_data": data, "period": period, "interval": interval, "source": "yfinance_index"}
        except Exception as e_index:
            logger.info("[get_stock_historical_data] yfinance 获取指数数据失败: %s", type(e_index).__name__)
    
    # 策略 5a: 尝试使用 IEX Cloud (免费额度大，优先使用)
    try:
        result = _fetch_with_iex_cloud(ticker, period)
        if result and "kline_data" in result and len(result["kline_data"]) > 0:
            return result
    except Exception as e4a:
        logger.info("[get_stock_historical_data] IEX Cloud 失败: %s", type(e4a).__name__)
    
    # 策略 5b: 尝试使用 Tiingo (免费额度: 每日500次)
    try:
        result = _fetch_with_tiingo(ticker, period)
        if result and "kline_data" in result and len(result["kline_data"]) > 0:
            return result
    except Exception as e4b:
        logger.info("[get_stock_historical_data] Tiingo 失败: %s", type(e4b).__name__)
    
    # 策略 5c: 尝试使用 Twelve Data (免费额度)
    try:
        result = _fetch_with_twelve_data(ticker, period)
        if result and "kline_data" in result and len(result["kline_data"]) > 0:
            return result
    except Exception as e4c:
        logger.info("[get_stock_historical_data] Twelve Data 失败: %s", type(e4c).__name__)
    
    # 策略 5d: 尝试使用 Marketstack (免费额度: 1000次/月)
    try:
        result = _fetch_with_marketstack(ticker, period)
        if result and "kline_data" in result and len(result["kline_data"]) > 0:
            return result
    except Exception as e4d:
        logger.info("[get_stock_historical_data] Marketstack 失败: %s", type(e4d).__name__)
    
    # 策略 5e: 尝试使用 Massive.com (原 Polygon.io)
    try:
        result = _fetch_with_massive_io(ticker, period)
        if result and "kline_data" in result and len(result["kline_data"]) > 0:
            return result
    except Exception as e4e:
        logger.info("[get_stock_historical_data] Massive.com 失败: %s", type(e4e).__name__)

    # 策略 5f: 尝试 Stooq 免 Key 回退
    try:
        result = _fetch_with_stooq_history(ticker, period, interval)
        if result and "kline_data" in result and len(result["kline_data"]) > 0:
            return result
    except Exception as e4f:
        logger.info("[get_stock_historical_data] Stooq 失败: %s", type(e4f).__name__)

    # 策略 6: 最后尝试 - 使用 yfinance 的备用方法（不通过 Ticker，直接下载）
    # 等待一段时间后再尝试，避免速率限制
    import time as time_module
    time_module.sleep(2)  # 等待2秒，避免速率限制
    
    try:
        logger.info(f"[get_stock_historical_data] 尝试 yfinance 备用方法（等待后重试）...")
        # 使用 yfinance 的 download 函数（yf 已在文件顶部导入）
        from datetime import datetime, timedelta
        
        period_days = {
            "1d": 1, "5d": 5, "1mo": 30, "3mo": 90, "6mo": 180,
            "1y": 365, "2y": 730, "5y": 1825, "10y": 3650, "max": 10000
        }
        days = period_days.get(period, 365)
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # 使用 yfinance.download 直接下载
        hist = yf.download(
            ticker,
            start=start_date.strftime('%Y-%m-%d'),
            end=end_date.strftime('%Y-%m-%d'),
            progress=False,
            timeout=20
        )
        
        if not hist.empty:
            include_time = interval.endswith('h') or interval.endswith('m')
            data = []
            for index, row in hist.iterrows():
                if include_time and hasattr(index, 'to_pydatetime'):
                    time_str = index.to_pydatetime().strftime('%Y-%m-%d %H:%M')
                elif hasattr(index, 'strftime'):
                    time_str = index.strftime('%Y-%m-%d')
                elif hasattr(index, 'date'):
                    time_str = index.date().strftime('%Y-%m-%d')
                else:
                    time_str = str(index)[:10]
                
                time_value = time_str if include_time else f"{time_str} 00:00"
                data.append({
                    "time": time_value,
                    "open": _safe_float_value(row['Open']),
                    "high": _safe_float_value(row['High']),
                    "low": _safe_float_value(row['Low']),
                    "close": _safe_float_value(row['Close']),
                    "volume": _safe_float_value(row.get('Volume')),
                })
            
            if data:
                logger.info("[get_stock_historical_data] yfinance 备用方法成功获取数据")
                return {"kline_data": data, "period": period, "interval": interval}
    except Exception as e5:
        logger.info("[get_stock_historical_data] yfinance 备用方法失败: %s", type(e5).__name__)
    
    # 此前指数全源失败时会用单一最新价伪造 OHLC 全等的平线序列（24 根"小时"/
    # 5 根日线，volume=0，source=price_fallback*）。伪平线让 RSI 恒 100、
    # ATR/波动率恒 0，下游技术指标静默失真（同 R7 判例）；全仓无消费方依赖
    # 该 source 标记。如实返回错误。

    # 所有策略都失败，返回错误
    return {"error": f"Failed to fetch historical data for {ticker}: All data sources failed. Please try again later or check your internet connection."}
