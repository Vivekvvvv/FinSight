# -*- coding: utf-8 -*-
"""智能问答：取数失败时答完不能装作"基于实时数据"。

`/api/research/qa` 的 prompt 写着"请基于以下数据回答用户问题"，但行情或新闻
拉取失败时旧代码只是把这一块静默省略——模型照常输出一段流畅回答，读起来
像是有数据支撑的结论（项目规则 2）。失败必须显式告知模型与调用方。
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import research_router as rr
from backend.security.auth import Principal, get_current_user


class _FakeLLM:
    def __init__(self):
        self.prompts: list[str] = []

    async def ainvoke(self, prompt):
        self.prompts.append(prompt)

        class _Resp:
            content = "answer"

        return _Resp()


@pytest.fixture
def client(monkeypatch):
    llm = _FakeLLM()
    import backend.llm_config as llm_config
    monkeypatch.setattr(llm_config, "create_llm", lambda **kwargs: llm)

    app = FastAPI()
    app.include_router(rr.router)
    app.dependency_overrides[get_current_user] = lambda: Principal(
        user_id="u1", session_id="s1",
    )
    return TestClient(app), llm


def _qa(client, monkeypatch, *, price=None, price_exc=None, news=None, news_exc=None):
    import backend.tools as tools_pkg

    if price_exc is not None:
        def _raise(_ticker):
            raise price_exc
        monkeypatch.setattr(tools_pkg, "get_stock_price", _raise)
    else:
        monkeypatch.setattr(tools_pkg, "get_stock_price", lambda _ticker: price)

    if news_exc is not None:
        def _raise_news(_ticker, limit=5):
            raise news_exc
        monkeypatch.setattr(tools_pkg, "get_company_news", _raise_news)
    else:
        monkeypatch.setattr(tools_pkg, "get_company_news", lambda _ticker, limit=5: news)

    test_client, llm = client
    resp = test_client.post(
        "/api/research/qa", json={"question": "走势如何", "ticker": "AAPL"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json(), llm.prompts[-1]


def test_quote_exception_is_reported_not_silently_dropped(client, monkeypatch):
    payload, prompt = _qa(client, monkeypatch, price_exc=RuntimeError("down"), news=[])

    assert payload["data_unavailable"] == ["最新行情"]
    assert payload["context_used"] == []
    assert "数据获取失败" in prompt
    assert "最新行情" in prompt


@pytest.mark.parametrize("price", [True, 0, -5, "nan", "inf", {}, []])
def test_invalid_quote_price_cannot_be_used_as_a_market_fact(client, monkeypatch, price):
    payload, prompt = _qa(client, monkeypatch, price={"price": price}, news=[])

    assert payload["data_unavailable"] == ["最新行情"]
    assert payload["context_used"] == []
    assert "数据获取失败" in prompt


@pytest.mark.parametrize("change", [True, -101, "nan", "inf", {}, []])
def test_invalid_quote_change_is_unknown_with_valid_price_retained(client, monkeypatch, change):
    payload, _ = _qa(client, monkeypatch, price={"price": "100", "change_percent": change}, news=[])

    assert payload["data_unavailable"] == []
    assert payload["context_used"] == ["【最新行情】AAPL 现价 100.0，涨跌幅 N/A%"]


def test_valid_quote_aliases_and_zero_change_are_retained(client, monkeypatch):
    payload, _ = _qa(client, monkeypatch, price={"price": "bad", "current_price": "100", "change_pct": 0}, news=[])

    assert payload["context_used"] == ["【最新行情】AAPL 现价 100.0，涨跌幅 0.0%"]


@pytest.mark.parametrize("failure", [{"success": False}, {"status": " ERROR "}, {"status": "unavailable"}])
def test_failed_quote_status_cannot_supply_retained_market_data(client, monkeypatch, failure):
    payload, _ = _qa(client, monkeypatch, price={**failure, "price": 100, "change_percent": 1}, news=[])

    assert payload["data_unavailable"] == ["最新行情"]
    assert payload["context_used"] == []


@pytest.mark.parametrize("identity", [{"ticker": "MSFT"}, {"symbol": "MSFT"}, {"ticker": "AAPL", "symbol": "MSFT"}])
def test_quote_for_another_instrument_is_not_relabelled_for_the_question(client, monkeypatch, identity):
    payload, _ = _qa(client, monkeypatch, price={**identity, "price": 100}, news=[])

    assert payload["data_unavailable"] == ["最新行情"]
    assert payload["context_used"] == []


def test_matching_quote_identity_ignores_case_and_whitespace(client, monkeypatch):
    payload, _ = _qa(client, monkeypatch, price={"ticker": " aapl ", "symbol": "AAPL", "price": 100}, news=[])

    assert payload["data_unavailable"] == []
    assert "AAPL 现价 100.0" in payload["context_used"][0]


def test_error_string_quote_is_reported_not_silently_dropped(client, monkeypatch):
    payload, prompt = _qa(
        client, monkeypatch,
        price="Error: All data sources failed to retrieve the price for AAPL.",
        news=[],
    )

    assert payload["data_unavailable"] == ["最新行情"]
    assert not any("Error:" in part for part in payload["context_used"])
    assert "数据获取失败" in prompt


def test_news_exception_is_reported(client, monkeypatch):
    payload, prompt = _qa(
        client, monkeypatch,
        price={"price": 100.0, "change_percent": 1.0},
        news_exc=RuntimeError("down"),
    )

    assert payload["data_unavailable"] == ["今日新闻"]
    assert "数据获取失败" in prompt
    assert any("最新行情" in part for part in payload["context_used"])


@pytest.mark.parametrize("news", [
    None, "invalid", {"news": "invalid"}, {"news": {"title": "invalid"}},
    {"success": False, "news": [{"title": "retained"}]},
    {"error": "provider failed", "news": [{"title": "retained"}]},
    {"status": " FAILED ", "news": [{"title": "retained"}]},
])
def test_unavailable_news_payload_is_reported_to_model_and_caller(client, monkeypatch, news):
    payload, prompt = _qa(client, monkeypatch, price={"price": 100}, news=news)

    assert payload["data_unavailable"] == ["今日新闻"]
    assert not any("相关新闻" in part for part in payload["context_used"])
    assert "本次未能获取：今日新闻" in prompt


def test_malformed_news_rows_do_not_hide_later_valid_headlines(client, monkeypatch):
    payload, _ = _qa(client, monkeypatch, price={"price": 100}, news=[
        None, "bad", {"title": {}}, {"title": "  第一条  "},
        {"title": "第二条"}, {"title": "第三条"}, {"title": "第四条"},
    ])

    assert payload["data_unavailable"] == []
    assert payload["context_used"][1] == "【今日相关新闻】\n- 第一条\n- 第二条\n- 第三条"


@pytest.mark.parametrize("news", [[None, 1], [{"title": {}}, {"title": True}], [{"title": "   "}]])
def test_nonempty_news_without_valid_titles_is_marked_unavailable(client, monkeypatch, news):
    payload, _ = _qa(client, monkeypatch, price={"price": 100}, news=news)

    assert payload["data_unavailable"] == ["今日新闻"]
    assert not any("相关新闻" in part for part in payload["context_used"])


@pytest.mark.parametrize("failure", [{"error": "failed"}, {"success": False}, {"status": " ERROR "}])
def test_failed_news_rows_do_not_supply_qa_headlines(client, monkeypatch, failure):
    payload, _ = _qa(client, monkeypatch, price={"price": 100}, news=[
        {**failure, "title": "失败记录"}, {"title": "有效新闻"},
    ])

    assert payload["context_used"][1] == "【今日相关新闻】\n- 有效新闻"
    assert payload["data_unavailable"] == []


def test_genuinely_empty_news_is_not_a_fetch_failure(client, monkeypatch):
    """新闻接口正常回空列表：确实没有新闻，不能报成取数失败。"""
    payload, prompt = _qa(
        client, monkeypatch,
        price={"price": 100.0, "change_percent": 1.0},
        news=[],
    )

    assert payload["data_unavailable"] == []
    assert "数据获取失败" not in prompt


def test_no_ticker_has_no_data_gap_warning(client, monkeypatch):
    import backend.llm_config as llm_config

    class _FakeLLM:
        async def ainvoke(self, prompt):
            self.prompt = prompt

            class _Resp:
                content = "answer"

            return _Resp()

    llm = _FakeLLM()
    monkeypatch.setattr(llm_config, "create_llm", lambda **kwargs: llm)
    test_client, _ = client

    resp = test_client.post("/api/research/qa", json={"question": "大盘怎么看？"})

    assert resp.status_code == 200
    assert resp.json()["data_unavailable"] == []
    assert "数据获取失败" not in llm.prompt
