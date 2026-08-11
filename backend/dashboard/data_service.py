"""Dashboard data service helpers.

This module consolidates market/snapshot/news data retrieval and lightweight
normalization for Dashboard API responses.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from backend.dashboard.cache import dashboard_cache
from backend.utils.quote import safe_float, safe_int

from backend.dashboard.data_providers import (
    _FINNHUB_BASE_URL,
    _fetch_financial_statements_from_cn_hk_market,
    _fetch_financial_statements_from_finnhub,
    _fetch_financial_statements_from_sec_companyfacts,
    _fetch_valuation_from_cn_hk_market,
    _fetch_valuation_from_finnhub,
    _finnhub_market_cap_to_usd,
    _finnhub_percent_to_ratio,
    _finnhub_request,
    _match_report_value,
)

logger = logging.getLogger(__name__)

from backend.dashboard.news_ranking import (
    _ASSET_ALIAS_WEIGHTS,
    _HIGH_IMPACT_KEYWORDS,
    _MEDIUM_IMPACT_KEYWORDS,
    _NEWS_RANKING_HALF_LIFE_HOURS,
    _SOURCE_RELIABILITY_WEIGHTS,
    _build_asset_tokens,
    _build_ranking_reason,
    _calculate_source_penalty,
    _calculate_time_decay,
    _empty_news_payload,
    _estimate_asset_relevance,
    _estimate_impact_score,
    _news_ranking_meta,
    _parse_news_text,
    _rank_news_items,
    _resolve_source_reliability,
    _score_news_item,
    _to_news_item,
    _ts_seconds,
)

from backend.dashboard.data_fetchers import (
    _build_ohlcv_frame_from_rows,
    _infer_equity_market,
    _label_fear_greed,
    _load_ohlcv_frame,
    _parse_fear_greed_value,
    _parse_time_to_unix,
    fetch_analyst_targets,
    fetch_earnings_history,
    fetch_financial_statements,
    fetch_holdings,
    fetch_indicator_series,
    fetch_macro_snapshot,
    fetch_market_chart,
    fetch_news,
    fetch_recommendations,
    fetch_revenue_trend,
    fetch_sector_weights,
    fetch_segment_mix,
    fetch_snapshot,
    fetch_technical_indicators,
    fetch_top_constituents,
    fetch_valuation,
)


class DashboardDataService:
    """Lightweight wrapper with cache-aware helper methods."""

    def __init__(self) -> None:
        self.cache = dashboard_cache

    def get_market_chart(self, symbol: str, period: str = "1y", interval: str = "1d", use_cache: bool = True) -> list[dict[str, Any]]:
        cache_key = f"market_chart:{period}:{interval}"
        if use_cache:
            cached = self.cache.get(symbol, cache_key)
            if cached is not None:
                return cached
        data = fetch_market_chart(symbol, period, interval)
        self.cache.set(symbol, cache_key, data, ttl=self.cache.TTL_CHARTS)
        return data

    def get_snapshot(self, symbol: str, asset_type: str, use_cache: bool = True) -> dict[str, Any]:
        if use_cache:
            cached = self.cache.get(symbol, "snapshot")
            if cached is not None:
                return cached
        data = fetch_snapshot(symbol, asset_type)
        self.cache.set(symbol, "snapshot", data, ttl=self.cache.TTL_SNAPSHOT)
        return data

    def get_revenue_trend(self, symbol: str, use_cache: bool = True) -> list[dict[str, Any]]:
        if use_cache:
            cached = self.cache.get(symbol, "revenue_trend")
            if cached is not None:
                return cached
        data = fetch_revenue_trend(symbol)
        self.cache.set(symbol, "revenue_trend", data, ttl=self.cache.TTL_CHARTS)
        return data

    def get_segment_mix(self, symbol: str, use_cache: bool = True) -> list[dict[str, Any]]:
        if use_cache:
            cached = self.cache.get(symbol, "segment_mix")
            if cached is not None:
                return cached
        data = fetch_segment_mix(symbol)
        self.cache.set(symbol, "segment_mix", data, ttl=self.cache.TTL_SEGMENT_MIX)
        return data

    def get_news(self, symbol: str, limit: int = 20, use_cache: bool = True) -> dict[str, Any]:
        if use_cache:
            cached = self.cache.get(symbol, "news")
            if cached is not None:
                return cached
        data = fetch_news(symbol, limit)
        self.cache.set(symbol, "news", data, ttl=self.cache.TTL_NEWS)
        return data

    def get_macro_snapshot(self, symbol: str, use_cache: bool = True) -> dict[str, Any]:
        if use_cache:
            cached = self.cache.get(symbol, "macro_snapshot")
            if cached is not None:
                return cached
        data = fetch_macro_snapshot()
        self.cache.set(symbol, "macro_snapshot", data, ttl=self.cache.TTL_MACRO)
        return data

    def get_sector_weights(self, symbol: str, asset_type: str, use_cache: bool = True) -> list[dict[str, Any]]:
        if use_cache:
            cached = self.cache.get(symbol, "sector_weights")
            if cached is not None:
                return cached
        data = fetch_sector_weights(symbol, asset_type)
        self.cache.set(symbol, "sector_weights", data, ttl=self.cache.TTL_SECTOR_WEIGHTS)
        return data

    def get_top_constituents(self, symbol: str, asset_type: str, limit: int = 10, use_cache: bool = True) -> list[dict[str, Any]]:
        if use_cache:
            cached = self.cache.get(symbol, "top_constituents")
            if cached is not None:
                return cached
        data = fetch_top_constituents(symbol, asset_type, limit)
        self.cache.set(symbol, "top_constituents", data, ttl=self.cache.TTL_CONSTITUENTS)
        return data

    def get_holdings(self, symbol: str, asset_type: str, limit: int = 50, use_cache: bool = True) -> list[dict[str, Any]]:
        if use_cache:
            cached = self.cache.get(symbol, "holdings")
            if cached is not None:
                return cached
        data = fetch_holdings(symbol, asset_type, limit)
        self.cache.set(symbol, "holdings", data, ttl=self.cache.TTL_HOLDINGS)
        return data

    # ── v2 data methods ────────────────────────────────────────

    def get_valuation(self, symbol: str, use_cache: bool = True) -> dict[str, Any] | None:
        if use_cache:
            cached = self.cache.get(symbol, "valuation")
            if cached is not None:
                return cached
        data = fetch_valuation(symbol)
        if data is not None:
            self.cache.set(symbol, "valuation", data, ttl=self.cache.TTL_VALUATION)
        return data

    def get_financial_statements(self, symbol: str, use_cache: bool = True) -> dict[str, Any] | None:
        if use_cache:
            cached = self.cache.get(symbol, "financials")
            if cached is not None:
                return cached
        data = fetch_financial_statements(symbol)
        if data is not None:
            self.cache.set(symbol, "financials", data, ttl=self.cache.TTL_FINANCIALS)
        return data

    def get_technical_indicators(self, symbol: str, use_cache: bool = True) -> dict[str, Any] | None:
        if use_cache:
            cached = self.cache.get(symbol, "technicals")
            if cached is not None:
                return cached
        data = fetch_technical_indicators(symbol)
        if data is not None:
            self.cache.set(symbol, "technicals", data, ttl=self.cache.TTL_TECHNICALS)
        return data

    # ── Phase G2 data methods ────────────────────────────────────

    def get_indicator_series(self, symbol: str, use_cache: bool = True) -> dict[str, Any] | None:
        if use_cache:
            cached = self.cache.get(symbol, "indicator_series")
            if cached is not None:
                return cached
        data = fetch_indicator_series(symbol)
        if data is not None:
            self.cache.set(symbol, "indicator_series", data, ttl=self.cache.TTL_TECHNICALS)
        return data

    def get_earnings_history(self, symbol: str, use_cache: bool = True) -> list[dict[str, Any]] | None:
        if use_cache:
            cached = self.cache.get(symbol, "earnings_history")
            if cached is not None:
                return cached
        data = fetch_earnings_history(symbol)
        if data is not None:
            self.cache.set(symbol, "earnings_history", data, ttl=self.cache.TTL_EARNINGS)
        return data

    def get_analyst_targets(self, symbol: str, use_cache: bool = True) -> dict[str, Any] | None:
        if use_cache:
            cached = self.cache.get(symbol, "analyst_targets")
            if cached is not None:
                return cached
        data = fetch_analyst_targets(symbol)
        if data is not None:
            self.cache.set(symbol, "analyst_targets", data, ttl=self.cache.TTL_ANALYST)
        return data

    def get_recommendations(self, symbol: str, use_cache: bool = True) -> dict[str, Any] | None:
        if use_cache:
            cached = self.cache.get(symbol, "recommendations")
            if cached is not None:
                return cached
        data = fetch_recommendations(symbol)
        if data is not None:
            self.cache.set(symbol, "recommendations", data, ttl=self.cache.TTL_ANALYST)
        return data


dashboard_data_service = DashboardDataService()
