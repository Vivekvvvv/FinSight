# -*- coding: utf-8 -*-
import backend.tools.sec as sec


class _FakeResponse:
    def __init__(self, status_code: int, json_payload=None, text: str = ""):
        self.status_code = status_code
        self._json_payload = json_payload
        self.text = text

    def json(self):
        return self._json_payload


def _reset_cache() -> None:
    sec._ticker_cache = {}
    sec._ticker_cache_expire_at = 0.0


def test_get_sec_filings_requires_user_agent(monkeypatch):
    _reset_cache()
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    monkeypatch.delenv("EMAIL_FROM", raising=False)
    payload = sec.get_sec_filings("AAPL")
    assert payload.get("error") == "missing_sec_user_agent"


def test_get_sec_filings_rejects_non_us_market(monkeypatch):
    _reset_cache()
    monkeypatch.setenv("SEC_USER_AGENT", "FinSight admin@finsight.app")
    payload = sec.get_sec_filings("600519.SS")
    assert payload.get("error") == "unsupported_market"
    assert payload.get("market") == "CN"


def test_get_sec_filings_success(monkeypatch):
    _reset_cache()
    monkeypatch.setenv("SEC_USER_AGENT", "FinSight admin@finsight.app")

    def _fake_http_get(url, **kwargs):
        if url.endswith("company_tickers.json"):
            return _FakeResponse(
                200,
                {
                    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
                },
            )
        if "submissions/CIK0000320193.json" in url:
            return _FakeResponse(
                200,
                {
                    "filings": {
                        "recent": {
                            "form": ["10-Q", "8-K", "10-K"],
                            "filingDate": ["2025-08-01", "2025-07-15", "2024-11-01"],
                            "reportDate": ["2025-06-30", "2025-07-14", "2024-09-30"],
                            "acceptanceDateTime": [
                                "2025-08-01T12:00:00.000Z",
                                "2025-07-15T12:00:00.000Z",
                                "2024-11-01T12:00:00.000Z",
                            ],
                            "accessionNumber": [
                                "0000320193-25-000001",
                                "0000320193-25-000002",
                                "0000320193-24-000003",
                            ],
                            "primaryDocument": ["a10q.htm", "a8k.htm", "a10k.htm"],
                            "primaryDocDescription": ["10-Q", "8-K", "10-K"],
                        }
                    }
                },
            )
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(sec, "_http_get", _fake_http_get)
    payload = sec.get_sec_filings("AAPL", forms="10-K,8-K", limit=10)
    assert payload.get("error") is None
    assert payload.get("cik") == "0000320193"
    filings = payload.get("filings") or []
    assert len(filings) == 2
    assert {item.get("form") for item in filings} == {"10-K", "8-K"}


def test_get_sec_material_events_uses_8k(monkeypatch):
    _reset_cache()
    monkeypatch.setenv("SEC_USER_AGENT", "FinSight admin@finsight.app")

    def _fake_http_get(url, **kwargs):
        if url.endswith("company_tickers.json"):
            return _FakeResponse(
                200,
                {
                    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
                },
            )
        if "submissions/CIK0000320193.json" in url:
            return _FakeResponse(
                200,
                {
                    "filings": {
                        "recent": {
                            "form": ["8-K", "10-Q", "8-K"],
                            "filingDate": ["2025-08-03", "2025-08-01", "2025-07-01"],
                            "reportDate": ["2025-08-02", "2025-06-30", "2025-06-30"],
                            "acceptanceDateTime": [
                                "2025-08-03T00:00:00.000Z",
                                "2025-08-01T00:00:00.000Z",
                                "2025-07-01T00:00:00.000Z",
                            ],
                            "accessionNumber": [
                                "0000320193-25-000010",
                                "0000320193-25-000011",
                                "0000320193-25-000012",
                            ],
                            "primaryDocument": ["event1.htm", "q2.htm", "event2.htm"],
                            "primaryDocDescription": ["8-K", "10-Q", "8-K"],
                        }
                    }
                },
            )
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(sec, "_http_get", _fake_http_get)
    payload = sec.get_sec_material_events("AAPL")
    assert payload.get("error") is None
    events = payload.get("events") or []
    assert len(events) == payload.get("event_count")
    assert all(event.get("form") == "8-K" for event in events)


def test_get_sec_risk_factors_extracts_item_1a(monkeypatch):
    _reset_cache()
    monkeypatch.setenv("SEC_USER_AGENT", "FinSight admin@finsight.app")

    def _fake_http_get(url, **kwargs):
        if url.endswith("company_tickers.json"):
            return _FakeResponse(
                200,
                {
                    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
                },
            )
        if "submissions/CIK0000320193.json" in url:
            return _FakeResponse(
                200,
                {
                    "filings": {
                        "recent": {
                            "form": ["10-K"],
                            "filingDate": ["2025-11-01"],
                            "reportDate": ["2025-09-30"],
                            "acceptanceDateTime": ["2025-11-01T00:00:00.000Z"],
                            "accessionNumber": ["0000320193-25-000020"],
                            "primaryDocument": ["annual.htm"],
                            "primaryDocDescription": ["10-K"],
                        }
                    }
                },
            )
        if "annual.htm" in url:
            return _FakeResponse(
                200,
                text=(
                    "<html><body>Item 1A. Risk Factors "
                    "Our business faces supply-chain and regulatory risks. "
                    "Item 1B. Unresolved Staff Comments</body></html>"
                ),
            )
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(sec, "_http_get", _fake_http_get)
    payload = sec.get_sec_risk_factors("AAPL")
    assert payload.get("error") is None
    assert payload.get("extracted") is True
    assert "Risk Factors" in (payload.get("risk_factors_excerpt") or "")


def test_get_sec_risk_factors_skips_toc_stub(monkeypatch):
    """真实 10-K 正文前有目录页：Item 1A 与 Item 1B 条目相邻出现。
    pattern.search 取首个匹配 → 目录行（group(2) 只有页码几个字符）
    被当成风险因子摘要返回，extracted=True 但内容是目录残片。
    应在所有匹配里选正文最长者。"""
    _reset_cache()
    monkeypatch.setenv("SEC_USER_AGENT", "FinSight admin@finsight.app")

    real_body = "Real risk discussion about supply chain concentration. " * 100

    def _fake_http_get(url, **kwargs):
        if url.endswith("company_tickers.json"):
            return _FakeResponse(
                200,
                {
                    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
                },
            )
        if "submissions/CIK0000320193.json" in url:
            return _FakeResponse(
                200,
                {
                    "filings": {
                        "recent": {
                            "form": ["10-K"],
                            "filingDate": ["2025-11-01"],
                            "reportDate": ["2025-09-30"],
                            "acceptanceDateTime": ["2025-11-01T00:00:00.000Z"],
                            "accessionNumber": ["0000320193-25-000020"],
                            "primaryDocument": ["annual.htm"],
                            "primaryDocDescription": ["10-K"],
                        }
                    }
                },
            )
        if "annual.htm" in url:
            return _FakeResponse(
                200,
                text=(
                    "<html><body>"
                    "Item 1A. Risk Factors 33 "
                    "Item 1B. Unresolved Staff Comments 55 "
                    "Item 2. Properties 56 "
                    "Item 1A. Risk Factors "
                    + real_body
                    + " Item 1B. Unresolved Staff Comments"
                    "</body></html>"
                ),
            )
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(sec, "_http_get", _fake_http_get)
    payload = sec.get_sec_risk_factors("AAPL")
    assert payload.get("extracted") is True
    excerpt = payload.get("risk_factors_excerpt") or ""
    assert "Real risk discussion" in excerpt


def test_get_sec_company_facts_quarterly_success(monkeypatch):
    _reset_cache()
    monkeypatch.setenv("SEC_USER_AGENT", "FinSight admin@finsight.app")

    def _fake_http_get(url, **kwargs):
        if url.endswith("company_tickers.json"):
            return _FakeResponse(
                200,
                {
                    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
                },
            )
        if "companyfacts/CIK0000320193.json" in url:
            return _FakeResponse(
                200,
                {
                    "facts": {
                        "us-gaap": {
                            "Revenues": {
                                "units": {
                                    "USD": [
                                        {"end": "2025-06-30", "val": 100.0, "form": "10-Q", "fp": "Q3", "filed": "2025-08-01"},
                                        {"end": "2025-03-31", "val": 90.0, "form": "10-Q", "fp": "Q2", "filed": "2025-05-01"},
                                    ]
                                }
                            },
                            "NetIncomeLoss": {
                                "units": {
                                    "USD": [
                                        {"end": "2025-06-30", "val": 25.0, "form": "10-Q", "fp": "Q3", "filed": "2025-08-01"},
                                        {"end": "2025-03-31", "val": 21.0, "form": "10-Q", "fp": "Q2", "filed": "2025-05-01"},
                                    ]
                                }
                            },
                            "EarningsPerShareDiluted": {
                                "units": {
                                    "USD/shares": [
                                        {"end": "2025-06-30", "val": 1.55, "form": "10-Q", "fp": "Q3", "filed": "2025-08-01"},
                                        {"end": "2025-03-31", "val": 1.42, "form": "10-Q", "fp": "Q2", "filed": "2025-05-01"},
                                    ]
                                }
                            },
                        }
                    }
                },
            )
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(sec, "_http_get", _fake_http_get)
    payload = sec.get_sec_company_facts_quarterly("AAPL", limit=4)
    assert payload.get("error") is None
    assert payload.get("source") == "sec_companyfacts"
    assert payload.get("periods")[:2] == ["2025Q3", "2025Q2"]
    assert (payload.get("revenue") or [None])[0] == 100.0
    assert (payload.get("net_income") or [None])[0] == 25.0
    assert (payload.get("eps") or [None])[0] == 1.55


def test_get_sec_company_facts_quarterly_rejects_non_us(monkeypatch):
    _reset_cache()
    monkeypatch.setenv("SEC_USER_AGENT", "FinSight admin@finsight.app")
    payload = sec.get_sec_company_facts_quarterly("600519.SS")
    assert payload.get("error") == "unsupported_market"
    assert payload.get("market") == "CN"


_TICKER_MAP_PAYLOAD = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
}


def _patch_clocks(monkeypatch, wall, mono):
    monkeypatch.setattr(sec.time, "time", lambda: wall["t"])
    monkeypatch.setattr(sec.time, "monotonic", lambda: mono["t"])


def _patch_ticker_map_http(monkeypatch, calls):
    def _fake_http_get(url, **kwargs):
        calls["n"] += 1
        assert url.endswith("company_tickers.json")
        return _FakeResponse(200, _TICKER_MAP_PAYLOAD)

    monkeypatch.setattr(sec, "_http_get", _fake_http_get)


def test_ticker_map_ttl_survives_wall_clock_jump_backward(monkeypatch):
    """ticker→CIK 缓存 TTL 用 time.time() 存截止点：系统时钟后跳
    （w32time 回校/NTP 大步回拨/VM 恢复快照/手动改时）把 now 拉回
    expire_at 之前，真实已过 24h TTL 的映射被当成仍有效——SEC 回收
    ticker 后旧 CIK 继续服役，submissions 取到别家公司的申报（错公司
    数据进报告）。缓存是纯进程内模块全局量、无持久化无序列化消费者，
    TTL 区间计时须用单调钟（同 58464b1/35553af/beff9ef/923aa76 修复类）。"""
    _reset_cache()
    wall = {"t": 1_700_000_000.0}
    mono = {"t": 1_000.0}
    _patch_clocks(monkeypatch, wall, mono)
    calls = {"n": 0}
    _patch_ticker_map_http(monkeypatch, calls)

    headers = {"User-Agent": "FinSight admin@finsight.app"}
    first = sec._load_ticker_map(headers)
    assert calls["n"] == 1
    assert "AAPL" in first

    wall["t"] -= 30 * 86400.0                    # 墙钟后跳 30 天——expire_at 变"未来"
    mono["t"] += sec._TICKER_CACHE_TTL_SECONDS + 1.0  # 真实已过 TTL

    sec._load_ticker_map(headers)
    assert calls["n"] == 2, "TTL 真实到期必须重取映射，不得续用陈旧 CIK"


def test_ticker_map_ttl_not_broken_by_wall_clock_jump_forward(monkeypatch):
    """反向：墙钟前跳把 expire_at 瞬间推成过去式，真实仅过几秒就
    重打 company_tickers.json（每次 ~4MB 下载），TTL 保护失效。"""
    _reset_cache()
    wall = {"t": 1_700_000_000.0}
    mono = {"t": 1_000.0}
    _patch_clocks(monkeypatch, wall, mono)
    calls = {"n": 0}
    _patch_ticker_map_http(monkeypatch, calls)

    headers = {"User-Agent": "FinSight admin@finsight.app"}
    sec._load_ticker_map(headers)
    assert calls["n"] == 1

    wall["t"] += 10 * 86400.0                    # 墙钟前跳 10 天
    mono["t"] += 5.0                             # 真实仅过 5s——缓存应仍有效

    second = sec._load_ticker_map(headers)
    assert calls["n"] == 1, "TTL 未到期不得重打 ticker 映射"
    assert "AAPL" in second
