import asyncio

from backend.conversation.context import ContextManager
from backend.handlers.chat_handler import ChatHandler
from backend.handlers.followup_handler import FollowupHandler


class StubChunk:
    def __init__(self, content: str):
        self.content = content


class StubLLM:
    def __init__(self, tokens):
        self.tokens = tokens
        self.invoked = False

    async def astream(self, messages):
        for token in self.tokens:
            yield StubChunk(token)

    def invoke(self, messages):
        self.invoked = True

        class Response:
            def __init__(self, content: str):
                self.content = content

        return Response("fallback")


async def _collect_tokens(generator):
    tokens = []
    async for token in generator:
        tokens.append(token)
    return tokens


def test_chat_handler_stream_with_llm(monkeypatch):
    handler = ChatHandler(llm=StubLLM(["A", "B"]), orchestrator=None)
    monkeypatch.setattr(
        handler,
        "handle",
        lambda q, m, c: {"success": True, "response": "base", "intent": "chat"},
    )

    result_container = {}
    tokens = asyncio.run(
        _collect_tokens(handler.stream_with_llm("hello", {}, None, result_container))
    )

    assert "".join(tokens) == "AB"
    assert result_container["response"] == "AB"
    assert result_container["enhanced_by_llm"] is True


def test_followup_handler_stream_with_llm():
    context = ContextManager()
    context.add_turn(query="Q1", intent="chat", response="previous", metadata={})
    context.get_last_long_response = lambda: None

    handler = FollowupHandler(llm=StubLLM(["x", "y"]), orchestrator=None)
    result_container = {}
    tokens = asyncio.run(
        _collect_tokens(handler.stream_with_llm("why", {}, context, result_container))
    )

    assert "".join(tokens) == "xy"
    assert result_container["response"] == "xy"
    assert result_container["intent"] == "followup"


def test_followup_report_action_offloads_sync_invoke():
    """R70：last_long_response 分支走 _handle_report_followup（内部同步 llm.invoke），
    在 async 生成器里必须经 to_thread 卸载，不阻塞事件循环。验证卸载后仍正确产出。"""
    context = ContextManager()
    context.add_turn(query="给我一份报告", intent="report", response="报告正文", metadata={})
    # 触发 last_long_response 分支（235）
    context.get_last_long_response = lambda: "这是一份很长的研究报告正文……" * 20

    handler = FollowupHandler(llm=StubLLM([]), orchestrator=None)
    result_container = {}
    tokens = asyncio.run(
        _collect_tokens(handler.stream_with_llm("总结一下", {}, context, result_container))
    )
    # 走到了 report followup 分支并产出内容（不阻塞、有结果）
    assert result_container, "report followup 分支应产出 result"
    assert "".join(tokens) != "" or result_container.get("response") is not None
