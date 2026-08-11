"""External valuation/financial-statement providers for the dashboard.

Extracted from data_service so the service layer stays focused on
aggregation while Finnhub/SEC/CN-HK adapters live here.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from backend.utils.quote import safe_float, safe_int

logger = logging.getLogger(__name__)

_FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


def _finnhub_request(path: str, params: Optional[dict[str, Any]] = None) -> Any | None:
    """Best-effort Finnhub request helper."""
    try:
        from backend.tools.env import FINNHUB_API_KEY
        from backend.tools.http import _http_get

        token = str(FINNHUB_API_KEY or "").strip()
        if not token:
            return None
        query = dict(params or {})
        query["token"] = token
        url = f"{_FINNHUB_BASE_URL}/{path.lstrip('/')}"
        resp = _http_get(url, params=query, timeout=12)
        if getattr(resp, "status_code", 0) != 200:
            return None
        payload = resp.json()
        if isinstance(payload, dict) and payload.get("error"):
            return None
        return payload
    except Exception as exc:
        logger.warning("[DataService] Finnhub request failed")
        return None


def _finnhub_percent_to_ratio(value: Any) -> Optional[float]:
    """Convert Finnhub percentage-like values into decimal ratio."""
    number = safe_float(value)
    if number is None:
        return None
    return number / 100.0


def _finnhub_market_cap_to_usd(value: Any) -> Optional[float]:
    """Finnhub marketCapitalization is in millions of USD."""
    number = safe_float(value)
    if number is None:
        return None
    return number * 1_000_000.0


def _fetch_valuation_from_finnhub(symbol: str) -> dict[str, Any] | None:
    """Fallback valuation fetcher using Finnhub free endpoints."""
    profile = _finnhub_request("stock/profile2", {"symbol": symbol})
    metric_payload = _finnhub_request("stock/metric", {"symbol": symbol, "metric": "all"})
    metric = metric_payload.get("metric") if isinstance(metric_payload, dict) else {}
    if not isinstance(metric, dict):
        metric = {}

    result = {
        "market_cap": _finnhub_market_cap_to_usd(
            (profile or {}).get("marketCapitalization") if isinstance(profile, dict) else metric.get("marketCapitalization")
        ),
        "trailing_pe": safe_float(metric.get("peTTM") or metric.get("peBasicExclExtraTTM")),
        "forward_pe": safe_float(metric.get("forwardPE") or metric.get("peExclExtraAnnual")),
        "price_to_book": safe_float(metric.get("pbQuarterly")),
        "price_to_sales": safe_float(metric.get("psTTM")),
        "ev_to_ebitda": safe_float(metric.get("evEbitdaTTM")),
        "dividend_yield": _finnhub_percent_to_ratio(metric.get("dividendYieldIndicatedAnnual")),
        "beta": safe_float(metric.get("beta")),
        "week52_high": safe_float(metric.get("52WeekHigh")),
        "week52_low": safe_float(metric.get("52WeekLow")),
    }
    if all(v is None for v in result.values()):
        return None
    return result


def _fetch_valuation_from_cn_hk_market(symbol: str) -> dict[str, Any] | None:
    try:
        from backend.tools.cn_hk_market import fetch_cn_hk_quote_metrics

        payload = fetch_cn_hk_quote_metrics(symbol)
        if not isinstance(payload, dict):
            return None
        result = {
            "market_cap": safe_float(payload.get("market_cap")),
            "trailing_pe": safe_float(payload.get("trailing_pe")),
            "forward_pe": safe_float(payload.get("forward_pe")),
            "price_to_book": safe_float(payload.get("price_to_book")),
            "price_to_sales": safe_float(payload.get("price_to_sales")),
            "ev_to_ebitda": safe_float(payload.get("ev_to_ebitda")),
            "dividend_yield": safe_float(payload.get("dividend_yield")),
            "beta": safe_float(payload.get("beta")),
            "week52_high": safe_float(payload.get("week52_high")),
            "week52_low": safe_float(payload.get("week52_low")),
        }
        if all(v is None for v in result.values()):
            return None
        return result
    except Exception as exc:
        logger.warning("[DataService] CN/HK valuation fallback failed")
        return None


def _match_report_value(
    rows: list[dict[str, Any]],
    *,
    label_terms: tuple[str, ...] = (),
    concept_terms: tuple[str, ...] = (),
) -> Optional[float]:
    for row in rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").strip().lower()
        concept = str(row.get("concept") or "").strip().lower()
        value = safe_float(row.get("value"))
        if value is None:
            continue
        if label_terms and any(term in label for term in label_terms):
            return value
        if concept_terms and any(term in concept for term in concept_terms):
            return value
    return None


def _fetch_financial_statements_from_sec_companyfacts(symbol: str, periods: int = 8) -> dict[str, Any] | None:
    try:
        from backend.tools.sec import get_sec_company_facts_quarterly

        payload = get_sec_company_facts_quarterly(symbol, limit=periods)
        if not isinstance(payload, dict) or payload.get("error"):
            return None
        result = {
            "periods": payload.get("periods") or [],
            "revenue": payload.get("revenue") or [],
            "gross_profit": payload.get("gross_profit") or [],
            "operating_income": payload.get("operating_income") or [],
            "net_income": payload.get("net_income") or [],
            "eps": payload.get("eps") or [],
            "total_assets": payload.get("total_assets") or [],
            "total_liabilities": payload.get("total_liabilities") or [],
            "operating_cash_flow": payload.get("operating_cash_flow") or [],
            "free_cash_flow": payload.get("free_cash_flow") or [],
        }
        metric_fields = [
            "revenue",
            "gross_profit",
            "operating_income",
            "net_income",
            "eps",
            "total_assets",
            "total_liabilities",
            "operating_cash_flow",
            "free_cash_flow",
        ]
        has_any_value = any(
            any(value is not None for value in (result.get(field) or []))
            for field in metric_fields
        )
        return result if has_any_value else None
    except Exception as exc:
        logger.warning("[DataService] SEC companyfacts fallback failed")
        return None


def _fetch_financial_statements_from_cn_hk_market(symbol: str, periods: int = 8) -> dict[str, Any] | None:
    try:
        from backend.tools.cn_hk_market import fetch_cn_hk_financial_statements

        payload = fetch_cn_hk_financial_statements(symbol, periods=periods)
        if not isinstance(payload, dict):
            return None
        result = {
            "periods": payload.get("periods") or [],
            "revenue": payload.get("revenue") or [],
            "gross_profit": payload.get("gross_profit") or [],
            "operating_income": payload.get("operating_income") or [],
            "net_income": payload.get("net_income") or [],
            "eps": payload.get("eps") or [],
            "total_assets": payload.get("total_assets") or [],
            "total_liabilities": payload.get("total_liabilities") or [],
            "operating_cash_flow": payload.get("operating_cash_flow") or [],
            "free_cash_flow": payload.get("free_cash_flow") or [],
        }
        metric_fields = [
            "revenue",
            "gross_profit",
            "operating_income",
            "net_income",
            "eps",
            "total_assets",
            "total_liabilities",
            "operating_cash_flow",
            "free_cash_flow",
        ]
        has_any_value = any(
            any(value is not None for value in (result.get(field) or []))
            for field in metric_fields
        )
        return result if has_any_value else None
    except Exception as exc:
        logger.warning("[DataService] CN/HK financials fallback failed")
        return None


def _fetch_financial_statements_from_finnhub(symbol: str, periods: int = 8) -> dict[str, Any] | None:
    """Fallback quarterly statements fetch using Finnhub financial reports."""
    payload = _finnhub_request("stock/financials-reported", {"symbol": symbol})
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        return None

    parsed: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        report = item.get("report")
        if not isinstance(report, dict):
            continue
        year = safe_int(item.get("year"), 0) or 0
        quarter = safe_int(item.get("quarter"), 0) or 0
        if year <= 0:
            continue
        label = f"{year}Q{quarter}" if quarter > 0 else f"{year}FY"
        parsed.append(
            {
                "period": label,
                "year": year,
                "quarter": quarter,
                "report": report,
            }
        )

    if not parsed:
        return None

    quarterly = [entry for entry in parsed if entry["quarter"] > 0]
    selected_source = quarterly if quarterly else parsed
    selected_source = sorted(
        selected_source,
        key=lambda entry: (entry["year"], entry["quarter"]),
        reverse=True,
    )

    deduped: list[dict[str, Any]] = []
    seen_periods: set[str] = set()
    for entry in selected_source:
        period = entry["period"]
        if period in seen_periods:
            continue
        seen_periods.add(period)
        deduped.append(entry)
        if len(deduped) >= max(1, periods):
            break

    if not deduped:
        return None

    period_labels: list[str] = []
    revenue: list[Optional[float]] = []
    gross_profit: list[Optional[float]] = []
    operating_income: list[Optional[float]] = []
    net_income: list[Optional[float]] = []
    eps: list[Optional[float]] = []
    total_assets: list[Optional[float]] = []
    total_liabilities: list[Optional[float]] = []
    operating_cash_flow: list[Optional[float]] = []
    free_cash_flow: list[Optional[float]] = []

    for entry in deduped:
        report = entry["report"]
        ic_rows = report.get("ic") if isinstance(report.get("ic"), list) else []
        bs_rows = report.get("bs") if isinstance(report.get("bs"), list) else []
        cf_rows = report.get("cf") if isinstance(report.get("cf"), list) else []

        period_labels.append(entry["period"])

        revenue.append(
            _match_report_value(
                ic_rows,
                label_terms=("net sales", "total revenue", "revenue"),
                concept_terms=("revenue", "salesrevenue"),
            )
        )
        gross_profit.append(
            _match_report_value(
                ic_rows,
                label_terms=("gross profit",),
                concept_terms=("grossprofit",),
            )
        )
        operating_income.append(
            _match_report_value(
                ic_rows,
                label_terms=("operating income",),
                concept_terms=("operatingincomeloss",),
            )
        )
        net_income.append(
            _match_report_value(
                ic_rows,
                label_terms=("net income",),
                concept_terms=("netincomeloss",),
            )
        )
        eps.append(
            _match_report_value(
                ic_rows,
                label_terms=("diluted earnings per share", "basic earnings per share", "earnings per share"),
                concept_terms=("earningspersharediluted", "earningspersharebasic"),
            )
        )
        total_assets.append(
            _match_report_value(
                bs_rows,
                label_terms=("total assets",),
                concept_terms=("assets",),
            )
        )
        total_liabilities.append(
            _match_report_value(
                bs_rows,
                label_terms=("total liabilities",),
                concept_terms=("liabilities",),
            )
        )

        ocf_value = _match_report_value(
            cf_rows,
            label_terms=(
                "net cash provided by operating activities",
                "net cash from operating activities",
                "cash generated by operating activities",
            ),
            concept_terms=(
                "netcashprovidedbyusedinoperatingactivities",
                "netcashprovidedbyusedinoperatingactivitiescontinuingoperations",
            ),
        )
        operating_cash_flow.append(ocf_value)

        fcf_value = _match_report_value(
            cf_rows,
            label_terms=("free cash flow",),
            concept_terms=("freecashflow",),
        )
        if fcf_value is None:
            capex = _match_report_value(
                cf_rows,
                label_terms=(
                    "payments to acquire property, plant and equipment",
                    "capital expenditures",
                    "purchase of property and equipment",
                ),
                concept_terms=(
                    "paymentstoacquirepropertyplantandequipment",
                    "capitalexpenditures",
                ),
            )
            if ocf_value is not None and capex is not None:
                fcf_value = ocf_value + capex if capex < 0 else ocf_value - capex
        free_cash_flow.append(fcf_value)

    result: dict[str, Any] = {
        "periods": period_labels,
        "revenue": revenue,
        "gross_profit": gross_profit,
        "operating_income": operating_income,
        "net_income": net_income,
        "eps": eps,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "operating_cash_flow": operating_cash_flow,
        "free_cash_flow": free_cash_flow,
    }
    metric_fields = [
        "revenue",
        "gross_profit",
        "operating_income",
        "net_income",
        "eps",
        "total_assets",
        "total_liabilities",
        "operating_cash_flow",
        "free_cash_flow",
    ]
    has_any_value = any(
        any(value is not None for value in (result.get(field) or []))
        for field in metric_fields
    )
    return result if has_any_value else None
