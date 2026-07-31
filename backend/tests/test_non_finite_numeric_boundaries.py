from __future__ import annotations

import asyncio
import math
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


NON_FINITE = [float("nan"), float("inf"), float("-inf")]


@pytest.mark.parametrize("value", NON_FINITE)
def test_agent_adapter_rejects_non_finite_confidence(value):
    from backend.graph.adapters.agent_adapter import _normalize_agent_output

    output = _normalize_agent_output(
        step_name="news_agent",
        output={"summary": "ok", "confidence": value},
        query="q",
        ticker="AAPL",
    )

    assert output["confidence"] == 0.3


@pytest.mark.parametrize("value", NON_FINITE)
def test_report_validator_repairs_non_finite_numeric_fields(value):
    from backend.report.validator import ReportValidator

    report = ReportValidator.validate_and_fix(
        {
            "confidence_score": value,
            "citations": [
                {
                    "title": "source",
                    "confidence": value,
                    "freshness_hours": value,
                }
            ],
            "sections": [{"title": "section", "confidence": value}],
        },
        as_dict=True,
    )

    assert report["confidence_score"] == 0.5
    assert report["citations"][0]["confidence"] == 0.7
    assert report["citations"][0]["freshness_hours"] == 24.0
    assert report["sections"][0]["confidence"] is None


@pytest.mark.parametrize(
    ("env_name", "default"),
    [
        ("LANGGRAPH_TOOL_TIMEOUT_SECONDS", 18.0),
        ("LANGGRAPH_AGENT_STEP_TIMEOUT_SECONDS", 120.0),
    ],
)
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_executor_non_finite_timeout_uses_default(monkeypatch, env_name, default, value):
    from backend.graph.executor import _env_float

    monkeypatch.setenv(env_name, value)
    assert _env_float(env_name, default) == default


@pytest.mark.parametrize("value", NON_FINITE)
def test_executor_ignores_non_finite_agent_signals(value):
    from backend.graph.executor import execute_plan

    calls = {"deep": 0}

    async def low_cost(_inputs):
        return {"confidence": value, "evidence_quality": {"overall_score": value}}

    async def deep(_inputs):
        calls["deep"] += 1
        return {"summary": "deep"}

    plan = {
        "steps": [
            {"id": "low", "kind": "agent", "name": "low", "inputs": {}},
            {
                "id": "deep",
                "kind": "agent",
                "name": "deep",
                "optional": True,
                "inputs": {
                    "__escalation_stage": "high_cost",
                    "__run_if_min_confidence": 0.8,
                },
            },
        ]
    }

    artifacts, _events = asyncio.run(
        execute_plan(plan, agent_invokers={"low": low_cost, "deep": deep}, dry_run=False)
    )

    assert calls["deep"] == 1
    assert artifacts["signals"] == {
        "max_confidence": 0.0,
        "latest_confidence": None,
        "max_evidence_quality": 0.0,
        "latest_evidence_quality": None,
    }


@pytest.mark.parametrize("value", NON_FINITE)
def test_executor_non_finite_escalation_threshold_uses_default(value):
    from backend.graph.executor import execute_plan

    calls = {"deep": 0}

    async def low_cost(_inputs):
        return {"confidence": 0.8}

    async def deep(_inputs):
        calls["deep"] += 1
        return {"summary": "deep"}

    plan = {
        "steps": [
            {"id": "low", "kind": "agent", "name": "low", "inputs": {}},
            {
                "id": "deep",
                "kind": "agent",
                "name": "deep",
                "optional": True,
                "inputs": {
                    "__escalation_stage": "high_cost",
                    "__run_if_min_confidence": value,
                },
            },
        ]
    }

    artifacts, _events = asyncio.run(
        execute_plan(plan, agent_invokers={"low": low_cost, "deep": deep}, dry_run=False)
    )

    assert calls["deep"] == 0
    assert artifacts["step_results"]["deep"]["output"]["min_confidence"] == 0.72


@pytest.mark.parametrize("value", NON_FINITE)
def test_policy_gate_rejects_non_finite_weights_and_scores(value):
    from backend.graph.nodes.policy_gate import _apply_persona_weights

    weighted = _apply_persona_weights(
        {"selected": ["a_agent", "b_agent"], "scores": {"a_agent": 1.0, "b_agent": value}},
        {"agent_weights": {"a": value, "b": 1.0}},
    )

    assert weighted["scores"] == {"a_agent": 1.0, "b_agent": 0.0}
    assert all(math.isfinite(score) for score in weighted["scores"].values())


@pytest.mark.parametrize("value", NON_FINITE)
def test_policy_gate_rejects_non_finite_boolean_and_budget_inputs(value):
    from backend.graph.nodes.policy_gate import _is_truthy, policy_gate

    assert _is_truthy(value) is False
    output = policy_gate(
        {
                "output_mode": "brief",
            "ui_context": {"budget_override": value},
            "subject": {"subject_type": "company"},
        }
    )
    assert output["policy"]["budget"]["max_rounds"] == 3


@pytest.mark.parametrize("value", NON_FINITE)
def test_macro_agent_rejects_non_finite_quality_confidence(value):
    from backend.agents.macro_agent import MacroAgent

    agent = MacroAgent(None, None, None)
    output = agent._format_output(
        "summary",
        {"status": "success", "evidence_quality": {"overall_score": value}},
    )

    assert output.confidence == 0.6


@pytest.mark.parametrize("value", NON_FINITE)
def test_deep_search_rejects_non_finite_evidence_quality(value):
    from backend.agents.deep_search_agent import DeepSearchAgent

    agent = DeepSearchAgent(None, MagicMock(), MagicMock())
    output = agent._format_output(
        "summary",
        [{"title": "doc", "content": "x" * 500, "source": "web"}],
        evidence_quality={"overall_score": value, "source_diversity": value},
    )
    metadata = output.evidence[0].meta["evidence_quality"]

    assert metadata["overall_score"] == 0.0
    assert metadata["source_diversity"] == 0


@pytest.mark.parametrize("value", NON_FINITE)
def test_deep_search_degraded_pdf_confidence_is_finite(monkeypatch, value):
    from backend.agents.deep_search_agent import DeepSearchAgent

    agent = DeepSearchAgent(None, MagicMock(), MagicMock())
    monkeypatch.setattr(
        agent,
        "_fetch_document",
        lambda _item: {
            "title": "PDF",
            "snippet": "fallback",
            "content": "",
            "is_pdf": True,
            "confidence": value,
        },
    )

    documents = agent._fetch_documents([{"title": "PDF", "snippet": "fallback"}])

    assert documents[0]["confidence"] == 0.45


@pytest.mark.parametrize("value", NON_FINITE)
def test_rebalance_ignores_non_finite_positions_and_prices(value):
    from backend.services.rebalance_engine import RebalanceContext, RebalanceEngine, _get_price

    assert _get_price("AAPL", {"AAPL": value}) == 0.0
    context = RebalanceContext(
        session_id="test",
        portfolio=[
            {"ticker": "AAPL", "shares": value},
            {"ticker": "MSFT", "shares": 2},
        ],
        live_prices={"AAPL": 100.0, "MSFT": 50.0},
    )

    diagnosis = RebalanceEngine()._diagnose_portfolio(context)

    assert diagnosis.position_values == {"MSFT": 100.0}
    assert math.isfinite(diagnosis.total_value)


def _backtest_series(days: int = 60) -> list[dict[str, object]]:
    start = datetime(2026, 1, 1)
    return [
        {"time": (start + timedelta(days=index)).date().isoformat(), "close": 100.0 + index}
        for index in range(days)
    ]


@pytest.mark.parametrize("field", ["fee_bps", "slippage_bps", "initial_cash"])
@pytest.mark.parametrize("value", NON_FINITE)
def test_backtest_rejects_non_finite_numeric_inputs(monkeypatch, field, value):
    from backend.services import backtest_engine as module

    monkeypatch.setattr(
        module,
        "get_stock_historical_data",
        lambda *_args, **_kwargs: {"kline_data": _backtest_series(), "source": "test"},
    )
    kwargs = {"ticker": "AAPL", "strategy": "ma_cross", field: value}

    result = module.BacktestEngine().run(**kwargs)

    assert result == {"success": False, "error": "invalid_numeric_input"}


@pytest.mark.parametrize("value", NON_FINITE)
def test_backtest_rejects_non_finite_strategy_signals(monkeypatch, value):
    from backend.services import backtest_engine as module

    series = _backtest_series()
    monkeypatch.setattr(
        module,
        "get_stock_historical_data",
        lambda *_args, **_kwargs: {"kline_data": series, "source": "test"},
    )
    monkeypatch.setattr(
        module,
        "build_strategy_signals",
        lambda *_args, **_kwargs: {"name": "test", "signals": [value] * len(series)},
    )

    result = module.BacktestEngine().run(ticker="AAPL", strategy="ma_cross")

    assert result == {"success": False, "error": "invalid_strategy_signals"}


@pytest.mark.parametrize(
    ("mode", "env_name", "expected"),
    [
        ("brief", "LANGGRAPH_EXECUTION_TIMEOUT_SECONDS", 500.0),
        ("investment_report", "LANGGRAPH_EXECUTION_TIMEOUT_REPORT_SECONDS", 900.0),
    ],
)
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_execution_service_non_finite_timeout_uses_default(monkeypatch, mode, env_name, expected, value):
    from backend.services.execution_service import _execution_timeout_seconds

    monkeypatch.setenv(env_name, value)

    assert _execution_timeout_seconds(mode) == expected


@pytest.mark.parametrize(
    ("env_name", "value", "field", "expected"),
    [
        ("LANGGRAPH_BUDGET_LATENCY_PER_ROUND_MS", "bad", "latency_budget_ms", 2800),
        ("LANGGRAPH_BUDGET_LATENCY_PER_ROUND_MS", "0", "latency_budget_ms", 2800),
        ("LANGGRAPH_BUDGET_LATENCY_PER_ROUND_MS", "-1", "latency_budget_ms", 2800),
        ("LANGGRAPH_BUDGET_COST_PER_TOOL_UNIT", "bad", "cost_budget_units", 6.0),
        ("LANGGRAPH_BUDGET_COST_PER_TOOL_UNIT", "NaN", "cost_budget_units", 6.0),
        ("LANGGRAPH_BUDGET_COST_PER_TOOL_UNIT", "Infinity", "cost_budget_units", 6.0),
        ("LANGGRAPH_BUDGET_COST_PER_TOOL_UNIT", "-1", "cost_budget_units", 6.0),
    ],
)
def test_planner_invalid_budget_environment_uses_default(monkeypatch, env_name, value, field, expected):
    from backend.graph.nodes.planner import _build_budget_assertions

    monkeypatch.setenv(env_name, value)
    result = _build_budget_assertions([], {"max_rounds": 2, "max_tools": 4})

    assert result[field] == expected


@pytest.mark.parametrize("value", ["bad", "NaN", "Infinity", "-Infinity", "-1", "2"])
def test_planner_invalid_escalation_threshold_uses_default(monkeypatch, value):
    from backend.graph.nodes.planner import _enforce_policy

    monkeypatch.setenv("LANGGRAPH_ESCALATION_MIN_CONFIDENCE", value)
    state = {
        "query": "AAPL report",
        "output_mode": "investment_report",
        "subject": {"subject_type": "company", "tickers": ["AAPL"]},
        "policy": {
            "budget": {"max_rounds": 3, "max_tools": 4},
            "allowed_agents": ["macro_agent"],
            "allowed_tools": [],
        },
    }
    plan, _assertions = _enforce_policy(
        {
            "summary": "test",
            "steps": [
                {"id": "macro", "kind": "agent", "name": "macro_agent", "inputs": {}}
            ],
        },
        state,
    )
    macro = next(step for step in plan["steps"] if step.get("name") == "macro_agent")

    assert macro["inputs"]["__run_if_min_confidence"] == 0.72


@pytest.mark.parametrize("value", NON_FINITE)
def test_report_builder_agent_status_rejects_non_finite_confidence(value):
    from backend.graph.report_builder import _agent_status_from_steps

    status = _agent_status_from_steps(
        allowed_agents=["news_agent"],
        plan_steps=[{"id": "news", "kind": "agent", "name": "news_agent"}],
        step_results={"news": {"output": {"confidence": value}}},
        errors=[],
    )

    assert status["news_agent"]["confidence"] == 0.6


@pytest.mark.parametrize("value", NON_FINITE)
def test_report_builder_agent_summary_rejects_non_finite_confidence(value):
    from backend.graph.report_builder import _agent_summaries_from_steps

    summaries = _agent_summaries_from_steps(
        allowed_agents=["news_agent"],
        plan_steps=[{"id": "news", "kind": "agent", "name": "news_agent"}],
        step_results={"news": {"output": {"summary": "ok", "confidence": value}}},
        errors=[],
    )

    assert summaries[0]["confidence"] == 0.6


@pytest.mark.parametrize("value", NON_FINITE)
def test_report_builder_core_viewpoint_rejects_non_finite_confidence(value):
    from backend.graph.report_builder import _build_core_viewpoints

    viewpoints = _build_core_viewpoints(
        [{"status": "success", "agent_name": "news_agent", "summary": "ok", "confidence": value}]
    )

    assert viewpoints[0]["confidence"] == 0.0


@pytest.mark.parametrize("value", NON_FINITE)
def test_report_payload_aggregate_rejects_non_finite_agent_confidence(value):
    from backend.graph.report_builder import build_report_payload

    report = build_report_payload(
        state={
            "output_mode": "investment_report",
            "subject": {"subject_type": "company", "tickers": ["AAPL"]},
            "policy": {"allowed_agents": ["news_agent"]},
            "plan_ir": {
                "steps": [{"id": "news", "kind": "agent", "name": "news_agent"}]
            },
            "artifacts": {
                "draft_markdown": "## AAPL\n\nSummary",
                "evidence_pool": [],
                "step_results": {
                    "news": {"output": {"summary": "news", "confidence": value}}
                },
                "errors": [],
                "render_vars": {"investment_summary": "summary"},
            },
            "trace": {},
        },
        query="AAPL summary",
        thread_id="finite-confidence",
    )

    assert report is not None
    assert report["confidence_score"] == 0.6
    assert math.isfinite(report["confidence_score"])


@pytest.mark.parametrize("value", NON_FINITE)
def test_execute_plan_evidence_rejects_non_finite_agent_confidence(monkeypatch, value):
    import importlib

    module = importlib.import_module("backend.graph.nodes.execute_plan_stub")

    async def fake_execute_plan(*_args, **_kwargs):
        return (
            {
                "step_results": {
                    "news": {
                        "output": {
                            "summary": "summary",
                            "confidence": value,
                            "evidence": [{"title": "item", "text": "detail", "confidence": value}],
                        }
                    }
                }
            },
            [],
        )

    monkeypatch.setattr(module, "execute_plan", fake_execute_plan)
    output = asyncio.run(
        module.execute_plan_stub(
            {
                "query": "",
                "trace": {},
                "subject": {},
                "plan_ir": {
                    "steps": [{"id": "news", "kind": "agent", "name": "news_agent"}]
                },
            }
        )
    )
    confidences = [item["confidence"] for item in output["artifacts"]["evidence_pool"]]

    assert confidences == [0.6, 0.6]
    assert all(math.isfinite(confidence) for confidence in confidences)


@pytest.mark.parametrize(
    ("confidence", "source_reliability"),
    [(float("inf"), 0.9), (0.9, float("inf")), (float("nan"), 0.9)],
)
def test_rag_ttl_rejects_non_finite_quality_signals(confidence, source_reliability):
    from backend.graph.nodes.execute_plan_stub import _ttl_hours_for_evidence

    ttl = _ttl_hours_for_evidence(
        subject_type="web_page",
        evidence_type="other",
        source="other",
        confidence=confidence,
        source_reliability=source_reliability,
    )

    assert ttl == 12


@pytest.mark.parametrize("value", NON_FINITE)
def test_news_agent_format_rejects_non_finite_source_reliability(value):
    from backend.agents.news_agent import NewsAgent

    agent = NewsAgent(None, MagicMock(), MagicMock())
    agent._last_reliability_summary = {"avg_reliability": value, "low_reliability_count": 0}
    output = agent._format_output(
        "summary",
        [
            {
                "title": "item",
                "source": "source",
                "confidence": 0.4,
                "source_reliability": {"reliability_score": value},
            }
        ],
    )

    assert output.confidence == 0.8
    assert output.evidence[0].confidence == 0.4
    assert all("reliability is low" not in risk for risk in output.risks)


@pytest.mark.parametrize("value", NON_FINITE)
def test_news_agent_annotation_rejects_non_finite_source_reliability(monkeypatch, value):
    from backend.agents.news_agent import NewsAgent

    agent = NewsAgent(None, MagicMock(), MagicMock())
    monkeypatch.setattr(
        agent,
        "_score_reliability_for_item",
        lambda _item: {"reliability_score": value},
    )

    annotated = agent._annotate_reliability([{"title": "item"}])

    assert "confidence" not in annotated[0]


@pytest.mark.parametrize("value", NON_FINITE)
def test_bge_embedding_falls_back_for_non_finite_dense_values(value):
    from backend.rag.embedder import _BGEM3Wrapper

    class FakeModel:
        def encode(self, *_args, **_kwargs):
            return {
                "dense_vecs": [[value] + [0.0] * 1023],
                "lexical_weights": [{"ok": 1.0}],
            }

    wrapper = _BGEM3Wrapper()
    wrapper._model = FakeModel()
    result = wrapper.encode(["finite fallback"])

    assert len(result.dense[0]) == 1024
    assert all(math.isfinite(component) for component in result.dense[0])
    assert any(component != 0.0 for component in result.dense[0])


def test_bge_embedding_falls_back_for_wrong_dense_dimension():
    from backend.rag.embedder import _BGEM3Wrapper

    class FakeModel:
        def encode(self, *_args, **_kwargs):
            return {"dense_vecs": [[1.0]], "lexical_weights": [{}]}

    wrapper = _BGEM3Wrapper()
    wrapper._model = FakeModel()

    assert len(wrapper.encode(["wrong dimension"]).dense[0]) == 1024


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "bad"])
def test_bge_embedding_drops_invalid_sparse_weights(value):
    from backend.rag.embedder import _BGEM3Wrapper

    class FakeModel:
        def encode(self, *_args, **_kwargs):
            return {
                "dense_vecs": [[0.0] * 1024],
                "lexical_weights": [{"bad": value, "good": 0.5}],
            }

    wrapper = _BGEM3Wrapper()
    wrapper._model = FakeModel()
    result = wrapper.encode(["sparse"])

    assert result.sparse[0].weights == {"good": 0.5}


@pytest.mark.parametrize("scores", [[float("nan"), 0.5], [float("inf"), 0.5], [0.5]])
def test_reranker_falls_back_for_invalid_model_scores(monkeypatch, scores):
    from backend.rag import reranker as module

    class FakeReranker:
        def predict(self, _pairs):
            return scores

    service = module.RerankerService(force_backend="bge-reranker")
    service._available = True
    monkeypatch.setattr(module, "_get_reranker", lambda: FakeReranker())
    documents = [{"content": "one"}, {"content": "two"}]

    assert service.rerank("query", documents) == documents


@pytest.mark.parametrize("value", NON_FINITE + ["bad"])
def test_hybrid_scores_reject_invalid_numeric_values(value):
    from backend.rag.hybrid_service import SparseVector, _cosine, _finite_score, _sparse_score

    assert _cosine([1.0], [value]) == 0.0
    assert _sparse_score(SparseVector(weights={"x": 1.0}), SparseVector(weights={"x": value})) == 0.0
    assert _finite_score(value) == 0.0


@pytest.mark.parametrize("value", NON_FINITE)
def test_postgres_vector_literal_rejects_non_finite_components(value):
    from backend.rag.hybrid_service import _vector_literal

    with pytest.raises(ValueError, match="non-finite"):
        _vector_literal([value])


@pytest.mark.parametrize("value", NON_FINITE + [0, -1, "bad"])
def test_alert_price_boundary_rejects_invalid_values(value):
    from backend.services.alert_scheduler import _positive_finite_float

    assert _positive_finite_float(value) is None


@pytest.mark.parametrize("field", ["last_price", "previous_close"])
@pytest.mark.parametrize("value", NON_FINITE)
def test_yfinance_rejects_non_finite_quote_values(monkeypatch, field, value):
    from backend.services.alert_scheduler import _fetch_with_yfinance

    info = {"last_price": 100.0, "previous_close": 90.0, field: value}
    fake_yfinance = SimpleNamespace(Ticker=lambda _ticker: SimpleNamespace(fast_info=info))
    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance)

    snapshot = _fetch_with_yfinance("AAPL")

    if field == "last_price":
        assert snapshot is None
    else:
        assert snapshot is not None
        assert snapshot.price == 100.0
        assert snapshot.change_percent is None


@pytest.mark.parametrize("field", ["last_price", "previous_close"])
@pytest.mark.parametrize("value", NON_FINITE)
def test_yfinance_uses_later_finite_fallback_value(monkeypatch, field, value):
    from backend.services.alert_scheduler import _fetch_with_yfinance

    info = {
        "last_price": 100.0,
        "last_close": 101.0,
        "previous_close": 90.0,
        "previousClose": 91.0,
        field: value,
    }
    fake_yfinance = SimpleNamespace(Ticker=lambda _ticker: SimpleNamespace(fast_info=info))
    monkeypatch.setitem(sys.modules, "yfinance", fake_yfinance)

    snapshot = _fetch_with_yfinance("AAPL")

    assert snapshot is not None
    assert snapshot.price == (101.0 if field == "last_price" else 100.0)
    expected_previous = 90.0 if field == "last_price" else 91.0
    assert snapshot.change_percent == pytest.approx(
        (snapshot.price - expected_previous) / expected_previous * 100.0
    )


@pytest.mark.parametrize("field", ["regularMarketPrice", "regularMarketPreviousClose"])
@pytest.mark.parametrize("value", NON_FINITE)
def test_yahoo_quote_rejects_non_finite_values(monkeypatch, field, value):
    from backend.services.alert_scheduler import _fetch_with_yahoo_quote

    item = {"regularMarketPrice": 100.0, "regularMarketPreviousClose": 90.0, field: value}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"quoteResponse": {"result": [item]}}

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=lambda *_args, **_kwargs: FakeResponse()))

    snapshot = _fetch_with_yahoo_quote("AAPL")

    if field == "regularMarketPrice":
        assert snapshot is None
    else:
        assert snapshot is not None
        assert snapshot.change_percent is None


@pytest.mark.parametrize("value", NON_FINITE)
def test_stooq_rejects_non_finite_snapshot_price(monkeypatch, value):
    from backend.services.alert_scheduler import _fetch_with_stooq

    class FakeResponse:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"symbols": [{"close": value}]}

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=lambda *_args, **_kwargs: FakeResponse()))

    assert _fetch_with_stooq("AAPL") is None


@pytest.mark.parametrize("value", NON_FINITE)
def test_stooq_ignores_non_finite_historical_close(monkeypatch, value):
    from backend.services.alert_scheduler import _fetch_with_stooq

    class QuoteResponse:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"symbols": [{"close": 100.0}]}

    class HistoryResponse:
        status_code = 200
        text = f"Date,Close\n2026-01-01,{value}\n"

    def fake_get(url, **_kwargs):
        return HistoryResponse() if "/q/d/" in url else QuoteResponse()

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=fake_get))

    snapshot = _fetch_with_stooq("AAPL")

    assert snapshot is not None
    assert snapshot.price == 100.0
    assert snapshot.change_percent is None


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("value", NON_FINITE)
def test_yahoo_chart_rejects_non_finite_closes(monkeypatch, index, value):
    from backend.services.alert_scheduler import _fetch_with_yahoo_chart

    closes = [90.0, 100.0]
    closes[index] = value

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"chart": {"result": [{"indicators": {"quote": [{"close": closes}]}}]}}

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=lambda *_args, **_kwargs: FakeResponse()))

    assert _fetch_with_yahoo_chart("AAPL") is None


@pytest.mark.parametrize("timestamp", NON_FINITE + ["bad"])
def test_alert_cache_rejects_invalid_timestamps(monkeypatch, timestamp):
    from backend.services import alert_scheduler as module

    module._PRICE_CACHE["AAPL"] = (
        module.PriceSnapshot(ticker="AAPL", price=100.0, change_percent=1.0),
        timestamp,
    )
    monkeypatch.setattr(module.time, "time", lambda: 1000.0)

    assert module._get_cached_snapshot("AAPL") is None
    assert "AAPL" not in module._PRICE_CACHE


@pytest.mark.parametrize("value", NON_FINITE + ["bad"])
def test_rag_observability_scores_reject_invalid_values(value):
    from backend.graph.nodes.execute_plan_stub import _finite_optional_float as execute_score
    from backend.rag.observability_store import _finite_optional_float as store_score

    assert execute_score(value) is None
    assert store_score(value) is None


@pytest.mark.parametrize("value", NON_FINITE + ["bad"])
def test_rag_observability_store_builds_finite_hit_records(value):
    from backend.rag.observability_models import QueryRunRecord, SearchRunContext
    from backend.rag.observability_store import SQLRAGObservabilityStore

    context = SearchRunContext(
        run=QueryRunRecord(
            id="run",
            user_id="user",
            session_id="session",
            thread_id=None,
            query_text="query",
            collection="session:test",
        )
    )
    store = SQLRAGObservabilityStore.__new__(SQLRAGObservabilityStore)
    records = store._build_hit_records(
        context,
        [
            {
                "source_id": "source",
                "dense_score": value,
                "sparse_score": value,
                "rrf_score": value,
            }
        ],
    )

    assert len(records) == 1
    assert records[0].dense_score is None
    assert records[0].sparse_score is None
    assert records[0].rrf_score is None


@pytest.mark.parametrize(
    ("relative_path", "needle"),
    [
        ("backend/graph/nodes/execute_plan_stub.py", 'dense_score=_finite_float(hit.get("dense_score"), 0.0)'),
        ("backend/graph/nodes/execute_plan_stub.py", 'sparse_score=_finite_float(hit.get("sparse_score"), 0.0)'),
        ("backend/graph/nodes/execute_plan_stub.py", 'rrf_score=_finite_float(hit.get("rrf_score"), 0.0)'),
        ("backend/graph/nodes/execute_plan_stub.py", 'rerank_score=_finite_optional_float(hit.get("rerank_score"))'),
        ("backend/rag/hybrid_service.py", '"dense_score": _finite_score(row.get("dense_score"))'),
        ("backend/rag/hybrid_service.py", '"sparse_score": _finite_score(row.get("sparse_score"))'),
        ("backend/rag/hybrid_service.py", '"rrf_score": _finite_score(row.get("rrf_score"))'),
    ],
)
def test_rag_score_boundary_is_wired_to_persistence_path(relative_path, needle):
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]

    assert needle in (root / relative_path).read_text(encoding="utf-8")


@pytest.mark.parametrize("value", NON_FINITE)
def test_price_agent_omits_non_finite_change_percent(value):
    from backend.agents.price_agent import PriceAgent

    agent = PriceAgent(None, MagicMock(), MagicMock())
    output = agent._format_output(
        "",
        {"ticker": "AAPL", "price": 100.0, "change_percent": value},
    )

    assert "nan" not in output.summary.lower()
    assert "inf" not in output.summary.lower()


@pytest.mark.parametrize("value", NON_FINITE)
def test_macro_agent_rejects_non_finite_indicator_inputs(value):
    from backend.agents.macro_agent import MacroAgent

    agent = MacroAgent(None, MagicMock(), MagicMock())

    assert agent._extract_numeric_metrics({"fed_rate": value}) == {}
    merged = agent._merge_indicator_sources(
        primary_source="fred",
        primary={"fed_rate": value},
        secondary_source="search",
        secondary={"fed_rate": 5.0},
    )
    assert merged["selected"]["fed_rate"] == 5.0
    assert all(math.isfinite(item["value"]) for item in merged["indicators"] if item["value"] is not None)


@pytest.mark.parametrize(
    ("strategy", "params", "expected"),
    [
        ("macd", {"fast": "bad", "slow": "bad", "signal": "bad"}, {"fast": 12, "slow": 26, "signal": 9}),
        ("macd", {"fast": 0, "slow": -1, "signal": 0}, {"fast": 12, "slow": 26, "signal": 9}),
        (
            "rsi",
            {"period": "bad", "oversold": float("nan"), "overbought": float("inf")},
            {"period": 14, "oversold": 30.0, "overbought": 70.0},
        ),
        (
            "ma_cross",
            {"short_window": "bad", "long_window": "bad"},
            {"short_window": 20, "long_window": 50},
        ),
    ],
)
def test_backtest_strategy_invalid_parameters_use_defaults(strategy, params, expected):
    from backend.services.backtest_strategies import build_strategy_signals

    result = build_strategy_signals(strategy, [100.0] * 80, params)

    assert result["params"] == expected
