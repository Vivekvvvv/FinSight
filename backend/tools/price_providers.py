# -*- coding: utf-8 -*-
"""Live price provider adapters (multi-source fallback chain) extracted from price.py."""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from urllib.parse import quote

import yfinance as yf
from bs4 import BeautifulSoup

from .env import ALPHA_VANTAGE_API_KEY, TWELVE_DATA_API_KEY, finnhub_client
from .http import _http_get
from .search import search
from backend.tools.price_history_providers import (
    _fallback_price_value,
    _map_to_stooq_symbol,
    _safe_float_value,
)

logger = logging.getLogger(__name__)


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
