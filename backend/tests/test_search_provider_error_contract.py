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
    assert f"query_chars={len(secret)}" in caplog.text


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
