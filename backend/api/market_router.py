from __future__ import annotations

import re
import traceback
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request

from backend.api.schemas import KlineResponse
from backend.demo_mode import demo_financials, demo_kline, demo_quote, is_demo_mode
from backend.tools.baostock_provider import fetch_cn_kline, fetch_cn_quote, is_cn_symbol
from backend.utils.market_evidence import attach_financials_evidence, attach_market_evidence
from backend.utils.quote import parse_quote_payload, resolve_live_quote


@dataclass(frozen=True)
class MarketRouterDeps:
    get_orchestrator_safe: Callable[[], Any]
    get_stock_price: Callable[[str], Any]
    get_company_news: Callable[[str], Any]
    get_financial_statements: Callable[[str], Any]
    get_financial_statements_summary: Callable[[str], Any]
    get_stock_historical_data: Callable[..., Any]
    detect_chart_type: Callable[[str, str | None], dict[str, Any]] | None
    logger: Any


_TICKER_PATTERN = re.compile(r"^[A-Z0-9^][A-Z0-9.^=-]{0,19}$")


def _normalize_ticker(raw_ticker: str) -> str:
    return str(raw_ticker or "").strip().upper()


def _validate_ticker_or_400(raw_ticker: str) -> str:
    ticker = _normalize_ticker(raw_ticker)
    if not ticker:
        raise HTTPException(status_code=400, detail="ticker 不能为空")
    if not _TICKER_PATTERN.fullmatch(ticker):
        raise HTTPException(status_code=400, detail=f"ticker 格式非法: {raw_ticker}")
    return ticker


def _extract_ticker_candidates(query: str, provided_ticker: str | None = None) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        ticker = _normalize_ticker(raw)
        if not ticker or ticker in seen:
            return
        if not _TICKER_PATTERN.fullmatch(ticker):
            return
        seen.add(ticker)
        candidates.append(ticker)

    if provided_ticker:
        _add(provided_ticker)

    try:
        from backend.config.ticker_mapping import extract_tickers as extract_tickers_from_query

        metadata = extract_tickers_from_query(query or "")
        for ticker in metadata.get("tickers") or []:
            _add(str(ticker))
    except Exception:
        pass

    return candidates


def _has_usable_payload(payload: Any) -> bool:
    if payload is None:
        return False
    if isinstance(payload, dict):
        if payload.get("error"):
            return False
        data = payload.get("data")
        if isinstance(data, dict) and data.get("error"):
            return False
        return bool(payload)
    if isinstance(payload, list):
        return bool(payload)
    return True


def _market_payload(payload: Any, fallback_source: str, *, cached: bool = False) -> Any:
    return attach_market_evidence(payload, fallback_source=fallback_source, cached=cached)


def _financials_payload(payload: Any, fallback_source: str = "financials", *, cached: bool = False) -> Any:
    return attach_financials_evidence(payload, fallback_source=fallback_source, cached=cached)


def create_market_router(deps: MarketRouterDeps) -> APIRouter:
    router = APIRouter(tags=["Market"])

    @router.post("/api/chart/detect")
    def detect_chart(payload: dict[str, Any]):
        query = str(payload.get("query") or "").strip()
        ticker = payload.get("ticker")
        ticker_value = str(ticker).strip() if ticker is not None else None
        ticker_candidates = _extract_ticker_candidates(query, ticker_value)
        resolved_ticker = ticker_candidates[0] if ticker_candidates else None

        if not query:
            return {
                "success": False,
                "should_generate": False,
                "chart_type": None,
                "data_dimension": None,
                "confidence": 0.0,
                "reason": "empty_query",
                "ticker_candidates": ticker_candidates,
                "resolved_ticker": resolved_ticker,
            }

        if deps.detect_chart_type is None:
            return {
                "success": False,
                "should_generate": False,
                "chart_type": None,
                "data_dimension": None,
                "confidence": 0.0,
                "reason": "chart_detector_unavailable",
                "ticker_candidates": ticker_candidates,
                "resolved_ticker": resolved_ticker,
            }

        try:
            detected = deps.detect_chart_type(query, ticker_value or None)
            chart_type = detected.get("chart_type") if isinstance(detected, dict) else None
            data_dimension = detected.get("data_dimension") if isinstance(detected, dict) else None
            confidence_raw = detected.get("confidence") if isinstance(detected, dict) else 0.0
            try:
                confidence = float(confidence_raw)
            except Exception:
                confidence = 0.0
            confidence = max(0.0, min(1.0, confidence))
            reason = (
                str(detected.get("reason") or "")
                if isinstance(detected, dict)
                else "invalid_detector_response"
            )
            should_generate = bool(chart_type) and confidence >= 0.35
            return {
                "success": True,
                "should_generate": should_generate,
                "chart_type": chart_type,
                "data_dimension": data_dimension,
                "confidence": confidence,
                "reason": reason,
                "ticker_candidates": ticker_candidates,
                "resolved_ticker": resolved_ticker,
            }
        except Exception as exc:
            deps.logger.warning("[ChartDetect] failed: %s", exc)
            return {
                "success": False,
                "should_generate": False,
                "chart_type": None,
                "data_dimension": None,
                "confidence": 0.0,
                "reason": str(exc),
                "ticker_candidates": ticker_candidates,
                "resolved_ticker": resolved_ticker,
            }

    @router.get("/api/stock/price/{ticker}")
    def get_price(ticker: str):
        normalized_ticker = _validate_ticker_or_400(ticker)
        try:
            orchestrator = deps.get_orchestrator_safe()
            if orchestrator:
                cache_key = f"price:{normalized_ticker}"
                cached_data = orchestrator.cache.get(cache_key)
                if cached_data is not None:
                    deps.logger.info("[API] price cache hit %s", normalized_ticker)
                    normalized = parse_quote_payload(cached_data)
                    result = normalized or cached_data
                    result = _market_payload(result, "cache", cached=True)
                    return {"ticker": normalized_ticker, "data": result, "cached": True}

            if is_demo_mode():
                demo = demo_quote(normalized_ticker)
                if demo:
                    return {"ticker": normalized_ticker, "data": _market_payload(demo, "demo"), "cached": False}

            if is_cn_symbol(normalized_ticker):
                cn_quote = fetch_cn_quote(normalized_ticker)
                if cn_quote is not None:
                    if orchestrator:
                        orchestrator.cache.set(f"price:{normalized_ticker}", cn_quote, ttl=300)
                    return {"ticker": normalized_ticker, "data": _market_payload(cn_quote, "baostock"), "cached": False}

            quote, raw_payload = resolve_live_quote(normalized_ticker, deps.get_stock_price)
            if quote is not None:
                quote_source = str(quote.get("source") or "live") if isinstance(quote, dict) else "live"
                quote = _market_payload(quote, quote_source)
                if orchestrator:
                    orchestrator.cache.set(f"price:{normalized_ticker}", quote, ttl=60)
                return {"ticker": normalized_ticker, "data": quote}

            if orchestrator and raw_payload:
                orchestrator.cache.set(f"price:{normalized_ticker}", raw_payload, ttl=60)
            if is_demo_mode():
                demo = demo_quote(normalized_ticker)
                if demo:
                    return {"ticker": normalized_ticker, "data": _market_payload(demo, "demo"), "cached": False}
            return {"ticker": normalized_ticker, "data": _market_payload(raw_payload or {"error": "price unavailable"}, "unknown")}
        except Exception as exc:
            if is_demo_mode():
                demo = demo_quote(normalized_ticker)
                if demo:
                    return {"ticker": normalized_ticker, "data": _market_payload(demo, "demo"), "cached": False}
            deps.logger.warning("[API] get_price failed for %s: %s", normalized_ticker, exc)
            raise HTTPException(status_code=502, detail=f"无法获取 {normalized_ticker} 价格数据") from exc

    @router.get("/api/quote/{ticker}")
    def get_quote(ticker: str):
        """别名：与 /api/stock/price 相同，返回实时报价"""
        return get_price(ticker)

    @router.get("/api/stock/news/{ticker}")
    def get_news(ticker: str):
        normalized_ticker = _validate_ticker_or_400(ticker)
        try:
            news = deps.get_company_news(normalized_ticker)
            return {"ticker": normalized_ticker, "data": news}
        except Exception as exc:
            deps.logger.warning("[API] get_news failed for %s: %s", normalized_ticker, exc)
            raise HTTPException(status_code=502, detail=f"无法获取 {normalized_ticker} 新闻数据") from exc

    @router.get("/api/financials/{ticker}")
    def get_financials(ticker: str):
        normalized_ticker = _validate_ticker_or_400(ticker)
        try:
            if is_demo_mode():
                demo = demo_financials(normalized_ticker)
                if demo:
                    return _financials_payload(demo, "demo")

            financials_data = deps.get_financial_statements(normalized_ticker)
            if _has_usable_payload(financials_data):
                return _financials_payload(financials_data, "financials")
            if is_demo_mode():
                demo = demo_financials(normalized_ticker)
                if demo:
                    return _financials_payload(demo, "demo")
            return _financials_payload(financials_data, "financials")
        except Exception as exc:
            if is_demo_mode():
                demo = demo_financials(normalized_ticker)
                if demo:
                    return _financials_payload(demo, "demo")
            deps.logger.warning("[API] get_financials failed for %s: %s", normalized_ticker, exc)
            raise HTTPException(status_code=502, detail=f"无法获取 {normalized_ticker} 财务数据") from exc

    @router.get("/api/financials/{ticker}/summary")
    def get_financials_summary(ticker: str):
        normalized_ticker = _validate_ticker_or_400(ticker)
        try:
            summary = deps.get_financial_statements_summary(normalized_ticker)
            return {"ticker": normalized_ticker, "summary": summary}
        except Exception as exc:
            deps.logger.warning("[API] get_financials_summary failed for %s: %s", normalized_ticker, exc)
            raise HTTPException(status_code=502, detail=f"无法获取 {normalized_ticker} 财务摘要") from exc

    @router.get("/api/stock/kline/{ticker}", response_model=KlineResponse)
    def get_kline_data(ticker: str, period: str = "1y", interval: str = "1d"):
        normalized_ticker = _validate_ticker_or_400(ticker)
        try:
            orchestrator = deps.get_orchestrator_safe()
            if orchestrator:
                cache_key = f"kline:{normalized_ticker}:{period}:{interval}"
                cached_data = orchestrator.cache.get(cache_key)
                if cached_data is not None:
                    deps.logger.info("[API] kline cache hit %s (%s,%s)", normalized_ticker, period, interval)
                    return {"ticker": normalized_ticker, "data": _market_payload(cached_data, "cache", cached=True), "cached": True}

            if is_demo_mode():
                demo = demo_kline(normalized_ticker, period=period, interval=interval)
                if demo:
                    return {"ticker": normalized_ticker, "data": _market_payload(demo, "demo"), "cached": False}

            if is_cn_symbol(normalized_ticker):
                cn_kline = fetch_cn_kline(normalized_ticker, period=period, interval=interval)
                if cn_kline is not None:
                    if orchestrator:
                        cache_key = f"kline:{normalized_ticker}:{period}:{interval}"
                        orchestrator.cache.set(cache_key, cn_kline, ttl=3600)
                    return {"ticker": normalized_ticker, "data": _market_payload(cn_kline, "baostock"), "cached": False}

            kline_data = deps.get_stock_historical_data(normalized_ticker, period=period, interval=interval)
            if kline_data.get("error") and is_demo_mode():
                demo = demo_kline(normalized_ticker, period=period, interval=interval)
                if demo:
                    return {"ticker": normalized_ticker, "data": _market_payload(demo, "demo"), "cached": False}
            if "error" not in kline_data and orchestrator:
                cache_key = f"kline:{normalized_ticker}:{period}:{interval}"
                orchestrator.cache.set(cache_key, kline_data, ttl=3600)

            kline_source = str(kline_data.get("source") or "kline") if isinstance(kline_data, dict) else "kline"
            return {"ticker": normalized_ticker, "data": _market_payload(kline_data, kline_source), "cached": False}
        except Exception as exc:
            if is_demo_mode():
                demo = demo_kline(normalized_ticker, period=period, interval=interval)
                if demo:
                    return {"ticker": normalized_ticker, "data": _market_payload(demo, "demo"), "cached": False}
            return {"ticker": normalized_ticker, "data": _market_payload({"error": str(exc)}, "unknown"), "cached": False}

    @router.get("/api/kline/{ticker}")
    def get_kline_alias(ticker: str, period: str = "1mo", interval: str = "1d"):
        """别名：与 /api/stock/kline 相同，返回 K 线数据"""
        return get_kline_data(ticker, period, interval)

    @router.post("/api/export/pdf")
    async def export_pdf(request: dict, http_request: Request):
        try:
            from datetime import datetime

            from fastapi.responses import Response

            from backend.services.pdf_export import get_pdf_service
            from backend.services.entitlements import enforce_feature

            enforce_feature(getattr(http_request.state, "principal", None), "export_pdf")

            pdf_service = get_pdf_service()
            if not pdf_service:
                raise HTTPException(status_code=503, detail="PDF export service unavailable")

            messages = request.get("messages", [])
            charts = request.get("charts", [])
            title = request.get("title", "FinSight 对话记录")

            if not messages:
                raise HTTPException(status_code=400, detail="messages 不能为空")

            if charts:
                pdf_bytes = pdf_service.export_with_charts(messages, charts, title=title)
            else:
                pdf_bytes = pdf_service.export_conversation(messages, title=title)

            if not pdf_bytes:
                raise HTTPException(status_code=500, detail="PDF generation failed")

            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename=finsight_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                },
            )
        except HTTPException:
            raise
        except ImportError as exc:
            raise HTTPException(status_code=503, detail=f"PDF export unavailable: {str(exc)}") from exc
        except Exception as exc:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return router
