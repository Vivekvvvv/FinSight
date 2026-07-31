import asyncio
import json
import logging
from pathlib import Path

import pytest

from backend.api import main


def _configure_minimal_lifespan(monkeypatch):
    class HealthyStore:
        @staticmethod
        def ensure_schema():
            return True

    async def no_graph_runner():
        return None

    monkeypatch.setattr(main, "_validate_production_runtime_config", lambda: None)
    monkeypatch.setattr(main, "_init_default_user_config", lambda: None)
    monkeypatch.setattr(main, "install_rag_observability_hooks", lambda: None)
    monkeypatch.setattr(main, "get_rag_observability_store", lambda: HealthyStore())
    monkeypatch.setattr(main, "aget_graph_runner", no_graph_runner)
    monkeypatch.setattr(main, "flush_langfuse", lambda: None)
    monkeypatch.setattr(main, "shutdown_langfuse", lambda: None)
    for name in (
        "PRICE_ALERT_SCHEDULER_ENABLED",
        "NEWS_ALERT_SCHEDULER_ENABLED",
        "RISK_ALERT_SCHEDULER_ENABLED",
        "HEALTH_PROBE_ENABLED",
        "RAG_OBSERVABILITY_RETENTION_ENABLED",
    ):
        monkeypatch.setenv(name, "false")


@pytest.mark.parametrize(
    ("enabled_name", "interval_name", "expected"),
    [
        ("PRICE_ALERT_SCHEDULER_ENABLED", "PRICE_ALERT_INTERVAL_MINUTES", 15.0),
        ("NEWS_ALERT_SCHEDULER_ENABLED", "NEWS_ALERT_INTERVAL_MINUTES", 30.0),
        ("RISK_ALERT_SCHEDULER_ENABLED", "RISK_ALERT_INTERVAL_MINUTES", 60.0),
        ("HEALTH_PROBE_ENABLED", "HEALTH_PROBE_INTERVAL_MINUTES", 30.0),
        (
            "RAG_OBSERVABILITY_RETENTION_ENABLED",
            "RAG_OBSERVABILITY_RETENTION_INTERVAL_MINUTES",
            360.0,
        ),
    ],
)
def test_lifespan_scheduler_invalid_interval_uses_default(
    monkeypatch, enabled_name, interval_name, expected
):
    from backend.services import scheduler_runner

    captured: list[float] = []

    def capture_scheduler(*_args, interval_minutes, **_kwargs):
        captured.append(interval_minutes)
        return None

    _configure_minimal_lifespan(monkeypatch)
    monkeypatch.setenv(enabled_name, "true")
    monkeypatch.setenv(interval_name, "NaN")
    monkeypatch.setattr(scheduler_runner, "start_price_change_scheduler", capture_scheduler)
    monkeypatch.setattr(scheduler_runner, "start_interval_scheduler", capture_scheduler)

    async def run_lifespan():
        async with main.lifespan(main.app):
            pass

    asyncio.run(run_lifespan())
    assert captured == [expected]


def test_report_index_async_error_log_is_redacted(monkeypatch, caplog):
    class FailingStore:
        @staticmethod
        def upsert_report(**_kwargs):
            raise RuntimeError("private report index detail")

    monkeypatch.setattr(main, "get_report_index_store", lambda: FailingStore())
    with caplog.at_level(logging.ERROR, logger="backend.api.main"):
        main._index_report_async(
            session_id="private:user:thread",
            report={"report_id": "report-1"},
            state=None,
        )

    assert "private report index detail" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_report_index_schedule_error_log_is_redacted(monkeypatch, caplog):
    def fail_running_loop():
        raise RuntimeError("private scheduler detail")

    monkeypatch.setattr(asyncio, "get_running_loop", fail_running_loop)
    with caplog.at_level(logging.ERROR, logger="backend.api.main"):
        main._schedule_report_index(
            session_id="private:user:thread",
            report={"report_id": "report-1"},
            state=None,
        )

    assert "private scheduler detail" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_session_context_update_error_log_is_redacted(monkeypatch, caplog):
    def fail_context(_thread_id):
        raise RuntimeError("private session context detail")

    monkeypatch.setattr(main, "_get_session_context", fail_context)
    with caplog.at_level(logging.ERROR, logger="backend.api.main"):
        main._update_session_context(
            thread_id="private:user:thread",
            original_query="question",
            response_markdown="answer",
        )

    assert "private session context detail" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_orchestrator_initialization_error_log_is_redacted(monkeypatch, caplog):
    def fail_orchestrator():
        raise RuntimeError("private orchestrator detail")

    monkeypatch.setattr(main, "get_global_orchestrator", fail_orchestrator)
    with caplog.at_level(logging.ERROR, logger="backend.api.main"):
        assert main._get_orchestrator_safe() is None

    assert "private orchestrator detail" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_lifespan_rag_initialization_error_log_is_redacted(monkeypatch, caplog):
    def fail_rag_hooks():
        raise RuntimeError("private rag initialization detail")

    async def no_graph_runner():
        return None

    monkeypatch.setattr(main, "_validate_production_runtime_config", lambda: None)
    monkeypatch.setattr(main, "_init_default_user_config", lambda: None)
    monkeypatch.setattr(main, "install_rag_observability_hooks", fail_rag_hooks)
    monkeypatch.setattr(main, "aget_graph_runner", no_graph_runner)
    monkeypatch.setattr(main, "flush_langfuse", lambda: None)
    monkeypatch.setattr(main, "shutdown_langfuse", lambda: None)
    for name in (
        "PRICE_ALERT_SCHEDULER_ENABLED",
        "NEWS_ALERT_SCHEDULER_ENABLED",
        "RISK_ALERT_SCHEDULER_ENABLED",
        "HEALTH_PROBE_ENABLED",
        "RAG_OBSERVABILITY_RETENTION_ENABLED",
    ):
        monkeypatch.setenv(name, "false")

    async def run_lifespan():
        async with main.lifespan(main.app):
            pass

    with caplog.at_level(logging.ERROR, logger="backend.api.main"):
        asyncio.run(run_lifespan())

    assert "private rag initialization detail" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_lifespan_rag_retention_error_log_is_redacted(monkeypatch, caplog):
    from backend.services import scheduler_runner

    class FailingStore:
        @staticmethod
        def ensure_schema():
            return True

        @staticmethod
        def cleanup_retention():
            raise RuntimeError("private rag retention detail")

    async def no_graph_runner():
        return None

    def run_job_now(job, **_kwargs):
        job()
        return None

    monkeypatch.setattr(main, "_validate_production_runtime_config", lambda: None)
    monkeypatch.setattr(main, "_init_default_user_config", lambda: None)
    monkeypatch.setattr(main, "install_rag_observability_hooks", lambda: None)
    monkeypatch.setattr(main, "get_rag_observability_store", lambda: FailingStore())
    monkeypatch.setattr(main, "aget_graph_runner", no_graph_runner)
    monkeypatch.setattr(main, "flush_langfuse", lambda: None)
    monkeypatch.setattr(main, "shutdown_langfuse", lambda: None)
    monkeypatch.setattr(scheduler_runner, "start_interval_scheduler", run_job_now)
    for name in (
        "PRICE_ALERT_SCHEDULER_ENABLED",
        "NEWS_ALERT_SCHEDULER_ENABLED",
        "RISK_ALERT_SCHEDULER_ENABLED",
        "HEALTH_PROBE_ENABLED",
    ):
        monkeypatch.setenv(name, "false")
    monkeypatch.setenv("RAG_OBSERVABILITY_RETENTION_ENABLED", "true")

    async def run_lifespan():
        async with main.lifespan(main.app):
            pass

    with caplog.at_level(logging.ERROR, logger="backend.api.main"):
        asyncio.run(run_lifespan())

    assert "private rag retention detail" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_lifespan_graph_runner_error_log_is_redacted(monkeypatch, caplog):
    class HealthyStore:
        @staticmethod
        def ensure_schema():
            return True

    async def fail_graph_runner():
        raise RuntimeError("private graph runner detail")

    monkeypatch.setattr(main, "_validate_production_runtime_config", lambda: None)
    monkeypatch.setattr(main, "_init_default_user_config", lambda: None)
    monkeypatch.setattr(main, "install_rag_observability_hooks", lambda: None)
    monkeypatch.setattr(main, "get_rag_observability_store", lambda: HealthyStore())
    monkeypatch.setattr(main, "aget_graph_runner", fail_graph_runner)
    monkeypatch.setattr(main, "flush_langfuse", lambda: None)
    monkeypatch.setattr(main, "shutdown_langfuse", lambda: None)
    for name in (
        "PRICE_ALERT_SCHEDULER_ENABLED",
        "NEWS_ALERT_SCHEDULER_ENABLED",
        "RISK_ALERT_SCHEDULER_ENABLED",
        "HEALTH_PROBE_ENABLED",
        "RAG_OBSERVABILITY_RETENTION_ENABLED",
    ):
        monkeypatch.setenv(name, "false")

    async def run_lifespan():
        async with main.lifespan(main.app):
            pass

    with caplog.at_level(logging.ERROR, logger="backend.api.main"):
        asyncio.run(run_lifespan())

    assert "private graph runner detail" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_lifespan_scheduler_shutdown_error_log_is_redacted(monkeypatch, caplog):
    shutdown_calls = []

    class FailingScheduler:
        @staticmethod
        def shutdown(*, wait):
            raise RuntimeError("private scheduler shutdown detail")

    class HealthyScheduler:
        @staticmethod
        def shutdown(*, wait):
            shutdown_calls.append(wait)

    _configure_minimal_lifespan(monkeypatch)
    main._schedulers.append(FailingScheduler())
    main._schedulers.append(HealthyScheduler())

    async def run_lifespan():
        async with main.lifespan(main.app):
            pass

    try:
        with caplog.at_level(logging.ERROR, logger="backend.api.main"):
            asyncio.run(run_lifespan())
    finally:
        main._schedulers.clear()

    assert "private scheduler shutdown detail" not in caplog.text
    assert "RuntimeError" in caplog.text
    assert shutdown_calls == [True]
    assert main._schedulers == []


def test_lifespan_graph_cleanup_error_log_is_redacted(monkeypatch, caplog):
    from backend.graph import checkpointer

    async def fail_checkpointer_reset():
        raise RuntimeError("private graph cleanup detail")

    _configure_minimal_lifespan(monkeypatch)
    monkeypatch.setattr(
        checkpointer,
        "areset_checkpointer_caches",
        fail_checkpointer_reset,
    )

    async def run_lifespan():
        async with main.lifespan(main.app):
            pass

    with caplog.at_level(logging.ERROR, logger="backend.api.main"):
        asyncio.run(run_lifespan())

    assert "private graph cleanup detail" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_default_user_config_bootstrap_uses_atomic_replace(monkeypatch, tmp_path):
    from backend import llm_config

    config_path = tmp_path / "user_config.json"
    replace_calls = []
    original_replace = main.os.replace

    def observed_replace(source, target):
        replace_calls.append((source, target))
        original_replace(source, target)

    monkeypatch.setattr(llm_config, "USER_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_BASE", "https://example.invalid/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "test-model")
    monkeypatch.setattr(main.os, "replace", observed_replace)

    main._init_default_user_config()

    assert len(replace_calls) == 1
    source, target = replace_calls[0]
    assert source != target
    assert str(source).endswith(".tmp")
    assert target == str(config_path)
    assert json.loads(config_path.read_text(encoding="utf-8"))["llm_model"] == "test-model"
    assert not list(tmp_path.glob("*.tmp"))


def test_default_user_config_error_log_and_temp_file_are_redacted(
    monkeypatch, tmp_path, caplog
):
    from backend import llm_config

    config_path = tmp_path / "user_config.json"

    def fail_replace(_source, _target):
        raise OSError("private default config storage detail")

    monkeypatch.setattr(llm_config, "USER_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_BASE", "https://example.invalid/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "test-key")
    monkeypatch.setattr(main.os, "replace", fail_replace)

    with caplog.at_level(logging.WARNING, logger="backend.api.main"):
        main._init_default_user_config()

    assert not config_path.exists()
    assert not list(tmp_path.glob("*.tmp"))
    assert "private default config storage detail" not in caplog.text
    assert "OSError" in caplog.text


def test_chart_detector_import_log_is_type_only():
    source = Path(main.__file__).read_text(encoding="utf-8")

    assert 'Error importing chart detector: {e}' not in source
    assert '"[Init] Error importing chart detector (%s)"' in source


def test_memory_service_initialization_log_is_type_only():
    source = Path(main.__file__).read_text(encoding="utf-8")

    assert 'Error initializing MemoryService: {e}' not in source
    assert '"[Init] Error initializing MemoryService (%s)"' in source


def test_core_tools_import_log_is_type_only():
    source = Path(main.__file__).read_text(encoding="utf-8")

    assert 'Error importing tools: {e2}' not in source
    assert '"[Init] Error importing tools (%s)"' in source
