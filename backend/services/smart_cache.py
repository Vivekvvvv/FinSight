"""
智能缓存策略服务（交易时段感知）

功能：
- 交易时段内：短TTL（30-60秒），数据保持新鲜
- 盘后时段：长TTL（30分钟），减少无意义请求
- 周末/节假日：超长TTL（24小时），极少变化
- A股节假日自动识别（2024-2027年）
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timezone, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

MarketType = Literal["cn", "us", "hk", "crypto"]


class TradingHoursCache:
    """交易时段感知的智能缓存策略"""

    # A股交易时间：09:30-11:30, 13:00-15:00 (UTC+8)
    CN_MORNING_START = time(9, 30)
    CN_MORNING_END = time(11, 30)
    CN_AFTERNOON_START = time(13, 0)
    CN_AFTERNOON_END = time(15, 0)

    # 美股交易时间：09:30-16:00 ET，按纽约时区处理夏令时。
    US_START = time(9, 30)
    US_END = time(16, 0)

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
        if market == "crypto":
            return cls._get_trading_ttl(data_type)
        now_utc = datetime.now(timezone.utc)

        # A股特殊处理：检查节假日
        if market == "cn":
            from backend.services.cn_holiday import is_cn_holiday
            from datetime import timedelta
            cn_time = now_utc + timedelta(hours=8)
            if is_cn_holiday(cn_time):
                return cls._cap_closed_ttl(market, now_utc, cls._get_weekend_ttl(data_type))

        is_trading = cls._is_trading_hours(market, now_utc)
        # 周末判定必须按市场本地日期：UTC 周日 = 北京周一 00:00-08:00，
        # 按 UTC 判周末会让北京周一凌晨抓取的 quote 拿 86400s TTL，
        # 缓存条目在周一整个交易时段都被视为新鲜（全天陈旧价）；反向
        # UTC 周五 = 北京周六凌晨又判成交易日空拉行情。us 用 UTC 足够
        # （ET 落后 UTC，UTC 周末与美东周末基本重合，偏差方向无害）。
        from datetime import timedelta as _timedelta
        if market in ("cn", "hk"):
            is_weekend = (now_utc + _timedelta(hours=8)).weekday() >= 5
        else:
            is_weekend = now_utc.weekday() >= 5  # 5=Saturday, 6=Sunday

        # 周末/节假日：超长缓存
        if is_weekend:
            return cls._cap_closed_ttl(market, now_utc, cls._get_weekend_ttl(data_type))

        # 交易时段内：短缓存
        if is_trading:
            return cls._get_trading_ttl(data_type)

        # 盘后时段：长缓存
        return cls._cap_closed_ttl(market, now_utc, cls._get_afterhours_ttl(data_type))

    @classmethod
    def _cap_closed_ttl(cls, market: MarketType, now_utc: datetime, ttl: int) -> int:
        """休市缓存不能把旧报价带进下一次交易时段。"""
        from backend.services.cn_holiday import is_cn_holiday

        zone = ZoneInfo("America/New_York") if market == "us" else timezone(timedelta(hours=8))
        local_date = now_utc.astimezone(zone).date()
        starts = (time(9, 30), time(13, 0)) if market in {"cn", "hk"} else (time(9, 30),)
        for offset in range(15):
            trading_date = local_date + timedelta(days=offset)
            if trading_date.weekday() >= 5 or market == "cn" and is_cn_holiday(trading_date):
                continue
            for start in starts:
                opening = datetime.combine(trading_date, start, tzinfo=zone)
                remaining = (opening.astimezone(timezone.utc) - now_utc).total_seconds()
                if remaining > 0:
                    return min(ttl, int(remaining))
        return ttl

    @classmethod
    def _is_trading_hours(cls, market: MarketType, now_utc: datetime) -> bool:
        """判断当前是否在交易时间内"""
        if market == "crypto":
            return True
        zone = ZoneInfo("America/New_York") if market == "us" else timezone(timedelta(hours=8))
        local_date = now_utc.astimezone(zone).date()
        if local_date.weekday() >= 5:
            return False
        if market == "cn":
            from backend.services.cn_holiday import is_cn_holiday
            if is_cn_holiday(local_date):
                return False
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
        from datetime import timedelta
        cn_time = now_utc + timedelta(hours=8)
        t = cn_time.time()

        morning = cls.CN_MORNING_START <= t < cls.CN_MORNING_END
        afternoon = cls.CN_AFTERNOON_START <= t < cls.CN_AFTERNOON_END
        return morning or afternoon

    @classmethod
    def _is_us_trading(cls, now_utc: datetime) -> bool:
        """美股交易时段判断（纽约本地时间）"""
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)
        t = now_utc.astimezone(ZoneInfo("America/New_York")).time()
        return cls.US_START <= t < cls.US_END

    @classmethod
    def _is_hk_trading(cls, now_utc: datetime) -> bool:
        """港股交易时段判断（UTC+8转换）"""
        from datetime import timedelta
        hk_time = now_utc + timedelta(hours=8)
        t = hk_time.time()

        morning = cls.HK_MORNING_START <= t < cls.HK_MORNING_END
        afternoon = cls.HK_AFTERNOON_START <= t < cls.HK_AFTERNOON_END
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
        symbol_upper = symbol.strip().upper()

        if symbol_upper.endswith(("-USD", "-USDT", "-BTC", "-ETH", "-BUSD")):
            return "crypto"

        # A股判断
        if symbol_upper.endswith((".SS", ".SH", ".SZ", ".BJ")):
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

    logger.debug("[SmartCache] ttl resolved")
    return ttl


__all__ = ["TradingHoursCache", "get_smart_cache_ttl", "MarketType"]
