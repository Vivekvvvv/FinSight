# -*- coding: utf-8 -*-
"""
Mock Tools Module for Regression Testing
固定数据源，不依赖外网，可复现
"""
import json
import os
from typing import Any, Dict, List, Optional

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name: str) -> Dict:
    path = os.path.join(FIXTURES_DIR, f"{name}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


class MockToolsModule:
    """Mock 工具模块 - 返回固定数据"""

    def __init__(self):
        self._price_data = _load_fixture("price_data")
        self._news_data = _load_fixture("news_data")
        self._sentiment_data = _load_fixture("sentiment_data")

    def get_stock_price(self, ticker: str) -> Dict[str, Any]:
        if ticker.startswith("INVALID") or ticker.startswith("UNKNOWN"):
            return {"error": f"No data found for {ticker}"}
        if ticker.startswith("FAIL_"):
            return {"error": "Simulated failure", "ticker": ticker}
        data = self._price_data.get(ticker)
        if data:
            return data
        # Default mock data
        return {
            "price": 100.00,
            "change_percent": 0.5,
            "volume": 1000000,
            "ticker": ticker
        }

    def _fetch_with_yfinance(self, ticker: str) -> Dict[str, Any]:
        return self.get_stock_price(ticker)

    def _fetch_with_finnhub(self, ticker: str) -> Dict[str, Any]:
        return self.get_stock_price(ticker)

    def _fetch_with_alpha_vantage(self, ticker: str) -> Dict[str, Any]:
        return self.get_stock_price(ticker)

    def _search_for_price(self, ticker: str) -> Dict[str, Any]:
        return self.get_stock_price(ticker)

    def get_option_chain_metrics(self, ticker: str) -> Dict[str, Any]:
        return {
            "ticker": ticker,
            "implied_volatility": 0.28,
            "put_call_ratio": 0.92,
            "skew": 0.04,
            "source": "mock_options",
        }

    def get_stock_historical_data(
        self,
        ticker: str,
        period: str = "6mo",
        interval: str = "1d",
    ) -> Dict[str, Any]:
        base = 100.0
        return {
            "ticker": ticker,
            "period": period,
            "interval": interval,
            "kline_data": [
                {
                    "time": f"2026-01-{(index % 28) + 1:02d}",
                    "open": base + index * 0.2,
                    "high": base + index * 0.2 + 1.0,
                    "low": base + index * 0.2 - 1.0,
                    "close": base + index * 0.25,
                    "volume": 1_000_000 + index * 1000,
                }
                for index in range(60)
            ],
        }

    def get_company_news(self, ticker: str) -> List[Dict[str, Any]]:
        if ticker.startswith("UNKNOWN"):
            return []
        news = self._news_data.get(ticker, [])
        if not news:
            return [{"headline": f"Mock news for {ticker}", "source": "Mock", "url": "#", "datetime": "2026-01-22"}]
        return news

    def _fetch_with_finnhub_news(self, ticker: str) -> List[Dict[str, Any]]:
        return self.get_company_news(ticker)

    def _search_company_news(self, query: str) -> List[Dict[str, Any]]:
        return [
            {
                "headline": f"Mock searched news for {query}",
                "source": "MockSearch",
                "url": "https://example.com/mock-news",
                "datetime": "2026-01-22",
            }
        ]

    def score_news_source_reliability(self, source: str = "", url: str = "") -> Dict[str, Any]:
        return {
            "source": source or "Mock",
            "url": url,
            "score": 0.85,
            "tier": "mock_authoritative",
        }

    def get_event_calendar(self, ticker: str, days_ahead: int = 30) -> Dict[str, Any]:
        return {
            "ticker": ticker,
            "days_ahead": days_ahead,
            "events": [
                {"event": "Mock earnings", "date": "2026-01-28", "impact": "high"}
            ],
        }

    def get_authoritative_media_news(
        self,
        query: str,
        max_results: int = 8,
        authoritative_only: bool = True,
    ) -> Dict[str, Any]:
        return {
            "query": query,
            "authoritative_only": authoritative_only,
            "articles": self.search_authoritative_feeds(query, max_results=max_results),
        }

    def get_market_sentiment(self) -> Dict[str, Any]:
        return self._sentiment_data or {"fear_greed_index": 50, "fear_greed_label": "Neutral"}

    def search(self, query: str) -> str:
        return f"[Mock Search Result] Query: {query}. Found relevant financial information."

    def search_authoritative_feeds(
        self,
        query: str,
        max_results: int = 5,
        authoritative_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """Return deterministic authoritative-feed items without network access."""
        return [
            {
                "title": f"Mock authoritative source for {query}",
                "url": "https://example.com/mock-authoritative-source",
                "snippet": "Mock authoritative market context.",
                "source": "MockAuthoritativeFeed",
                "published_date": "2026-01-22",
            }
        ][:max(0, max_results)]

    def get_performance_comparison(self, tickers: List[str]) -> Dict[str, Any]:
        result = {}
        for ticker in tickers:
            price_data = self.get_stock_price(ticker)
            result[ticker] = {
                "price": price_data.get("price", 100),
                "change_percent": price_data.get("change_percent", 0),
                "ytd_return": 5.0
            }
        return result

    def get_financial_statements(self, ticker: str) -> Dict[str, Any]:
        return {
            "ticker": ticker,
            "revenue": 100000000000,
            "net_income": 20000000000,
            "eps": 5.50,
            "pe_ratio": 28.5
        }

    def get_company_info(self, ticker: str) -> str:
        return f"{ticker} is a mock large-cap company used for deterministic regression tests."

    def get_earnings_estimates(self, ticker: str) -> Dict[str, Any]:
        return {
            "ticker": ticker,
            "next_quarter_eps": 2.1,
            "revenue_growth_estimate": 0.08,
            "eps_revisions": [{"period": "next_quarter", "change": "up"}],
        }

    def get_eps_revisions(self, ticker: str) -> Dict[str, Any]:
        return {
            "ticker": ticker,
            "revision_signal": "positive",
            "eps_revisions": [{"period": "next_quarter", "change": "up"}],
        }

    def get_fred_data(self) -> Dict[str, Any]:
        return {
            "fed_funds_rate": 4.5,
            "cpi_yoy": 2.8,
            "unemployment_rate": 4.0,
            "ten_year_yield": 4.2,
        }

    def get_official_macro_releases(self, query: str = "", max_results: int = 8) -> Dict[str, Any]:
        return {
            "query": query,
            "releases": [
                {
                    "title": "Mock CPI release",
                    "source": "BLS",
                    "url": "https://example.com/mock-cpi",
                    "published_date": "2026-01-22",
                }
            ][:max(0, max_results)],
        }

    def get_economic_events(self) -> List[Dict[str, Any]]:
        return [
            {"event": "Fed Meeting", "date": "2026-01-28", "impact": "high"},
            {"event": "GDP Report", "date": "2026-01-30", "impact": "medium"}
        ]

    def format_news_items(self, news_items: List[Dict], title: str = "News") -> str:
        lines = [f"**{title}**"]
        for item in news_items[:5]:
            headline = item.get("headline", item.get("title", "No title"))
            source = item.get("source", "Unknown")
            lines.append(f"- {headline} ({source})")
        return "\n".join(lines)
