# -*- coding: utf-8 -*-
"""
tests/test_historical_data_store.py
单元测试：A股历史K线数据下载与缓存
"""
import math
import pytest
import sys
from types import SimpleNamespace


# ── _to_bs_code 测试 ──────────────────────────────────────────────────────────

def test_to_bs_code_sh_600():
    from backend.services.historical_data_store import _to_bs_code
    assert _to_bs_code("600519.SS") == "sh.600519"


def test_to_bs_code_sh_601():
    from backend.services.historical_data_store import _to_bs_code
    assert _to_bs_code("601318.SS") == "sh.601318"


def test_to_bs_code_sh_688():
    from backend.services.historical_data_store import _to_bs_code
    assert _to_bs_code("688012.SS") == "sh.688012"


def test_to_bs_code_sz_000():
    from backend.services.historical_data_store import _to_bs_code
    assert _to_bs_code("000001.SZ") == "sz.000001"


def test_to_bs_code_sz_300():
    from backend.services.historical_data_store import _to_bs_code
    assert _to_bs_code("300750.SZ") == "sz.300750"


def test_to_bs_code_uppercase_suffix():
    from backend.services.historical_data_store import _to_bs_code
    assert _to_bs_code("600519.ss") == "sh.600519"


# ── _adjust_flag 测试 ─────────────────────────────────────────────────────────

def test_adjust_flag_qfq():
    from backend.services.historical_data_store import _adjust_flag
    assert _adjust_flag("qfq") == "2"


def test_adjust_flag_hfq():
    from backend.services.historical_data_store import _adjust_flag
    assert _adjust_flag("hfq") == "1"


def test_adjust_flag_none():
    from backend.services.historical_data_store import _adjust_flag
    assert _adjust_flag("none") == "3"


def test_adjust_flag_unknown_defaults_to_3():
    from backend.services.historical_data_store import _adjust_flag
    assert _adjust_flag("unknown") == "3"


def test_baostock_fetch_error_log_is_redacted(monkeypatch, caplog):
    from backend.services.historical_data_store import _fetch_baostock

    secret = "PRIVATE http://proxy-user:secret@proxy.local"

    def _fail_login():
        raise RuntimeError(secret)

    monkeypatch.setitem(
        sys.modules,
        "baostock",
        SimpleNamespace(login=_fail_login, logout=lambda: None),
    )

    assert _fetch_baostock("600519.SS", "2026-01-01", "2026-01-02", "qfq") == []
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


# ── _clean 测试 ──────────────────────────────────────────────────────────────

def test_clean_removes_zero_close():
    from backend.services.historical_data_store import _clean
    rows = [
        {"date": "2024-01-02", "open": 10.0, "high": 11.0, "low": 9.0, "close": 0.0, "volume": 1000},
        {"date": "2024-01-03", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5, "volume": 1000},
    ]
    result = _clean(rows)
    assert all(r["close"] > 0 for r in result)
    assert len(result) == 1


def test_clean_removes_none_close():
    from backend.services.historical_data_store import _clean
    rows = [
        {"date": "2024-01-02", "open": 10.0, "high": 11.0, "low": 9.0, "close": None, "volume": 1000},
        {"date": "2024-01-03", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.0, "volume": 1000},
    ]
    result = _clean(rows)
    assert len(result) == 1
    assert result[0]["close"] == 10.0


def test_clean_removes_invalid_and_non_finite_close():
    from backend.services.historical_data_store import _clean

    rows = [
        {"date": "2024-01-01", "open": 10.0, "high": 11.0, "low": 9.0, "close": "nan", "volume": 1000},
        {"date": "2024-01-02", "open": 10.0, "high": 11.0, "low": 9.0, "close": "inf", "volume": 1000},
        {"date": "2024-01-03", "open": 10.0, "high": 11.0, "low": 9.0, "close": "bad", "volume": 1000},
        {"date": "2024-01-04", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5, "volume": 1000},
    ]

    result = _clean(rows)

    assert len(result) == 1
    assert result[0]["date"] == "2024-01-04"


def test_clean_replaces_invalid_and_non_finite_ohlc_values():
    from backend.services.historical_data_store import _clean

    rows = [
        {"date": "2024-01-01", "open": "bad", "high": "nan", "low": "inf", "close": "10", "volume": 1000},
        {"date": "2024-01-02", "open": "-inf", "high": 0, "low": -1, "close": 11.0, "volume": 1000},
    ]

    result = _clean(rows)

    assert result[0]["open"] == result[0]["high"] == result[0]["low"] == 10.0
    assert result[1]["open"] == 10.0
    assert result[1]["high"] == result[1]["low"] == 11.0
    assert all(
        math.isfinite(row[field]) and row[field] > 0
        for row in result
        for field in ("open", "high", "low", "close")
    )


def test_clean_replaces_invalid_non_finite_and_negative_volume():
    from backend.services.historical_data_store import _clean

    rows = [
        {"date": "2024-01-01", "open": 10, "high": 11, "low": 9, "close": 10, "volume": value}
        for value in ("bad", "nan", "inf", -1, None, 0, "12.5")
    ]

    result = _clean(rows)

    assert [row["volume"] for row in result] == [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 12.5]
    assert all(math.isfinite(row["volume"]) and row["volume"] >= 0 for row in result)


def test_clean_marks_suspicious_large_change():
    from backend.services.historical_data_store import _clean
    rows = [
        {"date": "2024-01-02", "open": 10.0, "high": 10.5, "low": 9.5, "close": 10.0, "volume": 1000},
        # 涨幅 >22%：10.0 → 12.5 = +25%
        {"date": "2024-01-03", "open": 12.0, "high": 13.0, "low": 11.5, "close": 12.5, "volume": 1000},
    ]
    result = _clean(rows)
    assert result[1]["is_suspicious"] is True


def test_clean_normal_change_not_suspicious():
    from backend.services.historical_data_store import _clean
    rows = [
        {"date": "2024-01-02", "open": 10.0, "high": 10.5, "low": 9.5, "close": 10.0, "volume": 1000},
        {"date": "2024-01-03", "open": 10.0, "high": 10.3, "low": 9.8, "close": 10.2, "volume": 1000},
    ]
    result = _clean(rows)
    assert result[1]["is_suspicious"] is False


def test_clean_empty_input():
    from backend.services.historical_data_store import _clean
    assert _clean([]) == []


# ── 缓存命中判定（审计 C2 回归）───────────────────────────────────────────────


@pytest.fixture()
def store(tmp_path, monkeypatch):
    from backend.services import historical_data_store as store_module

    monkeypatch.setattr(store_module, "_DB_PATH", str(tmp_path / "kline.db"))
    monkeypatch.setattr(store_module, "_table_ready", False)
    return store_module


def _bars(*dates: str) -> list[dict]:
    return [
        {"date": d, "open": 10.0, "high": 10.5, "low": 9.5, "close": 10.0, "volume": 1000}
        for d in dates
    ]


def test_c2_holiday_start_hits_cache(store):
    """审计 C2 主场景：start 落在休市日（如 2020-01-01 元旦），首根 bar 晚于 start，
    旧写法 cached_start > start 恒真 → 永不命中。修复后按声明区间判定命中。"""
    store._write_cache(
        "600519.SS", _bars("2020-01-02", "2020-01-03"), "qfq",
        declared_start="2020-01-01", declared_end="2020-01-03",
    )
    result = store._read_cache("600519.SS", "2020-01-01", "2020-01-03", "qfq")
    assert result is not None
    assert [r["date"] for r in result] == ["2020-01-02", "2020-01-03"]


def test_c2_miss_when_head_not_fetched(store):
    store._write_cache(
        "600519.SS", _bars("2024-01-08", "2024-01-09"), "qfq",
        declared_start="2024-01-08", declared_end="2024-01-09",
    )
    # 请求起点早于声明区间 → 头部数据未拉取过，不能命中
    assert store._read_cache("600519.SS", "2024-01-03", "2024-01-09", "qfq") is None


def test_c2_weekend_end_hits_cache(store):
    store._write_cache(
        "600519.SS", _bars("2024-01-02", "2024-01-05"), "qfq",
        declared_start="2024-01-02", declared_end="2024-01-05",  # 周五
    )
    # 请求 end=周日：required_end 回退到周五，声明区间覆盖 → 命中
    result = store._read_cache("600519.SS", "2024-01-02", "2024-01-07", "qfq")
    assert result is not None


def test_c2_miss_when_tail_trading_day_not_fetched(store):
    store._write_cache(
        "600519.SS", _bars("2024-01-02", "2024-01-05"), "qfq",
        declared_start="2024-01-02", declared_end="2024-01-05",
    )
    # end=2024-01-09（周二，交易日）超出声明区间 → 缺尾部数据，不能命中
    assert store._read_cache("600519.SS", "2024-01-02", "2024-01-09", "qfq") is None


def test_c2_disjoint_declared_ranges_not_merged(store):
    """两次不连续区间不得合并声明，否则中间的洞会被假命中。"""
    store._write_cache(
        "600519.SS", _bars("2024-01-02", "2024-01-05"), "qfq",
        declared_start="2024-01-02", declared_end="2024-01-05",
    )
    store._write_cache(
        "600519.SS", _bars("2024-03-04", "2024-03-08"), "qfq",
        declared_start="2024-03-04", declared_end="2024-03-08",
    )
    # 跨洞请求不能命中（1 月与 3 月之间从未拉取）
    assert store._read_cache("600519.SS", "2024-01-02", "2024-03-08", "qfq") is None
    # 新声明区间内正常命中
    assert store._read_cache("600519.SS", "2024-03-04", "2024-03-08", "qfq") is not None


def test_c2_overlapping_declared_ranges_merge(store):
    store._write_cache(
        "600519.SS", _bars("2024-01-02", "2024-01-10"), "qfq",
        declared_start="2024-01-02", declared_end="2024-01-10",
    )
    store._write_cache(
        "600519.SS", _bars("2024-01-08", "2024-01-19"), "qfq",
        declared_start="2024-01-08", declared_end="2024-01-19",
    )
    result = store._read_cache("600519.SS", "2024-01-02", "2024-01-19", "qfq")
    assert result is not None


def test_c2_adjusted_cache_expires_after_ttl(store):
    """qfq/hfq 复权因子随分红除权回溯变化：声明区间过期须强制重拉；none 不受限。"""
    for adj in ("qfq", "none"):
        store._write_cache(
            "600519.SS", _bars("2024-01-02", "2024-01-03"), adj,
            declared_start="2024-01-02", declared_end="2024-01-03",
        )
    with store._lock, store._conn() as c:
        c.execute("UPDATE kline_fetch_meta SET updated_at='2020-01-01 00:00:00'")
    assert store._read_cache("600519.SS", "2024-01-02", "2024-01-03", "qfq") is None
    assert store._read_cache("600519.SS", "2024-01-02", "2024-01-03", "none") is not None


def test_c2_no_meta_means_miss(store):
    """存量库只有 bar 无声明区间：判未命中，重拉一次自然补齐 meta。"""
    store._ensure_table()
    with store._lock, store._conn() as c:
        c.execute(
            "INSERT INTO kline_cache (ticker, date, close, adjust) VALUES ('600519.SS','2024-01-02',10.0,'qfq')"
        )
    assert store._read_cache("600519.SS", "2024-01-02", "2024-01-02", "qfq") is None


def test_c2_future_end_not_overdeclared(store, monkeypatch):
    """end_date 为未来日期时，声明末端须收敛到“应已发布的最后交易日”，
    否则后续每个新交易日的请求都会假命中、永远拿不到新 bar。"""
    from datetime import date as real_date

    monkeypatch.setattr(
        store, "_fetch_baostock",
        lambda ticker, start, end, adjust: _bars("2026-06-29", "2026-06-30"),
    )
    store.fetch_and_cache_kline("600519.SS", "2026-06-29", "2030-12-31", "qfq")
    with store._lock, store._conn() as c:
        row = c.execute("SELECT fetched_end FROM kline_fetch_meta").fetchone()
    assert row is not None
    assert row[0] <= real_date.today().isoformat()


def test_c2_required_end_respects_publish_hour():
    from datetime import date, datetime, timedelta, timezone

    from backend.services.historical_data_store import _required_end

    bj = timezone(timedelta(hours=8))
    # 交易日（2026-07-07 周二）盘中 10 点：日线未发布，只要求到前一交易日
    assert _required_end(date(2026, 7, 7), datetime(2026, 7, 7, 10, 0, tzinfo=bj)) == date(2026, 7, 6)
    # 同日 20 点后：要求当日 bar
    assert _required_end(date(2026, 7, 7), datetime(2026, 7, 7, 20, 30, tzinfo=bj)) == date(2026, 7, 7)
    # 周六晚：回退到周五
    assert _required_end(date(2026, 7, 11), datetime(2026, 7, 11, 21, 0, tzinfo=bj)) == date(2026, 7, 10)
    # 过去区间不受“今天”影响，但休市日回退到最近交易日（2024-01-07 周日 → 01-05 周五）
    assert _required_end(date(2024, 1, 7), datetime(2026, 7, 7, 21, 0, tzinfo=bj)) == date(2024, 1, 5)
