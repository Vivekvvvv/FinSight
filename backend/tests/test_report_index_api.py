# -*- coding: utf-8 -*-
import importlib

import pytest
from fastapi.testclient import TestClient


def _load_main_module():
    import backend.api.main as main

    importlib.reload(main)
    return main


def test_report_index_list_replay_and_favorite_flow(tmp_path, monkeypatch):
    sqlite_path = tmp_path / "report_index.sqlite"
    monkeypatch.setenv("REPORT_INDEX_SQLITE_PATH", str(sqlite_path))

    main = _load_main_module()
    store = main.get_report_index_store()

    session_id = "tenant1:user1:thread1"
    report = {
        "report_id": "rpt-001",
        "ticker": "AAPL",
        "title": "AAPL 深度报告",
        "summary": "summary",
        "generated_at": "2026-02-07T00:00:00Z",
        "citations": [
            {
                "source_id": "src-1",
                "title": "citation-title",
                "url": "https://example.com/c1",
                "snippet": "snippet",
            }
        ],
    }
    store.upsert_report(session_id=session_id, report=report, trace_digest={"span_count": 3})

    client = TestClient(main.app)

    list_resp = client.get(
        "/api/reports/index",
        params={"session_id": session_id, "limit": 10},
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data.get("success") is True
    assert list_data.get("count") == 1
    assert list_data["items"][0]["report_id"] == "rpt-001"
    assert list_data["items"][0]["source_trigger"] is None
    assert list_data["items"][0]["analysis_depth"] is None

    replay_resp = client.get(
        "/api/reports/replay/rpt-001",
        params={"session_id": session_id},
    )
    assert replay_resp.status_code == 200
    replay_data = replay_resp.json()
    assert replay_data.get("success") is True
    assert replay_data.get("report", {}).get("report_id") == "rpt-001"
    assert isinstance(replay_data.get("citations"), list)

    fav_resp = client.post(
        "/api/reports/rpt-001/favorite",
        json={"session_id": session_id, "is_favorite": True},
    )
    assert fav_resp.status_code == 200
    fav_data = fav_resp.json()
    assert fav_data.get("is_favorite") is True

    note_resp = client.patch(
        "/api/reports/rpt-001/note",
        json={"session_id": session_id, "user_note": "下次财报后复核服务收入。"},
    )
    assert note_resp.status_code == 200
    note_data = note_resp.json()
    assert note_data.get("user_note") == "下次财报后复核服务收入。"

    note_list_resp = client.get(
        "/api/reports/index",
        params={"session_id": session_id, "limit": 10},
    )
    assert note_list_resp.status_code == 200
    note_item = note_list_resp.json()["items"][0]
    assert note_item["user_note"] == "下次财报后复核服务收入。"
    assert note_item["citation_count"] == 1

    note_replay_resp = client.get(
        "/api/reports/replay/rpt-001",
        params={"session_id": session_id},
    )
    assert note_replay_resp.status_code == 200
    note_replay_data = note_replay_resp.json()
    assert note_replay_data.get("user_note") == "下次财报后复核服务收入。"
    assert note_replay_data.get("report", {}).get("user_note") == "下次财报后复核服务收入。"


@pytest.mark.parametrize(
    ("corrupt_payload", "error_type"),
    [
        ("{ PRIVATE_CORRUPT_JSON", "JSONDecodeError"),
        ('{"value":NaN}', "ValueError"),
        ('{"value":1e309}', "ValueError"),
    ],
)
def test_report_index_logs_corrupt_stored_json_without_exposing_payload(
    tmp_path,
    monkeypatch,
    caplog,
    corrupt_payload,
    error_type,
):
    import logging

    from backend.services.report_index import ReportIndexStore

    sqlite_path = tmp_path / "report_index.sqlite"
    monkeypatch.setenv("REPORT_INDEX_SQLITE_PATH", str(sqlite_path))
    store = ReportIndexStore()
    session_id = "private:test-user:default"
    report_id = "report-corrupt-json"
    report = {
        "report_id": report_id,
        "title": "report",
        "tags": ["safe"],
        "citations": [{"title": "source", "url": "https://example.com"}],
    }
    store.upsert_report(
        session_id=session_id,
        report=report,
        trace_digest={"span_count": 1},
        include_blocked=True,
    )
    with store._connect() as conn:
        conn.execute(
            "UPDATE report_index SET tags_json = ?, quality_reasons_json = ?, trace_digest_json = ? "
            "WHERE report_id = ?",
            (corrupt_payload, corrupt_payload, corrupt_payload, report_id),
        )
        conn.execute(
            "UPDATE citation_index SET citation_json = ? WHERE report_id = ?",
            (corrupt_payload, report_id),
        )
        conn.commit()

    caplog.set_level(logging.WARNING, logger="backend.services.report_index")
    listed = store.list_reports(session_id=session_id, include_blocked=True)
    replay = store.get_report_replay(
        session_id=session_id,
        report_id=report_id,
        include_blocked=True,
    )
    citations = store.list_citations(session_id=session_id, report_id=report_id)

    assert listed[0]["tags"] == []
    assert listed[0]["quality_reasons"] == []
    assert replay is not None
    assert replay["trace_digest"] == {}
    assert replay["citations"] == []
    assert citations[0]["citation"] == {}
    assert caplog.text.count("parse failed") >= 5
    assert corrupt_payload not in caplog.text

    with store._connect() as conn:
        conn.execute(
            "UPDATE report_index SET report_json = ? WHERE report_id = ?",
            (corrupt_payload, report_id),
        )
        conn.commit()

    assert store.get_report_replay(
        session_id=session_id,
        report_id=report_id,
        include_blocked=True,
    ) is None
    assert "stored report payload parse failed" in caplog.text
    assert corrupt_payload not in caplog.text


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_report_index_rejects_non_finite_json(tmp_path, monkeypatch, value):
    from backend.services.report_index import ReportIndexStore

    monkeypatch.setenv("REPORT_INDEX_SQLITE_PATH", str(tmp_path / "report_index.sqlite"))
    store = ReportIndexStore()

    with pytest.raises(ValueError):
        store.upsert_report(
            session_id="private:user:default",
            report={"report_id": "report-non-finite", "payload": {"value": value}},
            include_blocked=True,
        )

    assert store.list_reports(
        session_id="private:user:default",
        include_blocked=True,
    ) == []


def test_report_note_rejects_long_text_and_missing_report(tmp_path, monkeypatch):
    sqlite_path = tmp_path / "report_index.sqlite"
    monkeypatch.setenv("REPORT_INDEX_SQLITE_PATH", str(sqlite_path))

    main = _load_main_module()
    client = TestClient(main.app)
    session_id = "tenant1:user1:thread-note"

    missing_resp = client.patch(
        "/api/reports/missing-report/note",
        json={"session_id": session_id, "user_note": "note"},
    )
    assert missing_resp.status_code == 404

    long_resp = client.patch(
        "/api/reports/missing-report/note",
        json={"session_id": session_id, "user_note": "x" * 2001},
    )
    assert long_resp.status_code == 422


def test_report_favorite_rejects_non_boolean_value(tmp_path, monkeypatch):
    sqlite_path = tmp_path / "report_index.sqlite"
    monkeypatch.setenv("REPORT_INDEX_SQLITE_PATH", str(sqlite_path))

    main = _load_main_module()
    store = main.get_report_index_store()
    session_id = "tenant1:user1:favorite-type"
    store.upsert_report(
        session_id=session_id,
        report={"report_id": "rpt-favorite-type", "title": "report"},
        include_blocked=True,
    )

    client = TestClient(main.app)
    response = client.post(
        "/api/reports/rpt-favorite-type/favorite",
        json={"session_id": session_id, "is_favorite": "false"},
    )

    assert response.status_code == 422
    assert store.list_reports(session_id=session_id, include_blocked=True)[0]["is_favorite"] is False


def test_report_review_status_rejects_unknown_value(tmp_path, monkeypatch):
    sqlite_path = tmp_path / "report_index.sqlite"
    monkeypatch.setenv("REPORT_INDEX_SQLITE_PATH", str(sqlite_path))

    main = _load_main_module()
    store = main.get_report_index_store()
    session_id = "tenant1:user1:review-status"
    store.upsert_report(
        session_id=session_id,
        report={"report_id": "rpt-review-status", "title": "report"},
        include_blocked=True,
    )

    client = TestClient(main.app)
    invalid_response = client.patch(
        "/api/reports/rpt-review-status/review_status",
        json={"session_id": session_id, "review_status": "done"},
    )
    valid_response = client.patch(
        "/api/reports/rpt-review-status/review_status",
        json={"session_id": session_id, "review_status": " WATCH "},
    )

    assert invalid_response.status_code == 422
    assert valid_response.status_code == 200
    assert valid_response.json()["review_status"] == "watch"
    assert store.list_reports(session_id=session_id, include_blocked=True)[0]["review_status"] == "watch"


def test_report_queries_reject_oversized_filters_and_limits(tmp_path, monkeypatch):
    sqlite_path = tmp_path / "report_index.sqlite"
    monkeypatch.setenv("REPORT_INDEX_SQLITE_PATH", str(sqlite_path))

    main = _load_main_module()
    client = TestClient(main.app)
    session_id = "tenant1:user1:thread-limits"

    query_response = client.get(
        "/api/reports/index",
        params={"session_id": session_id, "query": "x" * 2049},
    )
    limit_response = client.get(
        "/api/reports/index",
        params={"session_id": session_id, "limit": 501},
    )
    source_response = client.get(
        "/api/reports/citations",
        params={"session_id": session_id, "source_id": "x" * 257},
    )

    assert query_response.status_code == 422
    assert limit_response.status_code == 422
    assert source_response.status_code == 422


def test_report_index_replay_quality_matches_index_quality_state(tmp_path, monkeypatch):
    sqlite_path = tmp_path / "report_index.sqlite"
    monkeypatch.setenv("REPORT_INDEX_SQLITE_PATH", str(sqlite_path))

    main = _load_main_module()
    store = main.get_report_index_store()
    client = TestClient(main.app)

    session_id = "tenant_quality:user_quality:thread_quality"
    report = {
        "report_id": "rpt-quality-sync-1",
        "ticker": "MSFT",
        "title": "质量同步检查",
        "summary": "quality sync",
        "generated_at": "2026-02-10T00:00:00Z",
        "citations": [],
    }
    store.upsert_report(session_id=session_id, report=report, trace_digest={"span_count": 1})

    list_resp = client.get(
        "/api/reports/index",
        params={"session_id": session_id, "limit": 10},
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data.get("count") == 1
    quality_state = str(list_data["items"][0].get("quality_state") or "").strip().lower()
    assert quality_state in {"pass", "warn", "block"}

    replay_resp = client.get(
        "/api/reports/replay/rpt-quality-sync-1",
        params={"session_id": session_id, "include_blocked": True},
    )
    assert replay_resp.status_code == 200
    replay_data = replay_resp.json()
    quality = replay_data.get("report", {}).get("report_quality") or {}
    meta_quality = (replay_data.get("report", {}).get("meta") or {}).get("report_quality") or {}
    assert str(quality.get("state") or "").strip().lower() == quality_state
    assert str(meta_quality.get("state") or "").strip().lower() == quality_state


def test_report_index_supports_date_tag_filters_and_normalizes_source_id(tmp_path, monkeypatch):
    sqlite_path = tmp_path / "report_index.sqlite"
    monkeypatch.setenv("REPORT_INDEX_SQLITE_PATH", str(sqlite_path))

    main = _load_main_module()
    store = main.get_report_index_store()
    client = TestClient(main.app)

    session_id = "tenant2:user2:thread2"

    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": "rpt-ai-1",
            "ticker": "AAPL",
            "title": "AI 主题研报",
            "summary": "focus on ai",
            "tags": ["ai", "us-tech"],
            "generated_at": "2026-02-06T09:00:00Z",
            "meta": {"source_trigger": "dashboard_deep_search"},
            "citations": [
                {
                    "source_id": "legacy-source-id",
                    "title": "Apple AI Update",
                    "url": "https://example.com/apple-ai",
                    "snippet": "Apple shipped new AI features",
                }
            ],
        },
        trace_digest={"span_count": 2},
    )

    store.upsert_report(
        session_id=session_id,
        report={
            "report_id": "rpt-macro-1",
            "ticker": "MSFT",
            "title": "宏观观察",
            "summary": "macro view",
            "tags": ["macro"],
            "generated_at": "2026-02-08T12:30:00Z",
            "citations": [
                {
                    "title": "Macro Source",
                    "url": "https://example.com/macro",
                    "snippet": "macro news",
                }
            ],
        },
        trace_digest={"span_count": 1},
    )

    tag_resp = client.get(
        "/api/reports/index",
        params={"session_id": session_id, "tag": "ai", "limit": 10},
    )
    assert tag_resp.status_code == 200
    tag_data = tag_resp.json()
    assert tag_data.get("count") == 1
    assert tag_data["items"][0]["report_id"] == "rpt-ai-1"
    assert tag_data["items"][0]["source_trigger"] == "dashboard_deep_search"
    assert tag_data["items"][0]["analysis_depth"] == "deep_research"

    date_resp = client.get(
        "/api/reports/index",
        params={
            "session_id": session_id,
            "date_from": "2026-02-08T00:00:00Z",
            "date_to": "2026-02-08T23:59:59Z",
            "limit": 10,
        },
    )
    assert date_resp.status_code == 200
    date_data = date_resp.json()
    assert date_data.get("count") == 1
    assert date_data["items"][0]["report_id"] == "rpt-macro-1"

    replay_resp = client.get(
        "/api/reports/replay/rpt-ai-1",
        params={"session_id": session_id},
    )
    assert replay_resp.status_code == 200
    replay_data = replay_resp.json()
    citations = replay_data.get("citations") or []
    assert citations
    citation = citations[0]
    assert str(citation.get("source_id") or "").startswith("src_")
    assert citation.get("source_id_consistent") is False
    assert citation.get("source_id_original") == "legacy-source-id"


def test_report_citation_index_filters_by_source_and_query(tmp_path, monkeypatch):
    sqlite_path = tmp_path / "report_index.sqlite"
    monkeypatch.setenv("REPORT_INDEX_SQLITE_PATH", str(sqlite_path))

    main = _load_main_module()
    store = main.get_report_index_store()
    client = TestClient(main.app)

    session_id = "tenant3:user3:thread3"

    report = {
        "report_id": "rpt-cit-1",
        "ticker": "AAPL",
        "title": "Citation Query Report",
        "summary": "summary",
        "generated_at": "2026-02-08T10:00:00Z",
        "citations": [
            {
                "title": "Apple source",
                "url": "https://example.com/apple",
                "snippet": "Apple earnings beat",
                "published_date": "2026-02-08T09:00:00Z",
            },
            {
                "title": "Macro source",
                "url": "https://example.com/macro",
                "snippet": "Macro pressure remains",
                "published_date": "2026-02-07T09:00:00Z",
            },
        ],
    }
    store.upsert_report(session_id=session_id, report=report, trace_digest={"span_count": 1})

    replay_resp = client.get(
        "/api/reports/replay/rpt-cit-1",
        params={"session_id": session_id},
    )
    assert replay_resp.status_code == 200
    replay_data = replay_resp.json()
    citations = replay_data.get("citations") or []
    assert len(citations) == 2
    first_source_id = str(citations[0].get("source_id") or "").strip()
    assert first_source_id.startswith("src_")

    query_resp = client.get(
        "/api/reports/citations",
        params={"session_id": session_id, "query": "earnings", "limit": 20},
    )
    assert query_resp.status_code == 200
    query_data = query_resp.json()
    assert query_data.get("count") == 1
    assert "earnings" in str(query_data["items"][0].get("snippet") or "").lower()

    source_resp = client.get(
        "/api/reports/citations",
        params={"session_id": session_id, "source_id": first_source_id, "limit": 20},
    )
    assert source_resp.status_code == 200
    source_data = source_resp.json()
    assert source_data.get("count") == 1
    assert source_data["items"][0].get("source_id") == first_source_id


@pytest.mark.integration
def test_report_index_hides_blocked_by_default_and_supports_include_blocked(tmp_path, monkeypatch):
    sqlite_path = tmp_path / "report_index.sqlite"
    monkeypatch.setenv("REPORT_INDEX_SQLITE_PATH", str(sqlite_path))

    main = _load_main_module()
    store = main.get_report_index_store()
    client = TestClient(main.app)

    session_id = "tenant4:user4:thread4"
    blocked_report = {
        "report_id": "rpt-blocked-1",
        "ticker": "AAPL",
        "title": "Blocked report",
        "summary": "blocked",
        "generated_at": "2026-02-08T11:00:00Z",
        "citations": [],
        "report_quality": {
            "state": "block",
            "reasons": [
                {
                    "code": "EVIDENCE_COVERAGE_BELOW_MIN",
                    "severity": "block",
                    "metric": "coverage",
                    "actual": 0.2,
                    "threshold": 0.8,
                    "message": "coverage too low",
                }
            ],
        },
    }

    skipped = store.upsert_report(session_id=session_id, report=blocked_report, trace_digest={"span_count": 1})
    assert skipped.get("skipped") == "quality_blocked"

    # Force-insert blocked payload for audit/replay use case.
    inserted = store.upsert_report(
        session_id=session_id,
        report={**blocked_report, "report_id": "rpt-blocked-2"},
        trace_digest={"span_count": 1},
        include_blocked=True,
    )
    assert inserted.get("report_id") == "rpt-blocked-2"

    default_list = client.get("/api/reports/index", params={"session_id": session_id, "limit": 10})
    assert default_list.status_code == 200
    assert default_list.json().get("count") == 0

    include_list = client.get(
        "/api/reports/index",
        params={"session_id": session_id, "include_blocked": True, "limit": 10},
    )
    assert include_list.status_code == 200
    include_data = include_list.json()
    assert include_data.get("count") == 1
    assert include_data["items"][0].get("quality_state") == "block"
    assert include_data["items"][0].get("publishable") is False

    replay_default = client.get(
        "/api/reports/replay/rpt-blocked-2",
        params={"session_id": session_id},
    )
    assert replay_default.status_code == 404

    replay_include = client.get(
        "/api/reports/replay/rpt-blocked-2",
        params={"session_id": session_id, "include_blocked": True},
    )
    assert replay_include.status_code == 200


def test_report_compare_supports_include_blocked(tmp_path, monkeypatch):
    sqlite_path = tmp_path / "report_index.sqlite"
    monkeypatch.setenv("REPORT_INDEX_SQLITE_PATH", str(sqlite_path))

    main = _load_main_module()
    store = main.get_report_index_store()
    client = TestClient(main.app)

    session_id = "tenant4:user4:thread-compare"
    report_a = {
        "report_id": "rpt-compare-a",
        "ticker": "AAPL",
        "title": "Blocked A",
        "summary": "blocked",
        "generated_at": "2026-02-08T11:00:00Z",
        "citations": [],
        "confidence_score": 0.41,
        "report_quality": {
            "state": "block",
            "reasons": [
                {
                    "code": "EVIDENCE_COVERAGE_BELOW_MIN",
                    "severity": "block",
                    "metric": "coverage",
                    "actual": 0.2,
                    "threshold": 0.8,
                    "message": "coverage too low",
                }
            ],
        },
    }
    report_b = {
        "report_id": "rpt-compare-b",
        "ticker": "AAPL",
        "title": "Blocked B",
        "summary": "blocked",
        "generated_at": "2026-02-09T11:00:00Z",
        "citations": [],
        "confidence_score": 0.52,
        "report_quality": {
            "state": "block",
            "reasons": [
                {
                    "code": "GROUNDING_RATE_BELOW_MIN",
                    "severity": "block",
                    "metric": "grounding_rate",
                    "actual": 0.45,
                    "threshold": 0.6,
                    "message": "grounding too low",
                }
            ],
        },
    }

    store.upsert_report(session_id=session_id, report=report_a, trace_digest={}, include_blocked=True)
    store.upsert_report(session_id=session_id, report=report_b, trace_digest={}, include_blocked=True)

    default_resp = client.get(
        "/api/reports/compare",
        params={"session_id": session_id, "id1": "rpt-compare-a", "id2": "rpt-compare-b"},
    )
    assert default_resp.status_code == 404

    include_resp = client.get(
        "/api/reports/compare",
        params={
            "session_id": session_id,
            "id1": "rpt-compare-a",
            "id2": "rpt-compare-b",
            "include_blocked": True,
        },
    )
    assert include_resp.status_code == 200
    payload = include_resp.json()
    assert payload.get("success") is True
    assert payload.get("diff", {}).get("confidence_score", {}).get("delta") == 0.11
