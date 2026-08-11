"""Portfolio analytics helpers extracted from price.py."""

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import yfinance as yf

from backend.tools.price_history_providers import _safe_float_value
from backend.utils.quote import safe_float


def _normalize_positions(positions: Any) -> List[Dict[str, Any]]:
    parsed: List[Dict[str, Any]] = []
    if not isinstance(positions, list):
        return parsed

    for item in positions:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker") or item.get("symbol") or "").strip().upper()
        if not ticker:
            continue
        weight = _safe_float_value(item.get("weight"))
        quantity = _safe_float_value(item.get("quantity"))
        parsed.append({"ticker": ticker, "weight": weight, "quantity": quantity})

    if not parsed:
        return []

    weight_sum = sum((entry["weight"] or 0.0) for entry in parsed if entry["weight"] is not None)
    if weight_sum > 0:
        for entry in parsed:
            raw_weight = entry["weight"] or 0.0
            entry["weight"] = float(raw_weight / weight_sum)
        return parsed

    qty_sum = sum(abs(entry["quantity"] or 0.0) for entry in parsed if entry["quantity"] is not None)
    if qty_sum > 0:
        for entry in parsed:
            raw_qty = abs(entry["quantity"] or 0.0)
            entry["weight"] = float(raw_qty / qty_sum)
        return parsed

    equal_weight = 1.0 / float(len(parsed))
    for entry in parsed:
        entry["weight"] = equal_weight
    return parsed

def _download_close_frame(symbols: List[str], lookback_days: int) -> Optional[pd.DataFrame]:
    if not symbols:
        return None
    period_days = max(lookback_days, 30)
    period = f"{period_days}d"

    try:
        raw = yf.download(
            tickers=symbols if len(symbols) > 1 else symbols[0],
            period=period,
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=False,
        )
    except Exception:
        return None

    if raw is None or getattr(raw, "empty", True):
        return None

    try:
        if isinstance(raw.columns, pd.MultiIndex):
            level0 = set(raw.columns.get_level_values(0))
            if "Close" in level0:
                close_df = raw["Close"].copy()
            elif "Adj Close" in level0:
                close_df = raw["Adj Close"].copy()
            else:
                return None
            if isinstance(close_df, pd.Series):
                close_df = close_df.to_frame(name=symbols[0])
            return close_df.dropna(how="all")

        if "Close" in raw.columns:
            return raw[["Close"]].rename(columns={"Close": symbols[0]}).dropna(how="all")
        if "Adj Close" in raw.columns:
            return raw[["Adj Close"]].rename(columns={"Adj Close": symbols[0]}).dropna(how="all")
    except Exception:
        return None
    return None

def _compute_beta(portfolio_returns: pd.Series, factor_returns: pd.Series) -> Optional[float]:
    joined = pd.concat([portfolio_returns, factor_returns], axis=1).dropna()
    if joined.empty or len(joined) < 20:
        return None
    p = joined.iloc[:, 0]
    f = joined.iloc[:, 1]
    variance = f.var()
    if variance is None or variance <= 1e-12:
        return None
    covariance = p.cov(f)
    if covariance is None:
        return None
    return float(covariance / variance)

def get_factor_exposure(positions: Any, lookback_days: int = 252) -> Dict[str, Any]:
    """Estimate simple portfolio factor beta exposures from free yfinance history."""
    normalized = _normalize_positions(positions)
    result: Dict[str, Any] = {
        "source": "yfinance_factor_model",
        "as_of": datetime.now().isoformat(),
        "lookback_days": int(lookback_days),
        "positions": normalized,
        "factor_beta": {},
        "annualized_volatility": None,
        "max_drawdown": None,
        "market_r2": None,
        "observation_count": 0,
        "error": None,
    }
    if not normalized:
        result["error"] = "positions_required"
        return result

    factor_map = {
        "market": "SPY",
        "growth": "QQQ",
        "small_cap": "IWM",
        "rates": "TLT",
        "gold": "GLD",
        "usd": "UUP",
    }

    portfolio_symbols = [item["ticker"] for item in normalized]
    all_symbols = list(dict.fromkeys(portfolio_symbols + list(factor_map.values())))
    close_df = _download_close_frame(all_symbols, lookback_days=lookback_days)
    if close_df is None or close_df.empty:
        result["error"] = "historical_data_unavailable"
        return result

    returns = close_df.pct_change().dropna(how="all")
    if returns.empty:
        result["error"] = "insufficient_returns_data"
        return result

    available_symbols = [sym for sym in portfolio_symbols if sym in returns.columns]
    if not available_symbols:
        result["error"] = "portfolio_symbols_missing_in_history"
        return result

    weighted_series: List[pd.Series] = []
    for position in normalized:
        symbol = position["ticker"]
        if symbol not in returns.columns:
            continue
        weight = safe_float(position.get("weight")) or 0.0
        weighted_series.append(returns[symbol] * weight)

    if not weighted_series:
        result["error"] = "portfolio_returns_unavailable"
        return result

    portfolio_returns = sum(weighted_series)
    portfolio_returns = portfolio_returns.dropna()
    if portfolio_returns.empty:
        result["error"] = "portfolio_returns_empty"
        return result

    factor_beta: Dict[str, Optional[float]] = {}
    for factor_name, factor_symbol in factor_map.items():
        if factor_symbol not in returns.columns:
            factor_beta[factor_name] = None
            continue
        beta = _compute_beta(portfolio_returns, returns[factor_symbol])
        factor_beta[factor_name] = round(beta, 4) if beta is not None else None

    ann_vol = float(portfolio_returns.std() * (252 ** 0.5))
    cumulative = (1.0 + portfolio_returns).cumprod()
    drawdown_series = cumulative / cumulative.cummax() - 1.0
    max_drawdown = float(drawdown_series.min()) if not drawdown_series.empty else None

    market_symbol = factor_map["market"]
    market_r2 = None
    if market_symbol in returns.columns:
        joined = pd.concat([portfolio_returns, returns[market_symbol]], axis=1).dropna()
        if len(joined) >= 20:
            corr = joined.iloc[:, 0].corr(joined.iloc[:, 1])
            if corr is not None:
                market_r2 = float(corr ** 2)

    result.update(
        {
            "factor_beta": factor_beta,
            "annualized_volatility": round(ann_vol, 4),
            "max_drawdown": round(max_drawdown, 4) if max_drawdown is not None else None,
            "market_r2": round(market_r2, 4) if market_r2 is not None else None,
            "observation_count": int(len(portfolio_returns)),
        }
    )
    return result

def run_portfolio_stress_test(
    positions: Any,
    scenarios: Optional[Dict[str, Dict[str, float]]] = None,
    lookback_days: int = 252,
) -> Dict[str, Any]:
    """Run lightweight factor-based stress tests (free, no paid risk engine)."""
    factor_payload = get_factor_exposure(positions, lookback_days=lookback_days)
    result: Dict[str, Any] = {
        "source": "factor_stress_model",
        "as_of": datetime.now().isoformat(),
        "lookback_days": int(lookback_days),
        "factor_exposure": factor_payload,
        "scenarios": [],
        "worst_case_return": None,
        "error": None,
    }
    if factor_payload.get("error"):
        result["error"] = f"factor_exposure_error:{factor_payload.get('error')}"
        return result

    factor_beta = factor_payload.get("factor_beta")
    if not isinstance(factor_beta, dict):
        result["error"] = "missing_factor_beta"
        return result

    scenario_map = scenarios or {
        "equity_selloff": {
            "market": -0.10,
            "growth": -0.14,
            "small_cap": -0.16,
            "rates": 0.04,
            "gold": 0.02,
            "usd": 0.02,
        },
        "rate_shock_up": {
            "market": -0.04,
            "growth": -0.08,
            "small_cap": -0.06,
            "rates": -0.09,
            "gold": -0.03,
            "usd": 0.03,
        },
        "volatility_spike": {
            "market": -0.06,
            "growth": -0.09,
            "small_cap": -0.10,
            "rates": 0.03,
            "gold": 0.01,
            "usd": 0.01,
        },
    }

    annualized_vol = _safe_float_value(factor_payload.get("annualized_volatility")) or 0.0
    scenarios_out: List[Dict[str, Any]] = []
    for scenario_name, shocks in scenario_map.items():
        if not isinstance(shocks, dict):
            continue
        projected_return = 0.0
        used_factors: Dict[str, float] = {}
        for factor_name, shock in shocks.items():
            beta = _safe_float_value(factor_beta.get(factor_name))
            shock_value = _safe_float_value(shock)
            if beta is None or shock_value is None:
                continue
            used_factors[factor_name] = round(beta * shock_value, 4)
            projected_return += beta * shock_value

        if "volatility" in scenario_name.lower():
            projected_return -= 0.25 * annualized_vol
        elif projected_return < 0:
            projected_return -= 0.10 * annualized_vol
        else:
            projected_return -= 0.05 * annualized_vol

        projected_drawdown = min(0.0, projected_return * 1.2)
        scenarios_out.append(
            {
                "name": scenario_name,
                "projected_return": round(float(projected_return), 4),
                "projected_drawdown": round(float(projected_drawdown), 4),
                "factor_contribution": used_factors,
            }
        )

    if not scenarios_out:
        result["error"] = "no_valid_scenarios"
        return result

    worst_case = min(item["projected_return"] for item in scenarios_out)
    result.update(
        {
            "scenarios": sorted(scenarios_out, key=lambda item: item["projected_return"]),
            "worst_case_return": round(float(worst_case), 4),
        }
    )
    return result

def get_performance_comparison(tickers: Union[dict, list]) -> str:
    """Compare YTD and 1-Year performance for a labeled ticker map.

    Args:
        tickers: 支持两种格式:
            - dict: {"Apple": "AAPL", "Tesla": "TSLA"}
            - list: ["AAPL", "TSLA"]
    """
    # 兼容 list 输入：将 list 转换为 dict 格式
    from backend.tools.price import get_stock_historical_data  # noqa: PLC0415 (avoid import cycle)

    if isinstance(tickers, list):
        tickers = {t: t for t in tickers}

    data: Dict[str, Dict[str, str]] = {}
    notes: List[str] = []
    now = datetime.now()

    def _calc_from_hist(hist: pd.DataFrame):
        if hist is None or hist.empty or 'Close' not in hist.columns:
            return None
        hist = hist.copy()
        try:
            hist.index = hist.index.tz_localize(None)
        except Exception:
            pass
        end_price = _safe_float_value(hist['Close'].iloc[-1])
        if end_price is None or end_price <= 0:
            return None
        start_of_year = datetime(now.year, 1, 1)
        ytd_hist = hist[hist.index >= start_of_year]
        perf_ytd = None
        if not ytd_hist.empty:
            start_price_ytd = _safe_float_value(ytd_hist['Close'].iloc[0])
            if start_price_ytd is not None and start_price_ytd > 0:
                perf_ytd = ((end_price - start_price_ytd) / start_price_ytd) * 100
        one_year_ago = now - timedelta(days=365)
        one_year_hist = hist[hist.index >= one_year_ago]
        perf_1y = None
        if not one_year_hist.empty:
            start_price_1y = _safe_float_value(one_year_hist['Close'].iloc[0])
            if start_price_1y is not None and start_price_1y > 0:
                perf_1y = ((end_price - start_price_1y) / start_price_1y) * 100
        coverage_start = hist.index.min() if not hist.empty else None
        return end_price, perf_ytd, perf_1y, coverage_start

    def _calc_from_kline(kline_data: List[Dict[str, Any]]):
        if not kline_data:
            return None
        df = pd.DataFrame(kline_data)
        if 'time' not in df.columns or 'close' not in df.columns:
            return None
        df['time'] = pd.to_datetime(df['time'], errors='coerce')
        df = df.dropna(subset=['time']).sort_values('time')
        if df.empty:
            return None
        end_price = _safe_float_value(df['close'].iloc[-1])
        if end_price is None or end_price <= 0:
            return None
        start_of_year = datetime(now.year, 1, 1)
        ytd_df = df[df['time'] >= start_of_year]
        perf_ytd = None
        if not ytd_df.empty:
            start_price_ytd = _safe_float_value(ytd_df['close'].iloc[0])
            if start_price_ytd is not None and start_price_ytd > 0:
                perf_ytd = ((end_price - start_price_ytd) / start_price_ytd) * 100
        one_year_ago = now - timedelta(days=365)
        one_year_df = df[df['time'] >= one_year_ago]
        perf_1y = None
        if not one_year_df.empty:
            start_price_1y = _safe_float_value(one_year_df['close'].iloc[0])
            if start_price_1y is not None and start_price_1y > 0:
                perf_1y = ((end_price - start_price_1y) / start_price_1y) * 100
        coverage_start = df['time'].iloc[0]
        return end_price, perf_ytd, perf_1y, coverage_start

    for name, ticker in tickers.items():
        time.sleep(0.3)
        perf = None
        fallback_used = False
        error_note = ""
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2y")
            perf = _calc_from_hist(hist)
            if perf is None:
                error_note = "yfinance returned empty data"
                raise ValueError(error_note)
        except Exception as e:
            error_note = type(e).__name__
            try:
                fallback = get_stock_historical_data(ticker, period="2y", interval="1d")
                kline = fallback.get("kline_data") if isinstance(fallback, dict) else None
                perf = _calc_from_kline(kline or [])
                fallback_used = perf is not None
                if not perf and isinstance(fallback, dict) and fallback.get("error"):
                    error_note = fallback.get("error")
            except Exception as fb_e:
                error_note = f"{error_note}; fallback failed: {type(fb_e).__name__}"

        if not perf:
            data[name] = {"Current": "N/A", "YTD": "N/A", "1-Year": "N/A"}
            notes.append(f"{name}: data unavailable ({error_note})")
            continue

        end_price, perf_ytd, perf_1y, coverage_start = perf
        data[name] = {
            "Current": f"{end_price:,.2f}",
            "YTD": f"{perf_ytd:+.2f}%" if perf_ytd is not None else "N/A",
            "1-Year": f"{perf_1y:+.2f}%" if perf_1y is not None else "N/A",
        }
        missing = []
        if perf_ytd is None:
            missing.append("YTD")
        if perf_1y is None:
            missing.append("1-Year")
        if missing and coverage_start is not None:
            notes.append(f"{name}: limited history from {coverage_start:%Y-%m-%d} (missing {', '.join(missing)})")
        if fallback_used:
            notes.append(f"{name}: used fallback price history")

    if not data:
        return "Unable to fetch performance data for any ticker."

    header = f"{'Ticker':<25} {'Current Price':<15} {'YTD %':<12} {'1-Year %':<12}\n" + "-" * 67 + "\n"
    rows = [
        f"{name:<25} {metrics['Current']:<15} {metrics['YTD']:<12} {metrics['1-Year']:<12}"
        for name, metrics in data.items()
    ]
    note_text = f"\n\nNotes:\n- " + "\n- ".join(notes) if notes else ""
    return "Performance Comparison:\n\n" + header + "\n".join(rows) + note_text
