from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _set_required_production_env(monkeypatch):
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_BASE", "https://llm.test/v1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_MODEL", "test-model")
    monkeypatch.setenv("POSTGRES_DB", "test")
    monkeypatch.setenv("POSTGRES_USER", "test")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test")
    monkeypatch.setenv("JWT_SECRET", "0123456789abcdef0123456789abcdef")


def _compose_smoke_env() -> dict[str, str]:
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
    workflow = workflow_path.read_text(encoding="utf-8")
    job = re.search(
        r"(?ms)^  stage7-e2e-compose:\s*$\n(?P<body>.*?)(?=^  [a-zA-Z0-9_-]+:\s*$|\Z)",
        workflow,
    )
    assert job, "stage7-e2e-compose job is missing"
    env_block = re.search(
        r"(?ms)^    env:\s*$\n(?P<body>.*?)(?=^    [a-zA-Z0-9_-]+:\s*$|\Z)",
        job.group("body"),
    )
    assert env_block, "stage7-e2e-compose env block is missing"
    return {
        key: value.strip().strip('"\'')
        for key, value in re.findall(
            r"(?m)^      ([A-Z][A-Z0-9_]+):\s*(\S.*?)\s*$",
            env_block.group("body"),
        )
    }


def test_compose_smoke_env_passes_production_runtime_validation(monkeypatch):
    from backend.api.security_config import validate_production_runtime_config

    monkeypatch.setenv("DEV_MODE", "0")
    for key, value in _compose_smoke_env().items():
        monkeypatch.setenv(key, value)

    validate_production_runtime_config()


def test_security_gate_rejects_missing_api_key_when_enabled(monkeypatch):
    from backend.api import main

    monkeypatch.setenv("DEV_MODE", "0")
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("API_AUTH_KEYS", "release-key-1")
    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))

    with TestClient(main.app) as client:
        response = client.get("/api/user/profile", params={"user_id": "auth-check"})

    assert response.status_code == 401
    assert response.json().get("detail") == "Unauthorized"


def test_security_gate_returns_503_when_auth_enabled_without_keys(monkeypatch):
    from backend.api import main

    monkeypatch.setenv("DEV_MODE", "0")
    _set_required_production_env(monkeypatch)
    monkeypatch.delenv("API_AUTH_KEYS", raising=False)
    monkeypatch.delenv("API_AUTH_KEY", raising=False)
    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))

    with pytest.raises(SystemExit) as exc_info:
        main._validate_production_runtime_config()

    assert "API_AUTH_KEYS" in str(exc_info.value)


def test_security_gate_rejects_missing_llm_model(monkeypatch):
    from backend.api import main

    monkeypatch.setenv("DEV_MODE", "0")
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("API_AUTH_KEYS", "release-key-1")
    monkeypatch.delenv("OPENAI_COMPATIBLE_MODEL", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        main._validate_production_runtime_config()

    assert "OPENAI_COMPATIBLE_MODEL" in str(exc_info.value)


@pytest.mark.parametrize("api_keys", ["x", "release-key-1,REPLACE_ME_INTERNAL_API_KEY"])
def test_security_gate_rejects_weak_or_placeholder_api_keys(monkeypatch, api_keys):
    from backend.api import main

    monkeypatch.setenv("DEV_MODE", "0")
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("API_AUTH_KEYS", api_keys)

    with pytest.raises(SystemExit) as exc_info:
        main._validate_production_runtime_config()

    assert "Invalid API_AUTH_KEYS" in str(exc_info.value)


@pytest.mark.parametrize("jwt_secret", ["x", "REPLACE_ME_LONG_RANDOM_SECRET"])
def test_security_gate_rejects_weak_or_placeholder_jwt_secret(monkeypatch, jwt_secret):
    from backend.api import main

    monkeypatch.setenv("DEV_MODE", "0")
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("API_AUTH_KEYS", "release-key-1")
    monkeypatch.setenv("JWT_SECRET", jwt_secret)

    with pytest.raises(SystemExit) as exc_info:
        main._validate_production_runtime_config()

    assert "Invalid JWT_SECRET" in str(exc_info.value)


def test_security_gate_rejects_repository_postgres_password_placeholder(monkeypatch):
    from backend.api import main

    monkeypatch.setenv("DEV_MODE", "0")
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("API_AUTH_KEYS", "release-key-1")
    monkeypatch.setenv("POSTGRES_PASSWORD", "REPLACE_ME_STRONG_PASSWORD")

    with pytest.raises(SystemExit) as exc_info:
        main._validate_production_runtime_config()

    assert "Invalid POSTGRES_PASSWORD" in str(exc_info.value)


def test_security_gate_rejects_repository_llm_key_placeholder(monkeypatch):
    from backend.api import main

    monkeypatch.setenv("DEV_MODE", "0")
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("API_AUTH_KEYS", "release-key-1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-REPLACE_ME")

    with pytest.raises(SystemExit) as exc_info:
        main._validate_production_runtime_config()

    assert "Invalid OPENAI_COMPATIBLE_API_KEY" in str(exc_info.value)


def test_security_gate_rejects_repository_llm_base_placeholder(monkeypatch):
    from backend.api import main

    monkeypatch.setenv("DEV_MODE", "0")
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("API_AUTH_KEYS", "release-key-1")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_BASE", "https://example.invalid/v1")

    with pytest.raises(SystemExit) as exc_info:
        main._validate_production_runtime_config()

    assert "Invalid OPENAI_COMPATIBLE_API_BASE" in str(exc_info.value)


def test_security_gate_allowlisted_path_bypasses_auth(monkeypatch):
    from backend.api import main

    monkeypatch.setenv("DEV_MODE", "0")
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("API_AUTH_KEYS", "release-key-1")
    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))

    with TestClient(main.app) as client:
        response = client.get("/health")

    assert response.status_code == 200


def test_security_gate_dashboard_requires_auth_by_default(monkeypatch):
    from backend.api import main

    monkeypatch.setenv("DEV_MODE", "0")
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("API_AUTH_KEYS", "release-key-1")
    monkeypatch.delenv("API_PUBLIC_PATHS", raising=False)
    monkeypatch.setattr(main, "_rate_limiter", main.SimpleRateLimiter(limit_per_window=100, window_seconds=60, enabled=False))

    with TestClient(main.app) as client:
        response = client.get("/api/dashboard", params={"symbol": "AAPL"})

    assert response.status_code == 401
    assert response.json().get("detail") == "Unauthorized"


def test_allowlisted_paths_can_be_configured_via_env(monkeypatch):
    from backend.api import main

    monkeypatch.delenv("API_PUBLIC_PATHS", raising=False)
    assert main._is_allowlisted_path("/api/dashboard") is False

    monkeypatch.setenv("API_PUBLIC_PATHS", "/health,/api/dashboard")
    assert main._is_allowlisted_path("/api/dashboard") is True
    assert main._is_allowlisted_path("/api/dashboard/sub") is False


def test_security_gate_rate_limit_blocks_second_request(monkeypatch):
    from backend.api import main

    monkeypatch.setenv("DEV_MODE", "0")
    _set_required_production_env(monkeypatch)
    monkeypatch.setenv("API_AUTH_KEYS", "release-key-1")
    limiter = main.SimpleRateLimiter(limit_per_window=1, window_seconds=60, enabled=True)
    monkeypatch.setattr(main, "_rate_limiter", limiter)

    with TestClient(main.app) as client:
        first = client.get("/api/user/profile", headers={"x-api-key": "release-key-1"})
        second = client.get("/api/user/profile", headers={"x-api-key": "release-key-1"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json().get("detail") == "Rate limit exceeded"
    assert second.headers.get("Retry-After") is not None
    assert "release-key-1" not in limiter._buckets
    assert list(limiter._buckets) == [main.api_key_fingerprint("release-key-1")]


def test_research_qa_internal_error_is_redacted(monkeypatch, caplog):
    from backend.api.research_router import router
    from backend import llm_config

    class FailingLlm:
        async def ainvoke(self, _prompt):
            raise RuntimeError("private LLM provider detail")

    monkeypatch.setattr(llm_config, "create_llm", lambda **_kwargs: FailingLlm())
    caplog.set_level(logging.ERROR, logger="backend.api.research_router")
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post(
            "/api/research/qa",
            json={"question": "analyze risk", "use_cn_data": False},
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert "private LLM provider detail" not in response.text
    assert "private LLM provider detail" not in caplog.text
    assert "智能问答失败" in caplog.text


def test_research_qa_uses_configured_llm_factory(monkeypatch):
    from backend.api.research_router import router
    from backend import llm_config

    captured = {}

    class Response:
        content = "configured model answer"

    class WorkingLlm:
        async def ainvoke(self, _prompt):
            return Response()

    def fake_create_llm(**kwargs):
        captured.update(kwargs)
        return WorkingLlm()

    monkeypatch.setattr(llm_config, "create_llm", fake_create_llm)
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post(
            "/api/research/qa",
            json={"question": "analyze risk", "use_cn_data": False},
        )

    assert response.status_code == 200
    assert response.json()["answer"] == "configured model answer"
    assert captured == {"temperature": 0.3, "max_tokens": 1024}


def test_research_report_uses_configured_llm_factory(monkeypatch):
    from backend.api.research_router import router
    from backend import llm_config, tools

    captured = {}

    class Response:
        content = "configured report content"

    class WorkingLlm:
        async def ainvoke(self, _prompt):
            return Response()

    def fake_create_llm(**kwargs):
        captured.update(kwargs)
        return WorkingLlm()

    monkeypatch.setattr(llm_config, "create_llm", fake_create_llm)
    monkeypatch.setattr(tools, "get_company_info", lambda _ticker: {})
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post(
            "/api/research/report/generate",
            json={
                "ticker": "AAPL",
                "report_type": "technical",
                "include_news": False,
                "include_technical": False,
            },
        )

    assert response.status_code == 200
    assert response.json()["content"] == "configured report content"
    assert captured == {"temperature": 0.3, "max_tokens": 4096, "model": "gpt-4o"}


def test_research_report_fallback_redacts_llm_error(monkeypatch, caplog):
    from backend.api.research_router import router
    from backend import llm_config, tools

    class FailingLlm:
        async def ainvoke(self, _prompt):
            raise RuntimeError("private report provider detail")

    monkeypatch.setattr(llm_config, "create_llm", lambda **_kwargs: FailingLlm())
    monkeypatch.setattr(tools, "get_company_info", lambda _ticker: {})
    caplog.set_level(logging.ERROR, logger="backend.services.report_generator")
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post(
            "/api/research/report/generate",
            json={
                "ticker": "AAPL",
                "report_type": "technical",
                "include_news": False,
                "include_technical": False,
            },
        )

    assert response.status_code == 200
    assert "生成报告时遇到错误，请稍后重试。" in response.json()["content"]
    assert "private report provider detail" not in response.text
    assert "private report provider detail" not in caplog.text
    assert "[ResearchReport] LLM调用失败" in caplog.text


def test_research_report_internal_error_is_redacted(monkeypatch, caplog):
    from backend.api.research_router import router
    from backend.services import report_generator

    def fail_get_report_generator():
        raise RuntimeError("private report initialization detail")

    monkeypatch.setattr(report_generator, "get_report_generator", fail_get_report_generator)
    caplog.set_level(logging.ERROR, logger="backend.api.research_router")
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post(
            "/api/research/report/generate",
            json={
                "ticker": "AAPL",
                "report_type": "technical",
                "include_news": False,
                "include_technical": False,
            },
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert "private report initialization detail" not in response.text
    assert "private report initialization detail" not in caplog.text
    assert "生成报告失败" in caplog.text


def test_financials_analysis_uses_configured_llm_factory(monkeypatch):
    from backend.api.research_router import router
    from backend import llm_config, tools

    captured = {}

    class Response:
        content = '{"overall_rating":{"score":8}}'

    class WorkingLlm:
        async def ainvoke(self, _prompt):
            return Response()

    def fake_create_llm(**kwargs):
        captured.update(kwargs)
        return WorkingLlm()

    monkeypatch.setattr(llm_config, "create_llm", fake_create_llm)
    monkeypatch.setattr(tools, "get_financial_statements", lambda _ticker: {"revenue": 100})
    monkeypatch.setattr(tools, "get_company_info", lambda _ticker: {"name": "Apple"})
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post(
            "/api/research/financials/analyze",
            json={"ticker": "AAPL"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["overall_rating"]["score"] == 8
    assert captured == {"temperature": 0.1, "max_tokens": 2048}


def test_financials_analysis_fallback_redacts_llm_error(monkeypatch, caplog):
    from backend.api.research_router import router
    from backend import llm_config, tools

    class FailingLlm:
        async def ainvoke(self, _prompt):
            raise RuntimeError("private financials provider detail")

    monkeypatch.setattr(llm_config, "create_llm", lambda **_kwargs: FailingLlm())
    monkeypatch.setattr(tools, "get_financial_statements", lambda _ticker: {"revenue": 100})
    monkeypatch.setattr(tools, "get_company_info", lambda _ticker: {"name": "Apple"})
    caplog.set_level(logging.ERROR, logger="backend.services.financials_analyzer")
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post(
            "/api/research/financials/analyze",
            json={"ticker": "AAPL"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert response.json()["error"] == "Internal server error"
    assert "private financials provider detail" not in response.text
    assert "private financials provider detail" not in caplog.text
    assert "[FinancialsAnalyzer] 分析失败" in caplog.text


def test_financials_analysis_json_parse_fallback_redacts_error(monkeypatch, caplog):
    from backend.api.research_router import router
    from backend import llm_config, tools

    class NonJsonLlm:
        async def ainvoke(self, _prompt):
            class Response:
                content = "not-json-private-fragment"

            return Response()

    monkeypatch.setattr(llm_config, "create_llm", lambda **_kwargs: NonJsonLlm())
    monkeypatch.setattr(tools, "get_financial_statements", lambda _ticker: {"revenue": 100})
    monkeypatch.setattr(tools, "get_company_info", lambda _ticker: {"name": "Apple"})
    caplog.set_level(logging.WARNING, logger="backend.services.financials_analyzer")
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post(
            "/api/research/financials/analyze",
            json={"ticker": "AAPL"},
        )

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "error"
    assert body["error"] == "Internal server error"
    assert "not-json-private-fragment" not in response.text
    assert "解析LLM响应失败" not in response.text
    assert "not-json-private-fragment" not in caplog.text
    assert "[FinancialsAnalyzer] LLM返回非JSON，fallback" in caplog.text


def test_financials_analysis_non_finite_json_falls_back(monkeypatch, caplog):
    from backend.api.research_router import router
    from backend import llm_config, tools

    class NonFiniteJsonLlm:
        async def ainvoke(self, _prompt):
            class Response:
                content = '{"overall_rating":{"score":NaN}}'

            return Response()

    monkeypatch.setattr(llm_config, "create_llm", lambda **_kwargs: NonFiniteJsonLlm())
    monkeypatch.setattr(tools, "get_financial_statements", lambda _ticker: {"revenue": 100})
    monkeypatch.setattr(tools, "get_company_info", lambda _ticker: {"name": "Apple"})
    caplog.set_level(logging.ERROR, logger="backend.services.financials_analyzer")
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post(
            "/api/research/financials/analyze",
            json={"ticker": "AAPL"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert response.json()["error"] == "Internal server error"
    assert "NaN" not in response.text
    assert "[FinancialsAnalyzer] 分析失败" in caplog.text


def test_financials_analysis_internal_error_is_redacted(monkeypatch, caplog):
    from backend.api.research_router import router
    from backend import tools
    from backend.services import financials_analyzer

    async def fail_analyze_financials(**_kwargs):
        raise RuntimeError("private financials service detail")

    monkeypatch.setattr(financials_analyzer, "analyze_financials", fail_analyze_financials)
    monkeypatch.setattr(tools, "get_financial_statements", lambda _ticker: {"revenue": 100})
    monkeypatch.setattr(tools, "get_company_info", lambda _ticker: {"name": "Apple"})
    caplog.set_level(logging.ERROR, logger="backend.api.research_router")
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post(
            "/api/research/financials/analyze",
            json={"ticker": "AAPL"},
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert "private financials service detail" not in response.text
    assert "private financials service detail" not in caplog.text
    assert "财报分析失败" in caplog.text


def test_financials_fetch_warning_redacts_exception_text(monkeypatch, caplog):
    from backend.api.research_router import router
    from backend import tools

    def fail_get_financial_statements(_ticker):
        raise RuntimeError("private financials fetch detail")

    monkeypatch.setattr(tools, "get_financial_statements", fail_get_financial_statements)
    monkeypatch.setattr(tools, "get_company_info", lambda _ticker: {"name": "Apple"})
    caplog.set_level(logging.WARNING, logger="backend.api.research_router")
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post(
            "/api/research/financials/analyze",
            json={"ticker": "AAPL"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "无法获取该股票财报数据，请确认代码正确"
    assert "private financials fetch detail" not in caplog.text
    assert "获取财报失败" in caplog.text


def test_news_sentiment_uses_configured_llm_factory(monkeypatch):
    from backend.api.research_router import router
    from backend import llm_config

    captured = {}

    class Response:
        content = (
            '[{"sentiment":"positive","sentiment_cn":"利好",'
            '"confidence":0.9,"key_event":"earnings beat","impact_level":"high"}]'
        )

    class WorkingLlm:
        async def ainvoke(self, _prompt):
            return Response()

    def fake_create_llm(**kwargs):
        captured.update(kwargs)
        return WorkingLlm()

    monkeypatch.setattr(llm_config, "create_llm", fake_create_llm)
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post(
            "/api/research/news/sentiment",
            json={
                "ticker": "AAPL",
                "news": [{"title": "Quarterly earnings beat expectations"}],
            },
        )

    assert response.status_code == 200
    assert response.json()["news"][0]["sentiment"] == "positive"
    assert response.json()["aggregate"]["positive"] == 1
    assert captured == {"temperature": 0.0, "max_tokens": 2048}


def test_news_sentiment_fallback_redacts_llm_error(monkeypatch, caplog):
    from backend.api.research_router import router
    from backend import llm_config

    class FailingLlm:
        async def ainvoke(self, _prompt):
            raise RuntimeError("private sentiment provider detail")

    monkeypatch.setattr(llm_config, "create_llm", lambda **_kwargs: FailingLlm())
    caplog.set_level(logging.ERROR, logger="backend.services.news_sentiment")
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post(
            "/api/research/news/sentiment",
            json={
                "ticker": "AAPL",
                "news": [{"title": "Quarterly earnings beat expectations"}],
            },
        )

    assert response.status_code == 200
    assert response.json()["news"][0]["sentiment"] == "neutral"
    assert "private sentiment provider detail" not in response.text
    assert "private sentiment provider detail" not in caplog.text
    assert "[NewsSentiment] 分析失败" in caplog.text


def test_news_sentiment_json_parse_fallback_redacts_error(monkeypatch, caplog):
    from backend.api.research_router import router
    from backend import llm_config

    class NonJsonLlm:
        async def ainvoke(self, _prompt):
            class Response:
                content = "not-json-private-sentiment-fragment"

            return Response()

    monkeypatch.setattr(llm_config, "create_llm", lambda **_kwargs: NonJsonLlm())
    caplog.set_level(logging.WARNING, logger="backend.services.news_sentiment")
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post(
            "/api/research/news/sentiment",
            json={
                "ticker": "AAPL",
                "news": [{"title": "Quarterly earnings beat expectations"}],
            },
        )

    assert response.status_code == 200
    assert response.json()["news"][0]["sentiment"] == "neutral"
    assert "not-json-private-sentiment-fragment" not in response.text
    assert "not-json-private-sentiment-fragment" not in caplog.text
    assert "[NewsSentiment] LLM返回非JSON" in caplog.text


def test_news_sentiment_non_finite_json_falls_back(monkeypatch, caplog):
    from backend.api.research_router import router
    from backend import llm_config

    class NonFiniteJsonLlm:
        async def ainvoke(self, _prompt):
            class Response:
                content = (
                    '[{"sentiment":"positive","sentiment_cn":"positive",'
                    '"confidence":NaN,"key_event":"earnings beat",'
                    '"impact_level":"high"}]'
                )

            return Response()

    monkeypatch.setattr(llm_config, "create_llm", lambda **_kwargs: NonFiniteJsonLlm())
    caplog.set_level(logging.ERROR, logger="backend.services.news_sentiment")
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post(
            "/api/research/news/sentiment",
            json={
                "ticker": "AAPL",
                "news": [{"title": "Quarterly earnings beat expectations"}],
            },
        )

    assert response.status_code == 200
    assert response.json()["news"][0]["sentiment"] == "neutral"
    assert "NaN" not in response.text
    assert "[NewsSentiment] 分析失败" in caplog.text


def test_news_sentiment_internal_error_is_redacted(monkeypatch, caplog):
    from backend.api.research_router import router
    from backend.services import news_sentiment

    async def fail_analyze_news_sentiment(*_args, **_kwargs):
        raise RuntimeError("private sentiment service detail")

    monkeypatch.setattr(news_sentiment, "analyze_news_sentiment", fail_analyze_news_sentiment)
    caplog.set_level(logging.ERROR, logger="backend.api.research_router")
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.post(
            "/api/research/news/sentiment",
            json={
                "ticker": "AAPL",
                "news": [{"title": "Quarterly earnings beat expectations"}],
            },
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert "private sentiment service detail" not in response.text
    assert "private sentiment service detail" not in caplog.text
    assert "新闻情绪分析失败" in caplog.text
