import sys
from types import SimpleNamespace

from backend.services import langfuse_tracer


def test_langfuse_initialization_error_log_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE https://secret-token@tracing.example.com"

    def _fail_langfuse(**_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "public-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "secret-test")
    monkeypatch.setattr(langfuse_tracer, "_langfuse_client", None)
    monkeypatch.setattr(langfuse_tracer, "_init_attempted", False)
    monkeypatch.setitem(sys.modules, "langfuse", SimpleNamespace(Langfuse=_fail_langfuse))

    assert langfuse_tracer.get_langfuse_client() is None
    assert secret not in caplog.text
    assert "[LangFuse] 初始化失败" in caplog.text


# ── langfuse_span: 业务体异常不得被改写 ─────────────────────────────────────────

import pytest


class _FakeSpan:
    def update(self, **_kwargs):
        pass


class _FakeSpanCM:
    """模拟 langfuse v3 start_as_current_span 返回的 async context manager。"""

    def __init__(self, *, fail_enter: bool = False):
        self._fail_enter = fail_enter
        self.exited_with = None

    async def __aenter__(self):
        if self._fail_enter:
            raise RuntimeError("otel down")
        return _FakeSpan()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.exited_with = exc_type
        return False


class _FakeClient:
    def __init__(self, *, fail_enter: bool = False):
        self.cms = []
        self._fail_enter = fail_enter

    def start_as_current_span(self, **_kwargs):
        cm = _FakeSpanCM(fail_enter=self._fail_enter)
        self.cms.append(cm)
        return cm


@pytest.mark.asyncio
async def test_langfuse_span_propagates_body_exception_type(monkeypatch):
    """节点函数抛错时，调用方必须看到原始异常类型。

    bug：旧实现把 ``yield span`` 包在 ``try/except`` 里，except 分支再次
    ``yield None``——body 抛出的异常经 athrow 进入生成器后被捕获并二次
    yield，contextlib 随之抛 ``RuntimeError("generator didn't stop after
    athrow()")``，真实异常类型/消息被抹掉（Langfuse 启用时每个节点错误
    都变成 RuntimeError）。
    """
    monkeypatch.setattr(
        langfuse_tracer, "get_langfuse_client_safe", lambda: _FakeClient()
    )

    with pytest.raises(ValueError, match="node exploded"):
        async with langfuse_tracer.langfuse_span("planner"):
            raise ValueError("node exploded")


@pytest.mark.asyncio
async def test_langfuse_span_creation_failure_degrades_to_none(monkeypatch):
    """span 创建/进入失败仍降级为 yield None，不影响业务体。"""
    client = _FakeClient(fail_enter=True)
    monkeypatch.setattr(
        langfuse_tracer, "get_langfuse_client_safe", lambda: client
    )

    async with langfuse_tracer.langfuse_span("planner") as span:
        assert span is None


@pytest.mark.asyncio
async def test_langfuse_span_disabled_yields_none(monkeypatch):
    monkeypatch.setattr(
        langfuse_tracer, "get_langfuse_client_safe", lambda: None
    )
    async with langfuse_tracer.langfuse_span("planner") as span:
        assert span is None
