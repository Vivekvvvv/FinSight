import json
import logging
import os
import time
from datetime import datetime
from typing import Optional, List, Dict, Any, Union

import pandas as pd
import requests
import yfinance as yf

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
    get_stock_historical_data,
)

from backend.tools.price_portfolio import (
    _normalize_positions,
    _download_close_frame,
    _compute_beta,
    get_factor_exposure,
    run_portfolio_stress_test,
    get_performance_comparison,
)

from backend.tools.price_providers import (
    _fetch_with_alpha_vantage,
    _fetch_with_finnhub,
    _fetch_with_yfinance,
    _fetch_with_twelve_data_price,
    _fetch_yahoo_api_v8,
    _scrape_google_finance,
    _scrape_cnbc,
    _fetch_with_pandas_datareader,
    _scrape_yahoo_finance,
    _fetch_index_price,
    _search_for_price,
    _fetch_with_stooq_price,
    _to_yahoo_cn_symbol,
)


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
