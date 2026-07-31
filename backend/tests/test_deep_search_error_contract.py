import asyncio
import builtins
import logging
import sys
import types

import pytest

from backend.agents.deep_search_agent import DeepSearchAgent


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_deep_search_json_parser_rejects_non_finite_constants(constant):
    agent = DeepSearchAgent(llm=None, cache=None, tools_module=None)

    assert agent._extract_json('{"needs_more":' + constant + "}") == {}


def test_rag_observability_recording_error_is_redacted(monkeypatch, caplog):
    from backend import rag

    def fail_rag_service():
        raise RuntimeError("private deep search rag detail")

    monkeypatch.setattr(rag, "get_rag_service", fail_rag_service)
    agent = DeepSearchAgent(llm=None, cache=None, tools_module=None)
    with caplog.at_level(logging.ERROR, logger="backend.agents.deep_search_agent"):
        result = asyncio.run(
            agent._record_rag_observability(
                query="AAPL outlook",
                ticker="AAPL",
                docs=[{"content": "evidence", "title": "Example"}],
            )
        )

    assert result["enabled"] is False
    assert result["error"] == "unavailable"
    assert "private deep search rag detail" not in str(result)
    assert "private deep search rag detail" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_rag_observability_import_error_is_redacted(monkeypatch, caplog):
    original_import = builtins.__import__

    def fail_rag_import(name, *args, **kwargs):
        if name == "backend.rag":
            raise ImportError("private rag import detail")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_rag_import)
    agent = DeepSearchAgent(llm=None, cache=None, tools_module=None)
    with caplog.at_level(logging.INFO, logger="backend.agents.deep_search_agent"):
        result = asyncio.run(
            agent._record_rag_observability(
                query="AAPL outlook",
                ticker="AAPL",
                docs=[{"content": "evidence"}],
            )
        )

    assert result == {"enabled": False, "error": "unavailable"}
    assert "private rag import detail" not in str(result)
    assert "private rag import detail" not in caplog.text
    assert "ImportError" in caplog.text


def test_pdf_parse_error_log_is_redacted(monkeypatch, caplog):
    from backend.agents import deep_search_agent as deep_search_module

    def fail_pdf_reader(_stream):
        raise RuntimeError("private pdf parser detail")

    monkeypatch.setattr(deep_search_module, "PdfReader", fail_pdf_reader)
    agent = DeepSearchAgent(llm=None, cache=None, tools_module=None)
    with caplog.at_level(logging.INFO, logger="backend.agents.deep_search_agent"):
        result = agent._extract_pdf_text(b"not-a-pdf")

    assert result == ""
    assert "private pdf parser detail" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_tavily_search_error_log_is_redacted(monkeypatch, caplog):
    class Tools:
        TAVILY_API_KEY = "test-key"
        TAVILY_AVAILABLE = True
        EXA_API_KEY = ""
        EXA_AVAILABLE = False

    class FailingTavilyClient:
        def __init__(self, **_kwargs):
            raise RuntimeError("private tavily provider detail")

    tavily_module = types.ModuleType("tavily")
    tavily_module.TavilyClient = FailingTavilyClient
    monkeypatch.setitem(sys.modules, "tavily", tavily_module)
    agent = DeepSearchAgent(llm=None, cache=None, tools_module=Tools())

    with caplog.at_level(logging.INFO, logger="backend.agents.deep_search_agent"):
        results = agent._search_web("AAPL outlook")

    assert results == []
    assert "private tavily provider detail" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_exa_search_error_log_is_redacted(monkeypatch, caplog):
    class Tools:
        TAVILY_API_KEY = ""
        TAVILY_AVAILABLE = False
        EXA_API_KEY = "test-key"
        EXA_AVAILABLE = True

    class FailingExa:
        def __init__(self, **_kwargs):
            raise RuntimeError("private exa provider detail")

    exa_module = types.ModuleType("exa_py")
    exa_module.Exa = FailingExa
    monkeypatch.setitem(sys.modules, "exa_py", exa_module)
    agent = DeepSearchAgent(llm=None, cache=None, tools_module=Tools())

    with caplog.at_level(logging.INFO, logger="backend.agents.deep_search_agent"):
        results = agent._search_web("AAPL outlook")

    assert results == []
    assert "private exa provider detail" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_local_search_fallback_error_log_is_redacted(caplog):
    class Tools:
        TAVILY_API_KEY = ""
        TAVILY_AVAILABLE = False
        EXA_API_KEY = ""
        EXA_AVAILABLE = False

        @staticmethod
        def search(_query):
            raise RuntimeError("private local search detail")

    agent = DeepSearchAgent(llm=None, cache=None, tools_module=Tools())
    with caplog.at_level(logging.INFO, logger="backend.agents.deep_search_agent"):
        results = agent._search_web("AAPL outlook")

    assert results == []
    assert "private local search detail" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_authoritative_feed_error_log_is_redacted(caplog):
    class Tools:
        TAVILY_API_KEY = ""
        TAVILY_AVAILABLE = False
        EXA_API_KEY = ""
        EXA_AVAILABLE = False

        @staticmethod
        def search_authoritative_feeds(*_args, **_kwargs):
            raise RuntimeError("private authoritative feed detail")

    agent = DeepSearchAgent(llm=None, cache=None, tools_module=Tools())
    with caplog.at_level(logging.INFO, logger="backend.agents.deep_search_agent"):
        results = agent._search_web("AAPL outlook")

    assert results == []
    assert "private authoritative feed detail" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_document_fetch_error_log_is_redacted(monkeypatch, caplog):
    from backend.agents import deep_search_agent as deep_search_module

    def fail_request(*_args, **_kwargs):
        raise RuntimeError("private document fetch detail")

    monkeypatch.setattr(deep_search_module, "safe_pinned_request", fail_request)
    agent = DeepSearchAgent(llm=None, cache=None, tools_module=None)
    with caplog.at_level(logging.INFO, logger="backend.agents.deep_search_agent"):
        result = agent._fetch_document({"url": "https://example.invalid/doc"})

    assert result is None
    assert "private document fetch detail" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_document_url_query_is_redacted_from_logs(monkeypatch, caplog):
    from backend.agents import deep_search_agent as deep_search_module

    secret = "PRIVATE_QUERY_TOKEN_456"
    monkeypatch.setattr(deep_search_module, "safe_pinned_request", lambda *_args, **_kwargs: None)
    agent = DeepSearchAgent(llm=None, cache=None, tools_module=None)

    with caplog.at_level(logging.INFO, logger="backend.agents.deep_search_agent"):
        result = agent._fetch_document(
            {"url": f"https://example.invalid/doc?access_token={secret}"}
        )

    assert result is None
    assert secret not in caplog.text
    assert "access_token" not in caplog.text
    assert "example.invalid" in caplog.text


def test_document_inventory_logs_only_url_host(caplog):
    secret = "PRIVATE_QUERY_TOKEN_789"
    agent = DeepSearchAgent(llm=None, cache=None, tools_module=None)

    with caplog.at_level(logging.INFO, logger="backend.agents.deep_search_agent"):
        agent._log_documents(
            [{"title": "Example", "url": f"https://example.invalid/doc?token={secret}"}],
            "search",
        )

    assert secret not in caplog.text
    assert "token=" not in caplog.text
    assert "example.invalid" in caplog.text
