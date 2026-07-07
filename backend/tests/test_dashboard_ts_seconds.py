# -*- coding: utf-8 -*-
"""R6 回归：_ts_seconds 对所有 naive 输入统一按 UTC 解释。

旧代码 fromisoformat 分支（含最常见的 "YYYY-MM-DD" K线日期串）与 naive
pd.Timestamp 分支按服务器本地时区取 timestamp，东八区部署整条时间轴偏
8 小时；而同函数的 datetime 分支和 strptime 分支都补了 UTC——同函数内
基准分裂。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from backend.dashboard.data_service import _ts_seconds

_EXPECTED = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp())


def test_ts_seconds_naive_iso_date_is_utc():
    # 东八区机器上旧代码返回 _EXPECTED - 8*3600
    assert _ts_seconds("2026-01-01") == _EXPECTED
    assert _ts_seconds("2026-01-01T00:00:00") == _EXPECTED


def test_ts_seconds_all_branches_agree_on_same_instant():
    aware = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert _ts_seconds("2026-01-01T00:00:00Z") == _EXPECTED
    assert _ts_seconds(aware) == _EXPECTED
    assert _ts_seconds(datetime(2026, 1, 1)) == _EXPECTED          # naive datetime 分支
    assert _ts_seconds(pd.Timestamp("2026-01-01")) == _EXPECTED    # naive pd.Timestamp 分支
    assert _ts_seconds("2026-01-01 00:00:00") == _EXPECTED         # strptime 分支
    assert _ts_seconds(_EXPECTED) == _EXPECTED                     # int 透传
