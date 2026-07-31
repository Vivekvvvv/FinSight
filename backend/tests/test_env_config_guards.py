from __future__ import annotations

import pytest

from backend.utils.env_config import env_float, env_int


@pytest.mark.parametrize("value", ["", "bad", "1.5", "nan"])
def test_env_int_rejects_malformed_values(monkeypatch, value):
    monkeypatch.setenv("TEST_INT_SETTING", value)
    assert env_int("TEST_INT_SETTING", 7, minimum=1) == 7


@pytest.mark.parametrize("value", ["0", "-1", "999"])
def test_env_int_rejects_values_outside_bounds(monkeypatch, value):
    monkeypatch.setenv("TEST_INT_SETTING", value)
    assert env_int("TEST_INT_SETTING", 7, minimum=1, maximum=100) == 7


@pytest.mark.parametrize("value", ["", "bad", "NaN", "Infinity", "-Infinity"])
def test_env_float_rejects_malformed_or_non_finite_values(monkeypatch, value):
    monkeypatch.setenv("TEST_FLOAT_SETTING", value)
    assert env_float("TEST_FLOAT_SETTING", 2.5, minimum=0.1) == 2.5


@pytest.mark.parametrize("value", ["0", "-1", "101"])
def test_env_float_rejects_values_outside_bounds(monkeypatch, value):
    monkeypatch.setenv("TEST_FLOAT_SETTING", value)
    assert env_float("TEST_FLOAT_SETTING", 2.5, minimum=0.1, maximum=100.0) == 2.5


def test_env_numeric_helpers_accept_bounded_values(monkeypatch):
    monkeypatch.setenv("TEST_INT_SETTING", "9")
    monkeypatch.setenv("TEST_FLOAT_SETTING", "1.25")
    assert env_int("TEST_INT_SETTING", 7, minimum=1, maximum=100) == 9
    assert env_float("TEST_FLOAT_SETTING", 2.5, minimum=0.1, maximum=100.0) == 1.25


def test_numeric_env_modules_use_guarded_defaults(monkeypatch):
    import json
    import subprocess
    import sys

    monkeypatch.setenv("DEEPSEARCH_MAX_RESULTS", "bad")
    monkeypatch.setenv("DEEPSEARCH_LLM_TOKEN_TIMEOUT_SECONDS", "NaN")
    monkeypatch.setenv("FINSIGHT_DASHBOARD_NEWS_TIMEOUT", "Infinity")
    monkeypatch.setenv("INSIGHTS_MAX_CONCURRENT_SYMBOLS", "0")
    monkeypatch.setenv("SMTP_PORT", "70000")

    code = """
import json
from backend.agents.deep_search_agent import DeepSearchAgent
from backend.api.dashboard_router import _DASHBOARD_NEWS_FETCH_TIMEOUT_SECONDS
from backend.dashboard.insights_engine import _MAX_CONCURRENT_SYMBOLS
from backend.services.email_service import SMTP_PORT
print(json.dumps([
    DeepSearchAgent.MAX_RESULTS,
    DeepSearchAgent.LLM_TOKEN_TIMEOUT_SECONDS,
    _DASHBOARD_NEWS_FETCH_TIMEOUT_SECONDS,
    _MAX_CONCURRENT_SYMBOLS,
    SMTP_PORT,
]))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout.strip().splitlines()[-1]) == [8, 500.0, 45.0, 3, 587]


def test_tool_modules_survive_invalid_numeric_environment(monkeypatch):
    import json
    import subprocess
    import sys

    monkeypatch.setenv("AUTHORITATIVE_FEED_TIMEOUT", "bad")
    monkeypatch.setenv("MACRO_OFFICIAL_MAX_SOURCES", "0")
    monkeypatch.setenv("WAYBACK_MAX_CHARS", "-1")
    monkeypatch.setenv("EASTMONEY_TIMEOUT", "bad")
    monkeypatch.setenv("JINA_READER_TIMEOUT", "0")
    monkeypatch.setenv("FINSIGHT_RSS_TIMEOUT", "bad")
    monkeypatch.setenv("SEARCH_QUOTA_COOLDOWN_SECONDS", "-1")

    code = """
import importlib
import json
names = [
    "backend.tools.authoritative_feeds",
    "backend.tools.cn_hk_market",
    "backend.tools.jina_reader",
    "backend.tools.macro_official",
    "backend.tools.news",
    "backend.tools.search",
    "backend.tools.wayback",
]
modules = [importlib.import_module(name) for name in names]
print(json.dumps([
    modules[0]._REQUEST_TIMEOUT,
    modules[1]._EASTMONEY_TIMEOUT,
    modules[2]._JINA_TIMEOUT,
    modules[3]._MAX_SOURCES,
    modules[4]._RSS_TIMEOUT,
    modules[5]._SEARCH_QUOTA_COOLDOWN_SECONDS,
    modules[6]._WAYBACK_MAX_CHARS,
]))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(completed.stdout.strip().splitlines()[-1]) == [
        10,
        12,
        30,
        5,
        4,
        1800,
        12000,
    ]


def test_rate_limiter_invalid_environment_uses_defaults(monkeypatch):
    from backend.api.security_config import SimpleRateLimiter

    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "bad")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "bad")
    limiter = SimpleRateLimiter.from_env()

    assert limiter.limit == 120
    assert limiter.window_seconds == 60


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_report_quality_float_environment_rejects_non_finite(monkeypatch, value):
    from backend.report.evidence_policy import _env_float as evidence_env_float
    from backend.report.quality_engine import load_runtime_quality_thresholds

    monkeypatch.setenv("REPORT_QUALITY_MIN_COVERAGE", value)
    monkeypatch.setenv("REPORT_QUALITY_GROUNDING_BLOCK", value)
    monkeypatch.setenv("REPORT_QUALITY_GROUNDING_WARN", value)

    assert evidence_env_float("REPORT_QUALITY_MIN_COVERAGE", 0.8) == 0.8
    thresholds = load_runtime_quality_thresholds()
    assert thresholds.grounding_block == 0.6
    assert thresholds.grounding_warn == 0.75
