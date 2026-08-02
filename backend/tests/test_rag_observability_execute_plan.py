# -*- coding: utf-8 -*-
import asyncio
import logging


def _run(coro):
    return asyncio.run(coro)


class _FakeObservabilityStore:
    def __init__(self):
        self.run_records = []
        self.events = []
        self.source_docs = []
        self.chunks = []
        self.retrieval_hits = []
        self.rerank_hits = []
        self.fallback_events = []
        self.updates = []

    def ensure_schema(self):
        return True

    def start_query_run(self, record):
        self.run_records.append(record)
        return record.id

    def update_query_run(self, run_id, **fields):
        self.updates.append((run_id, fields))
        return 1

    def append_query_events(self, records):
        self.events.extend(list(records))
        return len(self.events)

    def append_source_docs(self, records):
        self.source_docs.extend(list(records))
        return len(self.source_docs)

    def append_chunks(self, records):
        self.chunks.extend(list(records))
        return len(self.chunks)

    def append_retrieval_hits(self, records):
        self.retrieval_hits.extend(list(records))
        return len(self.retrieval_hits)

    def append_rerank_hits(self, records):
        self.rerank_hits.extend(list(records))
        return len(self.rerank_hits)

    def append_fallback_event(self, record):
        self.fallback_events.append(record)
        return record.id


def _minimal_rag_state(thread_id):
    selection_payload = [
        {
            "id": "n1",
            "type": "news",
            "title": "Apple update",
            "snippet": "Material evidence for the report.",
            "source": "news",
        }
    ]
    return {
        "thread_id": thread_id,
        "query": "analyze AAPL evidence",
        "plan_ir": {
            "subject": {
                "subject_type": "company",
                "tickers": ["AAPL"],
                "selection_payload": selection_payload,
            },
            "output_mode": "investment_report",
            "steps": [],
        },
        "policy": {"allowed_tools": [], "allowed_agents": []},
        "subject": {
            "subject_type": "company",
            "tickers": ["AAPL"],
            "selection_payload": selection_payload,
        },
        "trace": {},
    }


def test_execute_plan_stub_redacts_observability_write_error_log(monkeypatch, caplog):
    monkeypatch.setenv("LANGGRAPH_EXECUTE_LIVE_TOOLS", "false")
    monkeypatch.setenv("RAG_V2_BACKEND", "memory")
    sentinel = "PRIVATE_OBSERVABILITY_DSN_DETAIL"

    class _FailingEnsureStore(_FakeObservabilityStore):
        def ensure_schema(self):
            raise RuntimeError(sentinel)

    fake_store = _FailingEnsureStore()
    monkeypatch.setattr(
        "backend.rag.observability_runtime.get_rag_observability_store",
        lambda: fake_store,
    )
    caplog.set_level(logging.WARNING, logger="backend.graph.nodes.execute_plan_stub")

    from backend.graph.nodes.execute_plan_stub import execute_plan_stub

    out = _run(execute_plan_stub(_minimal_rag_state("tenant1:userA:write-failure")))

    assert isinstance(out, dict)
    assert sentinel not in caplog.text
    assert "RAG observability write failed" in caplog.text


def test_execute_plan_stub_redacts_reranker_error_log(monkeypatch, caplog):
    monkeypatch.setenv("LANGGRAPH_EXECUTE_LIVE_TOOLS", "false")
    monkeypatch.setenv("RAG_V2_BACKEND", "memory")
    monkeypatch.setenv("RAG_ENABLE_RERANKER", "true")
    sentinel = "PRIVATE_RERANKER_MODEL_DETAIL"
    fake_store = _FakeObservabilityStore()

    class _FailingReranker:
        is_enabled = True

        def rerank(self, *_args, **_kwargs):
            raise RuntimeError(sentinel)

    monkeypatch.setattr(
        "backend.rag.observability_runtime.get_rag_observability_store",
        lambda: fake_store,
    )
    monkeypatch.setattr(
        "backend.rag.reranker.get_reranker_service",
        lambda: _FailingReranker(),
    )
    caplog.set_level(logging.DEBUG, logger="backend.graph.nodes.execute_plan_stub")

    from backend.graph.nodes.execute_plan_stub import execute_plan_stub

    out = _run(execute_plan_stub(_minimal_rag_state("tenant1:userA:reranker-failure")))

    assert (out.get("artifacts") or {}).get("rag_context")
    assert sentinel not in caplog.text
    assert "Reranker unavailable; using RRF order" in caplog.text


def test_execute_plan_stub_records_rag_observability(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_EXECUTE_LIVE_TOOLS", "false")
    monkeypatch.setenv("RAG_V2_BACKEND", "memory")
    monkeypatch.setenv("RAG_V2_TOP_K", "4")
    monkeypatch.setenv("RAG_ENABLE_RERANKER", "false")

    from backend.rag.hybrid_service import reset_rag_service_cache
    from backend.rag.observability_runtime import reset_rag_observability_store_cache

    reset_rag_service_cache()
    reset_rag_observability_store_cache()

    fake_store = _FakeObservabilityStore()
    monkeypatch.setattr(
        "backend.rag.observability_runtime.get_rag_observability_store",
        lambda: fake_store,
    )

    from backend.graph.nodes.execute_plan_stub import execute_plan_stub

    thread_id = "tenant1:userA:thread-rag-observe"
    selection_payload = [
        {
            "id": "n1",
            "type": "news",
            "title": "Apple reports strong iPhone demand",
            "snippet": "Revenue guidance improved with stronger iPhone upgrades.",
            "source": "news",
            "url": "https://example.com/apple-1",
        },
        {
            "id": "n2",
            "type": "news",
            "title": "Apple AI features lift services engagement",
            "snippet": "Services usage rose as Apple Intelligence previews expanded.",
            "source": "news",
            "url": "https://example.com/apple-2",
        },
    ]
    state = {
        "thread_id": thread_id,
        "query": "苹果最近的 iPhone 需求和服务业务怎么样",
        "plan_ir": {
            "goal": "x",
            "subject": {
                "subject_type": "company",
                "tickers": ["AAPL"],
                "selection_ids": ["n1", "n2"],
                "selection_types": ["news", "news"],
                "selection_payload": selection_payload,
            },
            "output_mode": "investment_report",
            "steps": [],
            "budget": {"max_rounds": 1, "max_tools": 1},
            "synthesis": {"style": "concise", "sections": []},
        },
        "policy": {"allowed_tools": [], "allowed_agents": [], "budget": {"max_rounds": 1, "max_tools": 1}},
        "subject": {
            "subject_type": "company",
            "tickers": ["AAPL"],
            "selection_payload": selection_payload,
        },
        "trace": {},
    }

    out = _run(execute_plan_stub(state))
    artifacts = out.get("artifacts") or {}
    rag_trace = (out.get("trace") or {}).get("rag") or {}

    assert fake_store.run_records, "should create query run record"
    run_record = fake_store.run_records[0]
    assert run_record.id.startswith("ragrun_")
    assert run_record.user_id == "userA"
    assert run_record.session_id == thread_id

    assert fake_store.source_docs, "should persist source docs"
    assert fake_store.chunks, "should persist chunks"
    assert fake_store.retrieval_hits, "should persist retrieval hits"
    assert fake_store.rerank_hits, "should persist rerank hits"
    assert fake_store.events, "should persist query events"
    assert any(event.event_type == "retrieval_done" for event in fake_store.events)
    assert any(event.event_type == "run_completed" for event in fake_store.events)

    rag_context = artifacts.get("rag_context") or []
    assert rag_context, "rag_context should remain populated"
    top_hit = rag_context[0]
    assert top_hit.get("run_id") == run_record.id
    assert top_hit.get("source_doc_id")
    assert top_hit.get("chunk_id")
    assert top_hit.get("chunk_strategy")

    assert rag_trace.get("run_id") == run_record.id
    assert rag_trace.get("source_doc_count", 0) >= 1
    assert rag_trace.get("chunk_count", 0) >= 1
    assert fake_store.updates and fake_store.updates[-1][0] == run_record.id


def test_execute_plan_stub_redacts_rag_pipeline_error(monkeypatch, caplog):
    monkeypatch.setenv("LANGGRAPH_EXECUTE_LIVE_TOOLS", "false")
    monkeypatch.setenv("RAG_V2_BACKEND", "memory")
    secret = "PRIVATE_RAG_PIPELINE_ERROR_SENTINEL"
    fake_store = _FakeObservabilityStore()

    monkeypatch.setattr(
        "backend.rag.observability_runtime.get_rag_observability_store",
        lambda: fake_store,
    )

    def fail_rag_service():
        raise RuntimeError(secret)

    monkeypatch.setattr(
        "backend.rag.hybrid_service.get_rag_service",
        fail_rag_service,
    )

    from backend.graph.nodes.execute_plan_stub import execute_plan_stub

    state = {
        "thread_id": "tenant1:userA:thread-rag-failure",
        "query": "analyze AAPL evidence",
        "plan_ir": {
            "subject": {
                "subject_type": "company",
                "tickers": ["AAPL"],
                "selection_payload": [
                    {
                        "id": "n1",
                        "type": "news",
                        "title": "Apple update",
                        "snippet": "Material evidence for the report.",
                        "source": "news",
                    }
                ],
            },
            "output_mode": "investment_report",
            "steps": [],
        },
        "policy": {"allowed_tools": [], "allowed_agents": []},
        "subject": {
            "subject_type": "company",
            "tickers": ["AAPL"],
            "selection_payload": [
                {
                    "id": "n1",
                    "type": "news",
                    "title": "Apple update",
                    "snippet": "Material evidence for the report.",
                    "source": "news",
                }
            ],
        },
        "trace": {},
    }

    out = _run(execute_plan_stub(state))
    rag_trace = (out.get("trace") or {}).get("rag") or {}

    assert rag_trace["error"] == "rag_pipeline_error"
    assert fake_store.fallback_events[-1].reason_text == "rag_pipeline_error"
    assert fake_store.updates[-1][1]["error_message"] == "rag_pipeline_error"
    assert secret not in str(out)
    assert secret not in str(fake_store.fallback_events)
    assert secret not in str(fake_store.updates)
    assert secret not in caplog.text
    assert "RAG pipeline failed" in caplog.text
