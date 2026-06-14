"""
智能缓存策略服务（交易时段感知）

功能：
- 交易时段内：短TTL（30-60秒），数据保持新鲜
- 盘后时段：长TTL（30分钟），减少无意义请求
- 周末/节假日：超长TTL（24小时），极少变化
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timezone
from typing import Literal

logger = logging.getLogger(__name__)

MarketType = Literal["cn", "us", "hk"]


class TradingHoursCache:
    """交易时段感知的智能缓存策略"""

    # A股交易时间：09:30-11:30, 13:00-15:00 (UTC+8)
    CN_MORNING_START = time(9, 30)
    CN_MORNING_END = time(11, 30)
    CN_AFTERNOON_START = time(13, 0)
    CN_AFTERNOON_END = time(15, 0)

    # 美股交易时间：09:30-16:00 EST (夏令时UTC-4, 冬令时UTC-5)
    # 简化处理：21:30-04:00 UTC (覆盖夏令时和冬令时)
    US_START = time(21, 30)  # UTC
    US_END = time(4, 0)  # UTC次日

    # 港股交易时间：09:30-12:00, 13:00-16:00 (UTC+8)
    HK_MORNING_START = time(9, 30)
    HK_MORNING_END = time(12, 0)
    HK_AFTERNOON_START = time(13, 0)
    HK_AFTERNOON_END = time(16, 0)

    @classmethod
    def get_smart_ttl(cls, market: MarketType, data_type: Literal["quote", "kline", "intraday"]) -> int:
        """
        根据市场类型、数据类型和当前时间，返回智能TTL（秒）。

        Args:
            market: 市场类型 (cn/us/hk)
            data_type: 数据类型 (quote=实时行情, kline=K线, intraday=分时)

        Returns:
            TTL秒数
        """
        now_utc = datetime.now(timezone.utc)
        is_trading = cls._is_trading_hours(market, now_utc)
        is_weekend = now_utc.weekday() >= 5  # 5=Saturday, 6=Sunday

        # 周末/节假日：超长缓存
        if is_weekend:
            return cls._get_weekend_ttl(data_type)

        # 交易时段内：短缓存
        if is_trading:
            return cls._get_trading_ttl(data_type)

        # 盘后时段：长缓存
        return cls._get_afterhours_ttl(data_type)

    @classmethod
    def _is_trading_hours(cls, market: MarketType, now_utc: datetime) -> bool:
        """判断当前是否在交易时间内"""
        if market == "cn":
            return cls._is_cn_trading(now_utc)
        elif market == "us":
            return cls._is_us_trading(now_utc)
        elif market == "hk":
            return cls._is_hk_trading(now_utc)
        return False

    @classmethod
    def _is_cn_trading(cls, now_utc: datetime) -> bool:
        """A股交易时段判断（UTC+8转换）"""
        # UTC → UTC+8
        cn_time = now_utc.replace(tzinfo=None) + (8 * 3600 * 1000000000 // 1000000000)  # 粗略+8小时
        # 更精确的方式
        from datetime import timedelta
        cn_time = now_utc + timedelta(hours=8)
        t = cn_time.time()

        morning = cls.CN_MORNING_START <= t <= cls.CN_MORNING_END
        afternoon = cls.CN_AFTERNOON_START <= t <= cls.CN_AFTERNOON_END
        return morning or afternoon

    @classmethod
    def _is_us_trading(cls, now_utc: datetime) -> bool:
        """美股交易时段判断（UTC时间）"""
        t = now_utc.time()
        # 跨日判断：21:30-23:59 或 00:00-04:00
        if cls.US_START <= t or t <= cls.US_END:
            return True
        return False

    @classmethod
    def _is_hk_trading(cls, now_utc: datetime) -> bool:
        """港股交易时段判断（UTC+8转换）"""
        from datetime import timedelta
        hk_time = now_utc + timedelta(hours=8)
        t = hk_time.time()

        morning = cls.HK_MORNING_START <= t <= cls.HK_MORNING_END
        afternoon = cls.HK_AFTERNOON_START <= t <= cls.HK_AFTERNOON_END
        return morning or afternoon

    @classmethod
    def _get_trading_ttl(cls, data_type: str) -> int:
        """交易时段TTL"""
        if data_type == "quote":
            return 30  # 实时行情：30秒
        elif data_type == "intraday":
            return 60  # 分时数据：60秒
        elif data_type == "kline":
            return 300  # K线数据：5分钟
        return 60

    @classmethod
    def _get_afterhours_ttl(cls, data_type: str) -> int:
        """盘后时段TTL"""
        if data_type == "quote":
            return 1800  # 实时行情：30分钟
        elif data_type == "intraday":
            return 1800  # 分时数据：30分钟
        elif data_type == "kline":
            return 3600  # K线数据：1小时
        return 1800

    @classmethod
    def _get_weekend_ttl(cls, data_type: str) -> int:
        """周末TTL"""
        if data_type == "quote":
            return 86400  # 实时行情：24小时
        elif data_type == "intraday":
            return 86400  # 分时数据：24小时
        elif data_type == "kline":
            return 86400  # K线数据：24小时
        return 86400

    @classmethod
    def detect_market(cls, symbol: str) -> MarketType:
        """根据股票代码检测市场类型"""
        symbol_upper = symbol.upper()

        # A股判断
        if symbol_upper.endswith(".SS") or symbol_upper.endswith(".SZ") or symbol_upper.endswith(".BJ"):
            return "cn"

        # 港股判断
        if symbol_upper.endswith(".HK"):
            return "hk"

        # 默认美股
        return "us"


def get_smart_cache_ttl(symbol: str, data_type: Literal["quote", "kline", "intraday"]) -> int:
    """
    获取智能缓存TTL（快捷函数）

    Args:
        symbol: 股票代码 (如 600519.SS, AAPL, 0700.HK)
        data_type: 数据类型 (quote/kline/intraday)

    Returns:
        TTL秒数

    Example:
        >>> get_smart_cache_ttl("600519.SS", "quote")
        30  # 交易时段内
        >>> get_smart_cache_ttl("AAPL", "kline")
        3600  # 盘后时段
    """
    market = TradingHoursCache.detect_market(symbol)
    ttl = TradingHoursCache.get_smart_ttl(market, data_type)

    logger.debug(
        f"[SmartCache] {symbol} ({market}) {data_type} → TTL={ttl}s"
    )
    return ttl


__all__ = ["TradingHoursCache", "get_smart_cache_ttl", "MarketType"]
