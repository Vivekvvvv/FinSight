"""Historical price data provider functions.

Extracted from tools.price to keep the price module focused; price
re-exports every name here for backward compatibility.
"""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

import yfinance as yf

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


logger = logging.getLogger(__name__)


from backend.tools.price_history_vendor_providers import (
    _fetch_with_iex_cloud,
    _fetch_with_marketstack,
    _fetch_with_massive_io,
    _fetch_with_stooq_history,
    _fetch_with_tiingo,
    _fetch_with_twelve_data,
    _fetch_with_yahoo_scrape_historical,
    _fallback_price_value,
    _map_to_stooq_symbol,
    _safe_float_value,
)



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
