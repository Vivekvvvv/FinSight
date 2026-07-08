# -*- coding: utf-8 -*-
"""R15 回归：价格结果必须短路 LLM 改写。

守卫集合里写的是 'price'，但价格查询实际产生的 intent 是 'market_data'
（chat_handler 全文件从不产生 'price'）——死条件使守卫失效，价格响应
继续进入 LLM 改写，真实成交价可能被模型篡改，与注释"避免 LLM 改写价格
细节"的意图相反。
"""
from __future__ import annotations

from backend.handlers.chat_handler import ChatHandler


class _ExplodingLLM:
    """任何调用即失败——用于断言 LLM 完全未被触碰。"""

    def invoke(self, *_args, **_kwargs):
        raise AssertionError("market_data result must bypass LLM rewriting")

    def __call__(self, *_args, **_kwargs):
        raise AssertionError("market_data result must bypass LLM rewriting")


def test_market_data_result_bypasses_llm_rewrite(monkeypatch):
    handler = ChatHandler(llm=_ExplodingLLM())

    price_result = {
        "success": True,
        "intent": "market_data",
        "response": "AAPL Current Price: $123.45 | Change: +1.00 (+0.82%)",
    }
    monkeypatch.setattr(handler, "handle", lambda *a, **k: dict(price_result))

    result = handler.handle_with_llm("AAPL 现在多少钱", metadata={}, context=None)

    # 原样返回，价格数字未经 LLM 改写
    assert result["intent"] == "market_data"
    assert result["response"] == price_result["response"]
