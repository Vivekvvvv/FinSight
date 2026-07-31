from __future__ import annotations

import ast
import json
import importlib
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest


_ROOT = Path(__file__).resolve().parents[2]


NUMERIC_BOUNDARY_ROUNDS = [
    ("R301", "backend/tools/price.py", '"close": _safe_float_value(item.get(\'close\'))'),
    ("R322", "backend/agents/technical_agent.py", "parsed_close = safe_float(close)"),
    ("R323", "backend/langchain_tools.py", "parsed_close = safe_float(close)"),
    ("R324", "backend/tools/financial.py", "row[col] = safe_float(value)"),
    ("R325", "backend/tools/financial.py", "item[str(column)] = safe_float(value)"),
    ("R326", "backend/tools/financial.py", "result[key_text] = safe_float(value)"),
    ("R327", "backend/tools/financial.py", "up_7 = safe_float(row.get(\"upLast7days\"))"),
    ("R328", "backend/tools/financial.py", "up_30 = safe_float(row.get(\"upLast30days\"))"),
    ("R329", "backend/tools/financial.py", "down_7 = safe_float(row.get(\"downLast7Days\"))"),
    ("R330", "backend/tools/financial.py", "down_30 = safe_float(row.get(\"downLast30days\"))"),
    ("R331", "backend/tools/macro.py", "score = safe_float(data['fear_and_greed']['score'])"),
    ("R332", "backend/tools/macro.py", "score = safe_float(match.group(1))"),
    ("R333", "backend/tools/macro.py", '"cpi": "CPIAUCSL"'),
    ("R334", "backend/tools/macro.py", '"fed_rate": "FEDFUNDS"'),
    ("R335", "backend/tools/macro.py", '"gdp_growth": "A191RL1Q225SBEA"'),
    ("R336", "backend/tools/macro.py", '"unemployment": "UNRATE"'),
    ("R337", "backend/tools/macro.py", '"treasury_10y": "DGS10"'),
    ("R338", "backend/tools/macro.py", '"yield_spread": "T10Y2Y"'),
    ("R339", "backend/dashboard/insights_scorer.py", '_finite_number(_safe_get(data, "ma20"))'),
    ("R340", "backend/dashboard/insights_scorer.py", '_finite_number(_safe_get(data, "ma50"))'),
    ("R341", "backend/dashboard/insights_scorer.py", '_finite_number(_safe_get(data, "macd"))'),
    ("R342", "backend/dashboard/insights_scorer.py", '_finite_number(_safe_get(data, "macd_signal"))'),
    ("R343", "backend/dashboard/insights_scorer.py", '_safe_get(data, "net_income")'),
    ("R344", "backend/dashboard/insights_scorer.py", '_safe_get(data, "free_cash_flow")'),
    ("R345", "backend/dashboard/insights_scorer.py", '_finite_number(_safe_get(company, "revenue_growth"))'),
    ("R346", "backend/dashboard/insights_scorer.py", '_finite_number(p.get("revenue_growth"))'),
    ("R347", "backend/dashboard/insights_scorer.py", '_finite_number(_safe_get(company, "profit_margin"))'),
    ("R348", "backend/dashboard/insights_scorer.py", '_finite_number(p.get("profit_margin"))'),
    ("R349", "backend/dashboard/insights_scorer.py", "tech_score = _finite_number(tech_score)"),
    ("R350", "backend/dashboard/insights_scorer.py", "fin_score = _finite_number(fin_score)"),
    ("R351", "backend/dashboard/insights_scorer.py", "news_score = _finite_number(news_score)"),
    ("R352", "backend/dashboard/insights_scorer.py", "peers_score = _finite_number(peers_score)"),
    ("R353", "backend/dashboard/insights_scorer.py", '_finite_number(_safe_get(company, "trailing_pe"))'),
    ("R354", "backend/dashboard/insights_scorer.py", '_finite_number(p.get("trailing_pe"))'),
    ("R355", "backend/dashboard/insights_scorer.py", 'company_growth = _finite_number(_safe_get(company, "revenue_growth"))'),
    ("R356", "backend/dashboard/insights_scorer.py", '_finite_number(p.get("revenue_growth"))'),
    ("R357", "backend/tools/screener.py", 'price = _clean_float(row.get("price"))'),
    ("R358", "backend/tools/screener.py", '"market_cap": _clean_float(row.get("marketCap"))'),
    ("R359", "backend/tools/screener.py", 'volume = _clean_float(row.get("volume"))'),
    ("R360", "backend/tools/screener.py", '"beta": _clean_float(row.get("beta"))'),
    ("R361", "backend/tools/screener.py", '"dividend": _clean_float(row.get("lastAnnualDividend"))'),
    ("R362", "backend/tools/screener.py", '"change_percent": _clean_float(row.get("changesPercentage"))'),
    ("R363", "backend/tools/screener.py", 'previous_close = _clean_float(_get_fast_info_value'),
    ("R364", "backend/tools/screener.py", 'expires_at = _clean_float(_ALPHA_TOP_MOVERS_CACHE.get("expires_at"))'),
    ("R365", "backend/tools/price.py", 'spot_price = _safe_float_value(hist["Close"].iloc[-1])'),
    ("R366", "backend/tools/price.py", 'spot_price = _safe_float_value(info.get("regularMarketPrice"))'),
    ("R367", "backend/tools/price.py", 'weight = _safe_float_value(item.get("weight"))'),
    ("R368", "backend/tools/price.py", 'quantity = _safe_float_value(item.get("quantity"))'),
    ("R369", "backend/tools/price.py", 'value = _safe_float_value(subset.loc[idx, "impliedVolatility"])'),
    ("R370", "backend/tools/price.py", "return _safe_float_value(close)"),
    ("R371", "backend/tools/price.py", 'val = _safe_float_value(m.group(1).replace(",", ""))'),
    ("R372", "backend/tools/price.py", '"open": _safe_float_value(item.get(\'open\'))'),
    ("R373", "backend/tools/price.py", '"high": _safe_float_value(item.get(\'high\'))'),
    ("R374", "backend/tools/price.py", '"low": _safe_float_value(item.get(\'low\'))'),
    ("R375", "backend/tools/price.py", '"close": _safe_float_value(item.get(\'close\'))'),
    ("R376", "backend/tools/price.py", '"volume": _safe_float_value(item.get(\'volume\'))'),
    ("R377", "backend/tools/price.py", '"open": _safe_float_value(day_data["1. open"])'),
    ("R378", "backend/tools/price.py", '"high": _safe_float_value(day_data["2. high"])'),
    ("R379", "backend/tools/price.py", '"low": _safe_float_value(day_data["3. low"])'),
    ("R380", "backend/tools/price.py", '"close": _safe_float_value(day_data["4. close"])'),
    ("R381", "backend/tools/price.py", '"volume": _safe_float_value(day_data.get("5. volume"))'),
    ("R382", "backend/tools/price.py", "close_val = _safe_float_value(row[close_key])"),
    ("R383", "backend/tools/price.py", '"open": _safe_float_value(row[open_key])'),
    ("R384", "backend/tools/price.py", '"high": _safe_float_value(row[high_key])'),
    ("R385", "backend/tools/price.py", '"low": _safe_float_value(row[low_key])'),
    ("R386", "backend/tools/price.py", '"volume": _safe_float_value(row.get(volume_key))'),
    ("R387", "backend/dashboard/data_service.py", "parsed = safe_float(value)"),
    ("R388", "backend/dashboard/data_service.py", "parsed_half_life = safe_float(half_life_hours)"),
    ("R389", "backend/api/market_router.py", "confidence = safe_float(confidence_raw) or 0.0"),
    ("R390", "backend/agents/risk_agent.py", "safe_float(signal.severity) or 0.0"),
    ("R391", "backend/agents/price_agent.py", "pct = safe_float(change_pct)"),
    ("R392", "backend/agents/price_agent.py", 'iv_atm = safe_float(option_metrics.get("iv_atm"))'),
    ("R393", "backend/agents/price_agent.py", 'pcr = safe_float(option_metrics.get("put_call_ratio_oi")'),
    ("R394", "backend/agents/price_agent.py", 'skew = safe_float(option_metrics.get("iv_skew_25d"))'),
    ("R395", "backend/agents/price_agent.py", 'if iv_atm is not None:'),
    ("R396", "backend/agents/price_agent.py", 'if pcr is not None:'),
    ("R397", "backend/agents/price_agent.py", 'if skew is not None:'),
    ("R398", "backend/graph/nodes/alert_action.py", "price_target = safe_float(price_target)"),
    ("R399", "backend/graph/nodes/alert_action.py", "current_price = safe_float(snap.price if snap is not None else None)"),
    ("R400", "backend/tools/sec.py", "number = safe_float(val)"),
]


# Each tuple binds one R401-R500 fix to a concrete function and source expression.
NUMERIC_BOUNDARY_ROUNDS_401_500 = [
    ("R401", "backend/tools/price.py", "_fetch_with_alpha_vantage", "price = _safe_float_value(quote.get('05. price'))", 1),
    ("R402", "backend/tools/price.py", "_fetch_with_alpha_vantage", "change = _safe_float_value(quote.get('09. change'))", 1),
    ("R403", "backend/tools/price.py", "_fetch_with_alpha_vantage", "change_percent = _safe_float_value(change_percent_str)", 1),
    ("R404", "backend/tools/price.py", "_fetch_with_twelve_data_price", 'price = _safe_float_value(latest.get("close"))', 1),
    ("R405", "backend/tools/price.py", "_fetch_with_twelve_data_price", 'prev_close = _safe_float_value(values[1]["close"])', 1),
    ("R406", "backend/tools/price.py", "_fetch_with_yahoo_scrape_historical", '"open": _safe_float_value(row[\'Open\'])', 1),
    ("R407", "backend/tools/price.py", "_fetch_with_yahoo_scrape_historical", '"high": _safe_float_value(row[\'High\'])', 1),
    ("R408", "backend/tools/price.py", "_fetch_with_yahoo_scrape_historical", '"low": _safe_float_value(row[\'Low\'])', 1),
    ("R409", "backend/tools/price.py", "_fetch_with_yahoo_scrape_historical", '"close": _safe_float_value(row[\'Close\'])', 1),
    ("R410", "backend/tools/price.py", "_fetch_with_yahoo_scrape_historical", '"volume": _safe_float_value(row.get(\'Volume\'))', 1),
    ("R411", "backend/tools/price.py", "_fetch_with_tiingo", '"open": _safe_float_value(item.get(\'open\'))', 1),
    ("R412", "backend/tools/price.py", "_fetch_with_tiingo", '"high": _safe_float_value(item.get(\'high\'))', 1),
    ("R413", "backend/tools/price.py", "_fetch_with_tiingo", '"low": _safe_float_value(item.get(\'low\'))', 1),
    ("R414", "backend/tools/price.py", "_fetch_with_tiingo", '"volume": _safe_float_value(item.get(\'volume\'))', 1),
    ("R415", "backend/tools/price.py", "_fetch_with_twelve_data", '"open": _safe_float_value(item.get("open"))', 1),
    ("R416", "backend/tools/price.py", "_fetch_with_twelve_data", '"high": _safe_float_value(item.get("high"))', 1),
    ("R417", "backend/tools/price.py", "_fetch_with_twelve_data", '"low": _safe_float_value(item.get("low"))', 1),
    ("R418", "backend/tools/price.py", "_fetch_with_twelve_data", '"close": _safe_float_value(item.get("close"))', 1),
    ("R419", "backend/tools/price.py", "_fetch_with_twelve_data", '"volume": _safe_float_value(item.get("volume"))', 1),
    ("R420", "backend/tools/price.py", "_fetch_with_marketstack", '"open": _safe_float_value(item.get(\'open\'))', 1),
    ("R421", "backend/tools/price.py", "_fetch_with_marketstack", '"high": _safe_float_value(item.get(\'high\'))', 1),
    ("R422", "backend/tools/price.py", "_fetch_with_marketstack", '"low": _safe_float_value(item.get(\'low\'))', 1),
    ("R423", "backend/tools/price.py", "_fetch_with_marketstack", '"close": _safe_float_value(item.get(\'close\'))', 1),
    ("R424", "backend/tools/price.py", "_fetch_with_marketstack", '"volume": _safe_float_value(item.get(\'volume\'))', 1),
    ("R425", "backend/tools/price.py", "_fetch_with_massive_io", '"open": _safe_float_value(item.get(\'o\'))', 1),
    ("R426", "backend/tools/price.py", "_fetch_with_massive_io", '"high": _safe_float_value(item.get(\'h\'))', 1),
    ("R427", "backend/tools/price.py", "_fetch_with_massive_io", '"low": _safe_float_value(item.get(\'l\'))', 1),
    ("R428", "backend/tools/price.py", "_fetch_with_massive_io", '"close": _safe_float_value(item.get(\'c\'))', 1),
    ("R429", "backend/tools/price.py", "_fetch_with_massive_io", '"volume": _safe_float_value(item.get(\'v\'))', 1),
    ("R430", "backend/tools/price.py", "get_stock_historical_data", '"open": _safe_float_value(row[\'Open\'])', 1),
    ("R431", "backend/tools/price.py", "get_stock_historical_data", '"high": _safe_float_value(row[\'High\'])', 1),
    ("R432", "backend/tools/price.py", "get_stock_historical_data", '"low": _safe_float_value(row[\'Low\'])', 1),
    ("R433", "backend/tools/price.py", "get_stock_historical_data", '"close": _safe_float_value(row[\'Close\'])', 1),
    ("R434", "backend/tools/price.py", "get_stock_historical_data", '"volume": _safe_float_value(row.get(\'Volume\'))', 1),
    ("R435", "backend/tools/price.py", "get_stock_historical_data", '"open": _safe_float_value(res[\'o\'][i])', 1),
    ("R436", "backend/tools/price.py", "get_stock_historical_data", '"high": _safe_float_value(res[\'h\'][i])', 1),
    ("R437", "backend/tools/price.py", "get_stock_historical_data", '"low": _safe_float_value(res[\'l\'][i])', 1),
    ("R438", "backend/tools/price.py", "get_stock_historical_data", '"close": _safe_float_value(res[\'c\'][i])', 1),
    ("R439", "backend/tools/price.py", "get_stock_historical_data", '"volume": _safe_float_value(res.get(\'v\'', 1),
    ("R440", "backend/tools/price.py", "get_stock_historical_data", '"open": _safe_float_value(row[\'Open\'])', 2),
    ("R441", "backend/tools/price.py", "get_stock_historical_data", '"high": _safe_float_value(row[\'High\'])', 2),
    ("R442", "backend/tools/price.py", "get_stock_historical_data", '"low": _safe_float_value(row[\'Low\'])', 2),
    ("R443", "backend/tools/price.py", "get_stock_historical_data", '"close": _safe_float_value(row[\'Close\'])', 2),
    ("R444", "backend/tools/price.py", "get_stock_historical_data", '"volume": _safe_float_value(row.get(\'Volume\'))', 2),
    ("R445", "backend/tools/price.py", "get_stock_historical_data", '"open": _safe_float_value(row[\'Open\'])', 3),
    ("R446", "backend/tools/price.py", "get_stock_historical_data", '"high": _safe_float_value(row[\'High\'])', 3),
    ("R447", "backend/tools/price.py", "get_stock_historical_data", '"low": _safe_float_value(row[\'Low\'])', 3),
    ("R448", "backend/tools/price.py", "get_stock_historical_data", '"close": _safe_float_value(row[\'Close\'])', 3),
    ("R449", "backend/tools/price.py", "get_stock_historical_data", '"volume": _safe_float_value(row.get(\'Volume\'))', 3),
    ("R450", "backend/tools/screener.py", "_alpha_vantage_screen_stocks", '_clean_float(active_filters.get("priceMoreThan"))', 1),
    ("R451", "backend/tools/screener.py", "_alpha_vantage_screen_stocks", '_clean_float(active_filters.get("priceLowerThan"))', 1),
    ("R452", "backend/tools/screener.py", "_alpha_vantage_screen_stocks", '_clean_float(active_filters.get("volumeMoreThan"))', 1),
    ("R453", "backend/tools/screener.py", "_yfinance_popular_stocks", '_clean_float(filters.get("priceMoreThan"))', 1),
    ("R454", "backend/tools/screener.py", "_yfinance_popular_stocks", '_clean_float(filters.get("priceLowerThan"))', 1),
    ("R455", "backend/tools/screener.py", "_yfinance_popular_stocks", '_clean_float(filters.get("marketCapMoreThan"))', 1),
    ("R456", "backend/tools/screener.py", "_yfinance_popular_stocks", '_clean_float(filters.get("marketCapLowerThan"))', 1),
    ("R457", "backend/tools/screener.py", "_yfinance_popular_stocks", '_clean_float(filters.get("volumeMoreThan"))', 1),
    ("R458", "backend/tools/screener.py", "_passes_screener_filters", '_clean_float(active.get("priceMoreThan"))', 1),
    ("R459", "backend/tools/screener.py", "_passes_screener_filters", '_clean_float(active.get("priceLowerThan"))', 1),
    ("R460", "backend/tools/screener.py", "_passes_screener_filters", '_clean_float(active.get("marketCapMoreThan"))', 1),
    ("R461", "backend/tools/screener.py", "_passes_screener_filters", '_clean_float(active.get("marketCapLowerThan"))', 1),
    ("R462", "backend/tools/screener.py", "_passes_screener_filters", '_clean_float(active.get("volumeMoreThan"))', 1),
    ("R463", "backend/tools/screener.py", "_static_fallback_items", '_clean_float(active_filters.get("priceMoreThan"))', 1),
    ("R464", "backend/tools/screener.py", "_static_fallback_items", '_clean_float(active_filters.get("priceLowerThan"))', 1),
    ("R465", "backend/tools/screener.py", "_static_fallback_items", '_clean_float(active_filters.get("marketCapMoreThan"))', 1),
    ("R466", "backend/tools/screener.py", "_static_fallback_items", '_clean_float(active_filters.get("marketCapLowerThan"))', 1),
    ("R467", "backend/tools/screener.py", "_static_fallback_items", '_clean_float(active_filters.get("volumeMoreThan"))', 1),
    ("R468", "backend/services/historical_data_store.py", "_fetch_baostock", "safe_float(row[1])", 1),
    ("R469", "backend/services/historical_data_store.py", "_fetch_baostock", "safe_float(row[2])", 1),
    ("R470", "backend/services/historical_data_store.py", "_fetch_baostock", "safe_float(row[3])", 1),
    ("R471", "backend/services/historical_data_store.py", "_fetch_baostock", "safe_float(row[4])", 1),
    ("R472", "backend/services/historical_data_store.py", "_fetch_baostock", "safe_float(row[5])", 1),
    ("R473", "backend/services/historical_data_store.py", "_clean", 'safe_float(row.get("close"))', 1),
    ("R474", "backend/services/historical_data_store.py", "_clean", '"open"', 1),
    ("R475", "backend/services/historical_data_store.py", "_clean", '"high"', 1),
    ("R476", "backend/services/historical_data_store.py", "_clean", '"low"', 1),
    ("R477", "backend/services/historical_data_store.py", "_clean", 'safe_float(r.get("volume"))', 1),
    ("R478", "backend/tools/price.py", "_fetch_with_finnhub", "_safe_float_value(quote.get('c'))", 1),
    ("R479", "backend/tools/price.py", "_fetch_with_finnhub", "_safe_float_value(quote.get('d'))", 1),
    ("R480", "backend/tools/price.py", "_fetch_with_finnhub", "_safe_float_value(quote.get('dp'))", 1),
    ("R481", "backend/tools/price.py", "_fetch_with_yfinance", "_safe_float_value(hist['Close'].iloc[-1])", 1),
    ("R482", "backend/tools/price.py", "_fetch_with_yfinance", "_safe_float_value(hist['Close'].iloc[-2])", 1),
    ("R483", "backend/tools/price.py", "_fetch_yahoo_api_v8", "_safe_float_value(meta.get('regularMarketPrice'))", 1),
    ("R484", "backend/tools/price.py", "_fetch_yahoo_api_v8", "_safe_float_value(meta.get('previousClose')", 1),
    ("R485", "backend/tools/price.py", "_fetch_with_pandas_datareader", "_safe_float_value(df['Close'].iloc[0])", 1),
    ("R486", "backend/tools/price.py", "_fetch_with_pandas_datareader", "_safe_float_value(df['Close'].iloc[1])", 1),
    ("R487", "backend/tools/price.py", "_scrape_yahoo_finance", "_safe_float_value(price_elem.get('value'))", 1),
    ("R488", "backend/tools/price.py", "_scrape_yahoo_finance", "_safe_float_value(change_elem.get('value'))", 1),
    ("R489", "backend/tools/price.py", "_scrape_yahoo_finance", "_safe_float_value(change_percent_elem.get('value'))", 1),
    ("R490", "backend/tools/price.py", "_fetch_index_price", "_safe_float_value(closes[-1])", 1),
    ("R491", "backend/tools/price.py", "_fetch_index_price", "_safe_float_value(closes[-2])", 1),
    ("R492", "backend/tools/price.py", "_fetch_with_stooq_price", "_safe_float_value(close)", 1),
    ("R493", "backend/tools/price.py", "_calc_from_hist", "_safe_float_value(hist['Close'].iloc[-1])", 1),
    ("R494", "backend/tools/price.py", "_calc_from_hist", "_safe_float_value(ytd_hist['Close'].iloc[0])", 1),
    ("R495", "backend/tools/price.py", "_calc_from_hist", "_safe_float_value(one_year_hist['Close'].iloc[0])", 1),
    ("R496", "backend/tools/price.py", "_calc_from_kline", "_safe_float_value(df['close'].iloc[-1])", 1),
    ("R497", "backend/tools/price.py", "_calc_from_kline", "_safe_float_value(ytd_df['close'].iloc[0])", 1),
    ("R498", "backend/tools/price.py", "_calc_from_kline", "_safe_float_value(one_year_df['close'].iloc[0])", 1),
    ("R499", "backend/dashboard/scorers.py", "_parse_response", 'safe_float(parsed.get("score"))', 1),
    ("R500", "backend/tools/news.py", "get_news_sentiment", "score_val = safe_float(score)", 1),
]


NUMERIC_BOUNDARY_ROUNDS_501_600 = [
    ("R501", "backend/tools/price.py", "get_stock_historical_data", "if configured_fallback:", 1),
    ("R502", "backend/llm_config.py", "_parse_user_endpoints", 'safe_int(raw.get("weight"), 1)', 1),
    ("R503", "backend/llm_config.py", "_parse_user_endpoints", 'safe_int(raw.get("cooldown_sec"), default_cooldown)', 1),
    ("R504", "backend/api/subscription_router.py", "subscribe_email", 'safe_int((entitlements.get("limits") or {}).get("max_alerts"), 0)', 1),
    ("R505", "backend/api/user_router.py", "_watchlist_entitlement", 'safe_int((entitlements.get("limits") or {}).get("max_watchlist"), 0)', 1),
    ("R506", "backend/api/system_router.py", "internal_health_check", 'safe_int(getattr(rag_service, "vector_dim", 0), 0)', 1),
    ("R507", "backend/api/system_router.py", "internal_health_check", "safe_int(rag_service.count_documents(), 0)", 1),
    ("R508", "backend/api/system_router.py", "diagnostics_rag_status", "safe_int(rag_service.count_documents(), 0)", 1),
    ("R509", "backend/api/system_router.py", "diagnostics_rag_status", 'safe_int(getattr(rag_service, "vector_dim", 0), 0)', 1),
    ("R510", "backend/api/system_router.py", "diagnostics_rag_status", 'safe_int(observability.get("recent_run_count_24h"), 0)', 1),
    ("R511", "backend/api/system_router.py", "diagnostics_rag_status", 'safe_int(observability.get("recent_fallback_count_24h"), 0)', 1),
    ("R512", "backend/api/system_router.py", "diagnostics_rag_search_preview", "safe_int(payload.get('top_k', 10))", 1),
    ("R513", "backend/dashboard/data_service.py", "_fetch_financial_statements_from_finnhub", 'safe_int(item.get("year"), 0)', 1),
    ("R514", "backend/dashboard/data_service.py", "_fetch_financial_statements_from_finnhub", 'safe_int(item.get("quarter"), 0)', 1),
    ("R515", "backend/agents/deep_search_agent.py", "_dedupe_results", '_finite_int(merged.get("search_rank"), 10**9)', 1),
    ("R516", "backend/agents/deep_search_agent.py", "_dedupe_results", '_finite_int(item.get("search_rank"), 10**9)', 1),
    ("R517", "backend/report/quality_engine.py", "build_runtime_quality_reasons", 'safe_int(missing_counts.get("critical"), 0)', 1),
    ("R518", "backend/report/quality_engine.py", "build_runtime_quality_reasons", 'safe_int(missing_counts.get("important"), 0)', 1),
    ("R519", "backend/report/quality_engine.py", "build_runtime_quality_reasons", 'safe_int(missing_counts.get("minor"), 0)', 1),
    ("R520", "backend/report/validator.py", "_parse_section", "except (TypeError, ValueError, OverflowError):", 1),
    ("R521", "backend/rag/observability_runtime.py", "start_query_run", "safe_int(record.retrieval_k, 0)", 1),
    ("R522", "backend/rag/observability_runtime.py", "start_query_run", "safe_int(record.rerank_top_n, 0)", 1),
    ("R523", "backend/rag/observability_runtime.py", "start_query_run", "safe_int(record.source_doc_count, 0)", 1),
    ("R524", "backend/rag/observability_runtime.py", "start_query_run", "safe_int(record.chunk_count, 0)", 1),
    ("R525", "backend/rag/observability_runtime.py", "start_query_run", "safe_int(record.retrieval_hit_count, 0)", 1),
    ("R526", "backend/rag/observability_runtime.py", "start_query_run", "safe_int(record.rerank_hit_count, 0)", 1),
    ("R527", "backend/rag/observability_runtime.py", "_sql_health_summary", "safe_int(stats.get('recent_run_count_24h'), 0)", 1),
    ("R528", "backend/rag/observability_runtime.py", "_sql_health_summary", "safe_int(stats.get('recent_empty_hit_runs'), 0)", 1),
    ("R529", "backend/rag/observability_runtime.py", "_sql_health_summary", "safe_int(fallback.get('recent_fallback_count_24h'), 0)", 1),
    ("R530", "backend/rag/observability_store.py", "start_query_run", "safe_int(record.retrieval_k, 0)", 1),
    ("R531", "backend/rag/observability_store.py", "start_query_run", "safe_int(record.rerank_top_n, 0)", 1),
    ("R532", "backend/rag/observability_store.py", "start_query_run", "safe_int(record.source_doc_count, 0)", 1),
    ("R533", "backend/rag/observability_store.py", "start_query_run", "safe_int(record.chunk_count, 0)", 1),
    ("R534", "backend/rag/observability_store.py", "start_query_run", "safe_int(record.retrieval_hit_count, 0)", 1),
    ("R535", "backend/rag/observability_store.py", "start_query_run", "safe_int(record.rerank_hit_count, 0)", 1),
    ("R536", "backend/rag/observability_store.py", "health_summary", 'safe_int(run_stats.get("recent_run_count_24h"), 0)', 1),
    ("R537", "backend/rag/observability_store.py", "health_summary", 'safe_int(run_stats.get("recent_empty_hit_runs"), 0)', 1),
    ("R538", "backend/rag/observability_store.py", "health_summary", 'safe_int(fallback_stats.get("recent_fallback_count_24h"), 0)', 1),
    ("R539", "backend/rag/observability_store.py", "browse_db_table", 'safe_int(dict(total_row).get("total"), 0)', 1),
    ("R540", "backend/rag/observability_store.py", "complete_search_run", "safe_int(context.materialized_source_doc_count, 0)", 1),
    ("R541", "backend/rag/observability_store.py", "complete_search_run", "safe_int(context.materialized_chunk_count, 0)", 1),
    ("R542", "backend/rag/observability_store.py", "_materialize_pending_batch", "safe_int(meta.get('chunk_index'), index)", 1),
    ("R543", "backend/rag/observability_store.py", "_materialize_pending_batch", "safe_int(meta.get('total_chunks'), total_chunks)", 1),
    ("R544", "backend/rag/observability_store.py", "_materialize_pending_batch", "safe_int(meta.get('char_start'))", 1),
    ("R545", "backend/rag/observability_store.py", "_materialize_pending_batch", "safe_int(meta.get('char_end'))", 1),
    ("R546", "backend/rag/observability_store.py", "_next_seq", "safe_int(value, 0)", 1),
    ("R547", "backend/graph/nodes/execute_plan_stub.py", "execute_plan_stub", 'safe_int(chunk_meta.get("total_chunks"), chunk_total)', 1),
    ("R548", "backend/graph/nodes/execute_plan_stub.py", "execute_plan_stub", 'safe_int(chunk_profile.get("max_chunk_size"), len(chunk_body))', 1),
    ("R549", "backend/graph/nodes/execute_plan_stub.py", "execute_plan_stub", 'safe_int(chunk_profile.get("overlap"), 0)', 1),
    ("R550", "backend/graph/nodes/execute_plan_stub.py", "execute_plan_stub", 'safe_int(chunk_meta.get("total_chunks"), chunk_total)', 2),
    ("R551", "backend/graph/nodes/execute_plan_stub.py", "execute_plan_stub", 'safe_int(chunk_profile.get("max_chunk_size"), len(chunk_body))', 2),
    ("R552", "backend/graph/nodes/execute_plan_stub.py", "execute_plan_stub", 'safe_int(chunk_profile.get("overlap"), 0)', 2),
    ("R553", "backend/graph/nodes/execute_plan_stub.py", "execute_plan_stub", 'safe_int(input_rank_by_chunk_id.get(chunk_id or ""), output_rank)', 1),
    ("R554", "backend/graph/nodes/execute_plan_stub.py", "execute_plan_stub", 'safe_int(ingest_stats.get("indexed"), 0)', 1),
    ("R555", "backend/graph/nodes/execute_plan_stub.py", "execute_plan_stub", 'safe_int(ingest_stats.get("skipped"), 0)', 1),
    ("R556", "backend/graph/nodes/execute_plan_stub.py", "execute_plan_stub", 'safe_int(ingest_stats.get("indexed"), 0)', 2),
    ("R557", "backend/agents/macro_agent.py", "_format_output", "except (TypeError, ValueError, OverflowError):", 1),
    ("R558", "backend/services/alert_scheduler.py", "run_once", "except (TypeError, ValueError, OverflowError):", 1),
    ("R559", "backend/services/alert_scheduler.py", "run_once", "except (TypeError, ValueError, OverflowError):", 2),
    ("R560", "backend/services/next_actions.py", "_safe_priority", "safe_int(value, 0)", 1),
    ("R561", "backend/services/subscription_service.py", "record_alert_attempt", "safe_int(sub.get('alert_failures'), 0)", 1),
    ("R562", "backend/services/subscription_service.py", "list_alert_events", "safe_int(limit, 50)", 1),
    ("R563", "backend/services/historical_data_store.py", "_write_cache", 'safe_int(r.get("is_suspicious"), 0)', 1),
    ("R564", "backend/tools/financial.py", "get_company_info", "safe_float(profile.get('marketCapitalization'))", 1),
    ("R565", "backend/tools/financial.py", "get_company_info", "safe_float(data.get('MarketCapitalization'))", 1),
    ("R566", "backend/tools/price.py", "get_factor_exposure", 'safe_float(position.get("weight"))', 1),
    ("R567", "backend/utils/market_evidence.py", "normalize_market_fallback_level", "except (TypeError, ValueError, OverflowError):", 1),
    ("R568", "backend/api/security_config.py", "__init__", "safe_int(limit_per_window, 1)", 1),
    ("R569", "backend/api/security_config.py", "__init__", "safe_int(window_seconds, 1)", 1),
    ("R570", "backend/rag/hybrid_service.py", "from_env", "safe_int(raw_dim, 0)", 1),
    ("R571", "backend/rag/hybrid_service.py", "from_env", 'safe_int((os.getenv("RAG_V2_RRF_K") or "60").strip(), 60)', 1),
    ("R572", "backend/rag/hybrid_service.py", "count_documents", "safe_int(count_fn(), 0)", 1),
    ("R573", "backend/rag/hybrid_service.py", "cleanup_stale_filings", "safe_int(cleanup_fn(older_than_days=older_than_days), 0)", 1),
    ("R574", "backend/services/report_index.py", "list_reports", "safe_int(limit, 100)", 1),
    ("R575", "backend/services/report_index.py", "list_citations", "safe_int(limit, 100)", 1),
    ("R576", "backend/graph/failure.py", "append_failure", "safe_int(retry_attempts, 0)", 1),
    ("R577", "backend/graph/failure.py", "build_runtime", "safe_int(retry_attempts, 0)", 1),
    ("R578", "backend/tools/cn_hk_market.py", "fetch_cn_hk_kline", "safe_int(limit, 260)", 1),
    ("R579", "backend/tools/cn_market_board.py", "_eastmoney_list", "safe_int(limit, 20)", 1),
    ("R580", "backend/tools/cn_market_board.py", "fetch_lhb", "safe_int(limit, 20)", 1),
    ("R581", "backend/tools/cn_market_flow.py", "_eastmoney_list", "safe_int(limit, 20)", 1),
    ("R582", "backend/tools/concept_map.py", "fetch_concept_map", "safe_int(limit, 20)", 1),
    ("R583", "backend/tools/concept_map.py", "fetch_concept_map", 'safe_int(row.get("f104"))', 1),
    ("R584", "backend/tools/concept_map.py", "fetch_concept_map", 'safe_int(row.get("f105"))', 1),
    ("R585", "backend/tools/earnings_transcripts.py", "get_earnings_call_transcripts", "safe_int(limit, 6)", 1),
    ("R586", "backend/tools/local_disclosure.py", "get_local_market_filings", "safe_int(limit, 8)", 1),
    ("R587", "backend/services/monitoring_storage.py", "save_health_snapshot", 'safe_int(data.get("total_requests"), 0)', 1),
    ("R588", "backend/services/monitoring_storage.py", "save_health_snapshot", 'safe_int(data.get("success_count"), 0)', 1),
    ("R589", "backend/services/monitoring_storage.py", "save_health_snapshot", 'safe_int(data.get("failure_count"), 0)', 1),
    ("R590", "backend/services/monitoring_storage.py", "save_health_snapshot", 'safe_int(data.get("consecutive_failures"), 0)', 1),
    ("R591", "backend/services/timeline_service.py", "_collect_report_events", 'safe_int(report.get("citation_count"), 0)', 1),
    ("R592", "backend/services/entitlements.py", "check_quota", "safe_int(current_count, 0)", 1),
    ("R593", "backend/llm_config.py", "select", "safe_int(ep.cfg.weight, 1)", 1),
    ("R594", "backend/llm_config.py", "report_failure", "safe_int(ep.cfg.cooldown_sec, 1)", 1),
    ("R595", "backend/llm_config.py", "create_llm", "safe_int(resolved_max_tokens, 8192)", 1),
    ("R596", "backend/report/validator.py", "_build_report", "except (TypeError, ValueError, OverflowError):", 1),
    ("R597", "backend/report/validator.py", "_build_report", "except (TypeError, ValueError, OverflowError):", 2),
    ("R598", "backend/report/validator.py", "_parse_section", "except (TypeError, ValueError, OverflowError):", 2),
    ("R599", "backend/services/monitoring_storage.py", "save_health_snapshot", 'safe_float(data.get("success_rate"))', 1),
    ("R600", "backend/services/monitoring_storage.py", "save_health_snapshot", 'safe_float(data.get("avg_response_time_ms"))', 1),
]


NUMERIC_BOUNDARY_ROUNDS_601_700 = [
    ("R601", "backend/rag/hybrid_service.py", "hybrid_search", '_finite_score(x.get("rrf_score"))', 1),
    ("R602", "backend/rag/hybrid_service.py", "hybrid_search", '_finite_score(x.get("dense_score"))', 1),
    ("R603", "backend/rag/hybrid_service.py", "hybrid_search", '_finite_score(x.get("sparse_score"))', 1),
    ("R604", "backend/rag/hybrid_service.py", "hybrid_search", "limit = max(1, safe_int(top_k, 6))", 1),
    ("R605", "backend/rag/hybrid_service.py", "cleanup_stale_filings", "retention_days = max(1, safe_int(older_than_days, 365))", 1),
    ("R606", "backend/rag/hybrid_service.py", "_check_vector_dimension", "return safe_int(row[0], 0) or 0", 1),
    ("R607", "backend/rag/hybrid_service.py", "hybrid_search", "limit = max(1, safe_int(top_k, 6))", 2),
    ("R608", "backend/rag/hybrid_service.py", "cleanup_expired", "return safe_int(result.rowcount, 0) or 0", 1),
    ("R609", "backend/rag/hybrid_service.py", "count_documents", "return safe_int(value, 0) or 0", 1),
    ("R610", "backend/rag/hybrid_service.py", "cleanup_stale_filings", "retention_days = max(1, safe_int(older_than_days, 365))", 2),
    ("R611", "backend/rag/hybrid_service.py", "cleanup_stale_filings", "return safe_int(result.rowcount, 0) or 0", 1),
    ("R612", "backend/rag/hybrid_service.py", "__init__", "normalized_dim = safe_int(vector_dim, 0) or 0", 1),
    ("R613", "backend/rag/hybrid_service.py", "__init__", "self.rrf_k = max(1, safe_int(rrf_k, 60))", 1),
    ("R614", "backend/rag/hybrid_service.py", "hybrid_search", "limit = max(1, safe_int(top_k, 6))", 3),
    ("R615", "backend/rag/observability_runtime.py", "update_query_run", "return safe_int(result.rowcount, 0) or 0", 1),
    ("R616", "backend/rag/observability_runtime.py", "append_query_events", "safe_int(r.seq_no, 0) or 0", 1),
    ("R617", "backend/rag/observability_runtime.py", "append_source_docs", "safe_int(r.content_length, 0) or 0", 1),
    ("R618", "backend/rag/observability_runtime.py", "append_chunks", "safe_int(r.chunk_index, 0) or 0", 1),
    ("R619", "backend/rag/observability_runtime.py", "append_chunks", "safe_int(r.total_chunks, 0) or 0", 1),
    ("R620", "backend/rag/observability_runtime.py", "append_chunks", "safe_int(r.chunk_length, 0) or 0", 1),
    ("R621", "backend/rag/observability_runtime.py", "append_chunks", "safe_int(r.chunk_size, 0) or 0", 1),
    ("R622", "backend/rag/observability_runtime.py", "append_chunks", "safe_int(r.chunk_overlap, 0) or 0", 1),
    ("R623", "backend/rag/observability_runtime.py", "append_rerank_hits", "safe_int(r.input_rank, 0) or 0", 1),
    ("R624", "backend/rag/observability_runtime.py", "append_rerank_hits", "safe_int(r.output_rank, 0) or 0", 1),
    ("R625", "backend/rag/observability_runtime.py", "cleanup_retention", "total += safe_int(conn.execute", 1),
    ("R626", "backend/rag/observability_runtime.py", "cleanup_retention", "total += safe_int(conn.execute", 2),
    ("R627", "backend/rag/observability_runtime.py", "_sql_health_summary", "safe_int(recent_limit, 20)", 1),
    ("R628", "backend/rag/observability_runtime.py", "_sql_health_summary", "safe_int(fallback_limit, 20)", 1),
    ("R629", "backend/rag/observability_runtime.py", "_sql_list_runs", "safe_int(limit, 20)", 1),
    ("R630", "backend/rag/observability_runtime.py", "_sql_list_events", "safe_int(limit, 500)", 1),
    ("R631", "backend/rag/observability_runtime.py", "_sql_list_documents", "safe_int(limit, 200)", 1),
    ("R632", "backend/rag/observability_runtime.py", "_sql_list_chunks", "safe_int(limit, 500)", 1),
    ("R633", "backend/rag/observability_runtime.py", "_sql_list_hits", "safe_int(limit, 500)", 1),
    ("R634", "backend/rag/observability_runtime.py", "_sql_list_collections", "safe_int(limit, 200)", 1),
    ("R635", "backend/rag/observability_runtime.py", "_sql_search_preview", "safe_int(top_k, 10)", 1),
    ("R636", "backend/rag/observability_store.py", "browse_db_table", "safe_int(limit, 50)", 1),
    ("R637", "backend/rag/observability_store.py", "browse_db_table", "safe_int(offset, 0) or 0", 1),
    ("R638", "backend/rag/observability_store.py", "begin_search_run", "retrieval_k=max(1, safe_int(top_k, 6))", 1),
    ("R639", "backend/rag/observability_store.py", "health_summary", "safe_int(recent_limit, 20)", 1),
    ("R640", "backend/rag/observability_store.py", "health_summary", "safe_int(fallback_limit, 20)", 1),
    ("R641", "backend/rag/observability_store.py", "list_collections", "safe_int(limit, 200)", 1),
    ("R642", "backend/rag/observability_store.py", "browse_db_table", "safe_int(limit, 50)", 2),
    ("R643", "backend/rag/observability_store.py", "browse_db_table", "safe_int(offset, 0) or 0", 2),
    ("R644", "backend/rag/observability_store.py", "begin_search_run", "retrieval_k=max(1, safe_int(top_k, 6))", 2),
    ("R645", "backend/rag/observability_store.py", "observed_search", "safe_int(top_k, 6)", 1),
    ("R646", "backend/services/backtest_engine.py", "__init__", "fee_bps = self._finite_number(default_fee_bps)", 1),
    ("R647", "backend/services/backtest_engine.py", "__init__", "slippage_bps = self._finite_number(default_slippage_bps)", 1),
    ("R648", "backend/services/backtest_engine.py", "_normalize_points", 'BacktestEngine._finite_number(item.get("close"))', 1),
    ("R649", "backend/services/backtest_strategies.py", "_ema", "_int_value(period, 1)", 1),
    ("R650", "backend/services/backtest_strategies.py", "_rsi", "_int_value(period, 14)", 1),
    ("R651", "backend/services/backtest_strategies.py", "ma_cross_signals", "_int_value(short_window, 20)", 1),
    ("R652", "backend/services/backtest_strategies.py", "ma_cross_signals", "_int_value(long_window, 50)", 1),
    ("R653", "backend/services/backtest_strategies.py", "macd_signals", "_int_value(fast, 12)", 1),
    ("R654", "backend/services/backtest_strategies.py", "macd_signals", "_int_value(slow, 26)", 1),
    ("R655", "backend/services/backtest_strategies.py", "macd_signals", "_int_value(signal, 9)", 1),
    ("R656", "backend/services/entitlements.py", "check_quota", "safe_int(PLAN_LIMITS.get(plan, {}).get(quota_key, 0), 0) or 0", 1),
    ("R657", "backend/services/entitlements.py", "build_usage_view", 'safe_int(limits.get("max_reports_per_day"), 0) or 0', 1),
    ("R658", "backend/services/entitlements.py", "build_usage_view", 'safe_int(limits.get("max_alerts"), 0) or 0', 1),
    ("R659", "backend/services/entitlements.py", "build_usage_view", 'safe_int(limits.get("max_portfolio_positions"), 0) or 0', 1),
    ("R660", "backend/services/entitlements.py", "build_usage_view", "safe_int(limits.get(quota_key), 0) or 0", 1),
    ("R661", "backend/services/entitlements.py", "_quota_entry", "safe_int(used, 0) or 0", 1),
    ("R662", "backend/services/entitlements.py", "_quota_entry", "normalized_limit = safe_int(limit, 0) or 0", 1),
    ("R663", "backend/tools/authoritative_feeds.py", "get_authoritative_media_news", "safe_int(max_results, 8) or 8", 1),
    ("R664", "backend/tools/macro_official.py", "search_official_macro_releases", "safe_int(max_results, 10) or 10", 1),
    ("R665", "backend/tools/macro_official.py", "get_official_macro_releases", "safe_int(max_results, 10) or 10", 1),
    ("R666", "backend/tools/cn_hk_market.py", "_eastmoney_get_json", "safe_int(timeout, _EASTMONEY_TIMEOUT) or _EASTMONEY_TIMEOUT", 1),
    ("R667", "backend/tools/cn_hk_market.py", "_http_get_text", "safe_int(timeout, 3) or 3", 1),
    ("R668", "backend/tools/cn_hk_market.py", "fetch_cn_hk_financial_statements", "safe_int(periods, 8)", 1),
    ("R669", "backend/tools/tencent_provider.py", "_is_recent_eastmoney_date", "safe_int(max_age_days, 90)", 1),
    ("R670", "backend/tools/tencent_provider.py", "fetch_cn_top_list_history", "safe_int(days, 30)", 1),
    ("R671", "backend/tools/tencent_provider.py", "fetch_margin_trading_history", "safe_int(days, 90)", 1),
    ("R672", "backend/tools/wayback.py", "resolve_wayback_snapshot", "safe_int(timeout, _WAYBACK_TIMEOUT) or _WAYBACK_TIMEOUT", 1),
    ("R673", "backend/tools/wayback.py", "fetch_via_wayback", "safe_int(timeout, _WAYBACK_TIMEOUT) or _WAYBACK_TIMEOUT", 1),
    ("R674", "backend/tools/news.py", "get_company_news", "safe_int(limit, 5) or 5", 1),
    ("R675", "backend/tools/news.py", "_to_date_candidate", "timestamp = safe_float(value)", 1),
    ("R676", "backend/tools/news.py", "get_event_calendar", "safe_int(days_ahead, 30) or 30", 1),
    ("R677", "backend/tools/fmp.py", "get_etf_sector_weights", 'safe_float(str(weight_str).replace("%", "").strip()) or 0.0', 1),
    ("R678", "backend/tools/fmp.py", "get_etf_holdings", 'safe_float(str(weight_str).replace("%", "").strip()) or 0.0', 1),
    ("R679", "backend/orchestration/orchestrator.py", "fetch", 'safe_int(os.getenv("CACHE_NEGATIVE_TTL"), 60)', 1),
    ("R680", "backend/orchestration/orchestrator.py", "get_stats", 'safe_int(cb_state.get("cooldown_remaining"), 0)', 1),
    ("R681", "backend/graph/adapters/agent_adapter.py", "build_agent_invokers", '_env_float("LANGGRAPH_AGENT_TEMPERATURE", 0.2)', 1),
    ("R682", "backend/services/circuit_breaker.py", "__init__", "safe_int(failure_threshold, 3)", 1),
    ("R683", "backend/services/circuit_breaker.py", "__init__", "parsed_recovery_timeout = safe_float(recovery_timeout)", 1),
    ("R684", "backend/services/circuit_breaker.py", "__init__", "safe_int(half_open_success_threshold, 1)", 1),
    ("R685", "backend/services/circuit_breaker.py", "_get_failure_threshold", "safe_int(override, self.failure_threshold) or self.failure_threshold", 1),
    ("R686", "backend/services/circuit_breaker.py", "_get_failure_threshold", "safe_int(env_val, self.failure_threshold) or self.failure_threshold", 1),
    ("R687", "backend/services/circuit_breaker.py", "_get_recovery_timeout", "parsed = safe_float(override)", 1),
    ("R688", "backend/services/circuit_breaker.py", "_get_recovery_timeout", "parsed = safe_float(env_val)", 1),
    ("R689", "backend/services/chat_history.py", "list_messages", "safe_int(limit, _DEFAULT_LIMIT) or _DEFAULT_LIMIT", 1),
    ("R690", "backend/services/memory.py", "add_to_watchlist", "safe_int(priority, 0) or 0", 1),
    ("R691", "backend/services/report_index.py", "_normalize_citation_item", 'safe_float(item.get("confidence"))', 1),
    ("R692", "backend/services/report_index.py", "upsert_report", 'safe_float(report.get("confidence_score"))', 1),
    ("R693", "backend/api/agent_router.py", "_normalize_preferences", 'max_rounds_value = safe_int(raw.get("maxRounds"), defaults["maxRounds"])', 1),
    ("R694", "backend/services/rebalance_llm_enhancer.py", "_llm_enhance", "parsed_priority = safe_int(new_priority)", 1),
    ("R695", "backend/services/subscription_service.py", "record_alert_attempt", "safe_int(sub.get('alert_failures'), 0) or 0", 1),
    ("R696", "backend/services/next_actions.py", "_safe_priority", "return safe_int(value, 0) or 0", 1),
    ("R697", "backend/tools/fmp.py", "get_revenue_product_segmentation", "if (parsed := safe_float(raw)) is not None and parsed > 0", 1),
    ("R698", "backend/tools/fmp.py", "get_revenue_geographic_segmentation", "if (parsed := safe_float(raw)) is not None and parsed > 0", 1),
    ("R699", "backend/tools/fmp.py", "get_etf_holdings", "result_limit = max(0, safe_int(limit, 50))", 1),
    ("R700", "backend/tools/fmp.py", "get_index_constituents", "result_limit = max(0, safe_int(limit, 10))", 1),
]


@pytest.mark.parametrize(
    ("_round", "relative_path", "needle"),
    NUMERIC_BOUNDARY_ROUNDS,
    ids=[item[0] for item in NUMERIC_BOUNDARY_ROUNDS],
)
def test_numeric_boundary_round_has_source_binding(_round, relative_path, needle):
    source = (_ROOT / relative_path).read_text(encoding="utf-8-sig")
    assert needle in source


def test_rounds_301_through_400_are_complete_and_unique():
    from backend.tests.test_strict_json_boundaries import STRICT_JSON_ENTRYPOINTS

    strict_rounds = [item[0] for item in STRICT_JSON_ENTRYPOINTS if 301 <= int(item[0][1:]) <= 400]
    numeric_rounds = [item[0] for item in NUMERIC_BOUNDARY_ROUNDS]
    actual = strict_rounds + numeric_rounds
    expected = [f"R{number}" for number in range(301, 401)]

    assert len(actual) == len(set(actual)) == 100
    assert sorted(actual, key=lambda item: int(item[1:])) == expected


@pytest.mark.parametrize(
    ("_round", "relative_path", "scope", "needle", "occurrence"),
    NUMERIC_BOUNDARY_ROUNDS_401_500,
    ids=[item[0] for item in NUMERIC_BOUNDARY_ROUNDS_401_500],
)
def test_round_401_500_has_scoped_source_binding(_round, relative_path, scope, needle, occurrence):
    source = (_ROOT / relative_path).read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    matches = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == scope]

    assert matches, f"missing scope {scope}"
    scoped_source = "\n".join(ast.get_source_segment(source, match) or "" for match in matches)
    assert scoped_source.count(needle) >= occurrence


def test_rounds_401_through_500_are_complete_and_unique():
    actual = [item[0] for item in NUMERIC_BOUNDARY_ROUNDS_401_500]
    expected = [f"R{number}" for number in range(401, 501)]

    assert len(actual) == len(set(actual)) == 100
    assert actual == expected


@pytest.mark.parametrize(
    ("_round", "relative_path", "scope", "needle", "occurrence"),
    NUMERIC_BOUNDARY_ROUNDS_501_600,
    ids=[item[0] for item in NUMERIC_BOUNDARY_ROUNDS_501_600],
)
def test_round_501_600_has_scoped_source_binding(_round, relative_path, scope, needle, occurrence):
    source = (_ROOT / relative_path).read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    matches = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == scope]

    assert matches, f"missing scope {scope}"
    scoped_source = "\n".join(ast.get_source_segment(source, match) or "" for match in matches)
    assert scoped_source.count(needle) >= occurrence


def test_rounds_501_through_600_are_complete_and_unique():
    actual = [item[0] for item in NUMERIC_BOUNDARY_ROUNDS_501_600]
    expected = [f"R{number}" for number in range(501, 601)]

    assert len(actual) == len(set(actual)) == 100
    assert actual == expected


@pytest.mark.parametrize(
    ("_round", "relative_path", "scope", "needle", "occurrence"),
    NUMERIC_BOUNDARY_ROUNDS_601_700,
    ids=[item[0] for item in NUMERIC_BOUNDARY_ROUNDS_601_700],
)
def test_round_601_700_has_scoped_source_binding(_round, relative_path, scope, needle, occurrence):
    source = (_ROOT / relative_path).read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    matches = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == scope]

    assert matches, f"missing scope {scope}"
    scoped_source = "\n".join(ast.get_source_segment(source, match) or "" for match in matches)
    assert scoped_source.count(needle) >= occurrence


def test_rounds_601_through_700_are_complete_and_unique():
    actual = [item[0] for item in NUMERIC_BOUNDARY_ROUNDS_601_700]
    expected = [f"R{number}" for number in range(601, 701)]

    assert len(actual) == len(set(actual)) == 100
    assert actual == expected


@pytest.mark.parametrize("value", ["invalid", float("nan"), float("inf"), float("-inf")])
def test_rag_public_numeric_parameters_fall_back(value):
    from backend.rag.hybrid_service import HybridRAGService
    from backend.rag.observability_store import NoOpRAGObservabilityStore

    embedder = SimpleNamespace(dim=32, model_name="test")
    service = HybridRAGService(backend="memory", vector_dim=value, rrf_k=value, embedder=embedder)
    captured: dict[str, int] = {}
    service._store = SimpleNamespace(
        hybrid_search=lambda _query, *, collection, top_k: captured.update(top_k=top_k) or [],
    )

    assert service.vector_dim == 32
    assert service.rrf_k == 60
    assert service.hybrid_search("query", collection="test", top_k=value) == []
    assert captured["top_k"] == 6

    page = NoOpRAGObservabilityStore().browse_db_table(
        table_name="rag_query_runs",
        limit=value,
        offset=value,
    )
    assert page["limit"] == 50
    assert page["offset"] == 0


@pytest.mark.parametrize("value", ["invalid", float("nan"), float("inf"), float("-inf")])
def test_backtest_numeric_parameters_use_existing_defaults(value):
    from backend.services.backtest_engine import BacktestEngine
    from backend.services.backtest_strategies import ma_cross_signals, macd_signals

    engine = BacktestEngine(default_fee_bps=value, default_slippage_bps=value)
    assert engine.default_fee_bps == 5.0
    assert engine.default_slippage_bps == 3.0

    closes = [100.0] * 60
    ma = ma_cross_signals(closes, short_window=value, long_window=value)
    macd = macd_signals(closes, fast=value, slow=value, signal=value)
    assert ma["params"] == {"short_window": 20, "long_window": 50}
    assert macd["params"] == {"fast": 12, "slow": 26, "signal": 9}


@pytest.mark.parametrize("value", ["invalid", float("nan"), float("inf"), float("-inf")])
def test_configuration_and_persisted_numeric_values_fall_back(value, tmp_path):
    from backend.api.agent_router import _normalize_preferences
    from backend.services.chat_history import ChatHistoryStore
    from backend.services.circuit_breaker import CircuitBreaker
    from backend.services.entitlements import _quota_entry
    from backend.services.report_index import _normalize_citation_item

    breaker = CircuitBreaker(failure_threshold=value, recovery_timeout=value, half_open_success_threshold=value)
    assert breaker.failure_threshold == 3
    assert breaker.recovery_timeout == 300.0
    assert breaker.half_open_success_threshold == 1
    assert _normalize_preferences({"maxRounds": value})["maxRounds"] == 3
    assert _quota_entry(plan="free", used=value, limit=value)["used"] == 0
    assert ChatHistoryStore(tmp_path).list_messages(session_id="session", limit=value) == []
    assert _normalize_citation_item({"title": "source", "confidence": value})["confidence"] is None


def test_fmp_non_finite_values_and_invalid_limits_are_sanitized(monkeypatch):
    from backend.tools import fmp as module

    monkeypatch.setattr(
        module,
        "_fmp_request",
        lambda endpoint, params=None: (
            [{"AAPL": {"valid": 100.0, "invalid": float("nan")}}]
            if "segmentation" in endpoint
            else [
                {
                    "asset": "AAPL",
                    "name": "Apple",
                    "weightPercentage": "NaN",
                }
            ]
        ),
    )

    product = module.get_revenue_product_segmentation("AAPL")
    geographic = module.get_revenue_geographic_segmentation("AAPL")
    holdings = module.get_etf_holdings("SPY", limit=float("nan"))

    assert [item["segment"] for item in product] == ["valid"]
    assert [item["region"] for item in geographic] == ["valid"]
    assert holdings[0]["weight"] == 0.0


def test_zero_numeric_parameters_preserve_existing_clamp_semantics(monkeypatch):
    from backend.api.agent_router import _normalize_preferences
    from backend.rag.hybrid_service import HybridRAGService
    from backend.rag.observability_store import NoOpRAGObservabilityStore
    from backend.services.backtest_engine import BacktestEngine
    from backend.services.backtest_strategies import ma_cross_signals, macd_signals
    from backend.services.circuit_breaker import CircuitBreaker
    from backend.tools import fmp as fmp_module

    embedder = SimpleNamespace(dim=32, model_name="test")
    service = HybridRAGService(backend="memory", vector_dim=0, rrf_k=0, embedder=embedder)
    captured: dict[str, int] = {}
    service._store = SimpleNamespace(
        hybrid_search=lambda _query, *, collection, top_k: captured.update(top_k=top_k) or [],
    )
    service.hybrid_search("query", collection="test", top_k=0)

    assert service.rrf_k == 1
    assert captured["top_k"] == 1
    assert NoOpRAGObservabilityStore().browse_db_table(table_name="rag_query_runs", limit=0)["limit"] == 1
    assert BacktestEngine(default_fee_bps=0, default_slippage_bps=0).default_fee_bps == 0
    assert ma_cross_signals([100.0] * 5, short_window=0, long_window=0)["params"] == {
        "short_window": 2,
        "long_window": 3,
    }
    assert macd_signals([100.0] * 5, fast=0, slow=0, signal=0)["params"] == {
        "fast": 2,
        "slow": 3,
        "signal": 2,
    }
    assert CircuitBreaker(failure_threshold=0, half_open_success_threshold=0).failure_threshold == 1
    assert _normalize_preferences({"maxRounds": 0})["maxRounds"] == 1

    monkeypatch.setattr(fmp_module, "_fmp_request", lambda *_args, **_kwargs: [{"asset": "AAPL"}])
    assert fmp_module.get_etf_holdings("SPY", limit=0) == []


@pytest.mark.parametrize("value", ["not-an-int", object(), float("nan"), float("inf"), float("-inf")])
def test_safe_int_uses_default_for_invalid_values(value):
    from backend.utils.quote import safe_int

    assert safe_int(value, 7) == 7


def test_parse_user_endpoints_defaults_invalid_integer_fields():
    from backend.llm_config import _parse_user_endpoints

    endpoints = _parse_user_endpoints(
        {
            "llm_endpoints": [
                {
                    "name": "primary",
                    "api_key": "test-key",
                    "weight": float("nan"),
                    "cooldown_sec": "not-an-int",
                }
            ]
        },
        "openai_compatible",
        "test-model",
    )

    assert len(endpoints) == 1
    assert endpoints[0].weight == 1
    assert endpoints[0].cooldown_sec == 90


def test_runtime_quality_defaults_non_finite_missing_counts():
    from backend.report.quality_engine import build_runtime_quality_reasons

    reasons = build_runtime_quality_reasons(
        quality_hints={
            "deep_report_required": True,
            "missing_counts": {"critical": float("inf"), "important": float("nan"), "minor": "bad"},
        },
        grounding_stats={},
        verifier_claims=[],
    )

    assert not {"QUALITY_PROFILE_CRITICAL_MISSING", "QUALITY_PROFILE_IMPORTANT_MISSING", "QUALITY_PROFILE_MINOR_MISSING"} & {
        item.get("code") for item in reasons
    }


def test_report_validator_defaults_infinite_section_order():
    from backend.report.validator import ReportValidator

    section = ReportValidator._parse_section({"title": "test", "order": float("inf")}, 7)

    assert section.order == 7


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_technical_agent_skips_non_finite_close(value):
    from backend.agents.technical_agent import TechnicalAgent

    rows = [{"close": 100 + index, "time": str(index)} for index in range(30)]
    rows.insert(10, {"close": value, "time": "invalid"})

    series, last_time = TechnicalAgent(None, None, None)._build_close_series(rows)

    assert series is not None
    assert len(series) == 30
    assert all(math.isfinite(item) for item in series)
    assert last_time == "29"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_langchain_technical_snapshot_skips_non_finite_close(monkeypatch, value):
    import backend.langchain_tools as module

    rows = [{"close": 100 + index, "time": str(index)} for index in range(30)]
    rows.insert(5, {"close": value, "time": "invalid"})
    monkeypatch.setattr(
        module,
        "_get_stock_historical_data",
        lambda *_args, **_kwargs: {"kline_data": rows, "source": "test"},
    )

    payload = json.loads(module.get_technical_snapshot.invoke({"ticker": "AAPL"}))

    assert payload.get("error") is None
    assert math.isfinite(payload["close"])
    assert "NaN" not in json.dumps(payload, allow_nan=False)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_financial_table_serializers_replace_non_finite_numbers(value):
    from backend.tools.financial import (
        _build_table_payload,
        _serialize_calendar_payload,
        _serialize_table_records,
    )

    built = _build_table_payload(["2026-03-31"], [("Revenue", [value])])
    frame = pd.DataFrame({"estimate": [value]}, index=["2026Q1"])

    assert built == {"columns": ["2026-03-31"], "index": ["Revenue"], "data": [{"2026-03-31": None}]}
    assert _serialize_table_records(frame)[0]["estimate"] is None
    assert _serialize_calendar_payload({"estimate": value})["estimate"] is None


@pytest.mark.parametrize(
    "field",
    ["upLast7days", "upLast30days", "downLast7Days", "downLast30days"],
)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_revision_signal_ignores_non_finite_counts(field, value):
    from backend.tools.financial import _infer_revision_signal

    assert _infer_revision_signal([{field: value}]) == "neutral"


def test_market_sentiment_rejects_non_finite_api_and_search_scores(monkeypatch):
    from backend.tools import macro as module

    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"fear_and_greed": {"score": "1e309", "rating": "bad"}},
    )
    monkeypatch.setattr(module, "_http_get", lambda *_args, **_kwargs: response)
    monkeypatch.setattr(
        module,
        "search",
        lambda _query: f"Index: {'9' * 400} (Extreme Greed)",
    )

    assert module.get_market_sentiment() == "Fear & Greed Index: Unable to fetch. Please check manually."


_FRED_FIELDS = {
    "cpi": "CPIAUCSL",
    "fed_rate": "FEDFUNDS",
    "gdp_growth": "A191RL1Q225SBEA",
    "unemployment": "UNRATE",
    "treasury_10y": "DGS10",
    "yield_spread": "T10Y2Y",
}


@pytest.mark.parametrize("field", _FRED_FIELDS)
def test_fred_rejects_non_finite_observation_for_each_indicator(monkeypatch, field):
    from backend.tools import macro as module

    target_sid = _FRED_FIELDS[field]

    def fake_get(_url, *, params, **_kwargs):
        value = "1e309" if params["series_id"] == target_sid else "1.0"
        return SimpleNamespace(status_code=200, json=lambda: {"observations": [{"value": value}]})

    monkeypatch.setattr(module, "FRED_API_KEY", "test-key")
    monkeypatch.setattr(module, "_http_get", fake_get)

    result = module.get_fred_data()

    assert result[field] is None
    assert all(result[key] is None or math.isfinite(result[key]) for key in _FRED_FIELDS)


@pytest.mark.parametrize("field", ["ma20", "ma50", "macd", "macd_signal"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_technical_scoring_ignores_non_finite_comparison_fields(field, value):
    from backend.dashboard.insights_scorer import score_technical, score_technical_details

    base = {"ma20": 20.0, "ma50": 10.0, "macd": 2.0, "macd_signal": 1.0}
    poisoned = dict(base, **{field: value})
    missing = {key: item for key, item in base.items() if key != field}

    assert score_technical(poisoned) == score_technical(missing)
    assert score_technical_details(poisoned) == score_technical_details(missing)


@pytest.mark.parametrize("field", ["net_income", "free_cash_flow"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_financial_scoring_ignores_non_finite_unchecked_fields(field, value):
    from backend.dashboard.insights_scorer import score_financial, score_financial_details

    poisoned = {field: value}

    assert score_financial(poisoned) == score_financial({})
    assert score_financial_details(poisoned) == score_financial_details({})


@pytest.mark.parametrize(
    ("scope", "field"),
    [
        ("company", "trailing_pe"),
        ("peer", "trailing_pe"),
        ("company", "revenue_growth"),
        ("peer", "revenue_growth"),
        ("company", "profit_margin"),
        ("peer", "profit_margin"),
    ],
)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_peer_scoring_ignores_non_finite_growth_and_margin(scope, field, value):
    from backend.dashboard.insights_scorer import score_peers, score_peers_details

    base = {"company": {}, "peers": [{"ticker": "MSFT"}]}
    poisoned = {"company": dict(base["company"]), "peers": [dict(base["peers"][0])]}
    if scope == "company":
        poisoned["company"][field] = value
    else:
        poisoned["peers"][0][field] = value

    assert score_peers(poisoned) == score_peers(base)
    assert score_peers_details(poisoned) == score_peers_details(base)


@pytest.mark.parametrize("field", ["tech_score", "fin_score", "news_score", "peers_score"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_overview_scoring_defaults_non_finite_dimension(field, value):
    from backend.dashboard.insights_scorer import score_overview, score_overview_details

    poisoned = {"tech_score": 6.0, "fin_score": 6.0, "news_score": 6.0, "peers_score": 6.0}
    poisoned[field] = value
    expected = dict(poisoned, **{field: 5.0})

    assert score_overview(**poisoned) == score_overview(**expected)
    assert score_overview_details(**poisoned) == score_overview_details(**expected)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_screener_clean_float_rejects_non_finite_external_fields(value):
    from backend.tools.screener import _clean_float

    assert _clean_float(value) is None


def test_shared_numeric_boundaries_reject_integer_overflow():
    from backend.dashboard.insights_scorer import _finite_number
    from backend.utils.quote import safe_float

    value = 10**1000
    assert safe_float(value) is None
    assert _finite_number(value) is None


def test_screener_non_finite_cache_expiry_does_not_create_permanent_hit(monkeypatch):
    from backend.tools import screener as module

    calls = {"count": 0}

    def fake_get(*_args, **_kwargs):
        calls["count"] += 1
        return SimpleNamespace(
            status_code=200,
            json=lambda: {"most_actively_traded": [{"ticker": "MSFT", "price": "1"}]},
        )

    monkeypatch.setattr(module, "ALPHA_VANTAGE_API_KEY", "test-key")
    monkeypatch.setattr(module, "_http_get", fake_get)
    monkeypatch.setattr(module, "_ALPHA_TOP_MOVERS_CACHE", {"items": [{"ticker": "STALE"}], "expires_at": float("inf")})

    result = module._alpha_vantage_screen_stocks("US", {}, 5, "price", "desc")

    assert calls["count"] == 1
    assert result is not None
    assert result["items"][0]["symbol"] == "MSFT"


_SCREENER_FILTER_CASES = [
    *[("alpha", key) for key in ("priceMoreThan", "priceLowerThan", "volumeMoreThan")],
    *[
        ("yfinance", key)
        for key in ("priceMoreThan", "priceLowerThan", "marketCapMoreThan", "marketCapLowerThan", "volumeMoreThan")
    ],
    *[
        ("passes", key)
        for key in ("priceMoreThan", "priceLowerThan", "marketCapMoreThan", "marketCapLowerThan", "volumeMoreThan")
    ],
    *[
        ("static", key)
        for key in ("priceMoreThan", "priceLowerThan", "marketCapMoreThan", "marketCapLowerThan", "volumeMoreThan")
    ],
]


@pytest.mark.parametrize(("consumer", "filter_name"), _SCREENER_FILTER_CASES)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "1e309", "invalid"])
def test_screener_consumers_ignore_invalid_numeric_thresholds(monkeypatch, consumer, filter_name, value):
    from backend.tools import screener as module

    filters = {filter_name: value}
    if consumer == "alpha":
        monkeypatch.setattr(module, "ALPHA_VANTAGE_API_KEY", "test-key")
        monkeypatch.setattr(module, "_ALPHA_TOP_MOVERS_CACHE", {"items": None, "expires_at": 0.0})
        monkeypatch.setattr(
            module,
            "_http_get",
            lambda *_args, **_kwargs: SimpleNamespace(
                status_code=200,
                json=lambda: {"most_actively_traded": [{"ticker": "AAPL", "price": "100", "volume": "1000"}]},
            ),
        )
        result = module._alpha_vantage_screen_stocks("US", filters, 1, "price", "desc")
        assert result is not None
        assert result["items"][0]["symbol"] == "AAPL"
    elif consumer == "yfinance":
        monkeypatch.setattr(module, "_alpha_vantage_screen_stocks", lambda *_args: None)
        monkeypatch.setattr(module, "_POPULAR_TICKERS", {"US": ["AAPL"]})
        monkeypatch.setattr(
            module.yf,
            "Ticker",
            lambda _symbol: SimpleNamespace(
                fast_info={"last_price": 100.0, "market_cap": 1_000_000.0, "last_volume": 1000.0}
            ),
        )
        result = module._yfinance_popular_stocks("US", filters, 1, "price", "desc")
        assert result["items"][0]["symbol"] == "AAPL"
    elif consumer == "passes":
        item = {"price": 100.0, "market_cap": 1_000_000.0, "volume": 1000.0}
        assert module._passes_screener_filters(item, filters) is True
    else:
        result = module._static_fallback_items("US", filters)
        assert result


@pytest.mark.parametrize(
    ("filter_name", "value"),
    [
        ("priceMoreThan", 1_000_000.0),
        ("priceLowerThan", 0.0001),
        ("marketCapMoreThan", 1e30),
        ("marketCapLowerThan", 0.0001),
        ("volumeMoreThan", 1e30),
    ],
)
def test_screener_finite_thresholds_still_filter_static_items(filter_name, value):
    from backend.tools.screener import _static_fallback_items

    assert _static_fallback_items("US", {filter_name: value}) == []


@pytest.mark.parametrize("field", ["open", "high", "low", "close", "volume"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_iex_history_rejects_non_finite_ohlcv(monkeypatch, field, value):
    from backend.tools import price as module

    row = {"date": "2026-01-02", "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0}
    row[field] = value
    monkeypatch.setattr(module, "IEX_CLOUD_API_KEY", "test-key")
    monkeypatch.setattr(module, "_http_get", lambda *_args, **_kwargs: SimpleNamespace(status_code=200, json=lambda: [row]))

    result = module._fetch_with_iex_cloud("AAPL")

    assert result is not None
    assert result["kline_data"][0][field] is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_tiingo_history_rejects_non_finite_close(monkeypatch, value):
    from backend.tools import price as module

    row = {
        "date": "2026-01-02T00:00:00Z",
        "open": 1.0,
        "high": 2.0,
        "low": 0.5,
        "close": value,
        "volume": 10.0,
    }
    monkeypatch.setattr(module, "TIINGO_API_KEY", "test-key")
    monkeypatch.setattr(
        module,
        "_http_get",
        lambda *_args, **_kwargs: SimpleNamespace(status_code=200, json=lambda: [row]),
    )

    result = module._fetch_with_tiingo("AAPL")

    assert result is not None
    assert result["kline_data"][0]["close"] is None


@pytest.mark.parametrize("field", ["open", "high", "low", "volume"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "1e309"])
def test_tiingo_history_rejects_other_non_finite_ohlcv(monkeypatch, field, value):
    from backend.tools import price as module

    row = {
        "date": "2026-01-02T00:00:00Z",
        "open": 1.0,
        "high": 2.0,
        "low": 0.5,
        "close": 1.5,
        "volume": 10.0,
    }
    row[field] = value
    monkeypatch.setattr(module, "TIINGO_API_KEY", "test-key")
    monkeypatch.setattr(
        module,
        "_http_get",
        lambda *_args, **_kwargs: SimpleNamespace(status_code=200, json=lambda: [row]),
    )

    result = module._fetch_with_tiingo("AAPL")

    assert result is not None
    assert result["kline_data"][0][field] is None


@pytest.mark.parametrize("field", ["open", "high", "low", "close", "volume"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "1e309"])
@pytest.mark.parametrize(
    ("function_name", "key_name", "payload_factory"),
    [
        ("_fetch_with_twelve_data", "TWELVE_DATA_API_KEY", lambda row: {"status": "ok", "values": [row]}),
        ("_fetch_with_marketstack", "MARKETSTACK_API_KEY", lambda row: {"data": [row]}),
    ],
)
def test_json_history_providers_reject_non_finite_ohlcv(
    monkeypatch, function_name, key_name, payload_factory, field, value
):
    from backend.tools import price as module

    row = {
        "datetime": "2026-01-02T00:00:00Z",
        "date": "2026-01-02T00:00:00Z",
        "open": 1.0,
        "high": 2.0,
        "low": 0.5,
        "close": 1.5,
        "volume": 10.0,
    }
    row[field] = value
    monkeypatch.setattr(module, key_name, "test-key")
    monkeypatch.setattr(
        module,
        "_http_get",
        lambda *_args, **_kwargs: SimpleNamespace(status_code=200, json=lambda: payload_factory(row)),
    )

    result = getattr(module, function_name)("AAPL")

    assert result is not None
    assert result["kline_data"][0][field] is None


@pytest.mark.parametrize("field", ["open", "high", "low", "close", "volume"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "1e309"])
def test_massive_history_rejects_non_finite_ohlcv(monkeypatch, field, value):
    from backend.tools import price as module

    api_field = {"open": "o", "high": "h", "low": "l", "close": "c", "volume": "v"}[field]
    row = {"t": 1_767_312_000_000, "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 10.0}
    row[api_field] = value
    monkeypatch.setattr(module, "MASSIVE_API_KEY", "test-key")
    monkeypatch.setattr(
        module,
        "_http_get",
        lambda *_args, **_kwargs: SimpleNamespace(
            status_code=200,
            json=lambda: {"status": "OK", "results": [row]},
        ),
    )

    result = module._fetch_with_massive_io("AAPL")

    assert result is not None
    assert result["kline_data"][0][field] is None


@pytest.mark.parametrize("field", ["Open", "High", "Low", "Close", "Volume"])
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e309"])
def test_yahoo_scrape_history_rejects_non_finite_ohlcv(monkeypatch, field, value):
    from backend.tools import price as module

    row = {
        "Date": "2026-01-02",
        "Open": "1",
        "High": "2",
        "Low": "0.5",
        "Close": "1.5",
        "Adj Close": "1.5",
        "Volume": "10",
    }
    row[field] = value
    header = ",".join(row)
    text = header + "\n" + "\n".join([",".join(row.values())] * 5)
    monkeypatch.setattr(
        module,
        "_http_get",
        lambda *_args, **_kwargs: SimpleNamespace(status_code=200, text=text),
    )

    result = module._fetch_with_yahoo_scrape_historical("AAPL")

    assert result is not None
    expected = 0.0 if field == "Volume" else None
    assert result["kline_data"][0][field.lower()] == expected


def _history_frame(field, value):
    row = {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1000.0}
    row[field] = value
    return pd.DataFrame([row], index=pd.to_datetime(["2026-01-02"]))


@pytest.mark.parametrize("field", ["Open", "High", "Low", "Close", "Volume"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "1e309"])
def test_primary_yfinance_history_rejects_non_finite_ohlcv(monkeypatch, field, value):
    from backend.tools import price as module

    frame = _history_frame(field, value)
    monkeypatch.setattr(module, "ALPHA_VANTAGE_API_KEY", "")
    monkeypatch.setattr(module.yf, "Ticker", lambda _ticker: SimpleNamespace(history=lambda **_kwargs: frame))

    result = module.get_stock_historical_data("AAPL")

    assert result["kline_data"][0][field.lower()] is None


@pytest.mark.parametrize("field", ["o", "h", "l", "c", "v"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "1e309"])
def test_finnhub_history_rejects_non_finite_ohlcv(monkeypatch, field, value):
    from backend.tools import price as module

    response = {"s": "ok", "t": [1_767_312_000], "o": [100.0], "h": [101.0], "l": [99.0], "c": [100.0], "v": [1000.0]}
    response[field] = [value]
    monkeypatch.setattr(module, "ALPHA_VANTAGE_API_KEY", "")
    monkeypatch.setattr(module, "FINNHUB_API_KEY", "test-key")
    monkeypatch.setattr(
        module,
        "finnhub_client",
        SimpleNamespace(stock_candles=lambda *_args, **_kwargs: response),
    )
    monkeypatch.setattr(
        module.yf,
        "Ticker",
        lambda _ticker: SimpleNamespace(history=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("offline"))),
    )
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    result = module.get_stock_historical_data("AAPL")

    output_field = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}[field]
    assert result["kline_data"][0][output_field] is None


def test_empty_yfinance_history_continues_to_finnhub(monkeypatch):
    from backend.tools import price as module

    response = {"s": "ok", "t": [1_767_312_000], "o": [100.0], "h": [101.0], "l": [99.0], "c": [100.0], "v": [1000.0]}
    monkeypatch.setattr(module, "ALPHA_VANTAGE_API_KEY", "")
    monkeypatch.setattr(module, "FINNHUB_API_KEY", "test-key")
    monkeypatch.setattr(module, "finnhub_client", SimpleNamespace(stock_candles=lambda *_args, **_kwargs: response))
    monkeypatch.setattr(module.yf, "Ticker", lambda _ticker: SimpleNamespace(history=lambda **_kwargs: pd.DataFrame()))
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    result = module.get_stock_historical_data("AAPL")

    assert result["kline_data"][0]["close"] == 100.0


@pytest.mark.parametrize("field", ["Open", "High", "Low", "Close", "Volume"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "1e309"])
def test_index_yfinance_history_rejects_non_finite_ohlcv(monkeypatch, field, value):
    from backend.tools import price as module

    frame = _history_frame(field, value)
    calls = {"count": 0}

    def fake_ticker(_ticker):
        calls["count"] += 1
        if calls["count"] >= 4:
            return SimpleNamespace(history=lambda **_kwargs: frame)
        return SimpleNamespace(history=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("offline")))

    monkeypatch.setattr(module, "ALPHA_VANTAGE_API_KEY", "")
    monkeypatch.setattr(module, "FINNHUB_API_KEY", "")
    monkeypatch.setattr(module, "finnhub_client", None)
    monkeypatch.setattr(module, "_fetch_with_yahoo_scrape_historical", lambda *_args: None)
    monkeypatch.setattr(module.yf, "Ticker", fake_ticker)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)

    result = module.get_stock_historical_data("^GSPC")

    assert result["kline_data"][0][field.lower()] is None


@pytest.mark.parametrize("field", ["Open", "High", "Low", "Close", "Volume"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "1e309"])
def test_download_history_fallback_rejects_non_finite_ohlcv(monkeypatch, field, value):
    from backend.tools import price as module

    frame = _history_frame(field, value)
    monkeypatch.setattr(module, "ALPHA_VANTAGE_API_KEY", "")
    monkeypatch.setattr(module, "FINNHUB_API_KEY", "")
    monkeypatch.setattr(module, "finnhub_client", None)
    monkeypatch.setattr(
        module.yf,
        "Ticker",
        lambda _ticker: SimpleNamespace(history=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("offline"))),
    )
    monkeypatch.setattr(module.yf, "download", lambda *_args, **_kwargs: frame)
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    for name in (
        "_fetch_with_yahoo_scrape_historical",
        "_fetch_with_iex_cloud",
        "_fetch_with_tiingo",
        "_fetch_with_twelve_data",
        "_fetch_with_marketstack",
        "_fetch_with_massive_io",
        "_fetch_with_stooq_history",
    ):
        monkeypatch.setattr(module, name, lambda *_args, **_kwargs: None)

    result = module.get_stock_historical_data("AAPL")

    assert result["kline_data"][0][field.lower()] is None


@pytest.mark.parametrize("field", ["05. price", "09. change", "10. change percent"])
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e309"])
def test_alpha_vantage_quote_rejects_non_finite_fields(monkeypatch, field, value):
    from backend.tools import price as module

    quote = {"05. price": "100", "09. change": "1", "10. change percent": "1%"}
    quote[field] = f"{value}%" if field == "10. change percent" else value
    monkeypatch.setattr(
        module,
        "_http_get",
        lambda *_args, **_kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"Global Quote": quote},
        ),
    )

    assert module._fetch_with_alpha_vantage("AAPL") is None


@pytest.mark.parametrize("field", ["latest", "previous"])
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e309"])
def test_twelve_data_quote_rejects_non_finite_close(monkeypatch, field, value):
    from backend.tools import price as module

    values = [{"close": "100"}, {"close": "99"}]
    values[0 if field == "latest" else 1]["close"] = value
    monkeypatch.setattr(module, "TWELVE_DATA_API_KEY", "test-key")
    monkeypatch.setattr(
        module,
        "_http_get",
        lambda *_args, **_kwargs: SimpleNamespace(
            status_code=200,
            json=lambda: {"status": "ok", "values": values},
        ),
    )

    result = module._fetch_with_twelve_data_price("AAPL")

    if field == "latest":
        assert result is None
    else:
        assert result == "AAPL Current Price: $100.00"


@pytest.mark.parametrize("field", ["open", "high", "low", "close", "volume"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "1e309", 10**1000])
def test_historical_store_clean_handles_invalid_numeric_fields(field, value):
    from backend.services.historical_data_store import _clean

    row = {
        "date": "2026-01-02",
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.0,
        "volume": 1000.0,
    }
    row[field] = value

    result = _clean([row])

    if field == "close":
        assert result == []
    else:
        assert len(result) == 1
        expected = 0.0 if field == "volume" else 100.0
        assert result[0][field] == expected


@pytest.mark.parametrize(("field", "index"), [("open", 1), ("high", 2), ("low", 3), ("close", 4), ("volume", 5)])
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e309"])
def test_baostock_fetch_preserves_row_with_invalid_numeric_field(monkeypatch, field, index, value):
    from backend.services import historical_data_store as module

    values = ["2026-01-02", "100", "101", "99", "100", "1000"]
    values[index] = value

    class _Rows:
        error_code = "0"

        def __init__(self):
            self.remaining = 1

        def next(self):
            if self.remaining:
                self.remaining -= 1
                return True
            return False

        def get_row_data(self):
            return values

    fake = SimpleNamespace(
        login=lambda: None,
        logout=lambda: None,
        query_history_k_data_plus=lambda **_kwargs: _Rows(),
    )
    monkeypatch.setitem(sys.modules, "baostock", fake)

    result = module._fetch_baostock("600519.SS", "2026-01-01", "2026-01-03", "qfq")

    assert len(result) == 1
    assert result[0][field] is None


@pytest.mark.parametrize("field", ["c", "d", "dp"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "1e309"])
def test_finnhub_quote_rejects_non_finite_fields(monkeypatch, field, value):
    from backend.tools import price as module

    quote = {"c": 100.0, "d": 1.0, "dp": 1.0}
    quote[field] = value
    monkeypatch.setattr(module, "finnhub_client", SimpleNamespace(quote=lambda _ticker: quote))

    result = module._fetch_with_finnhub("AAPL")

    if field == "c":
        assert result is None
    else:
        assert result is not None
        assert "nan" not in result.lower()
        assert "inf" not in result.lower()
        expected_change = "$0.00" if field == "d" else "$1.00"
        expected_percent = "+0.00%" if field == "dp" else "+1.00%"
        assert expected_change in result
        assert expected_percent in result


@pytest.mark.parametrize("row_index", [0, 1])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "1e309"])
def test_yfinance_quote_rejects_non_finite_closes(monkeypatch, row_index, value):
    from backend.tools import price as module

    closes = [99.0, 100.0]
    closes[row_index] = value
    frame = pd.DataFrame({"Close": closes})
    monkeypatch.setattr(module.yf, "Ticker", lambda _ticker: SimpleNamespace(history=lambda **_kwargs: frame))

    result = module._fetch_with_yfinance("AAPL")

    if row_index == 1:
        assert result is None
    else:
        assert result == "AAPL Current Price: $100.00"


@pytest.mark.parametrize("field", ["regularMarketPrice", "previousClose"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "1e309"])
def test_yahoo_v8_quote_rejects_non_finite_fields(monkeypatch, field, value):
    from backend.tools import price as module

    meta = {"regularMarketPrice": 100.0, "previousClose": 99.0}
    meta[field] = value
    monkeypatch.setattr(
        module,
        "_http_get",
        lambda *_args, **_kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"chart": {"result": [{"meta": meta}]}},
        ),
    )

    result = module._fetch_yahoo_api_v8("AAPL")

    if field == "regularMarketPrice":
        assert result is None
    else:
        assert result == "AAPL Current Price: $100.00"


@pytest.mark.parametrize("row_index", [0, 1])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "1e309"])
def test_pandas_datareader_quote_rejects_non_finite_closes(monkeypatch, row_index, value):
    from backend.tools import price as module

    closes = [100.0, 99.0]
    closes[row_index] = value
    fake = SimpleNamespace(get_data_stooq=lambda *_args, **_kwargs: pd.DataFrame({"Close": closes}))
    monkeypatch.setitem(sys.modules, "pandas_datareader", fake)

    result = module._fetch_with_pandas_datareader("AAPL")

    if row_index == 0:
        assert result is None
    else:
        assert result == "AAPL Current Price: $100.00"


@pytest.mark.parametrize("field", ["regularMarketPrice", "regularMarketChange", "regularMarketChangePercent"])
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e309"])
def test_yahoo_scraped_quote_rejects_non_finite_fields(monkeypatch, field, value):
    from backend.tools import price as module

    values = {"regularMarketPrice": "100", "regularMarketChange": "1", "regularMarketChangePercent": "0.01"}
    values[field] = value
    html = "".join(
        f'<fin-streamer data-symbol="AAPL" data-field="{name}" value="{raw}"></fin-streamer>'
        for name, raw in values.items()
    )
    monkeypatch.setattr(
        module,
        "_http_get",
        lambda *_args, **_kwargs: SimpleNamespace(raise_for_status=lambda: None, text=html),
    )

    result = module._scrape_yahoo_finance("AAPL")

    if field == "regularMarketPrice":
        assert result is None
    else:
        assert result == "AAPL Current Price: $100.00"


@pytest.mark.parametrize("row_index", [0, 1])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "1e309"])
def test_index_quote_rejects_non_finite_closes(monkeypatch, row_index, value):
    from backend.tools import price as module

    closes = [99.0, 100.0]
    closes[row_index] = value
    monkeypatch.setattr(module.yf, "download", lambda *_args, **_kwargs: pd.DataFrame({"Close": closes}))
    monkeypatch.setattr(module, "_fetch_with_stooq_price", lambda _ticker: None)
    monkeypatch.setattr(module, "_fallback_price_value", lambda _ticker: None)

    result = module._fetch_index_price("^GSPC")

    assert result is None or ("nan" not in result.lower() and "inf" not in result.lower())
    if row_index == 0:
        assert result == "^GSPC Current Price: $100.00"
    elif isinstance(value, float) and math.isnan(value):
        assert result == "^GSPC Current Price: $99.00"
    else:
        assert result is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "1e309"])
def test_stooq_quote_rejects_non_finite_close(monkeypatch, value):
    from backend.tools import price as module

    monkeypatch.setattr(
        module,
        "_http_get",
        lambda *_args, **_kwargs: SimpleNamespace(
            status_code=200,
            json=lambda: {"symbols": [{"close": value}]},
        ),
    )

    assert module._fetch_with_stooq_price("AAPL") is None


@pytest.mark.parametrize("source", ["yfinance", "fallback"])
@pytest.mark.parametrize("row_index", [0, 1, 2])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "1e309"])
def test_performance_comparison_rejects_non_finite_prices(monkeypatch, source, row_index, value):
    from backend.tools import price as module

    dates = pd.to_datetime(["2025-08-01", "2026-01-01", "2026-07-31"])
    closes = [80.0, 90.0, 100.0]
    closes[row_index] = value
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    if source == "yfinance":
        frame = pd.DataFrame({"Close": closes}, index=dates)
        monkeypatch.setattr(module.yf, "Ticker", lambda _ticker: SimpleNamespace(history=lambda **_kwargs: frame))
        monkeypatch.setattr(module, "get_stock_historical_data", lambda *_args, **_kwargs: {"error": "unavailable"})
    else:
        monkeypatch.setattr(
            module.yf,
            "Ticker",
            lambda _ticker: SimpleNamespace(history=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("offline"))),
        )
        rows = [
            {"time": date.strftime("%Y-%m-%d"), "close": close}
            for date, close in zip(dates, closes)
        ]
        monkeypatch.setattr(module, "get_stock_historical_data", lambda *_args, **_kwargs: {"kline_data": rows})

    result = module.get_performance_comparison({"Index": "^TEST"})

    assert "nan" not in result.lower()
    assert "inf" not in result.lower()
    if row_index == 2:
        assert "N/A" in result
    elif row_index == 1:
        assert "YTD" in result and "N/A" in result
    else:
        assert "1-Year" in result and "N/A" in result


@pytest.mark.parametrize("value", ["invalid", None])
def test_dashboard_scorer_invalid_score_preserves_llm_content(value):
    from backend.dashboard.scorers import TechnicalScorer

    raw = json.dumps({"score": value, "summary": "preserved summary", "key_points": ["kept"]})
    card = TechnicalScorer()._parse_response(raw, {}, "2026-07-31T00:00:00+00:00")

    assert math.isfinite(card.score)
    assert card.summary == "preserved summary"
    assert card.key_points == ["kept"]


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e309", "invalid"])
def test_news_sentiment_rejects_non_finite_score(monkeypatch, value):
    from backend.tools import news as module

    monkeypatch.setattr(module, "ALPHA_VANTAGE_API_KEY", "test-key")
    monkeypatch.setattr(
        module,
        "_http_get",
        lambda *_args, **_kwargs: SimpleNamespace(
            json=lambda: {
                "feed": [
                    {
                        "title": "Headline",
                        "source": "Source",
                        "ticker_sentiment": [
                            {"ticker": "AAPL", "ticker_sentiment_score": value, "ticker_sentiment_label": "Neutral"}
                        ],
                    }
                ]
            }
        ),
    )

    result = module.get_news_sentiment("AAPL")

    assert "nan" not in result.lower()
    assert "inf" not in result.lower()
    assert "Neutral" in result


@pytest.mark.parametrize("field", ["Open", "High", "Low", "Close", "Volume"])
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_stooq_history_rejects_non_finite_ohlcv(monkeypatch, field, value):
    from backend.tools import price as module

    row = {"Date": "2026-01-02", "Open": "1", "High": "2", "Low": "0.5", "Close": "1.5", "Volume": "10"}
    row[field] = value
    csv_text = ",".join(row) + "\n" + ",".join(row.values())
    monkeypatch.setattr(module, "_http_get", lambda *_args, **_kwargs: SimpleNamespace(status_code=200, text=csv_text))

    result = module._fetch_with_stooq_history("AAPL")

    if field == "Close":
        assert result is None
    else:
        assert result is not None
        expected = 0.0 if field == "Volume" else None
        assert result["kline_data"][0][field.lower()] == expected


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_price_numeric_helpers_reject_non_finite_option_and_position_values(value):
    from backend.tools.price import _nearest_strike_iv, _normalize_positions, _safe_float_value

    option_frame = pd.DataFrame({"strike": [100.0], "impliedVolatility": [value]})

    assert _safe_float_value(value) is None
    assert _nearest_strike_iv(option_frame, 100.0) is None
    normalized = _normalize_positions([{"ticker": "AAPL", "weight": value, "quantity": value}])
    assert normalized == [{"ticker": "AAPL", "weight": 1.0, "quantity": None}]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_dashboard_numeric_labels_and_decay_default_non_finite_values(value):
    from backend.dashboard.data_service import _calculate_time_decay, _label_fear_greed

    assert _label_fear_greed(value) == "neutral"
    assert math.isfinite(_calculate_time_decay("2026-01-01T00:00:00+00:00", half_life_hours=value))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_chart_detector_defaults_non_finite_confidence(value):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from backend.api.market_router import MarketRouterDeps, create_market_router

    deps = MarketRouterDeps(
        get_orchestrator_safe=lambda: None,
        get_stock_price=lambda _ticker: {},
        get_company_news=lambda _ticker: [],
        get_financial_statements=lambda _ticker: {},
        get_financial_statements_summary=lambda _ticker: {},
        get_stock_historical_data=lambda *_args, **_kwargs: {},
        detect_chart_type=lambda *_args: {"chart_type": "line", "confidence": value},
        logger=None,
    )
    app = FastAPI()
    app.include_router(create_market_router(deps))

    with TestClient(app) as client:
        response = client.post("/api/chart/detect", json={"query": "AAPL chart"})

    assert response.status_code == 200
    assert response.json()["confidence"] == 0.0
    assert response.json()["should_generate"] is False


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_risk_score_ignores_non_finite_signal_severity(value):
    from backend.agents.risk_agent import RiskAgent, RiskSignal

    signal = RiskSignal("test", "technical", "risk", value)

    assert RiskAgent._score_signals([signal]) == 0.0


@pytest.mark.parametrize("field", ["iv_atm", "put_call_ratio_oi", "iv_skew_25d"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_price_agent_drops_non_finite_option_metrics_from_text(field, value):
    from backend.agents.price_agent import PriceAgent

    agent = PriceAgent(None, None, None)
    agent._last_option_metrics = {"source": "test", field: value}

    summary = agent._deterministic_summary({"ticker": "AAPL", "price": 100.0})
    output = agent._format_output(summary, {"ticker": "AAPL", "price": 100.0, "source": "test"})

    assert "nan" not in summary.lower()
    assert "inf" not in summary.lower()
    assert "nan" not in output.evidence[-1].text.lower()
    assert "inf" not in output.evidence[-1].text.lower()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_price_agent_drops_non_finite_change_percent(value):
    from backend.agents.price_agent import PriceAgent

    summary = PriceAgent(None, None, None)._deterministic_summary(
        {"ticker": "AAPL", "price": 100.0, "change_percent": value}
    )

    assert "nan" not in summary.lower()
    assert "inf" not in summary.lower()


class _SubscriptionStub:
    def __init__(self):
        self.payload = None

    def get_subscriptions(self, _email):
        return []

    def subscribe(self, **kwargs):
        self.payload = kwargs
        return True


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
async def test_alert_action_rejects_non_finite_target(monkeypatch, value):
    module = importlib.import_module("backend.graph.nodes.alert_action")

    service = _SubscriptionStub()
    monkeypatch.setattr(module, "get_subscription_service", lambda: service)

    result = await module.alert_action(
        {
            "user_email": "user@example.com",
            "alert_params": {"ticker": "AAPL", "alert_mode": "price_target", "price_target": value},
        }
    )

    assert result["alert_valid"] is False
    assert service.payload is None


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
async def test_alert_action_ignores_non_finite_current_price(monkeypatch, value):
    module = importlib.import_module("backend.graph.nodes.alert_action")

    service = _SubscriptionStub()
    monkeypatch.setattr(module, "get_subscription_service", lambda: service)
    monkeypatch.setattr(module, "fetch_price_snapshot", lambda _ticker: SimpleNamespace(price=value))

    result = await module.alert_action(
        {
            "user_email": "user@example.com",
            "alert_params": {
                "ticker": "AAPL",
                "alert_mode": "price_target",
                "price_target": 120.0,
                "direction": None,
            },
        }
    )

    assert result["alert_valid"] is True
    assert service.payload["direction"] == "above"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "1e309"])
def test_sec_companyfacts_ignores_non_finite_metric(value):
    from backend.tools.sec import _extract_companyfacts_metric

    payload = {
        "facts": {
            "us-gaap": {
                "Revenue": {
                    "units": {
                        "USD": [
                            {
                                "form": "10-Q",
                                "fp": "Q1",
                                "start": "2026-01-01",
                                "end": "2026-03-31",
                                "filed": "2026-04-20",
                                "val": value,
                            }
                        ]
                    }
                }
            }
        }
    }

    assert _extract_companyfacts_metric(payload, concepts=("Revenue",), unit_candidates=("USD",)) == {}
