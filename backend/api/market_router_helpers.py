"""Shared validation and payload helpers for the market router."""

from __future__ import annotations

import re
from datetime import date as date_type
from typing import Any

from fastapi import HTTPException

from backend.utils.market_evidence import attach_financials_evidence, attach_market_evidence


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


def _validate_iso_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        date_type.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid date") from exc
    return value


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
