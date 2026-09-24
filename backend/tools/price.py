import json
import logging
import os
import re
import time
from datetime import UTC, datetime, timedelta, date
from typing import Optional, List, Dict, Any, Union
from urllib.parse import quote

import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup

from .env import (
    ALPHA_VANTAGE_API_KEY,
    FINNHUB_API_KEY,
    IEX_CLOUD_API_KEY,
    MASSIVE_API_KEY,
    MARKETSTACK_API_KEY,
    TIINGO_API_KEY,
    TWELVE_DATA_API_KEY,
    finnhub_client,
)
from .http import _http_get
from .search import search
from backend.utils.quote import safe_float

logger = logging.getLogger(__name__)

from backend.tools.price_history_providers import (
    _fetch_with_yahoo_scrape_historical,
    _fetch_with_iex_cloud,
    _fetch_with_tiingo,
    _fetch_with_twelve_data,
    _fetch_with_marketstack,
    _fetch_with_massive_io,
    _map_to_stooq_symbol,
    _fetch_with_stooq_history,
    _fallback_price_value,
    _safe_float_value,
)

from backend.tools.price_portfolio import (
    _normalize_positions,
    _download_close_frame,
    _compute_beta,
    get_factor_exposure,
    run_portfolio_stress_test,
    get_performance_comparison,
)


def _fetch_with_alpha_vantage(ticker: str):
    """优先方案：使用 Alpha Vantage API 获取实时股价"""
    logger.info("  - Attempting Alpha Vantage API...")
    try:
        url = "https://www.alphavantage.co/query"
        params = {
            'function': 'GLOBAL_QUOTE',
            'symbol': ticker,
            'apikey': ALPHA_VANTAGE_API_KEY
        }
        response = _http_get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if 'Global Quote' in data and data['Global Quote']:
            quote = data['Global Quote']
            price = _safe_float_value(quote.get('05. price'))
            change = _safe_float_value(quote.get('09. change'))
            change_percent_str = quote.get('10. change percent', '0%').replace('%', '')
            
            change_percent = _safe_float_value(change_percent_str)
            if price is not None and price > 0 and change is not None and change_percent is not None:
                return f"{ticker} Current Price: ${price:.2f} | Change: ${change:.2f} ({change_percent:+.2f}%)"
        
        if 'Note' in data or 'Information' in data:
            logger.info("  - Alpha Vantage returned a note")
        if 'Error Message' in data:
            logger.info("  - Alpha Vantage returned an error")
            
        return None
    except Exception as e:
        logger.info("  - Alpha Vantage exception: %s", type(e).__name__)
        return None

def _fetch_with_finnhub(ticker: str):
    """新增：使用 Finnhub API 获取实时股价"""
    if not finnhub_client:
        return None
    logger.info("  - Attempting Finnhub API...")
    try:
        quote = finnhub_client.quote(ticker)
        if quote:
            price = _safe_float_value(quote.get('c'))
            change = _safe_float_value(quote.get('d')) or 0.0
            change_percent = _safe_float_value(quote.get('dp')) or 0.0
            if price is None or price <= 0:
                return None
            return f"{ticker} Current Price: ${price:.2f} | Change: ${change:.2f} ({change_percent:+.2f}%)"
        return None
    except Exception as e:
        logger.info("  - Finnhub quote exception: %s", type(e).__name__)
        return None

def _fetch_with_yfinance(ticker: str):
    """尝试使用 yfinance 获取价格"""
    logger.info("  - Attempting yfinance...")
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="5d")
        if hist.empty or len(hist) < 2:
            return None
        
        current_price = _safe_float_value(hist['Close'].iloc[-1])
        prev_close = _safe_float_value(hist['Close'].iloc[-2])
        if current_price is None or current_price <= 0:
            return None
        msg = f"{ticker} Current Price: ${current_price:.2f}"
        if prev_close is not None and prev_close > 0:
            change = current_price - prev_close
            change_percent = (change / prev_close) * 100
            msg += f" | Change: ${change:.2f} ({change_percent:+.2f}%)"
        return msg
    except Exception as e:
        logger.info("  - yfinance exception: %s", type(e).__name__)
        return None

def _fetch_with_twelve_data_price(ticker: str):
    """备用方案：使用 Twelve Data 获取实时价格"""
    if not TWELVE_DATA_API_KEY:
        return None
    logger.info("  - Attempting Twelve Data...")
    try:
        params = {
            "symbol": ticker,
            "interval": "1day",
            "outputsize": 2,  # 最新两天计算涨跌幅
            "apikey": TWELVE_DATA_API_KEY,
            "order": "desc",
        }
        response = _http_get("https://api.twelvedata.com/time_series", params=params, timeout=10)
        if response.status_code != 200:
            return None

        data = response.json()
        if data.get("status") != "ok" or not data.get("values"):
            # Twelve Data 返回 {"status": "error", "message": "..."} 时也走兜底
            return None

        values = data.get("values", [])
        latest = values[0] if values else None
        if not latest:
            return None

        price = _safe_float_value(latest.get("close"))
        if price is None or price <= 0:
            return None

        prev_close = None
        if len(values) > 1 and values[1].get("close"):
            prev_close = _safe_float_value(values[1]["close"])

        change = None
        change_percent = None
        if prev_close and prev_close != 0:
            change = price - prev_close
            change_percent = (change / prev_close) * 100.0

        msg = f"{ticker} Current Price: ${price:.2f}"
        if change is not None and change_percent is not None:
            msg += f" | Change: {change:+.2f} ({change_percent:+.2f}%)"
        return msg
    except Exception as e:
        logger.info("  - Twelve Data price exception: %s", type(e).__name__)
        return None

def _fetch_yahoo_api_v8(ticker: str):
    """Yahoo Finance API v8 - 免费 JSON API，无需 API key，比爬虫更稳定"""
    logger.info("  - Attempting Yahoo Finance API v8...")
    try:
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = _http_get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        result = data.get('chart', {}).get('result', [])
        if not result:
            return None

        meta = result[0].get('meta', {})
        price = _safe_float_value(meta.get('regularMarketPrice'))
        prev_close = _safe_float_value(meta.get('previousClose') or meta.get('chartPreviousClose'))

        if price is None or price <= 0:
            return None

        change = None
        change_percent = None
        if prev_close and prev_close != 0:
            change = price - prev_close
            change_percent = (change / prev_close) * 100.0

        msg = f"{ticker} Current Price: ${price:.2f}"
        if change is not None and change_percent is not None:
            msg += f" | Change: {change:+.2f} ({change_percent:+.2f}%)"
        return msg
    except Exception as e:
        logger.info("  - Yahoo API v8 exception: %s", type(e).__name__)
        return None

def _scrape_google_finance(ticker: str):
    """Google Finance 爬虫 - 免费，无需 API key"""
    logger.info("  - Attempting Google Finance...")
    try:
        # 尝试不同交易所
        exchanges = ['NASDAQ', 'NYSE', 'NYSEARCA', '']
        for exchange in exchanges:
            if exchange:
                url = f"https://www.google.com/finance/quote/{ticker}:{exchange}"
            else:
                url = f"https://www.google.com/finance/quote/{ticker}"

            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = _http_get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                # 解析价格 - Google Finance 使用 data-last-price 属性
                match = re.search(r'data-last-price="([0-9.]+)"', response.text)
                if match:
                    price = float(match.group(1))
                    # 尝试获取变动
                    change_match = re.search(r'data-price-change="([+-]?[0-9.]+)"', response.text)
                    pct_match = re.search(r'data-price-change-percent="([+-]?[0-9.]+)"', response.text)

                    msg = f"{ticker} Current Price: ${price:.2f}"
                    if change_match and pct_match:
                        change = float(change_match.group(1))
                        pct = float(pct_match.group(1))
                        msg += f" | Change: {change:+.2f} ({pct:+.2f}%)"
                    return msg
        return None
    except Exception as e:
        logger.info("  - Google Finance exception: %s", type(e).__name__)
        return None

def _scrape_cnbc(ticker: str):
    """CNBC 爬虫 - 免费，实时性好"""
    logger.info("  - Attempting CNBC...")
    try:
        url = f"https://www.cnbc.com/quotes/{ticker}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = _http_get(url, headers=headers, timeout=10)
        response.raise_for_status()

        # CNBC 在 JSON-LD 中包含价格数据
        match = re.search(r'"price":\s*"?([0-9.]+)"?', response.text)
        if match:
            price = float(match.group(1))
            # 尝试获取变动
            change_match = re.search(r'"priceChange":\s*"?([+-]?[0-9.]+)"?', response.text)
            pct_match = re.search(r'"priceChangePercent":\s*"?([+-]?[0-9.]+)"?', response.text)

            msg = f"{ticker} Current Price: ${price:.2f}"
            if change_match and pct_match:
                change = float(change_match.group(1))
                pct = float(pct_match.group(1))
                msg += f" | Change: {change:+.2f} ({pct:+.2f}%)"
            return msg
        return None
    except Exception as e:
        logger.info("  - CNBC exception: %s", type(e).__name__)
        return None

def _fetch_with_pandas_datareader(ticker: str):
    """pandas_datareader - 免费，支持多数据源"""
    logger.info("  - Attempting pandas_datareader...")
    try:
        import pandas_datareader as pdr
        from datetime import datetime, timedelta

        end = datetime.now()
        start = end - timedelta(days=5)

        # 尝试 stooq 数据源（免费）
        df = pdr.get_data_stooq(ticker, start, end)
        if not df.empty:
            price = _safe_float_value(df['Close'].iloc[0])
            if price is None or price <= 0:
                return None
            if len(df) > 1:
                prev = _safe_float_value(df['Close'].iloc[1])
                if prev is not None and prev > 0:
                    change = price - prev
                    pct = (change / prev) * 100
                    return f"{ticker} Current Price: ${price:.2f} | Change: {change:+.2f} ({pct:+.2f}%)"
            return f"{ticker} Current Price: ${price:.2f}"
        return None
    except ImportError:
        logger.info(f"  - pandas_datareader not installed")
        return None
    except Exception as e:
        logger.info("  - pandas_datareader exception: %s", type(e).__name__)
        return None

def _scrape_yahoo_finance(ticker: str):
    """备用方案：直接爬取 Yahoo Finance 页面"""
    logger.info("  - Attempting to scrape Yahoo Finance...")
    try:
        url = f"https://finance.yahoo.com/quote/{ticker}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = _http_get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        price_elem = soup.find('fin-streamer', {'data-symbol': ticker, 'data-field': 'regularMarketPrice'})
        change_elem = soup.find('fin-streamer', {'data-symbol': ticker, 'data-field': 'regularMarketChange'})
        change_percent_elem = soup.find('fin-streamer', {'data-symbol': ticker, 'data-field': 'regularMarketChangePercent'})
        
        if price_elem and change_elem and change_percent_elem:
            price = _safe_float_value(price_elem.get('value'))
            change = _safe_float_value(change_elem.get('value'))
            change_percent = _safe_float_value(change_percent_elem.get('value'))
            
            if price is not None and price > 0:
                msg = f"{ticker} Current Price: ${price:.2f}"
                if change is not None and change_percent is not None:
                    msg += f" | Change: ${change:.2f} ({change_percent * 100:+.2f}%)"
                return msg
        
        return None
    except Exception as e:
        logger.info("  - Yahoo scraping exception: %s", type(e).__name__)
        return None

def _fetch_index_price(ticker: str):
    """
    指数专用：优先 yfinance.download 获取最近两日收盘，失败再用 Stooq/搜索兜底。
    """
    if not ticker.startswith('^'):
        return None
    logger.info("  - Attempting index price via yfinance.download...")
    try:
        hist = yf.download(ticker, period="3d", interval="1d", progress=False, timeout=5)
        if not hist.empty and len(hist) > 0:
            closes = hist['Close'].dropna().tolist()
            if closes:
                current_price = _safe_float_value(closes[-1])
                prev_close = _safe_float_value(closes[-2]) if len(closes) > 1 else None
                if current_price is None or current_price <= 0:
                    return None
                change = current_price - prev_close if prev_close else None
                change_pct = (change / prev_close) * 100 if prev_close else None
                msg = f"{ticker} Current Price: ${current_price:.2f}"
                if change is not None and change_pct is not None:
                    msg += f" | Change: {change:+.2f} ({change_pct:+.2f}%)"
                return msg
    except Exception as e:
        logger.info("  - Index price via yfinance failed: %s", type(e).__name__)
    # Fallback 1: Stooq 免费接口
    stooq_result = _fetch_with_stooq_price(ticker)
    if stooq_result:
        return stooq_result
    # Fallback 2: 搜索兜底
    try:
        price_val = _fallback_price_value(ticker)
        if price_val:
            return f"{ticker} Current Price: ${price_val:.2f}"
    except Exception as exc:
        logger.debug("stooq price fallback failed: %s", type(exc).__name__)
    return None

def _search_for_price(ticker: str):
    """最后手段：使用搜索引擎并用正则表达式解析价格"""
    logger.info("  - Attempting to find price via search...")
    try:
        search_result = search(f"{ticker} stock price today")
        patterns = [
            r'\$(\d{1,5}(?:,\d{3})*\.\d{2})',
            r'(?:Price|price)[:\s]+\$?(\d{1,5}(?:,\d{3})*\.\d{2})',
            r'(\d{1,5}(?:,\d{3})*\.\d{2})\s*USD'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, search_result)
            if match:
                price = match.group(1).replace(',', '')
                price_val = float(price)
                if price_val <= 0 or price_val > 1e8:
                    return None
                from datetime import date
                today = date.today().isoformat()
                return f"{ticker} Current Price (via search): ${price_val:.2f} (as of {today})"
        
        return None
    except Exception as e:
        logger.info("  - Search price exception: %s", type(e).__name__)
        return None

def _fetch_with_stooq_price(ticker: str):
    """
    使用 stooq 免费接口获取最新收盘价（免 Key），支持部分指数和美股。
    """
    try:
        symbol = _map_to_stooq_symbol(ticker)
        if not symbol:
            return None
        url = f"https://stooq.pl/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=json"
        resp = _http_get(url, timeout=8)
        data = resp.json().get("symbols") if resp.status_code == 200 else None
        if not data:
            return None
        item = data[0]
        close = item.get("close")
        if close in (None, "N/D"):
            return None
        price = _safe_float_value(close)
        if price is None or price <= 0:
            return None
        # stooq 该接口无昨收字段。此前用当日开盘价当基准算 "Change"，与兄弟源
        # （yfinance/yahoo 等一律相对昨收）量纲不同却共用同一标签，静默输出错值；
        # 宁缺毋错，只报价格。
        return f"{ticker} Current Price: ${price:.2f}"
    except Exception as e:
        logger.info("  - Stooq price exception: %s", type(e).__name__)
        return None

def _to_yahoo_cn_symbol(ticker: str) -> str:
    """将裸 A股代码转换为 Yahoo Finance 格式（加交易所后缀）。

    规则：
      600xxx / 601xxx / 603xxx / 605xxx / 688xxx → 上交所 .SS
      000xxx / 001xxx / 002xxx / 003xxx / 300xxx / 301xxx → 深交所 .SZ
      8xxxxx（6 位，北交所） → .BJ
    已含后缀的代码原样返回。
    """
    t = ticker.strip().upper()
    if '.' in t:
        return t  # 已有后缀，直接返回
    if len(t) == 6 and t.isdigit():
        if t[:3] in ('600', '601', '603', '605', '688'):
            return f"{t}.SS"
        if t[:3] in ('000', '001', '002', '003', '300', '301'):
            return f"{t}.SZ"
        if t.startswith('8'):
            return f"{t}.BJ"
    return t

def get_stock_price(ticker: str) -> str:
    """
    使用多数据源策略获取股票价格，以提高稳定性。
    根据资产类型选择不同的数据源策略。
    """
    logger.info("Fetching price with multi-source strategy...")
    upper = ticker.upper()

    # 判断资产类型
    is_index = ticker.startswith('^')
    is_crypto = any(crypto in upper for crypto in ['BTC', 'ETH', 'USDT', 'BNB', 'XRP', 'SOL', 'DOGE', 'ADA']) and '-' in upper
    is_china = (
        upper.endswith('.SS') or upper.endswith('.SZ') or upper.endswith('.BJ')
        or (len(upper) == 6 and upper.isdigit() and upper[:3] in (
            '600', '601', '603', '605', '688',  # 上交所
            '000', '001', '002', '003', '300', '301',  # 深交所
        ))
        or (len(upper) == 6 and upper.isdigit() and upper.startswith('8'))  # 北交所
    )
    is_commodity = '=' in upper  # GC=F, CL=F, SI=F

    # A股代码标准化：裸数字代码 → Yahoo Finance 格式（如 600036 → 600036.SS）
    if is_china:
        ticker = _to_yahoo_cn_symbol(ticker)
        upper = ticker.upper()
        logger.info("  [CN] Normalized ticker to Yahoo format")

    # 根据资产类型选择数据源
    if is_crypto:
        # 加密货币：只用 yfinance 和搜索
        sources = [
            _fetch_with_yfinance,
            _fetch_yahoo_api_v8,
            _search_for_price
        ]
    elif is_china:
        # A股：只用 yfinance 和搜索（其他源不支持）
        sources = [
            _fetch_with_yfinance,
            _fetch_yahoo_api_v8,
            _search_for_price
        ]
    elif is_commodity:
        # 商品期货：只用 yfinance 和搜索
        sources = [
            _fetch_with_yfinance,
            _fetch_yahoo_api_v8,
            _search_for_price
        ]
    elif is_index:
        sources = [
            _fetch_yahoo_api_v8,
            _fetch_index_price,
            _fetch_with_stooq_price,
            _search_for_price
        ]
    else:
        # 普通美股
        sources = [
            _fetch_yahoo_api_v8,
            _scrape_google_finance,
            _fetch_with_stooq_price,
            _scrape_cnbc,
            _fetch_with_pandas_datareader,
            _fetch_with_yfinance,
            _fetch_with_alpha_vantage,
            _fetch_with_finnhub,
            _fetch_with_twelve_data_price,
            _scrape_yahoo_finance,
            _search_for_price
        ]
    
    for i, source_func in enumerate(sources, 1):
        try:
            result = source_func(ticker)
            if result:
                logger.info("  Price source succeeded")
                # 只返回行情事实。此处曾按现价 -1%/-2% 追加 "Suggested ladder"
                # 两档建仓价，但 get_stock_price 是 LLM 工具（langchain_tools.py）
                # 且是 price/technical/report 链路的必跑首步（planner.py），
                # 那段文本会绕过 research_policy.sanitize_research_stance 直接
                # 进入模型上下文，违反 research_policy.TRADING_ACTION_PATTERN
                # 对"目标价/仓位建议/入场"的禁令。工具层不得输出交易动作。
                return result
            time.sleep(0.5)
        except Exception as e:
            logger.info(
                "  Price source %s failed: %s",
                source_func.__name__,
                type(e).__name__,
            )
            continue
            
    return f"Error: All data sources failed to retrieve the price for {ticker}. Please try again later."

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

def _nearest_strike_iv(option_df: Any, target_strike: float) -> Optional[float]:
    if option_df is None or getattr(option_df, "empty", True):
        return None
    if "strike" not in option_df.columns or "impliedVolatility" not in option_df.columns:
        return None
    subset = option_df[["strike", "impliedVolatility"]].dropna()
    if subset.empty:
        return None
    try:
        idx = (subset["strike"] - target_strike).abs().idxmin()
        value = _safe_float_value(subset.loc[idx, "impliedVolatility"])
        if value is None or value <= 0:
            return None
        return safe_float(value)
    except Exception:
        return None

def get_option_chain_metrics(ticker: str, expiry: Optional[str] = None) -> Dict[str, Any]:
    """Free option-chain derived signals via yfinance: IV / PCR / skew."""
    result: Dict[str, Any] = {
        "ticker": str(ticker or "").upper(),
        "source": "yfinance_options",
        "as_of": datetime.now().isoformat(),
        "expiry": None,
        "spot_price": None,
        "iv_atm": None,
        "put_call_ratio_oi": None,
        "put_call_ratio_volume": None,
        "iv_skew_25d": None,
        "call_open_interest": None,
        "put_open_interest": None,
        "call_volume": None,
        "put_volume": None,
        "error": None,
    }
    if not ticker:
        result["error"] = "ticker_required"
        return result

    try:
        stock = yf.Ticker(ticker)
        options = list(getattr(stock, "options", []) or [])
        if not options:
            result["error"] = "no_option_chain_available"
            return result

        selected_expiry = expiry if expiry in options else options[0]
        chain = stock.option_chain(selected_expiry)
        calls = getattr(chain, "calls", None)
        puts = getattr(chain, "puts", None)
        if calls is None or puts is None or calls.empty or puts.empty:
            result["error"] = "empty_option_chain"
            return result

        spot_price = None
        try:
            hist = stock.history(period="5d")
            if hist is not None and not hist.empty and "Close" in hist.columns:
                spot_price = _safe_float_value(hist["Close"].iloc[-1])
        except Exception:
            spot_price = None
        if spot_price is None:
            info = getattr(stock, "info", {}) or {}
            spot_price = _safe_float_value(info.get("regularMarketPrice"))
        if spot_price is None or spot_price <= 0:
            result["error"] = "spot_price_unavailable"
            return result

        call_oi = int(calls["openInterest"].fillna(0).sum()) if "openInterest" in calls.columns else 0
        put_oi = int(puts["openInterest"].fillna(0).sum()) if "openInterest" in puts.columns else 0
        call_volume = int(calls["volume"].fillna(0).sum()) if "volume" in calls.columns else 0
        put_volume = int(puts["volume"].fillna(0).sum()) if "volume" in puts.columns else 0

        call_atm_iv = _nearest_strike_iv(calls, float(spot_price))
        put_atm_iv = _nearest_strike_iv(puts, float(spot_price))
        iv_values = [v for v in [call_atm_iv, put_atm_iv] if isinstance(v, float)]
        iv_atm = float(sum(iv_values) / len(iv_values)) if iv_values else None

        put_25d_iv = _nearest_strike_iv(puts, float(spot_price) * 0.95)
        call_25d_iv = _nearest_strike_iv(calls, float(spot_price) * 1.05)
        iv_skew = (put_25d_iv - call_25d_iv) if (put_25d_iv is not None and call_25d_iv is not None) else None

        result.update(
            {
                "expiry": selected_expiry,
                "spot_price": float(spot_price),
                "iv_atm": iv_atm,
                "put_call_ratio_oi": (float(put_oi) / float(call_oi)) if call_oi > 0 else None,
                "put_call_ratio_volume": (float(put_volume) / float(call_volume)) if call_volume > 0 else None,
                "iv_skew_25d": float(iv_skew) if iv_skew is not None else None,
                "call_open_interest": call_oi,
                "put_open_interest": put_oi,
                "call_volume": call_volume,
                "put_volume": put_volume,
            }
        )
        return result
    except Exception as e:
        logger.info("[Options] get_option_chain_metrics failed: %s", type(e).__name__)
        result["error"] = f"fetch_failed:{e.__class__.__name__}"
        return result



def analyze_historical_drawdowns(ticker: str = "^IXIC") -> str:
    """Summarize the largest drawdowns over the available history."""
    hist = pd.DataFrame()
    error_note = ""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="max")
    except Exception as e:
        error_note = type(e).__name__

    if hist is None or hist.empty:
        try:
            fallback = get_stock_historical_data(ticker, period="max", interval="1d")
            kline = fallback.get("kline_data") if isinstance(fallback, dict) else None
            if kline:
                df = pd.DataFrame(kline)
                df['time'] = pd.to_datetime(df['time'], errors='coerce')
                df = df.dropna(subset=['time']).sort_values('time')
                if not df.empty:
                    df = df.rename(columns={'close': 'Close'})
                    hist = df.set_index('time')
        except Exception as fb_e:
            fallback_error = type(fb_e).__name__
            error_note = f"{error_note}; fallback failed: {fallback_error}" if error_note else fallback_error

    if hist is None or hist.empty or 'Close' not in hist.columns:
        return f"No historical data available for {ticker}." + (f" ({error_note})" if error_note else "")

    try:
        hist.index = hist.index.tz_localize(None)
    except Exception:
        pass

    start_date = hist.index.min()
    end_date = hist.index.max()
    coverage_years = (end_date - start_date).days / 365.25 if start_date and end_date else 0
    coverage_text = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} (~{coverage_years:.1f}y)"

    hist = hist.copy()
    hist['peak'] = hist['Close'].cummax()
    hist['drawdown'] = (hist['Close'] - hist['peak']) / hist['peak']

    drawdown_groups = hist[hist['drawdown'] < 0]
    if drawdown_groups.empty:
        return f"No significant drawdowns found for {ticker}. Coverage: {coverage_text}."

    troughs = drawdown_groups.loc[drawdown_groups.groupby((drawdown_groups['drawdown'] == 0).cumsum())['drawdown'].idxmin()]
    top_3 = troughs.nsmallest(3, 'drawdown')
    if top_3.empty:
        return f"No significant drawdowns found for {ticker}. Coverage: {coverage_text}."

    result = [f"Top 3 Historical Drawdowns for {ticker} (coverage {coverage_text}):\n"]
    for _, row in top_3.iterrows():
        trough_date = row.name
        peak_price = row['peak']
        peak_date = hist[(hist.index <= trough_date) & (hist['Close'] == peak_price)].index.max()
        recovery_df = hist[hist.index > trough_date]
        recovery_date_series = recovery_df[recovery_df['Close'] >= peak_price].index
        recovery_date = recovery_date_series[0] if not recovery_date_series.empty else None

        duration = (trough_date - peak_date).days if peak_date is not None else 0
        recovery_days = (recovery_date - trough_date).days if recovery_date is not None else "Ongoing"
        result.append(
            f"- Drawdown: {row['drawdown']:.2%} (from {peak_date.strftime('%Y-%m-%d')} to {trough_date.strftime('%Y-%m-%d')})\n"
            f"  Duration to trough: {duration} days. Recovery time: {recovery_days} days."
        )

    return "\n".join(result)
