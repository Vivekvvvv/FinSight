"""Peer comparison data service.

Resolves peer symbols based on industry/sector and fetches comparative
valuation metrics for a target symbol and its peers.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout, as_completed
from typing import Any, Optional

from backend.utils.quote import safe_float

logger = logging.getLogger(__name__)

# Hardcoded sector peer map used when dynamic resolution is unavailable.
_SECTOR_PEER_MAP: dict[str, list[str]] = {
    "Technology": ["AAPL", "MSFT", "GOOGL", "META", "NVDA", "AMZN", "CRM", "ORCL"],
    "Consumer Electronics": ["AAPL", "SONY", "SSNLF", "HPQ", "DELL"],
    "Semiconductors": ["NVDA", "AMD", "INTC", "AVGO", "QCOM", "TSM", "MU", "TXN"],
    "Internet Content & Information": ["GOOGL", "META", "SNAP", "PINS", "BIDU"],
    "Software - Infrastructure": ["MSFT", "ORCL", "CRM", "NOW", "ADBE", "INTU"],
    "Automotive": ["TSLA", "F", "GM", "TM", "HMC", "STLA", "RIVN"],
    "Financial Services": ["JPM", "BAC", "GS", "MS", "WFC", "C", "SCHW"],
    "Healthcare": ["JNJ", "UNH", "PFE", "ABBV", "MRK", "LLY", "TMO"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "EOG", "OXY", "MPC"],
    "Consumer Cyclical": ["AMZN", "TSLA", "HD", "NKE", "MCD", "SBUX", "TGT"],
    "Communication Services": ["GOOGL", "META", "DIS", "NFLX", "CMCSA", "T", "VZ"],
}

_DEFAULT_PEERS_BY_MARKET: dict[str, list[str]] = {
    "US": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "XOM", "UNH"],
    "CN": ["600519.SS", "000858.SZ", "601318.SS", "600036.SS", "600900.SS", "601899.SS"],
    "HK": ["0700.HK", "9988.HK", "1299.HK", "0005.HK", "0939.HK", "2318.HK"],
}
_DEFAULT_PEERS: list[str] = list(_DEFAULT_PEERS_BY_MARKET["US"])


_FINNHUB_BASE_URL = "https://finnhub.io/api/v1"


def _infer_market_from_symbol(symbol: str) -> str:
    ticker = str(symbol or "").strip().upper()
    if ticker.endswith((".SS", ".SH", ".SZ", ".BJ")) or ticker.isdigit() and len(ticker) == 6:
        return "CN"
    if ticker.endswith(".HK"):
        return "HK"
    return "US"


def _finnhub_request(path: str, params: Optional[dict[str, Any]] = None) -> Any | None:
    try:
        from backend.tools.env import FINNHUB_API_KEY
        from backend.tools.http import _http_get

        token = str(FINNHUB_API_KEY or "").strip()
        if not token:
            return None
        query = dict(params or {})
        query["token"] = token
        url = f"{_FINNHUB_BASE_URL}/{path.lstrip('/')}"
        resp = _http_get(url, params=query, timeout=8)
        if getattr(resp, "status_code", 0) != 200:
            return None
        payload = resp.json()
        if isinstance(payload, dict) and (payload.get("error") or payload.get("success") is False
            or str(payload.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            return None
        return payload
    except Exception as exc:
        logger.info("[PeerService] Finnhub request failed")
        return None


def _pct_to_ratio(value: Any) -> Optional[float]:
    number = safe_float(value)
    if number is None:
        return None
    return number / 100.0


def _market_cap_to_usd(value: Any) -> Optional[float]:
    number = safe_float(value)
    if number is None or number <= 0:
        return None
    return safe_float(number * 1_000_000.0)


def _has_peer_metrics(row: dict[str, Any]) -> bool:
    return any(
        (value := safe_float(row.get(key))) is not None and (key != "market_cap" or value > 0)
        and (key != "dividend_yield" or value >= 0)
        for key in (
            "trailing_pe",
            "forward_pe",
            "price_to_book",
            "ev_to_ebitda",
            "net_margin",
            "roe",
            "revenue_growth",
            "dividend_yield",
            "market_cap",
        )
    )


def _first_float(primary: Any, fallback: Any) -> float | None:
    number = safe_float(primary)
    return number if number is not None else safe_float(fallback)


def _fetch_single_peer_metrics_from_finnhub(sym: str) -> dict[str, Any] | None:
    profile = _finnhub_request("stock/profile2", {"symbol": sym})
    metric_payload = _finnhub_request("stock/metric", {"symbol": sym, "metric": "all"})
    for payload in (profile, metric_payload):
        if isinstance(payload, dict) and any(
            value is not None and str(value).strip().upper() != sym.strip().upper()
            for value in (payload.get("symbol"), payload.get("ticker"))
        ):
            return None
    metric = metric_payload.get("metric") if isinstance(metric_payload, dict) else {}
    if (not isinstance(metric, dict) or metric.get("error") or metric.get("success") is False
        or str(metric.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
        metric = {}

    result = {
        "symbol": sym,
        "name": (profile or {}).get("name") if isinstance(profile, dict) else sym,
        "trailing_pe": _first_float(metric.get("peTTM"), metric.get("peBasicExclExtraTTM")),
        "forward_pe": _first_float(metric.get("forwardPE"), metric.get("peExclExtraAnnual")),
        "price_to_book": safe_float(metric.get("pbQuarterly")),
        "ev_to_ebitda": safe_float(metric.get("evEbitdaTTM")),
        "net_margin": _pct_to_ratio(metric.get("netProfitMarginTTM")),
        "roe": _pct_to_ratio(metric.get("roeTTM")),
        "revenue_growth": _pct_to_ratio(metric.get("revenueGrowthTTMYoy")),
        "dividend_yield": _pct_to_ratio(metric.get("dividendYieldIndicatedAnnual")),
        "market_cap": _first_float(
            _market_cap_to_usd(profile.get("marketCapitalization") if isinstance(profile, dict) else None),
            _market_cap_to_usd(metric.get("marketCapitalization")),
        ),
    }
    if result["dividend_yield"] is not None and result["dividend_yield"] < 0:
        result["dividend_yield"] = None
    if not _has_peer_metrics(result):
        return None
    name = result.get("name")
    result["name"] = name.strip() if isinstance(name, str) and name.strip() else sym
    return result


def _fetch_single_peer_metrics_from_cn_hk(sym: str) -> dict[str, Any] | None:
    try:
        from backend.tools.cn_hk_market import fetch_cn_hk_quote_metrics

        payload = fetch_cn_hk_quote_metrics(sym)
        if (not isinstance(payload, dict) or payload.get("error") or payload.get("success") is False
            or str(payload.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            return None
        if any(value is not None and str(value).strip().upper() != sym.strip().upper()
               for value in (payload.get("symbol"), payload.get("ticker"))):
            return None
        result = {
            "symbol": sym,
            "name": payload.get("name") or sym,
            "trailing_pe": safe_float(payload.get("trailing_pe")),
            "forward_pe": safe_float(payload.get("forward_pe")),
            "price_to_book": safe_float(payload.get("price_to_book")),
            "ev_to_ebitda": safe_float(payload.get("ev_to_ebitda")),
            "net_margin": None,
            "roe": None,
            "revenue_growth": None,
            "dividend_yield": safe_float(payload.get("dividend_yield")),
            "market_cap": safe_float(payload.get("market_cap")),
        }
        name = result.get("name")
        result["name"] = name.strip() if isinstance(name, str) and name.strip() else sym
        if result["dividend_yield"] is not None and result["dividend_yield"] < 0:
            result["dividend_yield"] = None
        if result["market_cap"] is not None and result["market_cap"] <= 0:
            result["market_cap"] = None
        if not _has_peer_metrics(result):
            return None
        return result
    except Exception as exc:
        logger.info("[PeerService] CN/HK metrics fetch failed")
        return None


def resolve_peers(symbol: str, limit: int = 6) -> list[str]:
    """Find peer symbols based on industry/sector from yfinance.

    Falls back to a hardcoded sector map when dynamic lookup fails.
    The target *symbol* is excluded from the returned list.

    Args:
        symbol: The target ticker symbol.
        limit: Maximum number of peer symbols to return.

    Returns:
        A list of peer ticker strings (may be empty).
    """
    symbol = str(symbol or "").strip().upper()
    if not symbol or limit <= 0:
        return []
    market = _infer_market_from_symbol(symbol)
    if market in {"CN", "HK"}:
        defaults = _DEFAULT_PEERS_BY_MARKET.get(market, _DEFAULT_PEERS_BY_MARKET["US"])
        return [s for s in defaults if s.upper() != symbol
                and not (symbol.isdigit() and len(symbol) == 6 and s.split(".")[0] == symbol)][:limit]

    industry = ""
    sector = ""
    try:
        import yfinance as yf

        info = yf.Ticker(symbol).info or {}
        if (not isinstance(info, dict) or info.get("error") or info.get("success") is False
            or str(info.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}
            or any(value is not None and str(value).strip().upper() != symbol
                   for value in (info.get("ticker"), info.get("symbol")))):
            raise ValueError("peer classification unavailable")
        industry = info.get("industry")
        sector = info.get("sector")
        industry = industry.strip() if isinstance(industry, str) else ""
        sector = sector.strip() if isinstance(sector, str) else ""
    except Exception as exc:
                logger.info("[PeerService] yfinance info failed")

    # Try FMP stock screener with matching industry (best-effort)
    peers: list[str] = []
    if industry:
        try:
            from backend.tools.fmp import _fmp_request

            data = _fmp_request(
                "/v3/stock-screener",
                params={
                    "industry": industry,
                    "limit": str(limit + 5),
                    "exchange": "NYSE,NASDAQ",
                },
            )
            if isinstance(data, list):
                for item in data:
                    # 毒条目按条跳过——非 dict 的 .get AttributeError、symbol
                    # 非 str 的 .upper() 落进外层 except 让其后合法 peer 全丢
                    # （毒条目在首位时整份动态结果丢光走静态兜底，同 R107）
                    if (not isinstance(item, dict) or item.get("error") or item.get("success") is False
                        or str(item.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
                        continue
                    sym = item.get("symbol")
                    if not isinstance(sym, str) or not sym.strip():
                        continue
                    sym = sym.strip().upper()
                    if sym != symbol and sym not in peers:
                        peers.append(sym)
                    if len(peers) >= limit:
                        break
        except Exception as exc:
                logger.info("[PeerService] FMP screener failed")

    # Fallback to hardcoded sector map
    if not peers:
        candidates: list[str] = []
        # Try industry-level match first, then sector-level
        for key in (industry, sector):
            if key and key in _SECTOR_PEER_MAP:
                candidates = _SECTOR_PEER_MAP[key]
                break
        if not candidates:
            # Partial match on sector name
            sector_lower = sector.lower()
            for key, syms in _SECTOR_PEER_MAP.items():
                if sector_lower and (key.lower() in sector_lower or sector_lower in key.lower()):
                    candidates = syms
                    break
        peers = [s for s in candidates if s.upper() != symbol.upper()][:limit]

    if not peers:
        defaults = _DEFAULT_PEERS_BY_MARKET.get(market, _DEFAULT_PEERS_BY_MARKET["US"])
        peers = [s for s in defaults if s.upper() != symbol.upper()][:limit]

    return peers[:limit]


def _fetch_single_peer_metrics(sym: str) -> dict[str, Any]:
    """Fetch valuation metrics for a single symbol via yfinance."""
    market = _infer_market_from_symbol(sym)
    if market in {"CN", "HK"}:
        cn_hk_result = _fetch_single_peer_metrics_from_cn_hk(sym)
        if cn_hk_result:
            return cn_hk_result

    yfinance_result: dict[str, Any] = {"symbol": sym, "name": sym}
    try:
        import yfinance as yf

        info = yf.Ticker(sym).info or {}
        if (not isinstance(info, dict) or info.get("error") or info.get("success") is False
            or str(info.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            raise ValueError("peer metrics unavailable")
        if any(value is not None and str(value).strip().upper() != sym.strip().upper()
               for value in (info.get("symbol"), info.get("ticker"))):
            raise ValueError("peer instrument mismatch")
        yfinance_result = {
            "symbol": sym,
            "name": next((name.strip() for name in (info.get("shortName"), info.get("longName"))
                          if isinstance(name, str) and name.strip()), sym),
            "trailing_pe": safe_float(info.get("trailingPE")),
            "forward_pe": safe_float(info.get("forwardPE")),
            "price_to_book": safe_float(info.get("priceToBook")),
            "ev_to_ebitda": safe_float(info.get("enterpriseToEbitda")),
            "net_margin": safe_float(info.get("profitMargins")),
            "roe": safe_float(info.get("returnOnEquity")),
            "revenue_growth": safe_float(info.get("revenueGrowth")),
            "dividend_yield": safe_float(info.get("dividendYield")),
            "market_cap": safe_float(info.get("marketCap")),
        }
        if yfinance_result["dividend_yield"] is not None and yfinance_result["dividend_yield"] < 0:
            yfinance_result["dividend_yield"] = None
        if yfinance_result["market_cap"] is not None and yfinance_result["market_cap"] <= 0:
            yfinance_result["market_cap"] = None
        if _has_peer_metrics(yfinance_result):
            return yfinance_result
    except Exception as exc:
                logger.info("[PeerService] metrics fetch failed")

    finnhub_result = _fetch_single_peer_metrics_from_finnhub(sym)
    if finnhub_result:
        return finnhub_result
    return yfinance_result


def fetch_peer_comparison(
    symbol: str,
    peers: list[str] | None = None,
) -> dict[str, Any] | None:
    """Fetch comparison metrics for *symbol* and its peers.

    Args:
        symbol: The target ticker.
        peers: Optional explicit peer list.  If *None*, peers are
            resolved automatically via :func:`resolve_peers`.

    Returns:
        A dict matching the ``PeerComparisonData`` schema, or *None*
        on total failure.
    """
    try:
        symbol = str(symbol or "").strip().upper()
        if not symbol:
            return None
        if peers is None:
            peers = resolve_peers(symbol, limit=6)

        all_symbols = list(dict.fromkeys([symbol] + [
            p.strip().upper() for p in peers if isinstance(p, str) and p.strip()
        ]))

        # Fetch metrics in parallel (max 3 workers for budget constraint).
        # Use a global timeout to avoid cumulative per-future waits.
        results_by_symbol: dict[str, dict[str, Any]] = {
            s: {"symbol": s, "name": s} for s in all_symbols
        }
        # 不能用 `with`：`__exit__` 走 shutdown(wait=True)，超时未完成的
        # 慢 peer 线程会让本函数继续阻塞到其返回，8s 全局预算被架空。
        pool = ThreadPoolExecutor(max_workers=3)
        try:
            futures = {pool.submit(_fetch_single_peer_metrics, s): s for s in all_symbols}
            try:
                for future in as_completed(futures, timeout=8):
                    sym = futures[future]
                    try:
                        result = future.result()
                        if (not isinstance(result, dict) or result.get("error") or result.get("success") is False
                            or str(result.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
                            continue
                        if any(value is not None and str(value).strip().upper() != sym
                               for value in (result.get("symbol"), result.get("ticker"))):
                            continue
                        results_by_symbol[sym] = result
                    except Exception as exc:
                        logger.info("[PeerService] peer fetch failed")
            except FuturesTimeout:
                logger.info("[PeerService] global timeout while fetching peers")
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

        results: list[dict[str, Any]] = [results_by_symbol[s] for s in all_symbols]

        payload = {
            "subject_symbol": symbol,
            "peers": results,
        }
        has_any_metric = any(_has_peer_metrics(row) for row in results if isinstance(row, dict))
        return payload if has_any_metric else None
    except Exception as exc:
        logger.info("[PeerService] fetch_peer_comparison failed")
        return None
