from types import SimpleNamespace
import logging

import pytest

import backend.handlers.chat_handler as chat_handler_module
from backend.handlers.chat_handler import ChatHandler


def _handler(*, tools=None, orchestrator=None, llm=None):
    handler = object.__new__(ChatHandler)
    handler.llm = llm
    handler.orchestrator = orchestrator
    handler.news_agent = None
    handler.price_agent = None
    handler.tools_module = tools
    return handler


def _assert_redacted(result, secret, caplog, captured):
    assert result["success"] is False
    assert secret not in str(result)
    assert secret not in caplog.text
    assert secret not in captured.out
    assert secret not in captured.err


def test_handle_does_not_log_user_query(monkeypatch, caplog):
    secret = "PRIVATE_CHAT_QUERY_SENTINEL"
    caplog.set_level(logging.INFO, logger=chat_handler_module.__name__)
    handler = _handler()
    monkeypatch.setattr(
        handler,
        "_handle_with_search",
        lambda *_args, **_kwargs: {"success": True, "response": "ok"},
    )

    result = handler.handle(secret, {})

    assert result["success"] is True
    assert secret not in caplog.text
    assert f"query_chars={len(secret)}" in caplog.text


def test_handle_internal_error_is_redacted(monkeypatch, caplog, capsys):
    secret = "PRIVATE_CHAT_ERROR_SENTINEL"
    handler = _handler()

    def fail_intent(_query):
        raise RuntimeError(secret)

    monkeypatch.setattr(handler, "_is_generic_recommendation_intent", fail_intent)

    result = handler.handle("query", {})

    _assert_redacted(result, secret, caplog, capsys.readouterr())
    assert result["error"] == "internal_error"
    assert "RuntimeError" in caplog.text


def test_price_error_is_redacted(caplog, capsys):
    secret = "PRIVATE_PRICE_ERROR_SENTINEL"

    def fail_price(_ticker):
        raise RuntimeError(secret)

    tools = SimpleNamespace(
        get_stock_price=fail_price,
        get_stock_historical_data=lambda *_args, **_kwargs: None,
    )
    handler = _handler(tools=tools)

    result = handler._handle_price_query("AAPL", "price")

    _assert_redacted(result, secret, caplog, capsys.readouterr())
    assert result["error"] == "internal_error"
    assert "RuntimeError" in caplog.text


def test_news_error_is_redacted(caplog, capsys):
    secret = "PRIVATE_NEWS_ERROR_SENTINEL"

    def fail_news(*_args, **_kwargs):
        raise ConnectionError(secret)

    handler = _handler(tools=SimpleNamespace(get_company_news=fail_news))

    result = handler._handle_news_query("AAPL", "news")

    _assert_redacted(result, secret, caplog, capsys.readouterr())
    assert result["error"] == "internal_error"
    assert "ConnectionError" in caplog.text


def test_sentiment_error_is_redacted(caplog, capsys):
    secret = "PRIVATE_SENTIMENT_ERROR_SENTINEL"

    def fail_fetch(*_args, **_kwargs):
        raise RuntimeError(secret)

    handler = _handler(
        orchestrator=SimpleNamespace(fetch=fail_fetch),
        tools=SimpleNamespace(get_market_sentiment=fail_fetch),
    )

    result = handler._handle_sentiment_query("sentiment")

    _assert_redacted(result, secret, caplog, capsys.readouterr())
    assert result["error"] == "internal_error"
    assert "RuntimeError" in caplog.text


def test_economic_events_error_is_redacted(caplog, capsys):
    secret = "PRIVATE_CALENDAR_ERROR_SENTINEL"

    def fail_fetch(*_args, **_kwargs):
        raise ConnectionError(secret)

    handler = _handler(
        orchestrator=SimpleNamespace(fetch=fail_fetch),
        tools=SimpleNamespace(get_economic_events=fail_fetch),
    )

    result = handler._handle_economic_events("calendar")

    _assert_redacted(result, secret, caplog, capsys.readouterr())
    assert result["error"] == "internal_error"
    assert "ConnectionError" in caplog.text


def test_news_sentiment_error_is_redacted(caplog, capsys):
    secret = "PRIVATE_NEWS_SENTIMENT_ERROR_SENTINEL"

    def fail_fetch(*_args, **_kwargs):
        raise RuntimeError(secret)

    handler = _handler(
        orchestrator=SimpleNamespace(fetch=fail_fetch),
        tools=SimpleNamespace(get_news_sentiment=fail_fetch),
    )

    result = handler._handle_news_sentiment_query("AAPL", "news sentiment")

    _assert_redacted(result, secret, caplog, capsys.readouterr())
    assert result["error"] == "internal_error"
    assert "RuntimeError" in caplog.text


def test_company_info_error_is_redacted(caplog, capsys):
    secret = "PRIVATE_COMPANY_INFO_PASSWORD=provider-secret"

    def fail_info(_ticker):
        raise ConnectionError(secret)

    handler = _handler(tools=SimpleNamespace(get_company_info=fail_info))

    result = handler._handle_info_query("AAPL", "company info")

    _assert_redacted(result, secret, caplog, capsys.readouterr())
    assert result["error"] == "internal_error"
    assert "ConnectionError" in caplog.text


def test_composition_search_error_is_redacted(caplog, capsys):
    secret = "PRIVATE_COMPOSITION_ERROR_SENTINEL"

    def fail_search(_query):
        raise RuntimeError(secret)

    handler = _handler(tools=SimpleNamespace(search=fail_search))

    result = handler._handle_composition_query("SPY", "holdings")

    _assert_redacted(result, secret, caplog, capsys.readouterr())
    assert result["error"] == "internal_error"
    assert "RuntimeError" in caplog.text


def test_research_review_error_is_redacted(monkeypatch, caplog, capsys):
    secret = "PRIVATE_REVIEW_ERROR_SENTINEL"

    def fail_invoke(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(chat_handler_module, "LANGCHAIN_AVAILABLE", True)
    handler = _handler(llm=SimpleNamespace(invoke=fail_invoke))

    result = handler._handle_advice_query("AAPL", "review")

    _assert_redacted(result, secret, caplog, capsys.readouterr())
    assert result["error"] == "internal_error"
    assert "RuntimeError" in caplog.text


def test_general_search_error_is_redacted(caplog, capsys):
    secret = "PRIVATE_SEARCH_ERROR_SENTINEL"

    def fail_search(_query):
        raise ConnectionError(secret)

    handler = _handler(tools=SimpleNamespace(search=fail_search))

    result = handler._handle_with_search("query")

    _assert_redacted(result, secret, caplog, capsys.readouterr())
    assert result["error"] == "internal_error"
    assert "ConnectionError" in caplog.text


def test_handle_with_llm_error_does_not_print_traceback(monkeypatch, caplog, capsys):
    secret = "PRIVATE_LLM_ENHANCE_ERROR_SENTINEL"
    basic = {"success": True, "response": "base response", "intent": "chat"}

    def fail_invoke(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(chat_handler_module, "LANGCHAIN_AVAILABLE", True)
    handler = _handler(llm=SimpleNamespace(invoke=fail_invoke))
    monkeypatch.setattr(handler, "handle", lambda *_args, **_kwargs: dict(basic))

    result = handler.handle_with_llm("query", {})
    captured = capsys.readouterr()

    assert result == basic
    assert secret not in caplog.text
    assert secret not in captured.out
    assert secret not in captured.err
    assert "RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_stream_with_llm_error_does_not_print_traceback(monkeypatch, caplog, capsys):
    secret = "PRIVATE_STREAM_ERROR_SENTINEL"
    basic = {"success": True, "response": "base response", "intent": "chat"}

    class FailingLLM:
        async def astream(self, *_args, **_kwargs):
            raise ConnectionError(secret)
            yield "unreachable"

    monkeypatch.setattr(chat_handler_module, "LANGCHAIN_AVAILABLE", True)
    handler = _handler(llm=FailingLLM())
    monkeypatch.setattr(handler, "handle", lambda *_args, **_kwargs: dict(basic))
    result_container = {}

    chunks = [
        chunk
        async for chunk in handler.stream_with_llm("query", {}, None, result_container)
    ]
    captured = capsys.readouterr()

    assert chunks == ["base response"]
    assert result_container == basic
    assert secret not in caplog.text
    assert secret not in captured.out
    assert secret not in captured.err
    assert "ConnectionError" in caplog.text


def test_comparison_llm_error_does_not_leak(monkeypatch, caplog, capsys):
    secret = "PRIVATE_COMPARISON_ERROR_SENTINEL"
    caplog.set_level(logging.INFO, logger=chat_handler_module.__name__)

    def fail_invoke(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(chat_handler_module, "LANGCHAIN_AVAILABLE", True)
    handler = _handler(llm=SimpleNamespace(invoke=fail_invoke))

    result = handler._handle_comparison_query(["AAPL", "MSFT"], "compare", {})
    captured = capsys.readouterr()

    assert result["success"] is True
    assert result["intent"] == "chat"
    assert secret not in str(result)
    assert secret not in caplog.text
    assert secret not in captured.out
    assert secret not in captured.err
    assert "RuntimeError" in caplog.text
