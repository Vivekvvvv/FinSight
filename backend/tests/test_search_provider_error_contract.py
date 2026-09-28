import importlib
from types import SimpleNamespace

import pytest


search_tools = importlib.import_module("backend.tools.search")


def test_search_success_log_does_not_include_query(monkeypatch, caplog):
    secret = "PRIVATE customer acquisition plan"
    caplog.set_level("INFO")
    monkeypatch.setattr(search_tools, "EXA_API_KEY", "test-key")
    monkeypatch.setattr(search_tools, "EXA_AVAILABLE", True)
    monkeypatch.setattr(search_tools, "_EXA_QUOTA_BLOCKED_UNTIL", 0.0)
    monkeypatch.setattr(search_tools, "_search_with_exa", lambda _query: "x" * 1200)

    result = search_tools.search(secret)

    assert "综合搜索结果" in result
    assert secret not in caplog.text
    assert "[Search] Exa 搜索成功" in caplog.text


def test_search_exa_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE https://exa-token@search.example.com"
    caplog.set_level("INFO")
    monkeypatch.setattr(search_tools, "EXA_API_KEY", "test-key")
    monkeypatch.setattr(search_tools, "EXA_AVAILABLE", True)
    monkeypatch.setattr(search_tools, "_EXA_QUOTA_BLOCKED_UNTIL", 0.0)
    monkeypatch.setattr(search_tools, "TAVILY_API_KEY", "")
    monkeypatch.setattr(search_tools, "WIKIPEDIA_AVAILABLE", False)
    monkeypatch.setattr(search_tools, "DDGS_AVAILABLE", False)
    monkeypatch.setattr(
        search_tools,
        "_search_with_exa",
        lambda _query: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    result = search_tools.search("AAPL earnings")

    assert result == "Search error: 所有搜索源均失败，无法获取搜索结果。"
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_search_tavily_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE https://tavily-token@search.example.com"
    caplog.set_level("INFO")
    monkeypatch.setattr(search_tools, "EXA_API_KEY", "")
    monkeypatch.setattr(search_tools, "TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(search_tools, "TAVILY_AVAILABLE", True)
    monkeypatch.setattr(search_tools, "_TAVILY_QUOTA_BLOCKED_UNTIL", 0.0)
    monkeypatch.setattr(search_tools, "WIKIPEDIA_AVAILABLE", False)
    monkeypatch.setattr(search_tools, "DDGS_AVAILABLE", False)
    monkeypatch.setattr(
        search_tools,
        "_search_with_tavily",
        lambda _query: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    result = search_tools.search("AAPL earnings")

    assert result == "Search error: 所有搜索源均失败，无法获取搜索结果。"
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_search_wikipedia_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE session=wikipedia-search"
    caplog.set_level("INFO")
    monkeypatch.setattr(search_tools, "EXA_API_KEY", "")
    monkeypatch.setattr(search_tools, "TAVILY_API_KEY", "")
    monkeypatch.setattr(search_tools, "WIKIPEDIA_AVAILABLE", True)
    monkeypatch.setattr(search_tools, "DDGS_AVAILABLE", False)
    monkeypatch.setattr(
        search_tools,
        "_search_with_wikipedia",
        lambda _query: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    result = search_tools.search("Ada Lovelace biography")

    assert result == "Search error: 所有搜索源均失败，无法获取搜索结果。"
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_search_duckduckgo_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE http://proxy-user:secret@proxy.local/ddgs"
    caplog.set_level("INFO")
    monkeypatch.setattr(search_tools, "EXA_API_KEY", "")
    monkeypatch.setattr(search_tools, "TAVILY_API_KEY", "")
    monkeypatch.setattr(search_tools, "WIKIPEDIA_AVAILABLE", False)
    monkeypatch.setattr(search_tools, "DDGS_AVAILABLE", True)
    monkeypatch.setattr(search_tools, "DDGS", object())
    monkeypatch.setattr(
        search_tools,
        "_search_with_duckduckgo",
        lambda _query: (_ for _ in ()).throw(RuntimeError(secret)),
    )

    result = search_tools.search("AAPL earnings")

    assert result == "Search error: 所有搜索源均失败，无法获取搜索结果。"
    assert secret not in caplog.text
    assert "RuntimeError" in caplog.text


def test_wikipedia_page_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE session=wikipedia-page"
    caplog.set_level("INFO")

    class _DisambiguationError(Exception):
        pass

    class _PageError(Exception):
        pass

    fake_wikipedia = SimpleNamespace(
        exceptions=SimpleNamespace(
            DisambiguationError=_DisambiguationError,
            PageError=_PageError,
        ),
        search=lambda *_args, **_kwargs: ["Ada Lovelace"],
        page=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    monkeypatch.setattr(search_tools, "WIKIPEDIA_AVAILABLE", True)
    monkeypatch.setattr(search_tools, "wikipedia", fake_wikipedia)

    assert search_tools._search_with_wikipedia("Ada Lovelace") is None
    assert secret not in caplog.text
    assert "Ada Lovelace" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_wikipedia_search_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE session=wikipedia-outer"
    caplog.set_level("INFO")
    fake_wikipedia = SimpleNamespace(
        search=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    monkeypatch.setattr(search_tools, "WIKIPEDIA_AVAILABLE", True)
    monkeypatch.setattr(search_tools, "wikipedia", fake_wikipedia)

    assert search_tools._search_with_wikipedia("Ada Lovelace") is None
    assert secret not in caplog.text
    assert "维基百科搜索出错: RuntimeError" in caplog.text


def test_tavily_api_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE https://tavily-token@search.example.com/helper"
    caplog.set_level("INFO")
    client = SimpleNamespace(
        search=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    monkeypatch.setattr(search_tools, "TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(search_tools, "TAVILY_AVAILABLE", True)
    monkeypatch.setattr(search_tools, "TavilyClient", lambda **_kwargs: client)

    with pytest.raises(Exception):
        search_tools._search_with_tavily("AAPL earnings")

    assert secret not in caplog.text
    assert "Tavily API 错误" in caplog.text
    assert "RuntimeError" not in caplog.text


def test_tavily_api_error_is_redacted_when_raised(monkeypatch):
    secret = "PRIVATE https://tavily-token@search.example.com/raised"
    client = SimpleNamespace(
        search=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    monkeypatch.setattr(search_tools, "TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(search_tools, "TAVILY_AVAILABLE", True)
    monkeypatch.setattr(search_tools, "TavilyClient", lambda **_kwargs: client)

    with pytest.raises(RuntimeError) as exc_info:
        search_tools._search_with_tavily("AAPL earnings")

    assert str(exc_info.value) == "Tavily search failed"
    assert secret not in str(exc_info.value)


def test_exa_api_error_is_redacted_when_raised(monkeypatch):
    secret = "PRIVATE https://exa-token@search.example.com/raised"
    client = SimpleNamespace(
        search_and_contents=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError(secret)),
    )
    monkeypatch.setattr(search_tools, "EXA_API_KEY", "test-key")
    monkeypatch.setattr(search_tools, "EXA_AVAILABLE", True)
    monkeypatch.setattr(search_tools, "Exa", lambda **_kwargs: client)

    with pytest.raises(RuntimeError) as exc_info:
        search_tools._search_with_exa("AAPL earnings")

    assert str(exc_info.value) == "Exa search failed"
    assert secret not in str(exc_info.value)


def test_exa_quota_cooldown_survives_wall_clock_jump(monkeypatch):
    """配额冷却是区间计时，time.time() 随系统时钟跳变：前跳（w32time 大步进/
    VM 恢复快照/手动改时）把 blocked_until 瞬间推成过去式——刚因 402/额度耗尽
    被熔断的 Exa 立刻被 _is_provider_blocked 放行，之后每次 search() 都先打
    一次注定失败的付费 API 往返（数秒延迟+持续锤到死额度），冷却保护静默失效；
    后跳则 blocked_until 永久滞留未来，provider 再无法恢复。锚点纯进程内
    全局量、无持久化无序列化消费者，区间计时须用单调钟（同 23310e7/389d176/
    108c5f7/58464b1 修复类）。"""
    wall = {"t": 5_000_000.0}
    mono = {"t": 1_000.0}
    monkeypatch.setattr(search_tools.time, "time", lambda: wall["t"])
    monkeypatch.setattr(search_tools.time, "monotonic", lambda: mono["t"])
    monkeypatch.setattr(search_tools, "EXA_API_KEY", "test-key")
    monkeypatch.setattr(search_tools, "EXA_AVAILABLE", True)
    monkeypatch.setattr(search_tools, "TAVILY_API_KEY", "")
    monkeypatch.setattr(search_tools, "WIKIPEDIA_AVAILABLE", False)
    monkeypatch.setattr(search_tools, "DDGS_AVAILABLE", False)
    monkeypatch.setattr(search_tools, "DDGS", None)
    monkeypatch.setattr(search_tools, "_EXA_QUOTA_BLOCKED_UNTIL", 0.0)

    calls = {"n": 0}

    def _dead_exa(_query):
        calls["n"] += 1
        raise RuntimeError("status code 402: no_more_credits")

    monkeypatch.setattr(search_tools, "_search_with_exa", _dead_exa)

    search_tools.search("first query")
    assert calls["n"] == 1
    assert search_tools._EXA_QUOTA_BLOCKED_UNTIL > 0

    wall["t"] += 7200.0  # 墙钟前跳 2h——远超冷却窗口但真实经过 ~1s
    mono["t"] += 1.0

    search_tools.search("second query")
    assert calls["n"] == 1  # 冷却未真实到期，Exa 不应再被打
