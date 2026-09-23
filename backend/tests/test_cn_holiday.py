# -*- coding: utf-8 -*-
"""CN Holiday Calendar Tests"""
from __future__ import annotations

from datetime import date

from backend.services.cn_holiday import is_cn_holiday, get_holiday_name


def test_2026_mid_autumn_is_market_holiday():
    """2026 中秋节为 9 月 25 日（周五），当日 A 股休市。
    节假日表漏列时 is_cn_holiday 返回 False → smart_cache 按交易日
    给 30s TTL 空跑外部源，historical_data_store._required_end 会等
    一根永远不存在的 9/25 bar 反复判缓存未覆盖强制重拉。"""
    assert is_cn_holiday(date(2026, 9, 25)) is True
    assert get_holiday_name(date(2026, 9, 25)) == "中秋节"


def test_2026_mid_autumn_adjacent_weekend():
    """中秋连周末 9/26-27 本就休市；9/28 周一为交易日。"""
    assert is_cn_holiday(date(2026, 9, 26)) is True   # 周六
    assert is_cn_holiday(date(2026, 9, 28)) is False  # 周一


def test_weekend_workday_override_still_market_closed():
    """调休上班日是"国务院工作日"，不是"交易所开市日"——A股周六日一律休市，
    沪深交易所从不因调休周末开市。旧逻辑 WORKDAY_OVERRIDES→False 会把
    调休周末判成交易日：smart_cache 给 30s TTL 空拉行情、_required_end
    等一根永远不存在的 bar 判缓存未覆盖强制重拉。"""
    # 2026-09-27 周日，国庆前调休工作日 → 交易所休市
    assert is_cn_holiday(date(2026, 9, 27)) is True
    # 2026-02-07 周六，春节前调休工作日 → 交易所休市
    assert is_cn_holiday(date(2026, 2, 7)) is True
    # 2026-02-28 周六，春节后调休工作日 → 交易所休市
    assert is_cn_holiday(date(2026, 2, 28)) is True
    # 2026-10-10 周六，国庆后调休工作日 → 交易所休市
    assert is_cn_holiday(date(2026, 10, 10)) is True


def test_2027_mid_autumn_is_market_holiday():
    """2027 中秋节为 9 月 15 日（周三）。"""
    assert is_cn_holiday(date(2027, 9, 15)) is True
    assert get_holiday_name(date(2027, 9, 15)) == "中秋节"


def test_2026_holiday_table_matches_official_schedule():
    """2026 表按"预估"填的与国务院正式安排有三处交易日级出入
    （gov.cn 2025-11-04 通知）：
    - 春节 2/15-2/23 共9天：漏 2/16（周一·除夕）→ 休市日判开市；
    - 清明实为 4/4-4/6：多标 4/7（周二）→ 开市日判休市，smart_cache
      当日给 86400s TTL，盘中全天返回前收价；
    - 国庆实为 10/1-10/7：多标 10/8（周四）→ 同上，且 10/8 是未来
      交易日，不修会在两周后真实发生全天陈旧行情。"""
    # 漏标的休市日
    assert is_cn_holiday(date(2026, 2, 16)) is True   # 除夕（周一）
    # 错标的交易日
    assert is_cn_holiday(date(2026, 4, 7)) is False   # 清明实为 4/4-4/6
    assert is_cn_holiday(date(2026, 10, 8)) is False  # 国庆实为 10/1-10/7
    # 边界不变量：真正的休市日仍判休市
    assert is_cn_holiday(date(2026, 4, 6)) is True    # 清明周一
    assert is_cn_holiday(date(2026, 10, 7)) is True   # 国庆最后一天
    assert is_cn_holiday(date(2026, 2, 23)) is True   # 春节最后一天（周一）
