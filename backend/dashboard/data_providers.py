"""External valuation/financial-statement providers for the dashboard.

Extracted from data_service so the service layer stays focused on
aggregation while Finnhub/SEC/CN-HK adapters live here.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from backend.tools._item import iter_dict_items
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
        if isinstance(payload, dict) and (payload.get("error") or payload.get("success") is False
            or str(payload.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
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
    if number is None or number <= 0:
        return None
    return safe_float(number * 1_000_000.0)


def _fetch_valuation_from_finnhub(symbol: str) -> dict[str, Any] | None:
    """Fallback valuation fetcher using Finnhub free endpoints."""
    profile = _finnhub_request("stock/profile2", {"symbol": symbol})
    metric_payload = _finnhub_request("stock/metric", {"symbol": symbol, "metric": "all"})
    if any(value is not None and str(value).strip().upper() != symbol.strip().upper()
           for payload in (profile, metric_payload) if isinstance(payload, dict)
           for value in (payload.get("ticker"), payload.get("symbol"))):
        return None
    metric = metric_payload.get("metric") if isinstance(metric_payload, dict) else {}
    if (not isinstance(metric, dict) or metric.get("error") or metric.get("success") is False
        or str(metric.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
        metric = {}

    trailing_pe = safe_float(metric.get("peTTM"))
    if trailing_pe is None:
        trailing_pe = safe_float(metric.get("peBasicExclExtraTTM"))
    forward_pe = safe_float(metric.get("forwardPE"))
    if forward_pe is None:
        forward_pe = safe_float(metric.get("peExclExtraAnnual"))
    market_cap = _finnhub_market_cap_to_usd(profile.get("marketCapitalization")) if isinstance(profile, dict) else None
    if market_cap is None:
        market_cap = _finnhub_market_cap_to_usd(metric.get("marketCapitalization"))

    result = {
        "market_cap": market_cap,
        "trailing_pe": trailing_pe,
        "forward_pe": forward_pe,
        "price_to_book": safe_float(metric.get("pbQuarterly")),
        "price_to_sales": safe_float(metric.get("psTTM")),
        "ev_to_ebitda": safe_float(metric.get("evEbitdaTTM")),
        "dividend_yield": _finnhub_percent_to_ratio(metric.get("dividendYieldIndicatedAnnual")),
        "beta": safe_float(metric.get("beta")),
        "week52_high": safe_float(metric.get("52WeekHigh")),
        "week52_low": safe_float(metric.get("52WeekLow")),
    }
    if result["dividend_yield"] is not None and result["dividend_yield"] < 0:
        result["dividend_yield"] = None
    for key in ("market_cap", "week52_high", "week52_low"):
        if result[key] is not None and result[key] <= 0:
            result[key] = None
    if (result["week52_high"] is not None and result["week52_low"] is not None
        and result["week52_high"] < result["week52_low"]):
        result["week52_high"] = result["week52_low"] = None
    if all(v is None for v in result.values()):
        return None
    return result


def _fetch_valuation_from_cn_hk_market(symbol: str) -> dict[str, Any] | None:
    try:
        from backend.tools.cn_hk_market import fetch_cn_hk_quote_metrics

        payload = fetch_cn_hk_quote_metrics(symbol)
        if (not isinstance(payload, dict) or payload.get("error") or payload.get("success") is False
            or str(payload.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            return None
        if any(value is not None and str(value).strip().upper() != symbol.strip().upper()
               for value in (payload.get("ticker"), payload.get("symbol"))):
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
        if result["dividend_yield"] is not None and result["dividend_yield"] < 0:
            result["dividend_yield"] = None
        for key in ("market_cap", "week52_high", "week52_low"):
            if result[key] is not None and result[key] <= 0:
                result[key] = None
        if (result["week52_high"] is not None and result["week52_low"] is not None
            and result["week52_high"] < result["week52_low"]):
            result["week52_high"] = result["week52_low"] = None
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
    rows = [row for row in iter_dict_items(rows) if not row.get("error") and row.get("success") is not False
            and str(row.get("status") or "").strip().lower() not in {"error", "failed", "unavailable"}]
    for row in iter_dict_items(rows):
        concept = str(row.get("concept") or "").strip().lower()
        value = safe_float(row.get("value"))
        if value is not None and concept_terms and concept.rsplit("_", 1)[-1] in concept_terms:
            return value
    # 第一遍：标签子串 或 规范化 concept 全等（剥掉 us-gaap_/ifrs-full_ 等
    # 命名空间）。完整匹配必须优先于子串——"assets" 子串会命中 AssetsCurrent
    # 等分项概念，而 bs 行按报表顺序分项恒在合计之前 → 合计字段拿到分项值。
    for row in iter_dict_items(rows):
        label = str(row.get("label") or "").strip().lower()
        concept = str(row.get("concept") or "").strip().lower()
        value = safe_float(row.get("value"))
        if value is None:
            continue
        if label_terms and any(term in label for term in label_terms):
            return value
        if concept_terms and any(concept.rsplit("_", 1)[-1] == term for term in concept_terms):
            return value
    # 第二遍：宽松 concept 子串兜底——变体 concept 名（如
    # revenuefromcontractwithcustomerexcludingassessedtax、salesrevenuenet）
    # 且标签不含关键词时仍能命中，保持既有行为。
    for row in iter_dict_items(rows):
        concept = str(row.get("concept") or "").strip().lower()
        value = safe_float(row.get("value"))
        if value is None:
            continue
        if concept_terms and any(term in concept for term in concept_terms):
            return value
    return None


def _fetch_financial_statements_from_sec_companyfacts(symbol: str, periods: int = 8) -> dict[str, Any] | None:
    if periods <= 0:
        return None
    try:
        from backend.tools.sec import get_sec_company_facts_quarterly

        payload = get_sec_company_facts_quarterly(symbol, limit=periods)
        if (not isinstance(payload, dict) or payload.get("error") or payload.get("success") is False
            or str(payload.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            return None
        if any(value is not None and str(value).strip().upper() != symbol.strip().upper()
               for value in (payload.get("ticker"), payload.get("symbol"))):
            return None
        period_labels = payload.get("periods")
        if (not isinstance(period_labels, list) or not period_labels
            or any(not isinstance(label, str) or not label.strip() for label in period_labels)):
            return None
        period_labels = period_labels[:periods]
        result = {
            "periods": period_labels,
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
        for field in metric_fields:
            values = result[field]
            values = [safe_float(value) for value in values] if isinstance(values, list) else []
            result[field] = (values + [None] * len(period_labels))[:len(period_labels)]
        has_any_value = any(
            any(value is not None for value in (result.get(field) or []))
            for field in metric_fields
        )
        return result if has_any_value else None
    except Exception as exc:
        logger.warning("[DataService] SEC companyfacts fallback failed")
        return None


def _fetch_financial_statements_from_cn_hk_market(symbol: str, periods: int = 8) -> dict[str, Any] | None:
    if periods <= 0:
        return None
    try:
        from backend.tools.cn_hk_market import fetch_cn_hk_financial_statements

        payload = fetch_cn_hk_financial_statements(symbol, periods=periods)
        if (not isinstance(payload, dict) or payload.get("error") or payload.get("success") is False
            or str(payload.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            return None
        if any(value is not None and str(value).strip().upper() != symbol.strip().upper()
               for value in (payload.get("ticker"), payload.get("symbol"))):
            return None
        period_labels = payload.get("periods")
        if (not isinstance(period_labels, list) or not period_labels
            or any(not isinstance(label, str) or not label.strip() for label in period_labels)):
            return None
        period_labels = period_labels[:periods]
        result = {
            "periods": period_labels,
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
        for field in metric_fields:
            values = result[field]
            values = [safe_float(value) for value in values] if isinstance(values, list) else []
            result[field] = (values + [None] * len(period_labels))[:len(period_labels)]
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
    if periods <= 0:
        return None
    payload = _finnhub_request("stock/financials-reported", {"symbol": symbol})
    if isinstance(payload, dict) and any(
        value is not None and str(value).strip().upper() != symbol.strip().upper()
        for value in (payload.get("ticker"), payload.get("symbol"))
    ):
        return None
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        return None

    parsed: list[dict[str, Any]] = []
    for item in iter_dict_items(rows):
        if (item.get("error") or item.get("success") is False
            or str(item.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            continue
        if any(value is not None and str(value).strip().upper() != symbol.strip().upper()
               for value in (item.get("ticker"), item.get("symbol"))):
            continue
        report = item.get("report")
        if (not isinstance(report, dict) or report.get("error") or report.get("success") is False
            or str(report.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            continue
        year = safe_int(item.get("year"), 0) or 0
        quarter = safe_int(item.get("quarter"), 0) or 0
        if (not 1 <= year <= 9999 or quarter not in {0, 1, 2, 3, 4}
            or safe_float(item.get("year")) != year
            or item.get("quarter") is not None and safe_float(item.get("quarter")) != quarter):
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
                fcf_value = safe_float(ocf_value + capex if capex < 0 else ocf_value - capex)
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
