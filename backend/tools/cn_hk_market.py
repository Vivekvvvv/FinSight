from __future__ import annotations

import logging
import os

from backend.utils.env_config import env_int
import re
from datetime import datetime
from typing import Any, Iterator, Optional

from backend.utils.quote import safe_float, safe_int

from ._item import iter_dict_items
from .http import _http_get

logger = logging.getLogger(__name__)

_EASTMONEY_USER_AGENT = os.getenv("EASTMONEY_USER_AGENT", "Mozilla/5.0 (FinSight)")
_EASTMONEY_TIMEOUT = env_int("EASTMONEY_TIMEOUT", 12, minimum=1)
_EASTMONEY_QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
_EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_EASTMONEY_FINANCIAL_URL = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
_TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q={code}"
_SINA_QUOTE_URL = "https://hq.sinajs.cn/list={code}"


def detect_market(ticker: str) -> str:
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return "UNKNOWN"
    if symbol.endswith((".SS", ".SH", ".SZ", ".BJ")):
        return "CN"
    if symbol.endswith(".HK"):
        return "HK"
    return "UNKNOWN"


def normalize_ticker(ticker: str) -> str:
    return str(ticker or "").strip().upper()


def ticker_to_eastmoney_secid(ticker: str) -> str | None:
    symbol = normalize_ticker(ticker)
    market = detect_market(symbol)
    if market == "CN":
        if symbol.endswith((".SS", ".SH")):
            return f"1.{symbol[:-3]}"
        if symbol.endswith(".SZ") or symbol.endswith(".BJ"):
            return f"0.{symbol[:-3]}"
        return None
    if market == "HK":
        core = re.sub(r"\D", "", symbol[:-3])
        if not core:
            return None
        return f"116.{core.zfill(5)}"
    return None


def ticker_to_cn_quote_code(ticker: str) -> str | None:
    symbol = normalize_ticker(ticker)
    if symbol.endswith((".SS", ".SH")):
        return f"sh{symbol[:-3]}"
    if symbol.endswith(".SZ"):
        return f"sz{symbol[:-3]}"
    if symbol.endswith(".BJ"):
        # 北交所用 bj 前缀（腾讯/新浪一致），并入 .SZ 分支会产出
        # sz8xxxxx 查无此票，BJ 兜底链全灭。
        return f"bj{symbol[:-3]}"
    if symbol.endswith(".HK"):
        core = re.sub(r"\D", "", symbol[:-3])
        return f"hk{core.zfill(5)}" if core else None
    return None


def ticker_to_secu_code(ticker: str) -> str | None:
    symbol = normalize_ticker(ticker)
    market = detect_market(symbol)
    if market == "CN":
        if symbol.endswith((".SS", ".SH")):
            return f"{symbol[:-3]}.SH"
        if symbol.endswith(".SZ"):
            return f"{symbol[:-3]}.SZ"
        if symbol.endswith(".BJ"):
            return f"{symbol[:-3]}.BJ"
        return None
    if market == "HK":
        core = re.sub(r"\D", "", symbol[:-3])
        if not core:
            return None
        return f"{core.zfill(5)}.HK"
    return None


def _eastmoney_get_json(url: str, params: dict[str, Any], timeout: int | None = None) -> dict[str, Any] | None:
    try:
        resp = _http_get(
            url,
            params=params,
            timeout=max(1, safe_int(timeout, _EASTMONEY_TIMEOUT) or _EASTMONEY_TIMEOUT),
            headers={"User-Agent": _EASTMONEY_USER_AGENT},
        )
        if getattr(resp, "status_code", 0) != 200:
            return None
        payload = resp.json()
        if isinstance(payload, dict) and (
            payload.get("success") is False or payload.get("error")
            or str(payload.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}
            or (payload.get("rc") is not None and safe_int(payload["rc"]) != 0)
        ):
            return None
        return payload if isinstance(payload, dict) else None
    except Exception as exc:
        logger.info('[CNHK] eastmoney request failed')
        return None


def _http_get_text(url: str, *, timeout: int | None = None, referer: str | None = None) -> str | None:
    try:
        headers = {"User-Agent": _EASTMONEY_USER_AGENT}
        if referer:
            headers["Referer"] = referer
        resp = _http_get(url, timeout=max(1, safe_int(timeout, 3) or 3), headers=headers)
        if getattr(resp, "status_code", 0) != 200:
            return None
        return str(getattr(resp, "text", "") or "")
    except Exception as exc:
        logger.info('[CNHK] quote text request failed')
        return None


def _parse_tencent_quote(ticker: str, text: str) -> dict[str, Any] | None:
    code = ticker_to_cn_quote_code(ticker)
    if not code:
        return None
    match = re.search(rf'\bv_{re.escape(code)}\s*=\s*"([^"]*)"', text or "")
    if not match:
        return None
    parts = match.group(1).split("~")
    if len(parts) < 45:
        return None
    if parts[2].strip().lstrip("0") != normalize_ticker(ticker)[:-3].lstrip("0"):
        return None
    market = detect_market(ticker)
    price = safe_float(parts[3])
    if price is None or price <= 0:
        return None
    return {
        "symbol": normalize_ticker(ticker),
        "market": market,
        "name": parts[1].strip() or normalize_ticker(ticker),
        "last_price": price,
        "market_cap": safe_float(cap * 100_000_000) if len(parts) > 45 and (cap := safe_float(parts[45])) is not None and cap > 0 else None,
        "trailing_pe": safe_float(parts[39]) if len(parts) > 39 else None,
        "forward_pe": None,
        "price_to_book": None,
        "price_to_sales": None,
        "ev_to_ebitda": None,
        "dividend_yield": None,
        "beta": None,
        "week52_high": safe_float(parts[47]) if len(parts) > 47 else None,
        "week52_low": safe_float(parts[48]) if len(parts) > 48 else None,
        "source": "tencent_quote",
    }


def _parse_sina_cn_quote(ticker: str, text: str) -> dict[str, Any] | None:
    code = ticker_to_cn_quote_code(ticker)
    if not code:
        return None
    match = re.search(rf'\bhq_str_{re.escape(code)}\s*=\s*"([^"]*)"', text or "")
    if not match:
        return None
    parts = match.group(1).split(",")
    if len(parts) < 31:
        return None
    price = safe_float(parts[3])
    if price is None or price <= 0:
        return None
    return {
        "symbol": normalize_ticker(ticker),
        "market": "CN",
        "name": parts[0].strip() or normalize_ticker(ticker),
        "last_price": price,
        "market_cap": None,
        "trailing_pe": None,
        "forward_pe": None,
        "price_to_book": None,
        "price_to_sales": None,
        "ev_to_ebitda": None,
        "dividend_yield": None,
        "beta": None,
        # 新浪返回字段 [4]/[5] 是当日最高/最低，整条报文没有 52 周数据；
        # 旧代码把它们塞进 week52_high/week52_low，下游估值卡片会把
        # 日内振幅当成 52 周区间展示。数据源没有该字段时必须为 None。
        "week52_high": None,
        "week52_low": None,
        "source": "sina_quote",
    }


def _fetch_tencent_quote_metrics(ticker: str, *, timeout: int | None = None) -> dict[str, Any] | None:
    code = ticker_to_cn_quote_code(ticker)
    if not code:
        return None
    text = _http_get_text(_TENCENT_QUOTE_URL.format(code=code), timeout=timeout, referer="https://gu.qq.com/")
    return _parse_tencent_quote(ticker, text or "")


def _fetch_sina_cn_quote_metrics(ticker: str, *, timeout: int | None = None) -> dict[str, Any] | None:
    code = ticker_to_cn_quote_code(ticker)
    if not code:
        return None
    text = _http_get_text(_SINA_QUOTE_URL.format(code=code), timeout=timeout, referer="https://finance.sina.com.cn/")
    return _parse_sina_cn_quote(ticker, text or "")


def _period_label(report_date: Any, report_type: Any) -> str | None:
    date_text = str(report_date or "").strip()
    if not date_text:
        return None
    day_part = date_text.split(" ")[0]
    try:
        dt = datetime.fromisoformat(day_part)
    except Exception:
        return None
    year = dt.year
    report_text = str(report_type or "").strip()
    if any(token in report_text for token in ("一季报", "一季度")):
        return f"{year}Q1"
    if any(token in report_text for token in ("中报", "半年报", "二季报", "二季度")):
        return f"{year}Q2"
    if any(token in report_text for token in ("三季报", "三季度")):
        return f"{year}Q3"
    if any(token in report_text for token in ("年报", "年度")):
        return f"{year}FY"
    quarter = (dt.month - 1) // 3 + 1
    return f"{year}Q{quarter}"


def _period_sort_key(period: str) -> tuple[int, int]:
    match = re.match(r"^(20\d{2})(Q([1-4])|FY)$", str(period or ""))
    if not match:
        return (0, 0)
    year = int(match.group(1))
    token = match.group(2)
    if token == "FY":
        # 年报报告期末是 12-31，即当年的第 4 个报告期。映射 (year, 0)
        # 会让 FY 在倒序中排到当年 Q1-Q3 之后——最新年报被当成最旧一期，
        # periods[0] 错标成 Q3，且 [:periods] 窗口可能把 FY 直接截掉。
        return (year, 4)
    quarter = int(match.group(3) or 0)
    return (year, quarter)


def _price_from_raw(value: Any, decimals: int) -> Optional[float]:
    raw = safe_float(value)
    if raw is None or raw <= 0:
        return None
    scale = 10 ** max(0, min(decimals, 6))
    if scale <= 0:
        scale = 100
    return raw / scale


def _percent_div_100(value: Any) -> Optional[float]:
    raw = safe_float(value)
    if raw is None:
        return None
    return raw / 100.0


def _first_float(primary: Any, fallback: Any) -> float | None:
    number = safe_float(primary)
    return number if number is not None else safe_float(fallback)


def _has_any_metric(result: dict[str, Any], metric_fields: tuple[str, ...]) -> bool:
    for field in metric_fields:
        values = result.get(field) or []
        if any(v is not None for v in values):
            return True
    return False


def fetch_cn_hk_quote_metrics(ticker: str, *, timeout: int | None = None) -> dict[str, Any] | None:
    ticker_norm = normalize_ticker(ticker)
    market = detect_market(ticker_norm)
    if market not in {"CN", "HK"}:
        return None

    secid = ticker_to_eastmoney_secid(ticker_norm)
    if not secid:
        return None

    payload = _eastmoney_get_json(
        _EASTMONEY_QUOTE_URL,
        {
            "secid": secid,
            "fields": "f43,f57,f58,f59,f116,f162,f167,f170,f168,f169,f174,f175",
        },
        timeout=timeout,
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    if (not isinstance(data, dict) or data.get("error") or data.get("success") is False
        or str(data.get("status") or "").strip().lower() in {"error", "failed", "unavailable"} or (
        data.get("f57") is not None
        and str(data["f57"]).strip().lstrip("0") != ticker_norm[:-3].lstrip("0")
    )):
        if market in {"CN", "HK"}:
            return _fetch_tencent_quote_metrics(ticker_norm, timeout=timeout) or (
                _fetch_sina_cn_quote_metrics(ticker_norm, timeout=timeout) if market == "CN" else None
            )
        return None

    decimals = safe_int(data.get("f59"), 2)
    result = {
        "symbol": ticker_norm,
        "market": market,
        "name": name.strip() if isinstance(name := data.get("f58"), str) and name.strip() else ticker_norm,
        "last_price": _price_from_raw(data.get("f43"), decimals),
        "market_cap": cap if (cap := safe_float(data.get("f116"))) is not None and cap > 0 else None,
        "trailing_pe": _percent_div_100(data.get("f162")),
        "forward_pe": None,
        "price_to_book": _percent_div_100(data.get("f167")),
        "price_to_sales": None,
        "ev_to_ebitda": None,
        "dividend_yield": None,
        "beta": None,
        "week52_high": _price_from_raw(data.get("f174"), decimals),
        "week52_low": _price_from_raw(data.get("f175"), decimals),
        "source": "eastmoney_quote",
    }
    if all(
        result.get(key) is None
        for key in (
            "last_price",
            "market_cap",
            "trailing_pe",
            "price_to_book",
            "week52_high",
            "week52_low",
        )
    ):
        if market in {"CN", "HK"}:
            return _fetch_tencent_quote_metrics(ticker_norm, timeout=timeout) or (
                _fetch_sina_cn_quote_metrics(ticker_norm, timeout=timeout) if market == "CN" else None
            )
        return None
    return result


# 东财 kline 参数映射：klt 周期码 + 每交易日 bar 数（分钟线按 A 股 4 小时交易日）
_INTERVAL_KLT = {
    "1d": ("101", 1.0), "1wk": ("102", 1 / 5), "1mo": ("103", 1 / 22),
    "60m": ("60", 4.0), "1h": ("60", 4.0), "30m": ("30", 8.0), "15m": ("15", 16.0), "5m": ("5", 48.0),
}
_PERIOD_TRADING_DAYS = {
    "1d": 1, "5d": 5, "1mo": 22, "3mo": 66, "6mo": 132, "1y": 260,
    "2y": 520, "5y": 1300, "10y": 2600, "ytd": 260, "max": 2600,
}


def kline_params_for(period: str, interval: str) -> tuple[str, int] | None:
    """把 yfinance 风格的 (period, interval) 映射为东财 (klt, limit)。

    不支持的 interval 返回 None——调用方应跳过东财源而不是用日线冒充。
    """
    entry = _INTERVAL_KLT.get(str(interval or "1d").lower())
    if not entry:
        return None
    klt, bars_per_day = entry
    days = _PERIOD_TRADING_DAYS.get(str(period or "1y").lower(), 260)
    limit = max(10, min(1200, int(days * bars_per_day) + 1))
    return klt, limit


def fetch_cn_hk_kline(ticker: str, *, limit: int = 260, klt: str = "101", fqt: str = "1") -> list[dict[str, Any]]:
    requested_limit = max(0, min(safe_int(limit, 260), 1200))
    if requested_limit == 0:
        return []
    ticker_norm = normalize_ticker(ticker)
    market = detect_market(ticker_norm)
    if market not in {"CN", "HK"}:
        return []

    secid = ticker_to_eastmoney_secid(ticker_norm)
    if not secid:
        return []

    payload = _eastmoney_get_json(
        _EASTMONEY_KLINE_URL,
        {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": str(klt),
            "fqt": str(fqt),
            "lmt": str(requested_limit),
            "end": "20500101",
        },
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, dict) and (data.get("error") or data.get("success") is False
        or str(data.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
        return []
    if isinstance(data, dict) and data.get("code") is not None and (
        str(data["code"]).strip().lstrip("0") != ticker_norm[:-3].lstrip("0")
    ):
        return []
    klines = data.get("klines") if isinstance(data, dict) else None
    if not isinstance(klines, list):
        return []

    output: list[dict[str, Any]] = []
    for raw in klines:
        parts = str(raw or "").split(",")
        if len(parts) < 6:
            continue
        try:
            datetime.fromisoformat(parts[0].strip())
        except (TypeError, ValueError, OverflowError):
            continue
        prices = [safe_float(parts[index]) for index in (1, 2, 3, 4)]
        if any(price is None or price <= 0 for price in prices):
            continue
        open_price, close, high, low = prices
        if high < max(open_price, close) or low > min(open_price, close):
            continue
        output.append(
            {
                "time": parts[0],
                "open": open_price,
                "close": close,
                "high": high,
                "low": low,
                "volume": volume if (volume := safe_float(parts[5])) is not None and volume >= 0 else None,
            }
        )
    output = sorted({row["time"]: row for row in output}.values(), key=lambda row: row["time"])
    return output[-requested_limit:]


def _fetch_finance_rows(report_name: str, secu_code: str, limit: int) -> list[dict[str, Any]]:
    limit = max(0, min(safe_int(limit, 20), 20))
    if limit == 0:
        return []
    payload = _eastmoney_get_json(
        _EASTMONEY_FINANCIAL_URL,
        {
            "reportName": report_name,
            "columns": "ALL",
            "pageNumber": "1",
            "pageSize": str(max(1, min(limit, 20))),
            "sortTypes": "-1",
            "sortColumns": "REPORT_DATE",
            "source": "F10",
            "client": "PC",
            "filter": f'(SECUCODE="{secu_code}")',
        },
    )
    result = payload.get("result") if isinstance(payload, dict) else None
    if isinstance(result, dict) and (result.get("error") or result.get("success") is False
        or str(result.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
        return []
    rows = result.get("data") if isinstance(result, dict) else None
    return [row for row in iter_dict_items(rows)
            if not row.get("error") and row.get("success") is not False
            and str(row.get("status") or "").strip().lower() not in {"error", "failed", "unavailable"}
            and (row.get("SECUCODE") is None or str(row["SECUCODE"]).strip().upper() == secu_code.upper())
            and (row.get("SECURITY_CODE") is None
                 or str(row["SECURITY_CODE"]).strip().lstrip("0") == secu_code.split(".")[0].lstrip("0"))]


def _latest_period_rows(rows: Any) -> Iterator[tuple[str, dict[str, Any]]]:
    """按报告日期倒序，保留每个报告期的首条有效记录。"""
    seen: set[str] = set()
    for row in sorted(iter_dict_items(rows), key=lambda row: row.get("REPORT_DATE")
                      if isinstance(row.get("REPORT_DATE"), str) else "", reverse=True):
        if (row.get("error") or row.get("success") is False
            or str(row.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            continue
        period = _period_label(row.get("REPORT_DATE"), row.get("REPORT_TYPE"))
        if period and period not in seen:
            seen.add(period)
            yield period, row


def fetch_cn_hk_financial_statements(ticker: str, periods: int = 8) -> dict[str, Any] | None:
    ticker_norm = normalize_ticker(ticker)
    market = detect_market(ticker_norm)
    if market not in {"CN", "HK"}:
        return None

    secu_code = ticker_to_secu_code(ticker_norm)
    if not secu_code:
        return None

    target_periods = max(0, min(safe_int(periods, 8), 12))
    if target_periods == 0:
        return None
    rows_by_period: dict[str, dict[str, Any]] = {}

    if market == "CN":
        income_rows = _fetch_finance_rows("RPT_F10_FINANCE_GINCOME", secu_code, target_periods + 3)
        balance_rows = _fetch_finance_rows("RPT_F10_FINANCE_GBALANCE", secu_code, target_periods + 3)
        cash_rows = _fetch_finance_rows("RPT_F10_FINANCE_GCASHFLOW", secu_code, target_periods + 3)

        for period, row in _latest_period_rows(income_rows):
            entry = rows_by_period.setdefault(period, {})
            entry["revenue"] = _first_float(row.get("TOTAL_OPERATE_INCOME"), row.get("OPERATE_INCOME"))
            entry["gross_profit"] = safe_float(row.get("GROSS_PROFIT"))
            entry["operating_income"] = safe_float(row.get("OPERATE_PROFIT"))
            entry["net_income"] = _first_float(row.get("PARENT_NETPROFIT"), row.get("NETPROFIT"))
            entry["eps"] = safe_float(row.get("BASIC_EPS"))

        for period, row in _latest_period_rows(balance_rows):
            entry = rows_by_period.setdefault(period, {})
            entry["total_assets"] = safe_float(row.get("TOTAL_ASSETS"))
            entry["total_liabilities"] = safe_float(row.get("TOTAL_LIABILITIES"))

        for period, row in _latest_period_rows(cash_rows):
            entry = rows_by_period.setdefault(period, {})
            ocf = safe_float(row.get("NETCASH_OPERATE"))
            entry["operating_cash_flow"] = ocf
            free_cash_flow = safe_float(row.get("FREE_CASH_FLOW"))
            if free_cash_flow is None and ocf is not None:
                capex = _first_float(row.get("INVESTPAYCASH"), row.get("CONSTRUCT_LONG_ASSET"))
                if capex is not None:
                    free_cash_flow = safe_float(ocf - capex if capex > 0 else ocf + capex)
            entry["free_cash_flow"] = free_cash_flow
    else:
        hk_rows = _fetch_finance_rows("RPT_HKF10_FN_MAININDICATOR", secu_code, target_periods + 3)
        for period, row in _latest_period_rows(hk_rows):
            entry = rows_by_period.setdefault(period, {})
            entry["revenue"] = safe_float(row.get("OPERATE_INCOME"))
            entry["gross_profit"] = safe_float(row.get("GROSS_PROFIT"))
            entry["operating_income"] = safe_float(row.get("OPERATE_PROFIT"))
            entry["net_income"] = _first_float(row.get("HOLDER_PROFIT"), row.get("NETPROFIT"))
            entry["eps"] = safe_float(row.get("BASIC_EPS"))
            entry["total_assets"] = safe_float(row.get("TOTAL_ASSETS"))
            entry["total_liabilities"] = safe_float(row.get("TOTAL_LIABILITIES"))
            entry["operating_cash_flow"] = safe_float(row.get("NETCASH_OPERATE"))
            entry["free_cash_flow"] = safe_float(row.get("FREE_CASH_FLOW"))

    if not rows_by_period:
        return None

    period_labels = sorted(rows_by_period.keys(), key=_period_sort_key, reverse=True)[:target_periods]
    if not period_labels:
        return None

    result: dict[str, Any] = {
        "periods": period_labels,
        "revenue": [rows_by_period.get(period, {}).get("revenue") for period in period_labels],
        "gross_profit": [rows_by_period.get(period, {}).get("gross_profit") for period in period_labels],
        "operating_income": [rows_by_period.get(period, {}).get("operating_income") for period in period_labels],
        "net_income": [rows_by_period.get(period, {}).get("net_income") for period in period_labels],
        "eps": [rows_by_period.get(period, {}).get("eps") for period in period_labels],
        "total_assets": [rows_by_period.get(period, {}).get("total_assets") for period in period_labels],
        "total_liabilities": [rows_by_period.get(period, {}).get("total_liabilities") for period in period_labels],
        "operating_cash_flow": [rows_by_period.get(period, {}).get("operating_cash_flow") for period in period_labels],
        "free_cash_flow": [rows_by_period.get(period, {}).get("free_cash_flow") for period in period_labels],
        "source": "eastmoney_financials",
        "market": market,
    }
    metric_fields = (
        "revenue",
        "gross_profit",
        "operating_income",
        "net_income",
        "eps",
        "total_assets",
        "total_liabilities",
        "operating_cash_flow",
        "free_cash_flow",
    )
    return result if _has_any_metric(result, metric_fields) else None


__all__ = [
    "detect_market",
    "normalize_ticker",
    "ticker_to_eastmoney_secid",
    "ticker_to_secu_code",
    "fetch_cn_hk_quote_metrics",
    "fetch_cn_hk_kline",
    "fetch_cn_hk_financial_statements",
]
