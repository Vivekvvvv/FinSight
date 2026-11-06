# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Any

from backend.graph.state import GraphState

_PRICE_TARGET_RE = re.compile(
    r"(?:"
    # Chinese patterns
    r"不高于|不大于|不低于|不小于|"
    r"涨到|跌到|涨至|跌至|跌破|低于|小于|突破|高于|大于|到达|到|达到|至|"
    r"(?:(?<![a-z0-9_])(?:not|no|isn['’]t)\s*)?(?<![<>=!])(?:[<>]=?|[≤≥])|"
    # English patterns - price target
    r"(?<![a-z0-9_])(?:price\s+(?:of|at|to)|target\s+price|reaches?|hits?|"
    # English patterns - directional
    r"(?:drops?|falls?|goes?|dips?)\s+(?:below|under|to)\s*|"
    r"(?:rises?|climbs?|goes?)\s+(?:above|over|to)\s*|"
    r"(?:not|no|isn['’]t)\s+(?:(?:less|lower|greater|higher)\s+than|above|below|over|under)\s*|"
    r"(?:less|lower|greater|higher)\s+than\s*|"
    r"(?:above|below|over|under|at)\s*)"
    r")\s*(?:(?P<currency_prefix>[$€£])\s*)?"
    r"(?P<price>[+-]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+))"
    # Reject incomplete numbers and percentages without matching a shorter prefix.
    r"(?!\d|[.,，]\d|e[+-]?\d|\s*(?:[-–—~～/]|to(?![a-z_]))\s*(?:\$\s*)?(?:\d|\.\d)|\s*(?:[%％]|percent|per\s+cent|个点|pct|美分|[千万亿]|(?:[kmb]|thousands?|millions?|billions?|cents?|pence|penn(?:y|ies))(?![a-z_])))"
    r"\s*(?P<currency>元|块|美元|dollars?|usd|\$|欧元|英镑|€|£|(?:eur|gbp|euros?|pounds?)(?![a-z_]))?",
    re.IGNORECASE,
)

_PCT_THRESHOLD_RE = re.compile(
    r"(?:"
    # Chinese patterns
    r"涨|跌|上涨|下跌|变动|超过|涨跌超过|"
    # English patterns
    r"(?<![a-z0-9_])(?:(?:rises?|drops?|falls?|moves?|changes?|fluctuates?)\s*(?:by\s*)?|"
    r"(?:up|down)\s*(?:by\s*)?|"
    r"(?:more\s+than|exceeds?|over)\s*)"
    r")\s*"
    r"(?P<pct>\d+(?:\.\d+)?)\s*(?:[%％]|percent|per\s+cent|个点|pct)",
    re.IGNORECASE,
)

_NEGATED_PCT_CONDITION_RE = re.compile(
    r"(?:不|没(?:有)?|未|\b(?:not|no|isn['’]t|doesn['’]t|don['’]t)\s+)"
    r"(?:(?:rises?|drops?|falls?|moves?|changes?|fluctuates?)\s+)?"
    + _PCT_THRESHOLD_RE.pattern,
    re.IGNORECASE,
)

# Explicit denial blocks writes; "don't forget" remains an affirmative request.
_DECLINED_ALERT_RE = re.compile(
    r"(?:不要|(?<![特分])别|勿|不用|不必|无需|不需要|不想)"
    r"(?!\s*(?:忘记|忘了|漏掉|漏了|错过|取消|撤销|删除|关闭|停用|停止))"
    r"(?:[^。！？；.!?,，;\n]|(?<=\d)[.,，](?=\d))*(?:提醒|预警|通知|订阅)"
    r"|\b(?:do\s+not|don['’]?t|never|no\s+need\s+to)\s+"
    r"(?:(?:set|create|add|enable)\b(?:[^。！？；.!?,，;\n]|(?<=\d)[.,，](?=\d))*\b(?:alerts?|reminders?|notifications?)\b"
    r"|(?:subscribe|alert|notify|remind)\b)"
    r"|\b(?:(?:do\s+not|don['’]?t|no\s+longer)\s+(?:want|need)|no\s+need\s+for)\s+"
    r"(?:(?:an?|any|the|my|price)\s+)*(?:alerts?|reminders?|notifications?)\b"
    r"|\b(?:(?:do\s+not|don['’]?t|no\s+longer)\s+(?:want|need)|no\s+need\s+for)\s+"
    r"(?:(?:an?|any|the|my)\s+)+"
    r"[a-z0-9][a-z0-9._-]{0,31}\s+(?:price\s+)?(?:alerts?|reminders?|notifications?)\b",
    re.IGNORECASE,
)

# Match verbs separately; punctuation inside a price does not end the clause.
_CANCEL_ALERT_RE = re.compile(
    r"(?:取消|撤销|关闭|停用|停止|删除)"
    r"(?=(?:[^。！？；.!?,，;\n]|(?<=\d)[.,，](?=\d))*(?:提醒|预警|通知|订阅))"
    r"|\b(?:cancel|remove|delete|disable|stop|(?:turn|switch)\s+off)\b"
    r"(?=(?:[^。！？；.!?,，;\n]|(?<=\d)[.,，](?=\d))*\b(?:alerts?|notifications?|reminders?|subscriptions?)\b)"
    r"|\b(?:turn|switch)\b"
    r"(?=(?:[^。！？；.!?,，;\n]|(?<=\d)[.,，](?=\d))*\b(?:alerts?|notifications?|reminders?|subscriptions?)\s+off\b)"
    r"|\bstop\b(?=\s+(?:notifying|reminding|alerting)\b)"
    r"|\bunsubscribe\b",
    re.IGNORECASE,
)


def _pick_ticker(state: GraphState) -> str | None:
    subject = state.get("subject") or {}
    tickers = subject.get("tickers") if isinstance(subject, dict) else None
    if isinstance(tickers, list) and tickers:
        first = str(tickers[0] or "").strip().upper()
        if first:
            return first

    ui_context = state.get("ui_context") or {}
    active_symbol = str((ui_context.get("active_symbol") if isinstance(ui_context, dict) else "") or "").strip().upper()
    return active_symbol or None


def _extract_direction(query: str) -> str | None:
    lowered = str(query or "").lower()
    below_tokens = ("跌到", "跌至", "跌破", "低于", "小于", "<", "≤")
    above_tokens = ("涨到", "涨至", "突破", "高于", "大于", ">", "≥")
    price_triggers = " ".join(match.group(0) for match in _PRICE_TARGET_RE.finditer(lowered))

    if any(token in lowered for token in ("不高于", "不大于")):
        return "below"
    if any(token in lowered for token in ("不低于", "不小于")):
        return "above"
    if re.search(r"(?<![a-z_])(?:not|no|isn['’]t)(?:\s+(?:above|over|(?:higher|greater)\s+than)(?![a-z_])|\s*(?:>=?|≥))", lowered):
        return "below"
    if re.search(r"(?<![a-z_])(?:not|no|isn['’]t)(?:\s+(?:below|under|(?:lower|less)\s+than)(?![a-z_])|\s*(?:<=?|≤))", lowered):
        return "above"

    if (
        any(token in lowered for token in below_tokens)
        or re.search(r"(?<![a-z_])(?:below|under|(?:less|lower)\s+than)(?![a-z_])", lowered)
        or re.search(r"(?<![a-z_])(?:drops?|falls?|dips?)\s+to(?![a-z_])", price_triggers)
    ):
        return "below"
    if (
        any(token in lowered for token in above_tokens)
        or re.search(r"(?<![a-z_])(?:above|over|(?:greater|higher)\s+than)(?![a-z_])", lowered)
        or re.search(r"(?<![a-z_])(?:rises?|climbs?)\s+to(?![a-z_])", price_triggers)
    ):
        return "above"
    return None


def _is_alert_cancel_request(query: str) -> bool:
    for match in _CANCEL_ALERT_RE.finditer(query):
        negation = re.search(
            r"(?:不要|不需要|不用|无需|不必|不想|不能|不可|禁止|(?<![特分])别|勿|不"
            r"|\b(?:not|never|don['’]?t|can['’]?t|cannot|no\s+need\s+to))"
            r"\s*(?:(?:再|ever|again)\s*)?$",
            query[:match.start()],
            re.IGNORECASE,
        )
        if negation is None:
            return True
    return False


def alert_extractor(state: GraphState) -> dict[str, Any]:
    query = str(state.get("query") or "").strip()
    ticker = _pick_ticker(state)

    price_target_match = _PRICE_TARGET_RE.search(query)
    pct_match = _PCT_THRESHOLD_RE.search(query)

    alert_params: dict[str, Any] = {
        "ticker": ticker,
        "alert_mode": None,
        "price_target": None,
        "price_threshold": None,
        "direction": None,
    }

    if _DECLINED_ALERT_RE.search(query) or _is_alert_cancel_request(query):
        return {
            "alert_valid": False,
            "skip_session_context": True,
            "alert_params": alert_params,
            "artifacts": {"draft_markdown": "未创建或修改提醒。如需停用已有提醒，请在提醒设置中关闭或删除。"},
        }

    if any(
        match.group("currency_prefix") in {"€", "£"}
        or (match.group("currency") or "").lower() in {"eur", "gbp", "euro", "euros", "pound", "pounds", "欧元", "英镑", "€", "£"}
        for match in _PRICE_TARGET_RE.finditer(query)
    ):
        draft = "当前提醒不支持自动换算币种，未创建或修改提醒。请使用该股票行情的原始币种提供目标价格。"
        return {
            "alert_valid": False,
            "skip_session_context": True,
            "alert_params": alert_params,
            "clarify": {"needed": True, "reason": "alert_unsupported_currency", "question": draft},
            "artifacts": {"draft_markdown": draft},
        }

    subject = state.get("subject") or {}
    tickers = subject.get("tickers") if isinstance(subject, dict) else None
    alert_tickers = {str(item or "").strip().upper() for item in tickers if str(item or "").strip()} if isinstance(tickers, list) else set()
    if not re.search(r"\bUSD\b", _PRICE_TARGET_RE.sub("", query), re.IGNORECASE):
        alert_tickers.discard("USD")
        if ticker == "USD":
            ticker = _pick_ticker({"ui_context": state.get("ui_context")})
            alert_params["ticker"] = ticker
    if len(alert_tickers) == 1:
        ticker = next(iter(alert_tickers))
        alert_params["ticker"] = ticker
    if len(alert_tickers) > 1:
        draft = "检测到多个提醒标的，未创建或修改提醒。请一次只指定一只股票及其提醒条件。"
        return {
            "alert_valid": False,
            "skip_session_context": True,
            "alert_params": alert_params,
            "clarify": {
                "needed": True,
                "reason": "alert_multiple_tickers",
                "question": draft,
            },
            "artifacts": {"draft_markdown": draft},
        }

    price_targets = {
        float(match.group("price").replace(",", ""))
        for match in _PRICE_TARGET_RE.finditer(query)
    }
    pct_thresholds = {float(match.group("pct")) for match in _PCT_THRESHOLD_RE.finditer(query)}
    price_directions = {_extract_direction(match.group(0)) for match in _PRICE_TARGET_RE.finditer(query)}
    if len(price_targets) > 1 or len(pct_thresholds) > 1 or {"above", "below"} <= price_directions:
        draft = "检测到多个不同的提醒条件，未创建或修改提醒。请一次只提供一个目标价格及方向，或一个涨跌幅条件。"
        return {
            "alert_valid": False,
            "skip_session_context": True,
            "alert_params": alert_params,
            "clarify": {
                "needed": True,
                "reason": "alert_conflicting_thresholds",
                "question": draft,
            },
            "artifacts": {"draft_markdown": draft},
        }

    if price_target_match:
        alert_params["alert_mode"] = "price_target"
        alert_params["price_target"] = float(price_target_match.group("price").replace(",", ""))
        alert_params["direction"] = next((value for value in price_directions if value is not None), None)
    elif pct_match:
        if _NEGATED_PCT_CONDITION_RE.search(query):
            draft = "当前涨跌幅提醒只支持绝对涨跌幅达到指定百分比，无法按否定或上限条件触发。未创建或修改提醒，请提供达到的百分比阈值。"
            return {
                "alert_valid": False,
                "skip_session_context": True,
                "alert_params": alert_params,
                "clarify": {"needed": True, "reason": "alert_unsupported_pct_condition", "question": draft},
                "artifacts": {"draft_markdown": draft},
            }
        alert_params["alert_mode"] = "price_change_pct"
        alert_params["price_threshold"] = float(pct_match.group("pct"))

    missing: list[str] = []
    if not ticker:
        missing.append("ticker")
    if not alert_params["alert_mode"]:
        missing.append("trigger")

    if missing:
        reason = "缺少标的代码" if "ticker" in missing else "缺少提醒阈值"
        if "ticker" in missing and "trigger" in missing:
            reason = "缺少标的代码和提醒阈值"
        draft = (
            "我可以帮你设置提醒，但还缺少必要信息。\n"
            f"- 问题：{reason}\n"
            "- 示例1：`AAPL 涨到 220 美元提醒我` / `Alert me when AAPL hits 220`\n"
            "- 示例2：`平安银行 涨跌超过 3% 提醒我` / `Notify me if TSLA moves 5%`"
        )
        return {
            "alert_valid": False,
            "alert_params": alert_params,
            "clarify": {
                "needed": True,
                "reason": "alert_missing_required_fields",
                "question": draft,
                "suggestions": [
                    "输入 ticker + 到价，例如 AAPL 涨到 220 美元提醒我",
                    "输入 ticker + 涨跌幅，例如 NVDA 涨跌超过 4% 提醒我",
                    "English: Alert me when AAPL drops below 180",
                    "English: Notify me if TSLA rises 10 percent",
                ],
            },
            "artifacts": {"draft_markdown": draft},
        }

    return {
        "alert_valid": True,
        "alert_params": alert_params,
    }


__all__ = ["alert_extractor"]
