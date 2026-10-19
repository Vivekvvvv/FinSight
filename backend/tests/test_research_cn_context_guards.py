# -*- coding: utf-8 -*-
"""R19 回归：/api/research/qa 的 A 股特色数据不能把"没取到"渲染成"0 亿元"。

上游 fetch_cn_top_list / fetch_north_flow / fetch_margin_trading 在字段缺失时
返回 None 或直接返回 None，旧代码对这些情况按 0 参与 f-string，于是 prompt 里
出现"机构净买入 0.00亿元""今日净流入 0.00亿元""融资余额 0.00亿元"这类
**从未取到过的市场事实结论**（项目规则 2）。
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
    monkeypatch.setattr(rr, "create_llm", None, raising=False)
    # create_llm 在端点内部 import，直接替换 llm_config 上的符号。
    import backend.llm_config as llm_config
    monkeypatch.setattr(llm_config, "create_llm", lambda **kwargs: llm)

    app = FastAPI()
    app.include_router(rr.router)
    app.dependency_overrides[get_current_user] = lambda: Principal(
        user_id="u1", session_id="s1",
    )
    return TestClient(app), llm


def _ask(client, monkeypatch, *, top, north, margin):
    from backend.tools import baostock_provider, tencent_provider

    monkeypatch.setattr(baostock_provider, "is_cn_symbol", lambda t: True)
    monkeypatch.setattr(tencent_provider, "fetch_cn_top_list", lambda *a, **k: top)
    monkeypatch.setattr(tencent_provider, "fetch_north_flow", lambda *a, **k: north)
    monkeypatch.setattr(tencent_provider, "fetch_margin_trading", lambda *a, **k: margin)

    test_client, llm = client
    resp = test_client.post("/api/research/qa", json={
        "question": "600519 今天怎么样？",
        "ticker": "600519.SS",
    })
    assert resp.status_code == 200
    return resp.json(), llm.prompts[-1]


def test_qa_prompt_omits_cn_blocks_when_fields_missing(client, monkeypatch):
    monkeypatch.setattr(rr, "SafeLLM", None, raising=False)
    _, prompt = _ask(
        client, monkeypatch,
        top={"symbol": "600519.SS", "net_buy": None},
        north={"north_flow": None, "source": "eastmoney"},
        margin={"margin_balance": None, "source": "eastmoney"},
    )

    assert "净买入 0.00亿元" not in prompt
    assert "净流入 0.00亿元" not in prompt
    assert "融资余额 0.00亿元" not in prompt
    assert "【龙虎榜】" not in prompt
    assert "【北向资金】" not in prompt
    assert "【融资融券】" not in prompt


def test_qa_prompt_omits_cn_blocks_when_provider_returns_none(client, monkeypatch):
    _, prompt = _ask(
        client, monkeypatch,
        top=None,
        north=None,
        margin=None,
    )

    assert "【龙虎榜】" not in prompt
    assert "【北向资金】" not in prompt
    assert "【融资融券】" not in prompt


def test_qa_prompt_keeps_genuine_zero_flow(client, monkeypatch):
    """真实 0 元（平盘）是有效结论，不能连真实的 0 一起吞掉。"""
    _, prompt = _ask(
        client, monkeypatch,
        top={"symbol": "600519.SS", "net_buy": 0.0},
        north={"north_flow": 0.0, "source": "eastmoney"},
        margin={"margin_balance": 0.0, "source": "eastmoney"},
    )

    assert "【北向资金】今日净流入 0.00亿元" in prompt
    assert "【龙虎榜】今日上榜，机构净买入 0.00亿元" in prompt
    assert "【融资融券】融资余额 0.00亿元" in prompt
