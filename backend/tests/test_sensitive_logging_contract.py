import ast
import re
from collections import Counter
from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parents[2]

SECURITY_HARDENING_ROUNDS_701_800 = [
    ("R701", "backend/api/system_router.py", '"query_preview"'),
    ("R702", "backend/api/system_router.py", '"fallback_reason"'),
    ("R703", "backend/api/system_router.py", '"chunk_preview"'),
    ("R704", "backend/api/system_router.py", '"observability": observability if include_raw else _project_rag_observability(observability)'),
    ("R705", "backend/api/system_router.py", "payload = _rag_store().list_events"),
    ("R706", "backend/api/system_router.py", "payload = _rag_store().list_hits"),
    ("R707", "backend/api/system_router.py", '"data": _redact_rag_payload(result, include_raw=include_raw)'),
    ("R708", "backend/llm_config.py", 'logger.info("[LLM Rotation] select endpoint")'),
    ("R709", "backend/llm_config.py", "[LLM Rotation] select endpoint"),
    ("R710", "backend/agents/base_agent.py", "Tool-aware search succeeded"),
    ("R711", "backend/agents/base_agent.py", "Tool-aware search failed"),
    ("R712", "backend/agents/base_agent.py", "Fallback search succeeded"),
    ("R713", "backend/agents/deep_search_agent.py", "[DeepSearch] queries built"),
    ("R714", "backend/agents/deep_search_agent.py", "[DeepSearch] search started"),
    ("R715", "backend/agents/deep_search_agent.py", "[DeepSearch] documents fetched"),
    ("R716", "backend/agents/deep_search_agent.py", "[DeepSearch] document inspected"),
    ("R717", "backend/api/chart_detector.py", "查询已接收"),
    ("R718", "backend/tools/cn_hk_market.py", "eastmoney request failed"),
    ("R719", "backend/tools/cn_hk_market.py", "quote text request failed"),
    ("R720", "backend/tools/earnings_transcripts.py", "Search failed: %s"),
    ("R721", "backend/tools/local_disclosure.py", "Search failed: %s"),
    ("R722", "backend/tools/news.py", "Search failed: %s"),
    ("R723", "backend/tools/price.py", "Yahoo Finance request failed: %s"),
    ("R724", "backend/llm_config.py", "endpoint cooling down"),
    ("R725", "backend/api/market_router.py", "[API] price cache hit"),
    ("R726", "backend/api/market_router.py", '_log_warning("[API] get_price failed", exc)'),
    ("R727", "backend/api/market_router.py", '_log_warning("[API] get_news failed", exc)'),
    ("R728", "backend/api/market_router.py", '_log_warning("[API] get_financials failed", exc)'),
    ("R729", "backend/api/market_router.py", '_log_warning("[API] get_financials_summary failed", exc)'),
    ("R730", "backend/api/market_router.py", "[API] kline cache hit"),
    ("R731", "backend/api/market_router.py", '_log_warning("[API] get_kline_data failed", exc)'),
    ("R732", "backend/api/market_router.py", "[API] intraday cache hit"),
    ("R733", "backend/api/market_router.py", '_log_warning("[API] get_intraday_data failed", exc)'),
    ("R734", "backend/api/market_router.py", '_log_export_error("historical kline error", e)'),
    ("R735", "backend/services/datasource_monitor.py", "[Monitor] source degraded"),
    ("R736", "backend/services/health_probe.py", "[HealthProbe] check ok"),
    ("R737", "backend/services/health_probe.py", "[HealthProbe] check failed"),
    ("R738", "backend/services/execution_service.py", "[execution_service] graph timeout"),
    ("R739", "backend/services/memory.py", "Corrupt profile moved to backup (%s)"),
    ("R740", "backend/services/memory.py", "Error saving profile (%s)"),
    ("R741", "backend/graph/store.py", "[graph.store] load profile failed"),
    ("R742", "backend/graph/store.py", "[graph.store] load profile before persist failed"),
    ("R743", "backend/graph/store.py", "[graph.store] persist profile failed"),
    ("R744", "backend/services/risk_snapshot_scheduler.py", "Failed to snapshot portfolio: %s"),
    ("R745", "backend/dashboard/data_service.py", "[DataService] Finnhub request failed"),
    ("R746", "backend/dashboard/peer_service.py", "[PeerService] Finnhub request failed"),
    ("R747", "backend/handlers/chat_handler.py", "[ChatHandler] ticker lookup failed"),
    ("R748", "backend/handlers/chat_handler.py", "Direct price fetch failed: %s"),
    ("R749", "backend/handlers/chat_handler.py", "[ChatHandler] Kline fallback failed"),
    ("R750", "backend/handlers/chat_handler.py", "NewsAgent failed: %s"),
    ("R751", "backend/handlers/chat_handler.py", "DeepSearch news failed: %s"),
    ("R752", "backend/handlers/chat_handler.py", "Company news fetch failed: %s"),
    ("R753", "backend/handlers/chat_handler.py", "Financial report query failed: %s"),
    ("R754", "backend/handlers/chat_handler.py", "News sentiment fetch failed: %s"),
    ("R755", "backend/handlers/chat_handler.py", "Company info fetch failed: %s"),
    ("R756", "backend/handlers/chat_handler.py", "Composition search failed: %s"),
    ("R757", "backend/api/dashboard_router.py", "[Dashboard] Resolved asset"),
    ("R758", "backend/api/morning_brief_router.py", "[MorningBrief] price fetch failed"),
    ("R759", "backend/api/morning_brief_router.py", "[MorningBrief] news fetch failed"),
    ("R760", "backend/api/portfolio_router.py", "[portfolio] quote timeout"),
    ("R761", "backend/api/portfolio_router.py", "[portfolio] quote failed"),
    ("R762", "backend/api/rebalance_router.py", "[rebalance] failed to load live price"),
    ("R763", "backend/api/rebalance_router.py", "[rebalance] failed to load sector"),
    ("R764", "backend/api/research_router.py", "获取财报失败"),
    ("R765", "backend/api/research_router.py", "company info unavailable"),
    ("R766", "backend/api/research_router.py", "获取新闻失败"),
    ("R767", "backend/api/research_router.py", "stock price unavailable"),
    ("R768", "backend/api/research_router.py", "company news unavailable"),
    ("R769", "backend/api/research_router.py", "top list unavailable"),
    ("R770", "backend/api/research_router.py", "margin trading unavailable"),
    ("R771", "backend/services/alert_scheduler.py", 'Price fetch failed'),
    ("R772", "backend/services/alert_scheduler.py", 'Email send raised'),
    ("R773", "backend/services/alert_scheduler.py", "Email send failed"),
    ("R774", "backend/services/alert_scheduler.py", 'News fetch failed'),
    ("R775", "backend/services/alert_scheduler.py", 'News email send raised'),
    ("R776", "backend/services/alert_scheduler.py", "News email send failed"),
    ("R777", "backend/services/alert_scheduler.py", 'Risk price fetch failed'),
    ("R778", "backend/services/alert_scheduler.py", 'Risk email send raised'),
    ("R779", "backend/services/alert_scheduler.py", "Risk email send failed"),
    ("R780", "backend/services/alert_scheduler.py", "yfinance news failed: %s"),
    ("R781", "backend/services/alert_scheduler.py", "finnhub news failed: %s"),
    ("R782", "backend/services/alert_scheduler.py", "alpha vantage news failed: %s"),
    ("R783", "backend/services/alert_scheduler.py", 'yfinance quote fetch failed'),
    ("R784", "backend/services/alert_scheduler.py", 'Yahoo quote fetch failed'),
    ("R785", "backend/services/alert_scheduler.py", 'Stooq history fetch failed'),
    ("R786", "backend/services/alert_scheduler.py", 'Stooq quote fetch failed'),
    ("R787", "backend/services/alert_scheduler.py", 'Yahoo chart fetch failed'),
    ("R788", "backend/dashboard/insights_engine.py", "[Insights] Overall timeout, using fallbacks"),
    ("R789", "backend/dashboard/insights_engine.py", "[Insights] Background refresh completed"),
    ("R790", "backend/dashboard/insights_engine.py", "[Insights] Background refresh failed"),
    ("R791", "backend/dashboard/insights_engine.py", "[Insights] fetch timeout"),
    ("R792", "backend/dashboard/insights_engine.py", "[Insights] fetch failed"),
    ("R793", "backend/dashboard/peer_service.py", "[PeerService] yfinance info failed"),
    ("R794", "backend/dashboard/peer_service.py", "[PeerService] peer fetch failed"),
    ("R795", "backend/dashboard/peer_service.py", "global timeout while fetching peers"),
    ("R796", "backend/dashboard/peer_service.py", "[PeerService] fetch_peer_comparison failed"),
    ("R797", "backend/dashboard/scorers.py", "[Insights] scorer timed out"),
    ("R798", "backend/dashboard/scorers.py", "[Insights] scorer failed"),
    ("R799", "backend/services/historical_data_store.py", "baostock 拉取失败: %s"),
    ("R800", "backend/services/historical_data_store.py", 'historical fallback failed'),
]


@pytest.mark.parametrize(
    ("_round", "relative_path", "needle"),
    SECURITY_HARDENING_ROUNDS_701_800,
    ids=[item[0] for item in SECURITY_HARDENING_ROUNDS_701_800],
)
def test_round_701_800_has_source_binding(_round, relative_path, needle):
    source = (_ROOT / relative_path).read_text(encoding="utf-8-sig")
    assert needle in source


def test_rounds_701_through_800_are_complete_and_unique():
    actual = [item[0] for item in SECURITY_HARDENING_ROUNDS_701_800]
    expected = [f"R{number}" for number in range(701, 801)]

    assert len(actual) == len(set(actual)) == 100
    assert actual == expected


SECURITY_HARDENING_ROUNDS_801_900 = [
    ("R801", "backend/dashboard/cache.py", "Invalidated symbol cache entries"),
    ("R802", "backend/dashboard/data_service.py", "[DataService] fetch_market_chart failed"),
    ("R803", "backend/dashboard/data_service.py", "[DataService] fetch_snapshot failed"),
    ("R804", "backend/dashboard/data_service.py", "[DataService] fetch_revenue_trend failed"),
    ("R805", "backend/dashboard/data_service.py", "[DataService] fetch_segment_mix failed"),
    ("R806", "backend/dashboard/data_service.py", "[DataService] get_company_news failed"),
    ("R807", "backend/dashboard/data_service.py", "[DataService] fetch_news failed"),
    ("R808", "backend/dashboard/data_service.py", "[DataService] fetch_sector_weights failed"),
    ("R809", "backend/dashboard/data_service.py", "[DataService] fetch_top_constituents failed"),
    ("R810", "backend/dashboard/data_service.py", "[DataService] fetch_holdings failed"),
    ("R811", "backend/dashboard/data_service.py", "[DataService] CN/HK OHLCV fallback failed"),
    ("R812", "backend/dashboard/data_service.py", "[DataService] yfinance OHLCV failed"),
    ("R813", "backend/dashboard/data_service.py", "[DataService] OHLCV fallback hit via Stooq"),
    ("R814", "backend/dashboard/data_service.py", "[DataService] Stooq OHLCV fallback failed"),
    ("R815", "backend/dashboard/data_service.py", "[DataService] OHLCV fallback hit via price pipeline"),
    ("R816", "backend/dashboard/data_service.py", "[DataService] fallback OHLCV failed"),
    ("R817", "backend/dashboard/data_service.py", "[DataService] CN/HK valuation fallback failed"),
    ("R818", "backend/dashboard/data_service.py", "[DataService] SEC companyfacts fallback failed"),
    ("R819", "backend/dashboard/data_service.py", "[DataService] CN/HK financials fallback failed"),
    ("R820", "backend/dashboard/data_service.py", "[DataService] valuation fallback via CN/HK source"),
    ("R821", "backend/dashboard/data_service.py", "[DataService] fetch_valuation failed"),
    ("R822", "backend/dashboard/data_service.py", "[DataService] valuation fallback via Finnhub"),
    ("R823", "backend/dashboard/data_service.py", "[DataService] valuation late fallback via CN/HK source"),
    ("R824", "backend/dashboard/data_service.py", "[DataService] financials fallback via CN/HK source"),
    ("R825", "backend/dashboard/data_service.py", "[DataService] financials empty-period fallback via SEC companyfacts"),
    ("R826", "backend/dashboard/data_service.py", "[DataService] financials empty-period fallback via Finnhub"),
    ("R827", "backend/dashboard/data_service.py", "[DataService] financials empty-result fallback via SEC companyfacts"),
    ("R828", "backend/dashboard/data_service.py", "[DataService] financials empty-result fallback via Finnhub"),
    ("R829", "backend/dashboard/data_service.py", "[DataService] fetch_financial_statements failed"),
    ("R830", "backend/dashboard/data_service.py", "[DataService] financials exception fallback via SEC companyfacts"),
    ("R831", "backend/dashboard/data_service.py", "[DataService] financials exception fallback via Finnhub"),
    ("R832", "backend/dashboard/data_service.py", "[DataService] fetch_technical_indicators failed"),
    ("R833", "backend/dashboard/data_service.py", "[DataService] fetch_indicator_series failed"),
    ("R834", "backend/dashboard/data_service.py", "[DataService] fetch_earnings_history failed"),
    ("R835", "backend/dashboard/data_service.py", "[DataService] fetch_analyst_targets failed"),
    ("R836", "backend/dashboard/data_service.py", "[DataService] fetch_recommendations failed"),
    ("R837", "backend/services/historical_data_store.py", "kline cache hit"),
    ("R838", "backend/services/rebalance_llm_enhancer.py", '[rebalance-enhancer] news fetch failed'),
    ("R839", "backend/services/rebalance_llm_enhancer.py", '[rebalance-enhancer] info fetch failed'),
    ("R840", "backend/services/report_generator.py", "[ResearchReport] LLM调用失败"),
    ("R841", "backend/services/risk_attribution.py", "_fetch_returns failed: %s"),
    ("R842", "backend/services/smart_cache.py", "[SmartCache] ttl resolved"),
    ("R843", "backend/services/subscription_service.py", "Subscription created"),
    ("R844", "backend/services/subscription_service.py", "Subscription removed"),
    ("R845", "backend/services/subscription_service.py", "Subscription status updated for single ticker"),
    ("R846", "backend/tools/baostock_provider.py", '[BaoStock] history failed'),
    ("R847", "backend/tools/financial.py", "[Financials] SEC companyfacts fallback hit"),
    ("R848", "backend/tools/financial.py", "[Financials] SEC companyfacts fallback failed: %s"),
    ("R849", "backend/tools/financial.py", "[Financials] statement fetch succeeded"),
    ("R850", "backend/tools/financial.py", "yfinance info fetch failed: %s"),
    ("R851", "backend/tools/financial.py", "Trying Finnhub for company info"),
    ("R852", "backend/tools/financial.py", "Trying Alpha Vantage for company info"),
    ("R853", "backend/tools/financial.py", "Falling back to web search for company info"),
    ("R854", "backend/tools/financial.py", "[EarningsEstimates] fetch failed: %s"),
    ("R855", "backend/tools/fmp.py", "[FMP] revenue_product_segmentation OK: %s segments"),
    ("R856", "backend/tools/fmp.py", "[FMP] revenue_geographic_segmentation OK: %s regions"),
    ("R857", "backend/tools/fmp.py", "[FMP] etf_sector_weights OK: %s sectors"),
    ("R858", "backend/tools/fmp.py", "[FMP] etf_holdings OK: %s holdings"),
    ("R859", "backend/tools/fmp.py", "[FMP] Unknown index symbol"),
    ("R860", "backend/tools/fmp.py", "[FMP] index_constituents OK: %s constituents"),
    ("R861", "backend/tools/fmp.py", "[FMP] company_profile OK"),
    ("R862", "backend/tools/news.py", "yfinance index news error: %s"),
    ("R863", "backend/tools/news.py", "yfinance company news error: %s"),
    ("R864", "backend/tools/news.py", "Trying Finnhub company news"),
    ("R865", "backend/tools/news.py", "Trying Alpha Vantage company news"),
    ("R866", "backend/tools/news.py", "Falling back to company news search"),
    ("R867", "backend/tools/news.py", "[News] get_event_calendar yfinance failed: %s"),
    ("R868", "backend/tools/price.py", "  - Attempting Alpha Vantage API..."),
    ("R869", "backend/tools/price.py", "  - Attempting Finnhub API..."),
    ("R870", "backend/tools/price.py", "  - Attempting yfinance..."),
    ("R871", "backend/tools/price.py", "  - Attempting Twelve Data..."),
    ("R872", "backend/tools/price.py", "  - Attempting Yahoo Finance API v8..."),
    ("R873", "backend/tools/price.py", "  - Attempting Google Finance..."),
    ("R874", "backend/tools/price.py", "  - Attempting CNBC..."),
    ("R875", "backend/tools/price.py", "  - Attempting pandas_datareader..."),
    ("R876", "backend/tools/price.py", "  - Attempting to scrape Yahoo Finance..."),
    ("R877", "backend/tools/price.py", "  - Attempting index price via yfinance.download..."),
    ("R878", "backend/tools/price.py", "stooq price fallback failed: %s"),
    ("R879", "backend/tools/price.py", "  - Attempting to find price via search..."),
    ("R880", "backend/tools/price.py", "Fetching price with multi-source strategy..."),
    ("R881", "backend/tools/price.py", "  [CN] Normalized ticker to Yahoo format"),
    ("R882", "backend/tools/price.py", "[get_stock_historical_data] 尝试从 Yahoo Finance 网页抓取..."),
    ("R883", "backend/tools/price.py", "[get_stock_historical_data] 尝试使用 IEX Cloud..."),
    ("R884", "backend/tools/price.py", "[get_stock_historical_data] 尝试使用 Tiingo..."),
    ("R885", "backend/tools/price.py", "[get_stock_historical_data] Tiingo 不支持该证券，跳过"),
    ("R886", "backend/tools/price.py", "[get_stock_historical_data] 尝试使用 Twelve Data..."),
    ("R887", "backend/tools/price.py", "[get_stock_historical_data] 尝试使用 Marketstack..."),
    ("R888", "backend/tools/price.py", "[get_stock_historical_data] 尝试使用 Massive.com..."),
    ("R889", "backend/tools/price.py", "historical stooq price fallback failed: %s"),
    ("R890", "backend/tools/price.py", "[get_stock_historical_data] Stooq 指数兜底命中，返回日线数据"),
    ("R891", "backend/tools/price.py", "[get_stock_historical_data] 尝试使用 yfinance..."),
    ("R892", "backend/tools/price.py", "[get_stock_historical_data] 检测到指数代码，尝试使用 yfinance 专门获取指数数据..."),
    ("R893", "backend/tools/price.py", "[get_stock_historical_data] yfinance 成功获取指数数据"),
    ("R894", "backend/tools/price.py", "[Options] get_option_chain_metrics failed: %s"),
    ("R895", "backend/tools/sec.py", "[SEC] get_sec_filings failed: %s"),
    ("R896", "backend/tools/sec.py", "[SEC] get_sec_risk_factors failed: %s"),
    ("R897", "backend/tools/sec.py", "[SEC] get_sec_company_facts_quarterly failed: %s"),
    ("R898", "backend/tools/tencent_provider.py", "[Tencent] quote HTTP %d"),
    ("R899", "backend/tools/tencent_provider.py", "[Tencent] quote 字段不足: %d fields"),
    ("R900", "backend/tools/tencent_provider.py", "[Tencent] quote 获取失败: %s"),
]


def _matching_log_calls(relative_path: str, message: str) -> list[ast.Call]:
    source = (_ROOT / relative_path).read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    matches: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"debug", "info", "warning", "error", "exception", "critical"}:
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        if node.args[0].value == message:
            matches.append(node)
    return matches


@pytest.mark.parametrize(
    ("_round", "relative_path", "message"),
    SECURITY_HARDENING_ROUNDS_801_900,
    ids=[item[0] for item in SECURITY_HARDENING_ROUNDS_801_900],
)
def test_round_801_900_removes_instrument_identifiers_from_log_calls(
    _round,
    relative_path,
    message,
):
    calls = _matching_log_calls(relative_path, message)
    assert calls, f"missing log call: {relative_path}: {message}"

    sensitive_names = {"ticker", "symbol", "normalized_ticker", "stock_code"}
    for call in calls:
        logged_names = {
            child.id
            for argument in call.args[1:]
            for child in ast.walk(argument)
            if isinstance(child, ast.Name)
        }
        assert logged_names.isdisjoint(sensitive_names)


def test_rounds_801_through_900_are_complete_unique_and_source_bound():
    actual = [item[0] for item in SECURITY_HARDENING_ROUNDS_801_900]
    expected = [f"R{number}" for number in range(801, 901)]
    bindings = [(item[1], item[2]) for item in SECURITY_HARDENING_ROUNDS_801_900]

    assert len(actual) == len(set(actual)) == 100
    assert actual == expected
    assert len(bindings) == len(set(bindings)) == 100


SECURITY_HARDENING_ROUNDS_901_1000 = [
    ("R901", "backend/tools/tencent_provider.py", "[Tencent] K线 HTTP %d", "symbol"),
    ("R902", "backend/tools/tencent_provider.py", "[Tencent] K线返回错误", "symbol"),
    ("R903", "backend/tools/tencent_provider.py", "[Tencent] K线返回错误", "data"),
    ("R904", "backend/tools/tencent_provider.py", "[Tencent] K线数据为空", "symbol"),
    ("R905", "backend/tools/tencent_provider.py", "[Tencent] K线获取失败: %s", "symbol"),
    ("R906", "backend/tools/tencent_provider.py", "[Tencent] 分时 HTTP %d", "symbol"),
    ("R907", "backend/tools/tencent_provider.py", "[Tencent] 分时返回错误", "symbol"),
    ("R908", "backend/tools/tencent_provider.py", "[Tencent] 分时返回错误", "data"),
    ("R909", "backend/tools/tencent_provider.py", "[Tencent] 分时数据格式错误", "symbol"),
    ("R910", "backend/tools/tencent_provider.py", "[Tencent] 分时数据为空", "symbol"),
    ("R911", "backend/tools/tencent_provider.py", "[Tencent] 分时获取失败: %s", "symbol"),
    ("R912", "backend/tools/tencent_provider.py", "[Eastmoney] top list record is stale", "symbol"),
    ("R913", "backend/tools/tencent_provider.py", "[Eastmoney] top list record is stale", "trade_date"),
    ("R914", "backend/tools/tencent_provider.py", "[Eastmoney] new top list lookup failed: %s", "symbol"),
    ("R915", "backend/tools/tencent_provider.py", "[东方财富] 龙虎榜 HTTP %d", "symbol"),
    ("R916", "backend/tools/tencent_provider.py", "[东方财富] 龙虎榜数据解析失败", "symbol"),
    ("R917", "backend/tools/tencent_provider.py", "[东方财富] 龙虎榜无数据", "symbol"),
    ("R918", "backend/tools/tencent_provider.py", "[东方财富] 龙虎榜未找到记录", "symbol"),
    ("R919", "backend/tools/tencent_provider.py", "[东方财富] 龙虎榜获取失败: %s", "symbol"),
    ("R920", "backend/tools/tencent_provider.py", "[东方财富] 席位明细 HTTP %d", "stock_code"),
    ("R921", "backend/tools/tencent_provider.py", "[东方财富] 席位明细获取失败: %s", "stock_code"),
    ("R922", "backend/tools/tencent_provider.py", "[Eastmoney] new top list history lookup failed: %s", "symbol"),
    ("R923", "backend/tools/tencent_provider.py", "[东方财富] 龙虎榜历史 HTTP %d", "symbol"),
    ("R924", "backend/tools/tencent_provider.py", "[东方财富] 龙虎榜历史数据解析失败", "symbol"),
    ("R925", "backend/tools/tencent_provider.py", "[东方财富] 龙虎榜历史获取失败: %s", "symbol"),
    ("R926", "backend/tools/tencent_provider.py", "[Eastmoney] new margin trading lookup failed: %s", "symbol"),
    ("R927", "backend/tools/tencent_provider.py", "[东方财富] 融资融券 HTTP %d", "symbol"),
    ("R928", "backend/tools/tencent_provider.py", "[东方财富] 融资融券返回错误", "symbol"),
    ("R929", "backend/tools/tencent_provider.py", "[东方财富] 融资融券无数据", "symbol"),
    ("R930", "backend/tools/tencent_provider.py", "[东方财富] 融资融券获取失败: %s", "symbol"),
    ("R931", "backend/tools/tencent_provider.py", "[Eastmoney] new margin trading history lookup failed: %s", "symbol"),
    ("R932", "backend/tools/tencent_provider.py", "[东方财富] 融资融券历史 HTTP %d", "symbol"),
    ("R933", "backend/tools/tencent_provider.py", "[东方财富] 融资融券历史返回错误", "symbol"),
    ("R934", "backend/tools/tencent_provider.py", "[东方财富] 融资融券历史获取失败: %s", "symbol"),
    ("R935", "backend/api/portfolio_router.py", "获取历史数据失败", "t"),
    ("R936", "backend/tools/financial.py", "OpenFIGI lookup failed: %s", "company"),
    ("R937", "backend/tools/financial.py", "Finnhub symbol lookup failed: %s", "company"),
    ("R938", "backend/tools/financial.py", "EODHD lookup failed: %s", "company"),
    ("R939", "backend/tools/news.py", "  → Detected market index", "friendly_name"),
    ("R940", "backend/tools/news.py", "[MarketNews] fetch_news_articles failed: %s", "idx_ticker"),
    ("R941", "backend/tools/news.py", "[MarketNews] search failed: %s", "q"),
    ("R942", "backend/tools/news.py", "[MarketNews] retry search failed: %s", "q"),
    ("R943", "backend/tools/macro.py", "[FRED] Failed to fetch series: %s", "sid"),
    ("R944", "backend/tools/search.py", "[Search] 维基百科获取页面失败: %s", "page_title"),
    ("R945", "backend/api/entitlements_router.py", "[Audit] admin set plan completed", "request.user_id"),
    ("R946", "backend/api/entitlements_router.py", "[Audit] admin set plan completed", "normalized"),
    ("R947", "backend/api/entitlements_router.py", "[Audit] admin set plan completed", "current_user.user_id"),
    ("R948", "backend/api/subscription_router.py", "[Audit] admin subscription list completed", "current_user.user_id"),
    ("R949", "backend/api/subscription_router.py", "[Audit] admin subscription list completed", "current_user.role"),
    ("R950", "backend/dashboard/cache.py", "Cache expired", "key"),
    ("R951", "backend/dashboard/cache.py", "Cache hit", "key"),
    ("R952", "backend/dashboard/cache.py", "Cache hit (fresh)", "key"),
    ("R953", "backend/dashboard/cache.py", "Cache hit (stale)", "key"),
    ("R954", "backend/dashboard/cache.py", "Cache expired beyond stale window", "key"),
    ("R955", "backend/dashboard/cache.py", "Cache set", "key"),
    ("R956", "backend/personas/registry.py", "[personas] file does not contain a mapping; skipped", "path.name"),
    ("R957", "backend/personas/registry.py", '[personas] failed to parse file', "path.name"),
    ("R958", "backend/personas/registry.py", "[personas] duplicate id; overriding", "persona.id"),
    ("R959", "backend/personas/registry.py", "[personas] duplicate id; overriding", "yaml_path.name"),
    ("R960", "backend/services/chat_history.py", 'Backed up corrupt chat history file', "path.name"),
    ("R961", "backend/api/main.py", "[Config] wrote default user config", "USER_CONFIG_PATH"),
    ("R962", "backend/services/monitoring_storage.py", "监控数据库初始化完成", "self.db_path"),
    ("R963", "backend/services/notes_rag.py", "vectorize_note failed: %s", "note_id"),
    ("R964", "backend/services/research_notes.py", 'note vectorization failed', "note_id"),
    ("R965", "backend/services/research_notes.py", 'note re-vectorization failed', "note_id"),
    ("R966", "backend/services/report_index.py", 'stored report payload parse failed', "report_id"),
    ("R967", "backend/services/report_index.py", 'stored report citation parse failed', "report_id"),
    ("R968", "backend/services/report_index.py", 'stored report trace digest parse failed', "report_id"),
    ("R969", "backend/agents/deep_search_agent.py", "[DeepSearch] document inspected", "host"),
    ("R970", "backend/agents/deep_search_agent.py", "[DeepSearch] Blocked unsafe url or fetch failed", "self._normalized_domain_from_url(url)"),
    ("R971", "backend/agents/deep_search_agent.py", "[DeepSearch] Jina fallback succeeded", "domain"),
    ("R972", "backend/agents/deep_search_agent.py", "[DeepSearch] Wayback fallback succeeded", "domain"),
    ("R973", "backend/security/pinned_http.py", "[pinned_http] too many redirects", "_safe_log_host(url)"),
    ("R974", "backend/tools/authoritative_feeds.py", 'authoritative feed request failed', "_normalize_domain(url)"),
    ("R975", "backend/tools/macro_official.py", "official feed request failed: %s", "_normalize_domain(url)"),
    ("R976", "backend/tools/news.py", "news RSS request failed: %s", "_domain_from_url(url)"),
    ("R977", "backend/tools/jina_reader.py", "[JinaReader] fetch failed: %s", "_safe_log_host(target)"),
    ("R978", "backend/tools/wayback.py", "[Wayback] fetch failed: %s", "_normalize_domain(snapshot_url)"),
    ("R979", "backend/tools/web.py", "[fetch_url_content] Blocked unsafe url or fetch failed", "_safe_log_host(url)"),
    ("R980", "backend/tools/web.py", "[fetch_url_content] 成功抓取 (%s 字符)", "_safe_log_host(url)"),
    ("R981", "backend/tools/web.py", "[fetch_url_content] 超时", "_safe_log_host(url)"),
    ("R982", "backend/tools/web.py", "[fetch_url_content] 请求失败: error=%s", "_safe_log_host(url)"),
    ("R983", "backend/tools/web.py", "[fetch_url_content] 解析失败: error=%s", "_safe_log_host(url)"),
    ("R984", "backend/orchestration/orchestrator.py", "[Orchestrator] data validation failed: issue_count=%d", "validation.issues"),
    ("R985", "backend/tools/fmp.py", "[FMP] API returned an error payload", "data"),
    ("R986", "backend/tools/screener.py", "Alpha Vantage top movers unavailable", "raw"),
    ("R987", "backend/tools/fmp.py", "[FMP] Request timeout", "endpoint"),
    ("R988", "backend/tools/fmp.py", "[FMP] HTTP error: %s", "endpoint"),
    ("R989", "backend/tools/fmp.py", "[FMP] Request error: %s", "endpoint"),
    ("R990", "backend/tools/fmp.py", "[FMP] JSON parse error: %s", "endpoint"),
    ("R991", "backend/llm_config.py", '[LLM Rotation] endpoint cooling down', "endpoint_name"),
    ("R992", "backend/llm_config.py", "[LLM Rotation] endpoint restored", "endpoint_name"),
    ("R993", "backend/llm_config.py", "[LLM Config] endpoint has empty model field; using configured fallback. Please set the model name in Settings → Endpoint Pool.", "_safe_endpoint_name"),
    ("R994", "backend/llm_config.py", "[LLM Config] endpoint has empty model field; using configured fallback. Please set the model name in Settings → Endpoint Pool.", "endpoint_model"),
    ("R995", "backend/llm_config.py", "[LLM Config] legacy endpoint has empty llm_model; using configured fallback. Please set the model name in Settings.", "legacy_model"),
    ("R996", "backend/llm_config.py", "[LLM Rotation] select endpoint", "selected.name"),
    ("R997", "backend/llm_config.py", "[LLM Rotation] select endpoint", "selected.provider"),
    ("R998", "backend/llm_config.py", "[LLM Rotation] select endpoint", "selected.model"),
    ("R999", "backend/llm_config.py", "[LLM Rotation] select endpoint", "selected.api_key"),
    ("R1000", "backend/llm_config.py", "[LLM Factory] create", "api_base"),
]


@pytest.mark.parametrize(
    ("_round", "relative_path", "message", "forbidden_expression"),
    SECURITY_HARDENING_ROUNDS_901_1000,
    ids=[item[0] for item in SECURITY_HARDENING_ROUNDS_901_1000],
)
def test_round_901_1000_removes_sensitive_log_expressions(
    _round,
    relative_path,
    message,
    forbidden_expression,
):
    calls = _matching_log_calls(relative_path, message)
    assert calls, f"missing log call: {relative_path}: {message}"

    for call in calls:
        logged_expressions = {
            ast.unparse(argument)
            for argument in [*call.args[1:], *(keyword.value for keyword in call.keywords)]
        }
        assert forbidden_expression not in logged_expressions


def test_rounds_901_through_1000_are_complete_unique_and_source_bound():
    actual = [item[0] for item in SECURITY_HARDENING_ROUNDS_901_1000]
    expected = [f"R{number}" for number in range(901, 1001)]
    bindings = [(item[1], item[2], item[3]) for item in SECURITY_HARDENING_ROUNDS_901_1000]

    assert len(actual) == len(set(actual)) == 100
    assert actual == expected
    assert len(bindings) == len(set(bindings)) == 100


SECURITY_HARDENING_ROUNDS_1001_1100 = [
    ("R1001", "backend/agents/base_agent.py", "Rate limit timeout in _llm_analyze", "self.AGENT_NAME"),
    ("R1002", "backend/agents/base_agent.py", "_llm_analyze failed", "self.AGENT_NAME"),
    ("R1003", "backend/agents/base_agent.py", "LLM trace emission failed", "self.AGENT_NAME"),
    ("R1004", "backend/agents/base_agent.py", "on_event callback failed", "self.AGENT_NAME"),
    ("R1005", "backend/agents/base_agent.py", "on_event callback error in search notification", "self.AGENT_NAME"),
    ("R1006", "backend/agents/base_agent.py", "Rate limit timeout in _identify_gaps", "self.AGENT_NAME"),
    ("R1007", "backend/agents/base_agent.py", "Tool-aware search succeeded", "self.AGENT_NAME"),
    ("R1008", "backend/agents/base_agent.py", "Tool-aware search succeeded", "tool_name"),
    ("R1009", "backend/agents/base_agent.py", "Tool-aware search failed", "self.AGENT_NAME"),
    ("R1010", "backend/agents/base_agent.py", "Tool-aware search failed", "tool_name"),
    ("R1011", "backend/agents/base_agent.py", "Fallback search succeeded", "self.AGENT_NAME"),
    ("R1012", "backend/agents/base_agent.py", "Fallback search failed", "self.AGENT_NAME"),
    ("R1013", "backend/agents/base_agent.py", "Rate limit timeout in _update_summary", "self.AGENT_NAME"),
    ("R1014", "backend/agents/deep_search_agent.py", "[DeepSearch] Convergence stop", "metrics.reason"),
    ("R1015", "backend/agents/deep_search_agent.py", "[DeepSearch] document inspected", "label"),
    ("R1016", "backend/agents/deep_search_agent.py", "[DeepSearch] LLM call failed", "outer + 1"),
    ("R1017", "backend/agents/deep_search_agent.py", "[DeepSearch] LLM call failed", "max_outer_retries"),
    ("R1018", "backend/agents/deep_search_agent.py", "[DeepSearch] Waiting before outer retry", "backoff"),
    ("R1019", "backend/agents/deep_search_agent.py", "[DeepSearch] All outer retries exhausted", "max_outer_retries"),
    ("R1020", "backend/agents/deep_search_agent.py", "[DeepSearch] Rate limit timeout; skipping LLM call", "token_timeout"),
    ("R1021", "backend/api/dashboard_router.py", "[Dashboard] request timed out", "name"),
    ("R1022", "backend/api/dashboard_router.py", "[Dashboard] request failed", "name"),
    ("R1023", "backend/api/dashboard_router.py", "[Dashboard] Resolved asset", "active_asset.type"),
    ("R1024", "backend/api/market_router.py", "[API] kline cache hit", "period"),
    ("R1025", "backend/api/market_router.py", "[API] kline cache hit", "interval"),
    ("R1026", "backend/dashboard/insights_engine.py", "[Insights] cached news fallback stale; regenerate from refreshed dashboard data", "sym_upper"),
    ("R1027", "backend/dashboard/insights_engine.py", "[Insights] fetch timeout", "label"),
    ("R1028", "backend/dashboard/insights_engine.py", "[Insights] fetch failed", "label"),
    ("R1029", "backend/dashboard/insights_engine.py", "[Insights] Failed to deserialize insight", "tab_name"),
    ("R1030", "backend/dashboard/peer_service.py", "[PeerService] CN/HK metrics fetch failed", "sym"),
    ("R1031", "backend/dashboard/peer_service.py", "[PeerService] metrics fetch failed", "sym"),
    ("R1032", "backend/dashboard/scorers.py", "[Insights] scorer timed out", "self.AGENT_NAME"),
    ("R1033", "backend/dashboard/scorers.py", "[Insights] scorer failed", "self.AGENT_NAME"),
    ("R1034", "backend/dashboard/scorers.py", "[Insights] scorer JSON parse failed, using fallback", "self.AGENT_NAME"),
    ("R1035", "backend/graph/adapters/agent_adapter.py", "agent adapter failed to instantiate", "name"),
    ("R1036", "backend/graph/checkpointer.py", "LangGraph sync checkpointer initialized", "bundle.info.backend"),
    ("R1037", "backend/graph/checkpointer.py", "LangGraph async checkpointer initialized", "bundle.info.backend"),
    ("R1038", "backend/graph/executor.py", "[Executor] step failed", "step_id"),
    ("R1039", "backend/graph/executor.py", "[Executor] step failed", "kind"),
    ("R1040", "backend/graph/executor.py", "[Executor] step failed", "name"),
    ("R1041", "backend/graph/nodes/confirmation_gate.py", "[confirmation_gate] interrupt for confirmation", "output_mode"),
    ("R1042", "backend/graph/nodes/confirmation_gate.py", "[confirmation_gate] interrupt for confirmation", "confirmation_mode"),
    ("R1043", "backend/graph/nodes/confirmation_gate.py", "[confirmation_gate] resumed", "intent"),
    ("R1044", "backend/graph/nodes/execute_plan_stub.py", "RAG observability write failed", "method_name"),
    ("R1045", "backend/graph/nodes/planner.py", "[Planner] invalid JSON from first LLM output", "parse_error_info.get('error')"),
    ("R1046", "backend/graph/nodes/planner.py", "[Planner] invalid JSON after retry", "second_error_info.get('error')"),
    ("R1047", "backend/graph/nodes/synthesize.py", "[Synthesize] scrubbed unverified future claim", "claim"),
    ("R1048", "backend/graph/trace.py", "trace span data extraction failed", "node_name"),
    ("R1049", "backend/graph/trace.py", "LangFuse span update failed", "node_name"),
    ("R1050", "backend/handlers/followup_handler.py", "[Followup] LLM invoke failed: %s", "action"),
    ("R1051", "backend/rag/chunker.py", 'Chunking failed, falling back to whole doc', "doc_type"),
    ("R1052", "backend/rag/embedder.py", "Loading bge-m3 ...", "self._device"),
    ("R1053", "backend/rag/embedder.py", "Loading bge-m3 ...", "use_fp16"),
    ("R1054", "backend/rag/embedder.py", "Loading bge-m3 ...", "self._max_length"),
    ("R1055", "backend/security/pinned_http.py", "[pinned_http] blocked unsafe target", "_safe_log_host(current_url)"),
    ("R1056", "backend/orchestration/orchestrator.py", "[Orchestrator] data validation failed: issue_count=%d", "source.name"),
    ("R1057", "backend/orchestration/orchestrator.py", "[Orchestrator] source failed: %s", "source.name"),
    ("R1058", "backend/orchestration/orchestrator.py", "[Orchestrator] source rate limited", "source.name"),
    ("R1059", "backend/orchestration/plan.py", "[PlanExecutor._run_forum_step] Calling forum.synthesize", "step.timeout_seconds"),
    ("R1060", "backend/orchestration/plan.py", "[PlanExecutor._run_forum_step] Timeout", "step.timeout_seconds"),
    ("R1061", "backend/services/langfuse_tracer.py", "[LangFuse] 全链路追踪已启用", "host"),
    ("R1062", "backend/services/llm_retry.py", '[LLM] Rate limit token acquire retry', "agent_name or 'unknown'"),
    ("R1063", "backend/services/llm_retry.py", '[LLM] Rate limit retry', "agent_name or 'unknown'"),
    ("R1064", "backend/services/llm_retry.py", '[LLM] Execution error retry', "agent_name or 'unknown'"),
    ("R1065", "backend/services/pdf_export.py", "[PDF] 注册字体失败: %s", "font_path"),
    ("R1066", "backend/services/portfolio_store.py", 'Skipping invalid stored portfolio position', "r[0]"),
    ("R1067", "backend/services/portfolio_store.py", 'stored rebalance suggestion parse failed', "r[0]"),
    ("R1068", "backend/services/rate_limiter.py", "[RateLimiter] Initialized", "self.enabled"),
    ("R1069", "backend/services/rate_limiter.py", "[RateLimiter] Initialized", "self.requests_per_minute"),
    ("R1070", "backend/services/rate_limiter.py", "[RateLimiter] Initialized", "self.burst_capacity"),
    ("R1071", "backend/services/rate_limiter.py", "[RateLimiter] Initialized", "self.min_tokens_per_agent"),
    ("R1072", "backend/services/rate_limiter.py", "[RateLimiter] Initialized", "self.agent_window_seconds"),
    ("R1073", "backend/services/rate_limiter.py", "[RateLimiter] Guaranteed quota grant", "agent_name"),
    ("R1074", "backend/services/rate_limiter.py", "[RateLimiter] Timeout", "agent_name or 'unknown'"),
    ("R1075", "backend/services/rate_limiter.py", "[RateLimiter] Waiting for capacity", "agent_name or 'unknown'"),
    ("R1076", "backend/services/rate_limiter.py", "[RateLimiter] Waiting for capacity", "self._tokens"),
    ("R1077", "backend/services/report_index.py", 'stored report tags parse failed', "row['report_id']"),
    ("R1078", "backend/services/report_index.py", 'stored report quality reasons parse failed', "row['report_id']"),
    ("R1079", "backend/services/report_index.py", 'stored citation payload parse failed', "row['row_id']"),
    ("R1080", "backend/services/report_index.py", 'stored citation payload parse failed', "row['report_id']"),
    ("R1081", "backend/services/risk_snapshots.py", 'invalid stored risk snapshot summary', "row['snapshot_date']"),
    ("R1082", "backend/services/smart_cache.py", "[SmartCache] ttl resolved", "market"),
    ("R1083", "backend/services/smart_cache.py", "[SmartCache] ttl resolved", "data_type"),
    ("R1084", "backend/tools/baostock_provider.py", "[BaoStock] login failed", "getattr(login, 'error_msg', 'unknown')"),
    ("R1085", "backend/tools/financial.py", "[Financials] statement fetch succeeded", "table_label"),
    ("R1086", "backend/tools/financial.py", "[Financials] statement fetch succeeded", "attr"),
    ("R1087", "backend/tools/financial.py", "[Financials] statement fetch failed: %s", "table_label"),
    ("R1088", "backend/tools/financial.py", "[Financials] statement fetch failed: %s", "attr"),
    ("R1089", "backend/tools/macro_official.py", "official feed XML parse failed: %s", "feed_key"),
    ("R1090", "backend/services/datasource_monitor.py", "[Monitor] source 已恢复健康状态", "source"),
    ("R1091", "backend/services/datasource_monitor.py", "[Monitor] source degraded", "source"),
    ("R1092", "backend/services/scheduler_runner.py", "[Scheduler] scheduled job disabled (env).", "job_label"),
    ("R1093", "backend/services/scheduler_runner.py", "[Scheduler] scheduled job started", "job_label"),
    ("R1094", "backend/services/pdf_export.py", "[PDF] 成功注册中文字体", "font_path"),
    ("R1095", "backend/tools/env.py", "Proxy configured for yfinance", "YFINANCE_PROXY"),
    ("R1096", "backend/tools/search.py", "[Search] 最终使用 %d 个搜索源", "', '.join(sources_used)"),
    ("R1097", "backend/tools/price.py", "  Price source succeeded", "source_func.__name__"),
    ("R1098", "backend/dashboard/cache.py", "Invalidated cache entries by data type", "data_type"),
    ("R1099", "backend/services/health_probe.py", "[HealthProbe] check ok", "source"),
    ("R1100", "backend/services/health_probe.py", "[HealthProbe] check failed", "source"),
]


@pytest.mark.parametrize(
    ("_round", "relative_path", "message", "forbidden_expression"),
    SECURITY_HARDENING_ROUNDS_1001_1100,
    ids=[item[0] for item in SECURITY_HARDENING_ROUNDS_1001_1100],
)
def test_round_1001_1100_removes_sensitive_log_expressions(
    _round,
    relative_path,
    message,
    forbidden_expression,
):
    calls = _matching_log_calls(relative_path, message)
    assert calls, f"missing log call: {relative_path}: {message}"

    for call in calls:
        logged_expressions = {
            ast.unparse(argument)
            for argument in [*call.args[1:], *(keyword.value for keyword in call.keywords)]
        }
        assert forbidden_expression not in logged_expressions


def test_rounds_1001_through_1100_are_complete_unique_and_source_bound():
    actual = [item[0] for item in SECURITY_HARDENING_ROUNDS_1001_1100]
    expected = [f"R{number}" for number in range(1001, 1101)]
    bindings = [(item[1], item[2], item[3]) for item in SECURITY_HARDENING_ROUNDS_1001_1100]

    assert len(actual) == len(set(actual)) == 100
    assert actual == expected
    assert len(bindings) == len(set(bindings)) == 100


SECURITY_HARDENING_ROUNDS_1101_1200 = [
    ("R1101", "backend/agents/base_agent.py", "Rate limit timeout in _identify_gaps", "token_timeout"),
    ("R1102", "backend/agents/base_agent.py", "Rate limit timeout in _update_summary", "token_timeout"),
    ("R1103", "backend/agents/deep_search_agent.py", "[DeepSearch] documents fetched", "pdf_count"),
    ("R1104", "backend/agents/deep_search_agent.py", "[DeepSearch] All document fetches failed; falling back to search snippets", "len(results)"),
    ("R1105", "backend/agents/deep_search_agent.py", "[DeepSearch] document inspected", "idx"),
    ("R1106", "backend/agents/deep_search_agent.py", "[DeepSearch] document inspected", "is_pdf"),
    ("R1107", "backend/api/chart_detector.py", "  图表类型已解析", "result['chart_type']"),
    ("R1108", "backend/api/chart_detector.py", "  数据维度已解析", "result['data_dimension']"),
    ("R1109", "backend/api/chart_detector.py", "  置信度已计算", "result['confidence']"),
    ("R1110", "backend/api/chart_detector.py", "  原因已生成", "result['reason']"),
    ("R1111", "backend/api/dashboard_router.py", "[Dashboard] request timed out", "timeout"),
    ("R1112", "backend/api/main.py", "[RAGObservability] initialization completed", "rag_observability_status"),
    ("R1113", "backend/api/main.py", "[RAGObservability] retention cleanup completed", "deleted"),
    ("R1114", "backend/dashboard/cache.py", "Cache set", "ttl"),
    ("R1115", "backend/dashboard/cache.py", "Cache cleared", "count"),
    ("R1116", "backend/dashboard/cache.py", "Cleaned up expired cache entries", "len(expired_keys)"),
    ("R1117", "backend/graph/executor.py", "[Executor] step failed", "' (optional, continuing)' if optional else ' (REQUIRED, aborting)'"),
    ("R1118", "backend/graph/nodes/planner.py", "[Planner] invalid JSON from first LLM output", "parse_error_info.get('line')"),
    ("R1119", "backend/graph/nodes/planner.py", "[Planner] invalid JSON from first LLM output", "parse_error_info.get('column')"),
    ("R1120", "backend/graph/nodes/planner.py", "[Planner] invalid JSON after retry", "second_error_info.get('line')"),
    ("R1121", "backend/graph/nodes/planner.py", "[Planner] invalid JSON after retry", "second_error_info.get('column')"),
    ("R1122", "backend/graph/nodes/summarize_history.py", "[summarize_history] conversation history exceeds threshold; summarizing", "len(conversation_msgs)"),
    ("R1123", "backend/graph/nodes/summarize_history.py", "[summarize_history] conversation history compressed", "len(msgs_to_summarize)"),
    ("R1124", "backend/graph/nodes/synthesize.py", "[Synthesize] scrubbed unverified future claim", "len(claim)"),
    ("R1125", "backend/graph/nodes/synthesize.py", "[Synthesize/narrative] LLM output too short; discarding", "len(draft)"),
    ("R1126", "backend/graph/nodes/synthesize.py", "[Synthesize/narrative] generated narrative draft", "retry_attempts"),
    ("R1127", "backend/graph/nodes/synthesize.py", "[Synthesize/narrative] LLM call failed; using template fallback", "retryable"),
    ("R1128", "backend/graph/nodes/synthesize.py", "[Synthesize] LLM call failed; falling back to stub", "retryable"),
    ("R1129", "backend/graph/nodes/trim_conversation_history.py", "[trim_conversation_history] message history exceeds budget; trimming", "current_tokens"),
    ("R1130", "backend/graph/nodes/trim_conversation_history.py", "[trim_conversation_history] message history exceeds budget; trimming", "max_tokens"),
    ("R1131", "backend/graph/nodes/trim_conversation_history.py", "[trim_conversation_history] message history trimmed", "current_tokens"),
    ("R1132", "backend/graph/nodes/trim_conversation_history.py", "[trim_conversation_history] message history trimmed", "trimmed_tokens"),
    ("R1133", "backend/llm_config.py", '[LLM Rotation] endpoint cooling down', "ep.cfg.cooldown_sec"),
    ("R1134", "backend/llm_config.py", "[LLM Factory] create", "request_timeout"),
    ("R1135", "backend/orchestration/plan.py", "[PlanExecutor._run_forum_step] Entered", "len(agent_outputs) if agent_outputs else 0"),
    ("R1136", "backend/orchestration/plan.py", "[PlanExecutor._run_forum_step] forum.synthesize completed", "type(result).__name__ if result else 'None'"),
    ("R1137", "backend/orchestration/tools_bridge.py", "[Bridge] 价格数据源注册完成", "len(orchestrator.sources.get('price', []))"),
    ("R1138", "backend/rag/hybrid_service.py", "RAG v2 vector dimension mismatch; dropping and recreating table", "existing_dim"),
    ("R1139", "backend/rag/hybrid_service.py", "RAG v2 vector dimension mismatch; dropping and recreating table", "self._vector_dim"),
    ("R1140", "backend/rag/reranker.py", "Loading bge-reranker-v2-m3 ...", "self._max_length"),
    ("R1141", "backend/services/alert_scheduler.py", "Email send failed", "error_type"),
    ("R1142", "backend/services/alert_scheduler.py", "price_change run completed", "checked"),
    ("R1143", "backend/services/alert_scheduler.py", "News email send failed", "error_type"),
    ("R1144", "backend/services/alert_scheduler.py", "news run completed", "checked"),
    ("R1145", "backend/services/alert_scheduler.py", "Risk email send failed", "error_type"),
    ("R1146", "backend/services/alert_scheduler.py", "risk run completed", "checked"),
    ("R1147", "backend/services/datasource_monitor.py", "[Monitor] source degraded", "m.consecutive_failures"),
    ("R1148", "backend/services/execution_service.py", "[execution_service] graph timeout", "timeout_seconds"),
    ("R1149", "backend/services/health_probe.py", "[HealthProbe] run completed", "len(results)"),
    ("R1150", "backend/services/health_probe.py", "[HealthProbe] check failed", "bool(err)"),
    ("R1151", "backend/services/llm_retry.py", '[LLM] Rate limit token acquire retry', "attempt"),
    ("R1152", "backend/services/llm_retry.py", '[LLM] Rate limit token acquire retry', "max_attempts"),
    ("R1153", "backend/services/llm_retry.py", '[LLM] Rate limit retry', "attempt"),
    ("R1154", "backend/services/llm_retry.py", '[LLM] Rate limit retry', "max_attempts"),
    ("R1155", "backend/services/llm_retry.py", '[LLM] Execution error retry', "attempt"),
    ("R1156", "backend/services/llm_retry.py", '[LLM] Execution error retry', "max_attempts"),
    ("R1157", "backend/services/monitoring_storage.py", "已清理过期监控记录", "keep_days"),
    ("R1158", "backend/services/rate_limiter.py", "[RateLimiter] Guaranteed quota grant", "self._prune_agent_window(agent_name, time.monotonic())"),
    ("R1159", "backend/services/rate_limiter.py", "[RateLimiter] Guaranteed quota grant", "self.min_tokens_per_agent"),
    ("R1160", "backend/services/rate_limiter.py", "[RateLimiter] Timeout", "elapsed"),
    ("R1161", "backend/services/rate_limiter.py", "[RateLimiter] Timeout", "wait_time"),
    ("R1162", "backend/services/rate_limiter.py", "[RateLimiter] Timeout", "timeout"),
    ("R1163", "backend/services/rate_limiter.py", "[RateLimiter] Waiting for capacity", "wait_time"),
    ("R1164", "backend/services/rate_limiter.py", "[RateLimiter] Waiting for capacity", "self.requests_per_minute"),
    ("R1165", "backend/services/risk_snapshot_scheduler.py", "Active sessions loaded", "len(sessions)"),
    ("R1166", "backend/services/risk_snapshot_scheduler.py", "Daily risk snapshot completed", "success_count"),
    ("R1167", "backend/services/smart_cache.py", "[SmartCache] ttl resolved", "ttl"),
    ("R1168", "backend/services/subscription_service.py", "Subscription status updated for single ticker", "'enabled' if enabled else 'disabled'"),
    ("R1169", "backend/tools/cn_screener.py", "eastmoney screener page failed: %s", "page"),
    ("R1170", "backend/tools/price.py", "  Price source succeeded", "i"),
    ("R1171", "backend/tools/price.py", "  Price source %s failed: %s", "i"),
    ("R1172", "backend/tools/price.py", "[get_stock_historical_data] Yahoo Finance 网页抓取成功", "len(kline_data)"),
    ("R1173", "backend/tools/price.py", "[get_stock_historical_data] IEX Cloud 成功获取数据", "len(kline_data)"),
    ("R1174", "backend/tools/price.py", "[get_stock_historical_data] Tiingo 成功获取数据", "len(kline_data)"),
    ("R1175", "backend/tools/price.py", "[get_stock_historical_data] Twelve Data 成功获取数据", "len(kline_data)"),
    ("R1176", "backend/tools/price.py", "[get_stock_historical_data] Marketstack 成功获取数据", "len(kline_data)"),
    ("R1177", "backend/tools/price.py", "[get_stock_historical_data] Massive.com 成功获取数据", "len(kline_data)"),
    ("R1178", "backend/tools/price.py", "[get_stock_historical_data] Stooq 成功获取数据", "len(data)"),
    ("R1179", "backend/tools/price.py", "[get_stock_historical_data] 尝试使用 yfinance...", "attempt + 1"),
    ("R1180", "backend/tools/price.py", "[get_stock_historical_data] 尝试使用 yfinance...", "max_retries"),
    ("R1181", "backend/tools/price.py", "[get_stock_historical_data] yfinance 成功获取数据", "len(data)"),
    ("R1182", "backend/tools/price.py", "[get_stock_historical_data] yfinance 速率限制，等待后重试...", "wait_time"),
    ("R1183", "backend/tools/price.py", "[get_stock_historical_data] yfinance 失败: %s", "attempt + 1"),
    ("R1184", "backend/tools/price.py", "[get_stock_historical_data] yfinance 失败: %s", "max_retries"),
    ("R1185", "backend/tools/price.py", "[get_stock_historical_data] Alpha Vantage 成功获取数据", "len(kline_data)"),
    ("R1186", "backend/tools/price.py", "[get_stock_historical_data] yfinance 返回空数据，准备重试...", "attempt + 1"),
    ("R1187", "backend/tools/price.py", "[get_stock_historical_data] yfinance 返回空数据，准备重试...", "max_retries"),
    ("R1188", "backend/tools/price.py", "[get_stock_historical_data] yfinance fallback success", "len(data)"),
    ("R1189", "backend/tools/price.py", "[get_stock_historical_data] yfinance fallback 速率限制，等待后重试...", "wait_time"),
    ("R1190", "backend/tools/price.py", "[get_stock_historical_data] yfinance fallback 失败: %s", "attempt + 1"),
    ("R1191", "backend/tools/price.py", "[get_stock_historical_data] yfinance fallback 失败: %s", "max_retries"),
    ("R1192", "backend/tools/price.py", "[get_stock_historical_data] Finnhub 成功获取数据", "len(kline_data)"),
    ("R1193", "backend/tools/price.py", "[get_stock_historical_data] yfinance 成功获取指数数据", "len(data)"),
    ("R1194", "backend/tools/price.py", "[get_stock_historical_data] yfinance 备用方法成功获取数据", "len(data)"),
    ("R1195", "backend/tools/screener.py", "Alpha Vantage top movers returned a non-success status", "getattr(response, 'status_code', 'unknown')"),
    ("R1196", "backend/tools/screener.py", "FMP screener is in cooldown; using free sources", "unavailable_status"),
    ("R1197", "backend/tools/screener.py", "FMP screener returned a non-success status; falling back to free sources", "status_code or 'unknown'"),
    ("R1198", "backend/tools/search.py", "[Search] Exa quota exhausted; temporarily disabled", "max(60, _SEARCH_QUOTA_COOLDOWN_SECONDS)"),
    ("R1199", "backend/tools/search.py", "[Search] Tavily quota exhausted; temporarily disabled", "max(60, _SEARCH_QUOTA_COOLDOWN_SECONDS)"),
    ("R1200", "backend/tools/search.py", "[Search] Tavily API 错误", "error_type"),
]


@pytest.mark.parametrize(
    ("_round", "relative_path", "message", "forbidden_expression"),
    SECURITY_HARDENING_ROUNDS_1101_1200,
    ids=[item[0] for item in SECURITY_HARDENING_ROUNDS_1101_1200],
)
def test_round_1101_1200_removes_sensitive_log_expressions(
    _round,
    relative_path,
    message,
    forbidden_expression,
):
    calls = _matching_log_calls(relative_path, message)
    assert calls, f"missing log call: {relative_path}: {message}"

    for call in calls:
        logged_expressions = {
            ast.unparse(argument)
            for argument in [*call.args[1:], *(keyword.value for keyword in call.keywords)]
        }
        assert forbidden_expression not in logged_expressions


def test_rounds_1101_through_1200_are_complete_unique_and_source_bound():
    actual = [item[0] for item in SECURITY_HARDENING_ROUNDS_1101_1200]
    expected = [f"R{number}" for number in range(1101, 1201)]
    bindings = [(item[1], item[2], item[3]) for item in SECURITY_HARDENING_ROUNDS_1101_1200]

    assert len(actual) == len(set(actual)) == 100
    assert actual == expected
    assert len(bindings) == len(set(bindings)) == 100

SECURITY_HARDENING_ROUNDS_1401_1500 = [
    ('R1401', 'backend/handlers/chat_handler.py', '[ChatHandler] Streaming LLM enhancement failed', 'type(exc).__name__'),
    ('R1402', 'backend/handlers/followup_handler.py', '[Followup] streaming LLM fallback failed', 'type(exc).__name__'),
    ('R1403', 'backend/llm_config.py', '[Config] Corrupt user_config.json moved to a backup', 'type(exc).__name__'),
    ('R1404', 'backend/llm_config.py', '[Config] Failed to read user_config.json', 'type(exc).__name__'),
    ('R1405', 'backend/llm_config.py', '[LLM Rotation] endpoint cooling down', "len(reason or '')"),
    ('R1406', 'backend/orchestration/plan.py', '[PlanExecutor._run_forum_step] Exception', 'type(exc).__name__'),
    ('R1407', 'backend/orchestration/plan.py', '[PlanExecutor] Exception type', 'type(exc).__name__'),
    ('R1408', 'backend/personas/registry.py', '[personas] failed to parse file', 'type(exc).__name__'),
    ('R1409', 'backend/rag/chunker.py', 'Chunking failed, falling back to whole doc', 'type(exc).__name__'),
    ('R1410', 'backend/rag/hybrid_service.py', 'RAG v2 ivfflat index skipped', 'type(exc).__name__'),
    ('R1411', 'backend/rag/hybrid_service.py', 'RAG v2 embedding dimension lookup failed', 'type(exc).__name__'),
    ('R1412', 'backend/rag/observability_runtime.py', 'invalid stored RAG payload_json', 'type(exc).__name__'),
    ('R1413', 'backend/rag/observability_runtime.py', 'invalid stored RAG metadata_json', 'type(exc).__name__'),
    ('R1414', 'backend/rag/observability_runtime.py', 'invalid stored RAG metadata', 'type(exc).__name__'),
    ('R1415', 'backend/rag/observability_store.py', 'invalid stored RAG JSON', 'type(exc).__name__'),
    ('R1416', 'backend/rag/observability_store.py', '[RAGObservability] 缓存 ingest 批次失败', 'type(exc).__name__'),
    ('R1417', 'backend/rag/observability_store.py', '[RAGObservability] 创建查询运行失败', 'type(exc).__name__'),
    ('R1418', 'backend/rag/observability_store.py', '[RAGObservability] 记录失败查询时出错', 'type(inner_exc).__name__'),
    ('R1419', 'backend/rag/observability_store.py', '[RAGObservability] 记录查询完成失败', 'type(exc).__name__'),
    ('R1420', 'backend/services/alert_scheduler.py', 'Price fetch failed', 'type(exc).__name__'),
    ('R1421', 'backend/services/alert_scheduler.py', 'Email send raised', 'type(exc).__name__'),
    ('R1422', 'backend/services/alert_scheduler.py', 'News fetch failed', 'type(exc).__name__'),
    ('R1423', 'backend/services/alert_scheduler.py', 'News email send raised', 'type(exc).__name__'),
    ('R1424', 'backend/services/alert_scheduler.py', 'Risk price fetch failed', 'type(exc).__name__'),
    ('R1425', 'backend/services/alert_scheduler.py', 'Risk email send raised', 'type(exc).__name__'),
    ('R1426', 'backend/services/alert_scheduler.py', 'yfinance quote fetch failed', 'type(exc).__name__'),
    ('R1427', 'backend/services/alert_scheduler.py', 'Yahoo quote fetch failed', 'type(exc).__name__'),
    ('R1428', 'backend/services/alert_scheduler.py', 'Stooq history fetch failed', 'type(exc).__name__'),
    ('R1429', 'backend/services/alert_scheduler.py', 'Stooq quote fetch failed', 'type(exc).__name__'),
    ('R1430', 'backend/services/alert_scheduler.py', 'Yahoo chart fetch failed', 'type(exc).__name__'),
    ('R1431', 'backend/services/chat_history.py', 'Backed up corrupt chat history file', 'type(exc).__name__'),
    ('R1432', 'backend/services/email_service.py', '[EmailService] Transient network error', 'type(exc).__name__'),
    ('R1433', 'backend/services/email_service.py', '[EmailService] Permanent SMTP error', 'type(exc).__name__'),
    ('R1434', 'backend/services/email_service.py', '[EmailService] Unexpected error', 'type(exc).__name__'),
    ('R1435', 'backend/services/entitlements.py', 'User plans file was corrupt and moved to a backup', 'type(exc).__name__'),
    ('R1436', 'backend/services/entitlements.py', 'build_usage_view: count_reports_since failed; fallback 0', 'type(exc).__name__'),
    ('R1437', 'backend/services/entitlements.py', 'build_usage_view: count subscriptions failed; fallback 0', 'type(exc).__name__'),
    ('R1438', 'backend/services/entitlements.py', 'build_usage_view: count portfolio positions failed; fallback 0', 'type(exc).__name__'),
    ('R1439', 'backend/services/execution_service.py', '[execution_service] event queue enqueue failed', 'type(exc).__name__'),
    ('R1440', 'backend/services/execution_service.py', '[execution_service] report build failed', 'type(exc).__name__'),
    ('R1441', 'backend/services/execution_service.py', '[execution_service] record chat turn failed', 'type(exc).__name__'),
    ('R1442', 'backend/services/execution_service.py', '[execution_service] persist memory snapshot failed', 'type(exc).__name__'),
    ('R1443', 'backend/services/execution_service.py', '[execution_service] unhandled', 'type(exc).__name__'),
    ('R1444', 'backend/services/execution_service.py', '[execution_service] cancelled producer cleanup failed', 'type(exc).__name__'),
    ('R1445', 'backend/services/execution_service.py', '[resume_pipeline] event queue enqueue failed', 'type(exc).__name__'),
    ('R1446', 'backend/services/execution_service.py', '[resume_pipeline] report build failed', 'type(exc).__name__'),
    ('R1447', 'backend/services/execution_service.py', '[resume_pipeline] record chat turn failed', 'type(exc).__name__'),
    ('R1448', 'backend/services/execution_service.py', '[resume_pipeline] persist memory snapshot failed', 'type(exc).__name__'),
    ('R1449', 'backend/services/execution_service.py', '[resume_pipeline] unhandled', 'type(exc).__name__'),
    ('R1450', 'backend/services/execution_service.py', '[resume_pipeline] cancelled producer cleanup failed', 'type(exc).__name__'),
    ('R1451', 'backend/services/financials_analyzer.py', '[FinancialsAnalyzer] LLM返回非JSON，fallback', 'type(exc).__name__'),
    ('R1452', 'backend/services/financials_analyzer.py', '[FinancialsAnalyzer] 分析失败', 'type(exc).__name__'),
    ('R1453', 'backend/services/historical_data_store.py', 'baostock logout failed', 'type(logout_exc).__name__'),
    ('R1454', 'backend/services/historical_data_store.py', 'historical fallback failed', 'type(exc).__name__'),
    ('R1455', 'backend/services/langfuse_tracer.py', '[LangFuse] 初始化失败', 'type(exc).__name__'),
    ('R1456', 'backend/services/langfuse_tracer.py', '[LangFuse] safe client lookup failed', 'type(exc).__name__'),
    ('R1457', 'backend/services/langfuse_tracer.py', '[LangFuse] callback initialization failed', 'type(exc).__name__'),
    ('R1458', 'backend/services/langfuse_tracer.py', '[LangFuse] span creation failed', 'type(exc).__name__'),
    ('R1459', 'backend/services/langfuse_tracer.py', '[LangFuse] trace update failed', 'type(exc).__name__'),
    ('R1460', 'backend/services/langfuse_tracer.py', '[LangFuse] flush failed', 'type(exc).__name__'),
    ('R1461', 'backend/services/langfuse_tracer.py', '[LangFuse] shutdown failed', 'type(exc).__name__'),
    ('R1462', 'backend/services/llm_retry.py', '[LLM] Rate limit token acquire retry', 'type(exc).__name__'),
    ('R1463', 'backend/services/llm_retry.py', '[LLM] Rate limit retry', 'type(exc).__name__'),
    ('R1464', 'backend/services/llm_retry.py', '[LLM] Execution error retry', 'type(exc).__name__'),
    ('R1465', 'backend/services/memory.py', '[MemoryService] Failed to remove profile temp file', 'type(cleanup_error).__name__'),
    ('R1466', 'backend/services/news_sentiment.py', '[NewsSentiment] LLM返回非JSON', 'type(exc).__name__'),
    ('R1467', 'backend/services/news_sentiment.py', '[NewsSentiment] 分析失败', 'type(exc).__name__'),
    ('R1468', 'backend/services/notes_rag.py', 'embedding service unavailable', 'type(exc).__name__'),
    ('R1469', 'backend/services/notes_rag.py', 'invalid stored note vector', 'type(exc).__name__'),
    ('R1470', 'backend/services/notes_rag.py', 'invalid stored note tags', 'type(exc).__name__'),
    ('R1471', 'backend/services/portfolio_store.py', 'stored portfolio tags parse failed', 'type(exc).__name__'),
    ('R1472', 'backend/services/portfolio_store.py', 'Skipping invalid stored portfolio position', 'type(exc).__name__'),
    ('R1473', 'backend/services/portfolio_store.py', 'stored rebalance suggestion parse failed', 'type(exc).__name__'),
    ('R1474', 'backend/services/rebalance_engine.py', '[rebalance] enhancer failed, fallback to deterministic', 'type(exc).__name__'),
    ('R1475', 'backend/services/rebalance_llm_enhancer.py', '[rebalance-enhancer] news fetch failed', 'type(exc).__name__'),
    ('R1476', 'backend/services/rebalance_llm_enhancer.py', '[rebalance-enhancer] info fetch failed', 'type(exc).__name__'),
    ('R1477', 'backend/services/rebalance_llm_enhancer.py', '[rebalance-enhancer] LLM init failed', 'type(exc).__name__'),
    ('R1478', 'backend/services/rebalance_llm_enhancer.py', '[rebalance-enhancer] LLM call failed', 'type(exc).__name__'),
    ('R1479', 'backend/services/report_generator.py', '[ResearchReport] LLM调用失败', 'type(exc).__name__'),
    ('R1480', 'backend/services/report_index.py', 'stored report metadata parse failed', 'type(exc).__name__'),
    ('R1481', 'backend/services/report_index.py', 'stored report tags parse failed', 'type(exc).__name__'),
    ('R1482', 'backend/services/report_index.py', 'stored report quality reasons parse failed', 'type(exc).__name__'),
    ('R1483', 'backend/services/report_index.py', 'stored report payload parse failed', 'type(exc).__name__'),
    ('R1484', 'backend/services/report_index.py', 'stored report citation parse failed', 'type(exc).__name__'),
    ('R1485', 'backend/services/report_index.py', 'stored report trace digest parse failed', 'type(exc).__name__'),
    ('R1486', 'backend/services/report_index.py', 'stored citation payload parse failed', 'type(exc).__name__'),
    ('R1487', 'backend/services/research_notes.py', 'invalid stored research note tags', 'type(exc).__name__'),
    ('R1488', 'backend/services/research_notes.py', 'note vectorization failed', 'type(exc).__name__'),
    ('R1489', 'backend/services/research_notes.py', 'note re-vectorization failed', 'type(exc).__name__'),
    ('R1490', 'backend/services/risk_snapshots.py', 'invalid stored risk snapshot summary', 'type(exc).__name__'),
    ('R1491', 'backend/services/risk_snapshots.py', 'invalid stored risk snapshot', 'type(exc).__name__'),
    ('R1492', 'backend/tools/authoritative_feeds.py', 'authoritative domain normalization failed', 'type(exc).__name__'),
    ('R1493', 'backend/tools/authoritative_feeds.py', 'authoritative feed XML parse failed', 'type(exc).__name__'),
    ('R1494', 'backend/tools/authoritative_feeds.py', 'authoritative feed request failed', 'type(exc).__name__'),
    ('R1495', 'backend/tools/baostock_provider.py', '[BaoStock] package unavailable', 'type(exc).__name__'),
    ('R1496', 'backend/tools/baostock_provider.py', '[BaoStock] history failed', 'type(exc).__name__'),
    ('R1497', 'backend/tools/baostock_provider.py', '[BaoStock] logout failed', 'type(exc).__name__'),
    ('R1498', 'backend/tools/cn_hk_market.py', '[CNHK] eastmoney request failed', 'type(exc).__name__'),
    ('R1499', 'backend/tools/cn_hk_market.py', '[CNHK] quote text request failed', 'type(exc).__name__'),
    ('R1500', 'backend/tools/cn_market_board.py', 'cn market board list failed', 'type(exc).__name__'),
]


@pytest.mark.parametrize(
    ("_round", "relative_path", "message", "forbidden_expression"),
    SECURITY_HARDENING_ROUNDS_1401_1500,
    ids=[item[0] for item in SECURITY_HARDENING_ROUNDS_1401_1500],
)
def test_round_1401_1500_removes_sensitive_log_expressions(
    _round,
    relative_path,
    message,
    forbidden_expression,
):
    calls = _matching_log_calls(relative_path, message)
    assert calls, f"missing log call: {relative_path}: {message}"

    for call in calls:
        logged_expressions = {
            ast.unparse(argument)
            for argument in [*call.args[1:], *(keyword.value for keyword in call.keywords)]
        }
        assert forbidden_expression not in logged_expressions


def test_rounds_1401_through_1500_are_complete_unique_and_source_bound():
    actual = [item[0] for item in SECURITY_HARDENING_ROUNDS_1401_1500]
    expected = [f"R{number}" for number in range(1401, 1501)]
    bindings = [(item[1], item[2], item[3]) for item in SECURITY_HARDENING_ROUNDS_1401_1500]

    assert len(actual) == len(set(actual)) == 100
    assert actual == expected
    assert len(bindings) == len(set(bindings)) == 100


SECURITY_HARDENING_ROUNDS_1501_1507 = [
    ("R1501", "backend/tools/earnings_transcripts.py", "[Transcript] Search failed: %s", "len(query or '')"),
    ("R1502", "backend/tools/local_disclosure.py", "[LocalDisclosure] Search failed: %s", "len(query or '')"),
    ("R1503", "backend/tools/news.py", "  → Search failed: %s", "len(query or '')"),
    ("R1504", "backend/tools/search.py", "[Search] Exa 搜索成功", "len(query or '')"),
    ("R1505", "backend/tools/search.py", "[Search] Tavily 搜索成功", "len(query or '')"),
    ("R1506", "backend/tools/search.py", "[Search] 维基百科获取信息成功", "len(query or '')"),
    ("R1507", "backend/tools/search.py", "[Search] DuckDuckGo 搜索成功", "len(query or '')"),
]


@pytest.mark.parametrize(
    ("_round", "relative_path", "message", "forbidden_expression"),
    SECURITY_HARDENING_ROUNDS_1501_1507,
    ids=[item[0] for item in SECURITY_HARDENING_ROUNDS_1501_1507],
)
def test_round_1501_1507_removes_query_derived_log_expressions(
    _round,
    relative_path,
    message,
    forbidden_expression,
):
    calls = _matching_log_calls(relative_path, message)
    assert calls, f"missing log call: {relative_path}: {message}"

    for call in calls:
        logged_expressions = {
            ast.unparse(argument)
            for argument in [*call.args[1:], *(keyword.value for keyword in call.keywords)]
        }
        assert forbidden_expression not in logged_expressions


def test_rounds_1501_through_1507_are_complete_unique_and_source_bound():
    actual = [item[0] for item in SECURITY_HARDENING_ROUNDS_1501_1507]
    expected = [f"R{number}" for number in range(1501, 1508)]
    bindings = [(item[1], item[2], item[3]) for item in SECURITY_HARDENING_ROUNDS_1501_1507]

    assert len(actual) == len(set(actual)) == 7
    assert actual == expected
    assert len(bindings) == len(set(bindings)) == 7


_SAFE_AGGREGATE_LOG_EXPRESSIONS = {
    ("backend/orchestration/orchestrator.py", "len(validation.issues)"),
    ("backend/tools/fmp.py", "len(segments)"),
    ("backend/tools/fmp.py", "len(regions)"),
    ("backend/tools/fmp.py", "len(sectors)"),
    ("backend/tools/fmp.py", "len(holdings[:result_limit])"),
    ("backend/tools/fmp.py", "len(constituents[:result_limit])"),
    ("backend/tools/search.py", "len(sources_used)"),
    ("backend/tools/tencent_provider.py", "len(parts)"),
    ("backend/tools/web.py", "len(text)"),
}
_SAFE_PROVIDER_LOG_EXPRESSIONS = {
    ("backend/tools/price.py", "source_func.__name__"),
}


def _dynamic_log_expressions():
    for path in (_ROOT / "backend").rglob("*.py"):
        if "tests" in path.parts:
            continue
        relative_path = path.relative_to(_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"debug", "info", "warning", "warn", "error", "exception", "critical"}:
                continue
            if not node.args or ast.unparse(node.func.value) != "logger":
                continue

            expressions = [*node.args[1:], *(keyword.value for keyword in node.keywords)]
            if isinstance(node.args[0], ast.JoinedStr):
                expressions.extend(
                    value.value
                    for value in node.args[0].values
                    if isinstance(value, ast.FormattedValue)
                )
            for expression in expressions:
                yield relative_path, node.lineno, expression


def _is_exception_type_expression(expression):
    return (
        isinstance(expression, ast.Attribute)
        and expression.attr == "__name__"
        and isinstance(expression.value, ast.Call)
        and isinstance(expression.value.func, ast.Name)
        and expression.value.func.id == "type"
        and len(expression.value.args) == 1
        and isinstance(expression.value.args[0], ast.Name)
        and not expression.value.keywords
    )


def _classify_dynamic_log_expression(relative_path, expression):
    rendered = ast.unparse(expression)
    if _is_exception_type_expression(expression):
        return "exception_type"
    if rendered in {"resp.status_code", "response.status_code"}:
        return "http_status"
    if (relative_path, rendered) in _SAFE_AGGREGATE_LOG_EXPRESSIONS:
        return "aggregate_count"
    if (relative_path, rendered) in _SAFE_PROVIDER_LOG_EXPRESSIONS:
        return "provider_name"
    return None


def test_dynamic_log_expressions_do_not_reference_sensitive_input_names():
    forbidden_name_parts = {
        "query",
        "prompt",
        "message",
        "user",
        "email",
        "url",
        "path",
        "payload",
        "body",
        "token",
        "secret",
        "ticker",
        "symbol",
    }
    violations = []

    for relative_path, lineno, expression in _dynamic_log_expressions():
        names = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", ast.unparse(expression).lower())
        if any(part in name for name in names for part in forbidden_name_parts):
            violations.append(f"{relative_path}:{lineno}: {ast.unparse(expression)}")

    assert violations == []


def test_dynamic_log_expressions_match_reviewed_safe_baseline():
    classifications = Counter()
    unclassified = []

    for relative_path, lineno, expression in _dynamic_log_expressions():
        classification = _classify_dynamic_log_expression(relative_path, expression)
        if classification is None:
            unclassified.append(f"{relative_path}:{lineno}: {ast.unparse(expression)}")
        else:
            classifications[classification] += 1

    assert unclassified == []
    assert classifications == Counter(
        {
            "exception_type": 159,
            "http_status": 11,
            "aggregate_count": 9,
            "provider_name": 1,
        }
    )


def _contains_raw_exception_reference(node):
    exception_names = {"e", "exc", "err", "error", "exception"}
    if _is_exception_type_expression(node):
        return False
    if isinstance(node, ast.Name) and node.id.lower() in exception_names:
        return True
    return any(_contains_raw_exception_reference(child) for child in ast.iter_child_nodes(node))


def test_test_harnesses_do_not_print_raw_exceptions_or_tracebacks():
    violations = []

    for root in (_ROOT / "backend" / "tests", _ROOT / "tests"):
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler) and node.name:
                    for descendant in ast.walk(node):
                        if (
                            isinstance(descendant, ast.Call)
                            and isinstance(descendant.func, ast.Name)
                            and descendant.func.id == "str"
                            and len(descendant.args) == 1
                            and isinstance(descendant.args[0], ast.Name)
                            and descendant.args[0].id == node.name
                        ):
                            violations.append(
                                f"{path.relative_to(_ROOT)}:{descendant.lineno}: raw exception serialization"
                            )
                if not isinstance(node, ast.Call):
                    continue
                rendered_call = ast.unparse(node.func)
                if rendered_call in {
                    "traceback.print_exc",
                    "traceback.print_exception",
                    "traceback.format_exc",
                }:
                    violations.append(f"{path.relative_to(_ROOT)}:{node.lineno}: {rendered_call}")
                    continue
                if (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "print"
                    and any(_contains_raw_exception_reference(argument) for argument in node.args)
                ):
                    violations.append(f"{path.relative_to(_ROOT)}:{node.lineno}: raw exception print")

    assert violations == []



SECURITY_HARDENING_ROUNDS_1201_1300 = [
    ("R1201", "backend/agents/base_agent.py", "_llm_analyze failed", "type(exc).__name__"),
    ("R1202", "backend/agents/base_agent.py", "LLM trace emission failed", "type(trace_exc).__name__"),
    ("R1203", "backend/agents/base_agent.py", "Tool-aware search succeeded", "len(gap_desc or '')"),
    ("R1204", "backend/agents/base_agent.py", "Tool-aware search succeeded", "len(result_str)"),
    ("R1205", "backend/agents/base_agent.py", "Tool-aware search failed", "len(gap_desc or '')"),
    ("R1206", "backend/agents/base_agent.py", "Tool-aware search failed", "type(e).__name__"),
    ("R1207", "backend/agents/base_agent.py", "Fallback search succeeded", "len(gap_desc or '')"),
    ("R1208", "backend/agents/base_agent.py", "Fallback search failed", "type(fallback_exc).__name__"),
    ("R1209", "backend/agents/deep_search_agent.py", "[DeepSearch] queries built", "len(queries)"),
    ("R1210", "backend/agents/deep_search_agent.py", "[DeepSearch] event callback failed", "type(exc).__name__"),
    ("R1211", "backend/agents/deep_search_agent.py", "[DeepSearch] action callback failed", "type(exc).__name__"),
    ("R1212", "backend/agents/deep_search_agent.py", "[DeepSearch] search started", "len(q)"),
    ("R1213", "backend/agents/deep_search_agent.py", "[DeepSearch] documents fetched", "len(docs)"),
    ("R1214", "backend/agents/deep_search_agent.py", "[DeepSearch] documents fetched", "len(sources)"),
    ("R1215", "backend/agents/deep_search_agent.py", "[DeepSearch] document inspected", "len(title)"),
    ("R1216", "backend/agents/deep_search_agent.py", "[DeepSearch] Tavily search failed", "type(exc).__name__"),
    ("R1217", "backend/agents/deep_search_agent.py", "[DeepSearch] Exa search failed", "type(exc).__name__"),
    ("R1218", "backend/agents/deep_search_agent.py", "[DeepSearch] Search fallback failed", "type(exc).__name__"),
    ("R1219", "backend/agents/deep_search_agent.py", "[DeepSearch] Authoritative feed supplement failed", "type(exc).__name__"),
    ("R1220", "backend/agents/deep_search_agent.py", "[DeepSearch] Fetch failed", "type(exc).__name__"),
    ("R1221", "backend/agents/deep_search_agent.py", "[DeepSearch] Jina fallback succeeded", "len(text)"),
    ("R1222", "backend/agents/deep_search_agent.py", "[DeepSearch] Jina fallback failed", "type(exc).__name__"),
    ("R1223", "backend/agents/deep_search_agent.py", "[DeepSearch] Wayback fallback succeeded", "len(text)"),
    ("R1224", "backend/agents/deep_search_agent.py", "[DeepSearch] Wayback fallback failed", "type(exc).__name__"),
    ("R1225", "backend/agents/deep_search_agent.py", "[DeepSearch] RAG observability unavailable", "type(exc).__name__"),
    ("R1226", "backend/agents/deep_search_agent.py", "[DeepSearch] Failed to record RAG observability", "type(exc).__name__"),
    ("R1227", "backend/agents/deep_search_agent.py", "[DeepSearch] PDF parse failed", "type(exc).__name__"),
    ("R1228", "backend/agents/deep_search_agent.py", "[DeepSearch] LLM call failed", "type(exc).__name__"),
    ("R1229", "backend/agents/macro_agent.py", "[MacroAgent] FRED fetch failed", "type(exc).__name__"),
    ("R1230", "backend/agents/macro_agent.py", "[MacroAgent] Official release fetch failed", "type(exc).__name__"),
    ("R1231", "backend/agents/macro_agent.py", "[MacroAgent] Market sentiment fetch failed", "type(exc).__name__"),
    ("R1232", "backend/agents/macro_agent.py", "[MacroAgent] Economic events fetch failed", "type(exc).__name__"),
    ("R1233", "backend/agents/macro_agent.py", "[MacroAgent] Search cross-check failed", "type(exc).__name__"),
    ("R1234", "backend/agents/news_agent.py", "[NewsAgent] source reliability scoring failed", "type(exc).__name__"),
    ("R1235", "backend/agents/news_agent.py", "[NewsAgent] event calendar load failed", "type(exc).__name__"),
    ("R1236", "backend/agents/news_agent.py", "[NewsAgent] _fetch_with_finnhub_news failed", "type(e).__name__"),
    ("R1237", "backend/agents/news_agent.py", "[NewsAgent] get_company_news failed", "type(e).__name__"),
    ("R1238", "backend/agents/news_agent.py", "[NewsAgent] _search_company_news failed", "type(e).__name__"),
    ("R1239", "backend/agents/news_agent.py", "[NewsAgent] search fallback failed", "type(e).__name__"),
    ("R1240", "backend/agents/news_agent.py", "[NewsAgent] authoritative feed supplement failed", "type(exc).__name__"),
    ("R1241", "backend/agents/news_agent.py", "[NewsAgent] convergence trace creation failed", "type(exc).__name__"),
    ("R1242", "backend/agents/news_agent.py", "[NewsAgent] Finnhub stream fetch failed", "type(e).__name__"),
    ("R1243", "backend/agents/news_agent.py", "[NewsAgent] stream summary failed; falling back to retry invoke", "type(stream_exc).__name__"),
    ("R1244", "backend/agents/news_agent.py", "[NewsAgent] invoke summary fallback failed", "type(invoke_exc).__name__"),
    ("R1245", "backend/agents/price_agent.py", "[PriceAgent] search fallback failed", "type(exc).__name__"),
    ("R1246", "backend/api/chart_detector.py", "查询已接收", "len(query)"),
    ("R1247", "backend/api/chat_router.py", "[chat/supervisor] report build failed", "type(_report_exc).__name__"),
    ("R1248", "backend/api/chat_router.py", "[chat/supervisor] failed", "type(exc).__name__"),
    ("R1249", "backend/api/chat_router.py", "[chat/add-chart-data] failed", "type(exc).__name__"),
    ("R1250", "backend/api/dashboard_router.py", "[Dashboard] request failed", "type(exc).__name__"),
    ("R1251", "backend/api/dashboard_router.py", "[Dashboard] DashboardData construction failed", "type(exc).__name__"),
    ("R1252", "backend/api/main.py", "[Init] Error importing tools", "type(e2).__name__"),
    ("R1253", "backend/api/main.py", "[Init] Error importing chart detector", "type(e).__name__"),
    ("R1254", "backend/api/main.py", "[Init] Error initializing MemoryService", "type(e).__name__"),
    ("R1255", "backend/api/main.py", "report index async upsert failed", "type(exc).__name__"),
    ("R1256", "backend/api/main.py", "schedule async report indexing failed", "type(exc).__name__"),
    ("R1257", "backend/api/main.py", "failed to update session context", "type(exc).__name__"),
    ("R1258", "backend/api/main.py", "failed to initialize orchestrator", "type(exc).__name__"),
    ("R1259", "backend/api/main.py", "[Config] failed to write default user config", "type(_exc).__name__"),
    ("R1260", "backend/api/main.py", "[RAGObservability] initialization failed in lifespan", "type(exc).__name__"),
    ("R1261", "backend/api/main.py", "[RAGObservability] retention cleanup failed", "type(exc).__name__"),
    ("R1262", "backend/api/main.py", "[GraphRunner] initialization failed in lifespan", "type(exc).__name__"),
    ("R1263", "backend/api/main.py", "[Scheduler] shutdown error", "type(e).__name__"),
    ("R1264", "backend/api/main.py", "[GraphRunner] shutdown cleanup error", "type(e).__name__"),
    ("R1265", "backend/api/main.py", "rag access check failed due to upstream auth error", "type(exc).__name__"),
    ("R1266", "backend/api/morning_brief_router.py", "[MorningBrief] get_portfolio_positions failed", "type(exc).__name__"),
    ("R1267", "backend/api/morning_brief_router.py", "[MorningBrief] Graph Pipeline failed; falling back to direct fetch", "type(exc).__name__"),
    ("R1268", "backend/api/morning_brief_router.py", "[MorningBrief] price fetch failed", "type(exc).__name__"),
    ("R1269", "backend/api/morning_brief_router.py", "[MorningBrief] news fetch failed", "type(exc).__name__"),
    ("R1270", "backend/api/portfolio_router.py", "[portfolio] quote failed", "type(exc).__name__"),
    ("R1271", "backend/api/portfolio_router.py", "获取历史数据失败", "type(e).__name__"),
    ("R1272", "backend/api/portfolio_router.py", "组合优化失败", "type(e).__name__"),
    ("R1273", "backend/api/rebalance_router.py", "[rebalance] failed to load live price", "type(exc).__name__"),
    ("R1274", "backend/api/rebalance_router.py", "[rebalance] failed to load sector", "type(exc).__name__"),
    ("R1275", "backend/api/rebalance_router.py", "Rebalance engine failed", "type(exc).__name__"),
    ("R1276", "backend/api/rebalance_router.py", "Failed to save suggestion", "type(exc).__name__"),
    ("R1277", "backend/api/rebalance_router.py", "Rebalance streaming engine failed", "type(exc).__name__"),
    ("R1278", "backend/api/rebalance_router.py", "Failed to save streamed suggestion", "type(exc).__name__"),
    ("R1279", "backend/api/research_notes_router.py", "[research-notes/create] failed", "type(exc).__name__"),
    ("R1280", "backend/api/research_notes_router.py", "[research-notes/list] failed", "type(exc).__name__"),
    ("R1281", "backend/api/research_notes_router.py", "[research-notes/semantic-search] failed", "type(exc).__name__"),
    ("R1282", "backend/api/research_notes_router.py", "[research-notes/get] failed", "type(exc).__name__"),
    ("R1283", "backend/api/research_notes_router.py", "[research-notes/update] failed", "type(exc).__name__"),
    ("R1284", "backend/api/research_notes_router.py", "[research-notes/delete] failed", "type(exc).__name__"),
    ("R1285", "backend/api/research_notes_router.py", "[research-notes/upload-image] failed", "type(exc).__name__"),
    ("R1286", "backend/api/research_notes_router.py", "[research-notes/get-image] failed", "type(exc).__name__"),
    ("R1287", "backend/api/research_notes_router.py", "[research-notes/list-images] failed", "type(exc).__name__"),
    ("R1288", "backend/api/research_notes_router.py", "[research-notes/delete-image] failed", "type(exc).__name__"),
    ("R1289", "backend/api/research_notes_router.py", "[research-notes/vectorize-all] failed", "type(exc).__name__"),
    ("R1290", "backend/api/research_router.py", "company info context unavailable", "type(exc).__name__"),
    ("R1291", "backend/api/research_router.py", "financial context unavailable", "type(exc).__name__"),
    ("R1292", "backend/api/research_router.py", "technical context unavailable", "type(exc).__name__"),
    ("R1293", "backend/api/research_router.py", "news context unavailable", "type(exc).__name__"),
    ("R1294", "backend/api/research_router.py", "生成报告失败", "type(exc).__name__"),
    ("R1295", "backend/api/research_router.py", "获取财报失败", "type(exc).__name__"),
    ("R1296", "backend/api/research_router.py", "company info unavailable", "type(exc).__name__"),
    ("R1297", "backend/api/research_router.py", "财报分析失败", "type(exc).__name__"),
    ("R1298", "backend/api/research_router.py", "获取新闻失败", "type(exc).__name__"),
    ("R1299", "backend/api/research_router.py", "新闻情绪分析失败", "type(exc).__name__"),
    ("R1300", "backend/api/research_router.py", "stock price unavailable", "type(exc).__name__"),
]


@pytest.mark.parametrize(
    ("_round", "relative_path", "message", "forbidden_expression"),
    SECURITY_HARDENING_ROUNDS_1201_1300,
    ids=[item[0] for item in SECURITY_HARDENING_ROUNDS_1201_1300],
)
def test_round_1201_1300_removes_sensitive_log_expressions(
    _round,
    relative_path,
    message,
    forbidden_expression,
):
    calls = _matching_log_calls(relative_path, message)
    assert calls, f"missing log call: {relative_path}: {message}"

    for call in calls:
        logged_expressions = {
            ast.unparse(argument)
            for argument in [*call.args[1:], *(keyword.value for keyword in call.keywords)]
        }
        assert forbidden_expression not in logged_expressions


def test_rounds_1201_through_1300_are_complete_unique_and_source_bound():
    actual = [item[0] for item in SECURITY_HARDENING_ROUNDS_1201_1300]
    expected = [f"R{number}" for number in range(1201, 1301)]
    bindings = [(item[1], item[2], item[3]) for item in SECURITY_HARDENING_ROUNDS_1201_1300]

    assert len(actual) == len(set(actual)) == 100
    assert actual == expected
    assert len(bindings) == len(set(bindings)) == 100


SECURITY_HARDENING_ROUNDS_1301_1400 = [
    ("R1301", "backend/api/research_router.py", "智能问答失败", "type(exc).__name__"),
    ("R1302", "backend/api/research_router.py", "company news unavailable", "type(exc).__name__"),
    ("R1303", "backend/api/research_router.py", "top list unavailable", "type(exc).__name__"),
    ("R1304", "backend/api/research_router.py", "north flow unavailable", "type(exc).__name__"),
    ("R1305", "backend/api/research_router.py", "margin trading unavailable", "type(exc).__name__"),
    ("R1306", "backend/api/subscription_router.py", "[Audit] admin subscription list completed", "len(subscriptions)"),
    ("R1307", "backend/api/subscription_router.py", "[subscription/subscribe] failed", "type(exc).__name__"),
    ("R1308", "backend/api/subscription_router.py", "[subscription/unsubscribe] failed", "type(exc).__name__"),
    ("R1309", "backend/api/subscription_router.py", "[subscription/list] failed", "type(exc).__name__"),
    ("R1310", "backend/api/subscription_router.py", "[subscription/toggle] failed", "type(exc).__name__"),
    ("R1311", "backend/api/subscription_router.py", "[subscription/admin-list] failed", "type(exc).__name__"),
    ("R1312", "backend/api/task_router.py", "[Tasks] get_portfolio_positions failed", "type(exc).__name__"),
    ("R1313", "backend/api/timeline_router.py", "timeline invalid value", "type(exc).__name__"),
    ("R1314", "backend/api/timeline_router.py", "获取时间线失败", "type(exc).__name__"),
    ("R1315", "backend/api/today_router.py", "今日工作台生成失败", "type(exc).__name__"),
    ("R1316", "backend/api/today_router.py", "today alert events unavailable", "type(exc).__name__"),
    ("R1317", "backend/dashboard/cache.py", "Invalidated symbol cache entries", "len(keys_to_delete)"),
    ("R1318", "backend/dashboard/cache.py", "Invalidated cache entries by data type", "len(keys_to_delete)"),
    ("R1319", "backend/dashboard/data_service.py", "[DataService] OHLCV fallback hit via price pipeline", "len(frame)"),
    ("R1320", "backend/dashboard/data_service.py", "[DataService] fetch_macro_snapshot sentiment failed", "type(exc).__name__"),
    ("R1321", "backend/dashboard/data_service.py", "[DataService] fetch_macro_snapshot FRED failed", "type(exc).__name__"),
    ("R1322", "backend/dashboard/data_service.py", "[DataService] fetch_market_chart failed", "type(exc).__name__"),
    ("R1323", "backend/dashboard/data_service.py", "[DataService] fetch_snapshot failed", "type(exc).__name__"),
    ("R1324", "backend/dashboard/data_service.py", "[DataService] fetch_revenue_trend failed", "type(exc).__name__"),
    ("R1325", "backend/dashboard/data_service.py", "[DataService] fetch_segment_mix failed", "type(exc).__name__"),
    ("R1326", "backend/dashboard/data_service.py", "[DataService] fetch_news failed", "type(exc).__name__"),
    ("R1327", "backend/dashboard/data_service.py", "[DataService] fetch_sector_weights failed", "type(exc).__name__"),
    ("R1328", "backend/dashboard/data_service.py", "[DataService] fetch_top_constituents failed", "type(exc).__name__"),
    ("R1329", "backend/dashboard/data_service.py", "[DataService] fetch_holdings failed", "type(exc).__name__"),
    ("R1330", "backend/dashboard/data_service.py", "[DataService] yfinance OHLCV failed", "type(exc).__name__"),
    ("R1331", "backend/dashboard/data_service.py", "[DataService] Stooq OHLCV fallback failed", "type(exc).__name__"),
    ("R1332", "backend/dashboard/data_service.py", "[DataService] fallback OHLCV failed", "type(exc).__name__"),
    ("R1333", "backend/dashboard/data_service.py", "[DataService] Finnhub request failed", "type(exc).__name__"),
    ("R1334", "backend/dashboard/data_service.py", "[DataService] CN/HK valuation fallback failed", "type(exc).__name__"),
    ("R1335", "backend/dashboard/data_service.py", "[DataService] SEC companyfacts fallback failed", "type(exc).__name__"),
    ("R1336", "backend/dashboard/data_service.py", "[DataService] CN/HK financials fallback failed", "type(exc).__name__"),
    ("R1337", "backend/dashboard/data_service.py", "[DataService] fetch_valuation failed", "type(exc).__name__"),
    ("R1338", "backend/dashboard/data_service.py", "[DataService] fetch_financial_statements failed", "type(exc).__name__"),
    ("R1339", "backend/dashboard/data_service.py", "[DataService] fetch_technical_indicators failed", "type(exc).__name__"),
    ("R1340", "backend/dashboard/data_service.py", "[DataService] fetch_indicator_series failed", "type(exc).__name__"),
    ("R1341", "backend/dashboard/data_service.py", "[DataService] fetch_earnings_history failed", "type(exc).__name__"),
    ("R1342", "backend/dashboard/data_service.py", "[DataService] fetch_analyst_targets failed", "type(exc).__name__"),
    ("R1343", "backend/dashboard/data_service.py", "[DataService] fetch_recommendations failed", "type(exc).__name__"),
    ("R1344", "backend/dashboard/data_service.py", "[DataService] CN/HK OHLCV fallback failed", "type(exc).__name__"),
    ("R1345", "backend/dashboard/data_service.py", "[DataService] OHLCV fallback hit via Stooq", "len(frame)"),
    ("R1346", "backend/dashboard/data_service.py", "[DataService] get_company_news failed", "type(exc).__name__"),
    ("R1347", "backend/dashboard/data_service.py", "[DataService] get_market_news_headlines failed", "type(exc).__name__"),
    ("R1348", "backend/dashboard/insights_engine.py", "[Insights] Background refresh failed", "type(exc).__name__"),
    ("R1349", "backend/dashboard/insights_engine.py", "[Insights] fetch failed", "type(exc).__name__"),
    ("R1350", "backend/dashboard/peer_service.py", "[PeerService] Finnhub request failed", "type(exc).__name__"),
    ("R1351", "backend/dashboard/peer_service.py", "[PeerService] CN/HK metrics fetch failed", "type(exc).__name__"),
    ("R1352", "backend/dashboard/peer_service.py", "[PeerService] yfinance info failed", "type(exc).__name__"),
    ("R1353", "backend/dashboard/peer_service.py", "[PeerService] metrics fetch failed", "type(exc).__name__"),
    ("R1354", "backend/dashboard/peer_service.py", "[PeerService] fetch_peer_comparison failed", "type(exc).__name__"),
    ("R1355", "backend/dashboard/peer_service.py", "[PeerService] FMP screener failed", "type(exc).__name__"),
    ("R1356", "backend/dashboard/peer_service.py", "[PeerService] peer fetch failed", "type(exc).__name__"),
    ("R1357", "backend/dashboard/scorers.py", "[Insights] LLM init failed; dashboard scorers will use fallback", "type(exc).__name__"),
    ("R1358", "backend/dashboard/scorers.py", "[Insights] scorer failed", "type(exc).__name__"),
    ("R1359", "backend/graph/adapters/agent_adapter.py", "agent adapter failed to import legacy agents", "type(exc).__name__"),
    ("R1360", "backend/graph/adapters/agent_adapter.py", "agent output model serialization failed", "type(exc).__name__"),
    ("R1361", "backend/graph/adapters/agent_adapter.py", "agent adapter failed to instantiate", "type(exc).__name__"),
    ("R1362", "backend/graph/adapters/agent_adapter.py", "agent evidence model serialization failed", "type(exc).__name__"),
    ("R1363", "backend/graph/adapters/tool_adapter.py", "tool adapter failed to import registry", "type(exc).__name__"),
    ("R1364", "backend/graph/checkpointer.py", "LangGraph sync checkpointer fallback to memory", "type(exc).__name__"),
    ("R1365", "backend/graph/checkpointer.py", "LangGraph async checkpointer fallback to memory", "type(exc).__name__"),
    ("R1366", "backend/graph/checkpointer.py", "failed to close cached sync bundle during sync reset", "type(exc).__name__"),
    ("R1367", "backend/graph/checkpointer.py", "failed to close cached sync bundle during async reset", "type(exc).__name__"),
    ("R1368", "backend/graph/checkpointer.py", "failed to close cached async bundle", "type(exc).__name__"),
    ("R1369", "backend/graph/checkpointer.py", "failed to close async bundle", "type(exc).__name__"),
    ("R1370", "backend/graph/checkpointer.py", "failed to close async checkpointer context", "type(exc).__name__"),
    ("R1371", "backend/graph/checkpointer.py", "failed to close sync checkpointer stack asynchronously", "type(exc).__name__"),
    ("R1372", "backend/graph/checkpointer.py", "failed to close sync checkpointer stack", "type(exc).__name__"),
    ("R1373", "backend/graph/checkpointer.py", "failed to close stale async checkpointer bundle", "type(exc).__name__"),
    ("R1374", "backend/graph/event_bus.py", "graph event emission failed", "type(exc).__name__"),
    ("R1375", "backend/graph/executor.py", "[Executor] step failed", "type(exc).__name__"),
    ("R1376", "backend/graph/nodes/confirmation_gate.py", "[confirmation_gate] resumed", "bool(instruction)"),
    ("R1377", "backend/graph/nodes/execute_plan_stub.py", "RAG pipeline failed", "type(exc).__name__"),
    ("R1378", "backend/graph/nodes/execute_plan_stub.py", "RAG observability write failed", "type(exc).__name__"),
    ("R1379", "backend/graph/nodes/execute_plan_stub.py", "Reranker unavailable; using RRF order", "type(rerank_exc).__name__"),
    ("R1380", "backend/graph/nodes/planner.py", "[Planner] LLM initialization failed", "type(exc).__name__"),
    ("R1381", "backend/graph/nodes/planner.py", "[Planner] LLM planning failed", "type(exc).__name__"),
    ("R1382", "backend/graph/nodes/resolve_subject.py", "[resolve_subject] Tier-3 LLM classify failed", "type(exc).__name__"),
    ("R1383", "backend/graph/nodes/synthesize.py", "[Synthesize/verifier] create_llm unavailable", "type(exc).__name__"),
    ("R1384", "backend/graph/nodes/synthesize.py", "[Synthesize/verifier] verification failed", "type(exc).__name__"),
    ("R1385", "backend/graph/nodes/synthesize.py", "[Synthesize/narrative] LLM init failed", "type(exc).__name__"),
    ("R1386", "backend/graph/nodes/synthesize.py", "[Synthesize/narrative] LLM call failed; using template fallback", "type(exc).__name__"),
    ("R1387", "backend/graph/nodes/synthesize.py", "[Synthesize] LLM call failed; falling back to stub", "type(exc).__name__"),
    ("R1388", "backend/graph/report_builder.py", "[ReportBuilder] build_report_payload failed", "type(exc).__name__"),
    ("R1389", "backend/graph/runner.py", "graph trace metadata update failed", "type(exc).__name__"),
    ("R1390", "backend/graph/store.py", "[graph.store] init memory service failed", "type(exc).__name__"),
    ("R1391", "backend/graph/store.py", "[graph.store] load profile failed", "type(exc).__name__"),
    ("R1392", "backend/graph/store.py", "[graph.store] load profile before persist failed", "type(exc).__name__"),
    ("R1393", "backend/graph/store.py", "[graph.store] persist profile failed", "type(exc).__name__"),
    ("R1394", "backend/graph/trace.py", "trace preview serialization failed", "type(exc).__name__"),
    ("R1395", "backend/graph/trace.py", "trace span data extraction failed", "type(exc).__name__"),
    ("R1396", "backend/graph/trace.py", "LangFuse span update failed", "type(exc).__name__"),
    ("R1397", "backend/handlers/chat_handler.py", "[ChatHandler] 检查闲聊/建议意图", "len(query or '')"),
    ("R1398", "backend/handlers/chat_handler.py", "[ChatHandler] request handling failed", "type(e).__name__"),
    ("R1399", "backend/handlers/chat_handler.py", "[ChatHandler] ticker lookup failed", "type(e).__name__"),
    ("R1400", "backend/handlers/chat_handler.py", "[ChatHandler] Kline fallback failed", "type(e).__name__"),
]


@pytest.mark.parametrize(
    ("_round", "relative_path", "message", "forbidden_expression"),
    SECURITY_HARDENING_ROUNDS_1301_1400,
    ids=[item[0] for item in SECURITY_HARDENING_ROUNDS_1301_1400],
)
def test_round_1301_1400_removes_sensitive_log_expressions(
    _round,
    relative_path,
    message,
    forbidden_expression,
):
    calls = _matching_log_calls(relative_path, message)
    assert calls, f"missing log call: {relative_path}: {message}"

    for call in calls:
        logged_expressions = {
            ast.unparse(argument)
            for argument in [*call.args[1:], *(keyword.value for keyword in call.keywords)]
        }
        assert forbidden_expression not in logged_expressions


def test_rounds_1301_through_1400_are_complete_unique_and_source_bound():
    actual = [item[0] for item in SECURITY_HARDENING_ROUNDS_1301_1400]
    expected = [f"R{number}" for number in range(1301, 1401)]
    bindings = [(item[1], item[2], item[3]) for item in SECURITY_HARDENING_ROUNDS_1301_1400]

    assert len(actual) == len(set(actual)) == 100
    assert actual == expected
    assert len(bindings) == len(set(bindings)) == 100
