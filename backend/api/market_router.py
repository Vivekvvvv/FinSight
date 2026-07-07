from __future__ import annotations

import re
import traceback
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request

from backend.api.schemas import KlineResponse
from backend.demo_mode import demo_financials, demo_kline, demo_quote, is_demo_mode
from backend.tools.baostock_provider import is_cn_symbol
from backend.tools.tencent_provider import fetch_cn_quote, fetch_cn_kline, fetch_cn_intraday
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

            if is_cn_symbol(normalized_ticker):
                cn_quote = fetch_cn_quote(normalized_ticker)
                if cn_quote is not None:
                    if orchestrator:
                        from backend.services.smart_cache import get_smart_cache_ttl
                        ttl = get_smart_cache_ttl(normalized_ticker, "quote")
                        orchestrator.cache.set(f"price:{normalized_ticker}", cn_quote, ttl=ttl)
                    return {"ticker": normalized_ticker, "data": _market_payload(cn_quote, "tencent"), "cached": False}

            if is_demo_mode():
                demo = demo_quote(normalized_ticker)
                if demo:
                    return {"ticker": normalized_ticker, "data": _market_payload(demo, "demo"), "cached": False}

            quote, raw_payload = resolve_live_quote(normalized_ticker, deps.get_stock_price)
            if quote is not None:
                quote_source = str(quote.get("source") or "live") if isinstance(quote, dict) else "live"
                quote = _market_payload(quote, quote_source)
                if orchestrator:
                    from backend.services.smart_cache import get_smart_cache_ttl
                    ttl = get_smart_cache_ttl(normalized_ticker, "quote")
                    orchestrator.cache.set(f"price:{normalized_ticker}", quote, ttl=ttl)
                return {"ticker": normalized_ticker, "data": quote}

            if orchestrator and raw_payload:
                from backend.services.smart_cache import get_smart_cache_ttl
                ttl = get_smart_cache_ttl(normalized_ticker, "quote")
                orchestrator.cache.set(f"price:{normalized_ticker}", raw_payload, ttl=ttl)
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

            if is_cn_symbol(normalized_ticker):
                cn_kline = fetch_cn_kline(normalized_ticker, period=period, interval=interval)
                if cn_kline is not None:
                    if orchestrator:
                        from backend.services.smart_cache import get_smart_cache_ttl
                        cache_key = f"kline:{normalized_ticker}:{period}:{interval}"
                        ttl = get_smart_cache_ttl(normalized_ticker, "kline")
                        orchestrator.cache.set(cache_key, cn_kline, ttl=ttl)
                    return {"ticker": normalized_ticker, "data": _market_payload(cn_kline, "tencent"), "cached": False}

            if is_demo_mode():
                demo = demo_kline(normalized_ticker, period=period, interval=interval)
                if demo:
                    return {"ticker": normalized_ticker, "data": _market_payload(demo, "demo"), "cached": False}

            kline_data = deps.get_stock_historical_data(normalized_ticker, period=period, interval=interval)
            if kline_data.get("error") and is_demo_mode():
                demo = demo_kline(normalized_ticker, period=period, interval=interval)
                if demo:
                    return {"ticker": normalized_ticker, "data": _market_payload(demo, "demo"), "cached": False}
            if "error" not in kline_data and orchestrator:
                from backend.services.smart_cache import get_smart_cache_ttl
                cache_key = f"kline:{normalized_ticker}:{period}:{interval}"
                ttl = get_smart_cache_ttl(normalized_ticker, "kline")
                orchestrator.cache.set(cache_key, kline_data, ttl=ttl)

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

    @router.get("/api/stock/intraday/{ticker}")
    def get_intraday_data(ticker: str):
        """获取A股分时数据（当日逐分钟行情）"""
        normalized_ticker = _validate_ticker_or_400(ticker)
        try:
            orchestrator = deps.get_orchestrator_safe()
            if orchestrator:
                cache_key = f"intraday:{normalized_ticker}"
                cached_data = orchestrator.cache.get(cache_key)
                if cached_data is not None:
                    deps.logger.info("[API] intraday cache hit %s", normalized_ticker)
                    return {"ticker": normalized_ticker, "data": _market_payload(cached_data, "cache", cached=True), "cached": True}

            if is_cn_symbol(normalized_ticker):
                cn_intraday = fetch_cn_intraday(normalized_ticker)
                if cn_intraday is not None:
                    if orchestrator:
                        from backend.services.smart_cache import get_smart_cache_ttl
                        ttl = get_smart_cache_ttl(normalized_ticker, "intraday")
                        orchestrator.cache.set(cache_key, cn_intraday, ttl=ttl)
                    return {"ticker": normalized_ticker, "data": _market_payload(cn_intraday, "tencent"), "cached": False}

            # 非A股或腾讯失败，返回错误
            return {"ticker": normalized_ticker, "data": _market_payload({"error": "intraday data not available"}, "unknown"), "cached": False}
        except Exception as exc:
            return {"ticker": normalized_ticker, "data": _market_payload({"error": str(exc)}, "unknown"), "cached": False}

    @router.post("/api/export/pdf")
    def export_pdf(request: dict, http_request: Request):
        # def 而非 async def：PDF 渲染是同步 CPU 密集操作，async 下直接调用会
        # 阻塞事件循环拖垮全部并发请求；def 由 FastAPI 自动放线程池执行。
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

    @router.get("/api/system/health")
    def get_system_health():
        """数据源健康检查接口"""
        from backend.services.datasource_monitor import get_monitor

        monitor = get_monitor()
        return monitor.get_health_report()

    @router.get("/api/system/health/trend")
    def get_health_trend(source: str | None = None, days: int = 7):
        """
        查询历史健康趋势

        Query Parameters:
            source: 数据源名称（可选，不填则返回所有源）
            days: 查询天数（默认7天，最大30天）
        """
        from backend.services.monitoring_storage import get_storage

        if days < 1 or days > 30:
            raise HTTPException(status_code=400, detail="days 参数必须在 1-30 之间")

        storage = get_storage()
        trend_data = storage.get_trend(source_name=source, days=days)

        return {
            "source": source or "all",
            "days": days,
            "data_points": len(trend_data),
            "records": trend_data
        }

    @router.get("/api/system/health/stats")
    def get_storage_stats():
        """获取监控数据库统计信息"""
        from backend.services.monitoring_storage import get_storage

        storage = get_storage()
        return storage.get_stats()

    @router.get("/api/stock/top-list/{ticker}")
    def get_top_list(ticker: str, include_seats: bool = True):
        """
        获取龙虎榜数据（含席位明细）

        Path Parameters:
            ticker: 股票代码（如 600519.SS）

        Query Parameters:
            include_seats: 是否包含席位明细（默认True）

        Returns:
            {
                "symbol": "600519.SS",
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "date": "2026-06-14",
                "reason": "涨跌幅偏离值7%",
                "close_price": 1580.50,
                "change_percent": 5.32,
                "buy_amount": 123456789.0,
                "sell_amount": 98765432.0,
                "net_buy": 24691357.0,
                "turnover_rate": 1.23,
                "buy_seats": [
                    {
                        "rank": 1,
                        "seat_name": "机构专用",
                        "buy_amount": 50000000.0,
                        "sell_amount": 0.0,
                        "net_amount": 50000000.0,
                        "is_institution": True
                    },
                    ...
                ],
                "sell_seats": [...],
                "source": "eastmoney"
            }
        """
        ticker = _validate_ticker_or_400(ticker)

        if not is_cn_symbol(ticker):
            raise HTTPException(
                status_code=400,
                detail=f"龙虎榜仅支持A股，{ticker} 不是A股代码"
            )

        from backend.tools.tencent_provider import fetch_cn_top_list

        data = fetch_cn_top_list(ticker, include_seats=include_seats)

        if data is None:
            raise HTTPException(
                status_code=404,
                detail=f"{ticker} 未上榜或数据不可用"
            )

        return data

    @router.get("/api/stock/top-list/{ticker}/history")
    def get_top_list_history(
        ticker: str,
        start_date: str | None = None,
        end_date: str | None = None,
        days: int = 7
    ):
        """
        获取龙虎榜历史记录

        Path Parameters:
            ticker: 股票代码（如 600519.SS）

        Query Parameters:
            start_date: 开始日期（YYYY-MM-DD），优先级高于days
            end_date: 结束日期（YYYY-MM-DD），默认今天
            days: 查询天数（默认7天，最大90天）

        Returns:
            {
                "ticker": "600519.SS",
                "start_date": "2026-06-07",
                "end_date": "2026-06-14",
                "total_records": 3,
                "records": [
                    {
                        "date": "2026-06-14",
                        "reason": "涨跌幅偏离值7%",
                        "buy_amount": 123456789.0,
                        "sell_amount": 98765432.0,
                        "net_buy": 24691357.0,
                        ...
                    },
                    ...
                ]
            }
        """
        ticker = _validate_ticker_or_400(ticker)

        if not is_cn_symbol(ticker):
            raise HTTPException(
                status_code=400,
                detail=f"龙虎榜仅支持A股，{ticker} 不是A股代码"
            )

        if days < 1 or days > 90:
            raise HTTPException(status_code=400, detail="days 参数必须在 1-90 之间")

        from backend.tools.tencent_provider import fetch_cn_top_list_history

        records = fetch_cn_top_list_history(
            ticker,
            start_date=start_date,
            end_date=end_date,
            days=days
        )

        return {
            "ticker": ticker,
            "start_date": start_date or f"最近{days}天",
            "end_date": end_date or "今天",
            "total_records": len(records),
            "records": records
        }

    @router.get("/api/market/north-flow")
    def get_north_flow(date: str | None = None):
        """
        获取北向资金实时流向

        Query Parameters:
            date: 查询日期（YYYY-MM-DD），默认今天

        Returns:
            {
                "date": "2026-06-14",
                "time": "15:00:00",
                "north_flow": 12345678900.0,
                "sh_flow": 8000000000.0,
                "sz_flow": 4345678900.0,
                "data_points": [
                    {"time": "09:30", "north": 123456789, "sh": 80000000, "sz": 43456789},
                    ...
                ],
                "source": "eastmoney"
            }
        """
        from backend.tools.tencent_provider import fetch_north_flow

        data = fetch_north_flow(date=date)

        if data is None:
            raise HTTPException(
                status_code=404,
                detail="北向资金数据不可用"
            )

        return data

    @router.get("/api/market/north-flow/history")
    def get_north_flow_history(days: int = 30):
        """
        获取北向资金历史数据

        Query Parameters:
            days: 查询天数（默认30天，最大90天）

        Returns:
            {
                "days": 30,
                "total_records": 25,
                "records": [
                    {
                        "date": "2026-06-14",
                        "north_flow": 12345678900.0,
                        "sh_flow": 8000000000.0,
                        "sz_flow": 4345678900.0
                    },
                    ...
                ]
            }
        """
        if days < 1 or days > 90:
            raise HTTPException(status_code=400, detail="days 参数必须在 1-90 之间")

        from backend.tools.tencent_provider import fetch_north_flow_history

        records = fetch_north_flow_history(days=days)

        return {
            "days": days,
            "total_records": len(records),
            "records": records
        }

    @router.get("/api/stock/margin/{ticker}")
    def get_margin_trading(ticker: str):
        """
        获取融资融券最新数据

        Path Parameters:
            ticker: 股票代码（如 600519.SS）

        Returns:
            {
                "symbol": "600519.SS",
                "date": "2026-06-14",
                "margin_balance": 1234567890.0,
                "margin_buy": 50000000.0,
                "margin_repay": 30000000.0,
                "short_balance": 123456.0,
                "short_sell": 10000.0,
                "short_repay": 5000.0,
                "total_balance": 1234691346.0,
                "source": "eastmoney"
            }
        """
        ticker = _validate_ticker_or_400(ticker)

        if not is_cn_symbol(ticker):
            raise HTTPException(
                status_code=400,
                detail=f"融资融券仅支持A股，{ticker} 不是A股代码"
            )

        from backend.tools.tencent_provider import fetch_margin_trading

        data = fetch_margin_trading(ticker)

        if data is None:
            raise HTTPException(
                status_code=404,
                detail=f"{ticker} 融资融券数据不可用"
            )

        return data

    @router.get("/api/stock/margin/{ticker}/history")
    def get_margin_trading_history(ticker: str, days: int = 90):
        """
        获取融资融券历史数据

        Path Parameters:
            ticker: 股票代码（如 600519.SS）

        Query Parameters:
            days: 查询天数（默认90天，最大180天）

        Returns:
            {
                "ticker": "600519.SS",
                "days": 90,
                "total_records": 85,
                "records": [
                    {
                        "date": "2026-06-14",
                        "margin_balance": 1234567890.0,
                        "margin_buy": 50000000.0,
                        ...
                    },
                    ...
                ]
            }
        """
        ticker = _validate_ticker_or_400(ticker)

        if not is_cn_symbol(ticker):
            raise HTTPException(
                status_code=400,
                detail=f"融资融券仅支持A股，{ticker} 不是A股代码"
            )

        if days < 1 or days > 180:
            raise HTTPException(status_code=400, detail="days 参数必须在 1-180 之间")

        from backend.tools.tencent_provider import fetch_margin_trading_history

        records = fetch_margin_trading_history(ticker, days=days)

        return {
            "ticker": ticker,
            "days": days,
            "total_records": len(records),
            "records": records
        }

    # ── 历史K线（带缓存+复权+清洗） ──────────────────────────────────────────

    @router.get("/api/market/historical/{ticker}")
    def get_historical_kline(
        ticker: str,
        start: str = "2020-01-01",
        end: str | None = None,
        adjust: str = "qfq",
    ):
        # def 而非 async def：缓存未命中时 baostock 同步网络拉取可达数秒，
        # async 下直接调用会冻结事件循环；def 由 FastAPI 放线程池执行。
        """
        历史K线（A股支持前复权/后复权）

        - **adjust**: qfq前复权（默认）、hfq后复权、none不复权
        - 数据来源：baostock 优先，不可用时降级为 yfinance
        - 结果缓存到 SQLite 避免重复请求
        """
        clean_ticker = _validate_ticker_or_400(ticker)
        valid_adjust = adjust.lower() if adjust.lower() in ("qfq", "hfq", "none") else "qfq"
        try:
            from backend.services.historical_data_store import fetch_and_cache_kline
            bars = fetch_and_cache_kline(
                ticker=clean_ticker,
                start_date=start,
                end_date=end,
                adjust=valid_adjust,
            )
            return {
                "ticker": clean_ticker,
                "adjust": valid_adjust,
                "start": start,
                "end": end,
                "bars": len(bars),
                "data": bars,
            }
        except Exception as e:
            deps.logger.exception("historical kline error %s: %s", clean_ticker, e)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/api/market/historical-cache/tickers")
    def list_cached_tickers():
        """列出已有历史缓存的股票代码（def：同步 SQLite 读走线程池，不占事件循环）"""
        from backend.services.historical_data_store import get_cached_tickers
        return {"tickers": get_cached_tickers()}

    return router
