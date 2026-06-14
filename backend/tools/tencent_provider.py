from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from backend.tools.http import _http_get
from backend.utils.quote import safe_float

logger = logging.getLogger(__name__)


def is_cn_symbol(symbol: str) -> bool:
    """判断是否为A股代码（.SS/.SZ/.BJ后缀）"""
    text = str(symbol or "").strip().upper()
    return text.endswith((".SS", ".SZ", ".BJ"))


def to_tencent_code(symbol: str) -> str | None:
    """将 Yahoo 格式（600519.SS）转换为腾讯格式（sh600519）"""
    text = str(symbol or "").strip().upper()
    if text.endswith(".SS"):
        return f"sh{text[:-3]}"
    if text.endswith(".SZ"):
        return f"sz{text[:-3]}"
    if text.endswith(".BJ"):
        return f"bj{text[:-3]}"
    return None


def fetch_cn_quote(symbol: str) -> dict[str, Any] | None:
    """
    从腾讯财经获取A股实时行情。
    API: https://qt.gtimg.cn/q=sh600519,sz000001
    返回格式: v_sh600519="51~贵州茅台~600519~2086.00~2080.00~2085.00~..."
    """
    code = to_tencent_code(symbol)
    if code is None:
        return None

    url = f"https://qt.gtimg.cn/q={code}"
    try:
        resp = _http_get(url, timeout=(3, 6))
        if resp.status_code != 200:
            logger.info("[Tencent] HTTP %d for %s", resp.status_code, symbol)
            return None

        # 解析响应：v_sh600519="51~贵州茅台~600519~2086.00~2080.00~..."
        text = resp.text.strip()
        if not text or "~" not in text:
            return None

        parts = text.split('"')[1].split("~") if '"' in text else []
        if len(parts) < 34:
            logger.info("[Tencent] 字段不足 for %s: %d fields", symbol, len(parts))
            return None

        # 字段映射（腾讯接口字段索引）:
        # 3=现价, 4=昨收, 5=开盘, 6=成交量(手), 7=外盘, 8=内盘
        # 9=买一, 10=买一量, ..., 30=日期, 31=时间
        price = safe_float(parts[3])
        prev_close = safe_float(parts[4])
        if price is None or prev_close is None or prev_close == 0:
            return None

        change = price - prev_close
        change_percent = (change / prev_close) * 100
        volume = safe_float(parts[6])  # 成交量(手)
        if volume:
            volume = volume * 100  # 转换为股

        # 拼接时间戳
        date_str = parts[30] if len(parts) > 30 else ""  # 20260614
        time_str = parts[31] if len(parts) > 31 else ""  # 150000
        as_of = datetime.now(timezone.utc).isoformat()
        if date_str and len(date_str) == 8:
            try:
                as_of = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                if time_str and len(time_str) == 6:
                    as_of += f"T{time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}+08:00"
            except Exception:
                pass

        return {
            "symbol": symbol.upper(),
            "currentPrice": price,
            "regularMarketPrice": price,
            "price": price,
            "regularMarketChange": change,
            "change": change,
            "regularMarketChangePercent": change_percent,
            "change_percent": change_percent,
            "regularMarketVolume": volume,
            "volume": volume,
            "regularMarketPreviousClose": prev_close,
            "previousClose": prev_close,
            "source": "tencent",
            "as_of": as_of,
            "freshness_status": "live",
            "fallback_level": 1,
            "modelGenerated": False,
        }
    except Exception as exc:
        logger.info("[Tencent] 获取失败 %s: %s", symbol, exc)
        return None


__all__ = ["is_cn_symbol", "to_tencent_code", "fetch_cn_quote"]
