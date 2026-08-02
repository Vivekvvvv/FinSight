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
