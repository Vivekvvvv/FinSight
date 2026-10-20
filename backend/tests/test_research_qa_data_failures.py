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
