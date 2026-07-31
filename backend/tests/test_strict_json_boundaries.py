from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest

from backend.utils.strict_json import ensure_json_finite, json_load_strict, json_loads_strict


_ROOT = Path(__file__).resolve().parents[2]

# Each tuple identifies one independently fixed external/persisted JSON entrypoint.
STRICT_JSON_ENTRYPOINTS = [
    ("R201", "backend/agents/news_agent.py", "payload = json_loads_strict(payload)", 1),
    ("R202", "backend/api/main.py", "payload = json_loads_strict(response.read().decode", 1),
    ("R203", "backend/graph/nodes/execute_plan_stub.py", "parsed = json_loads_strict(output)", 1),
    ("R204", "backend/graph/nodes/execute_plan_stub.py", "output = json_loads_strict(output)", 1),
    ("R205", "backend/graph/nodes/synthesize.py", "obj = json_loads_strict(cleaned)", 1),
    ("R206", "backend/graph/nodes/synthesize.py", "payload = json_loads_strict(_extract_json_object", 1),
    ("R207", "backend/graph/nodes/synthesize.py", "obj = json_loads_strict(raw_text)", 1),
    ("R208", "backend/graph/nodes/synthesize.py", "out = json_loads_strict(out)", 1),
    ("R209", "backend/graph/nodes/synthesize.py", "out = json_loads_strict(out)", 2),
    ("R210", "backend/graph/nodes/synthesize.py", "facts_out = json_loads_strict(facts_out)", 1),
    ("R211", "backend/graph/nodes/synthesize.py", "payload = json_loads_strict(_extract_json_object", 2),
    ("R212", "backend/graph/report_builder.py", "obj = json_loads_strict(candidate)", 1),
    ("R213", "backend/orchestration/plan.py", "data = json_load_strict(f)", 1),
    ("R214", "backend/rag/hybrid_service.py", "metadata = json_loads_strict(metadata)", 1),
    ("R215", "backend/security/auth.py", "mappings = json_loads_strict(mappings_raw)", 1),
    ("R216", "backend/services/research_notes.py", "parsed = json_loads_strict(value)", 1),
    ("R217", "backend/tools/tencent_provider.py", "data_list = json_loads_strict(match.group(1))", 1),
    ("R218", "backend/tools/tencent_provider.py", "buy_data = json_loads_strict(buy_match.group(1))", 1),
    ("R219", "backend/tools/tencent_provider.py", "sell_data = json_loads_strict(sell_match.group(1))", 1),
    ("R220", "backend/tools/tencent_provider.py", "data_list = json_loads_strict(match.group(1))", 2),
    ("R221", "backend/tools/tencent_provider.py", "data = json_loads_strict(match.group(1))", 1),
    ("R222", "backend/tools/tencent_provider.py", "data = json_loads_strict(resp.text)", 1),
    ("R223", "backend/tools/wayback.py", "else json_loads_strict(resp.text)", 1),
    ("R224", "backend/tools/wayback.py", "else json_loads_strict(resp.text)", 2),
    ("R302", "backend/agents/deep_search_agent.py", "return json_loads_strict(match.group(0))", 1),
    ("R303", "backend/api/config_router.py", "saved_config = json_load_strict(file_obj)", 1),
    ("R304", "backend/api/config_router.py", "existing = json_load_strict(file_obj)", 1),
    ("R305", "backend/dashboard/scorers.py", "parsed = json_loads_strict(text)", 1),
    ("R306", "backend/graph/nodes/planner.py", "return json_loads_strict(candidate, strict=False)", 1),
    ("R307", "backend/llm_config.py", "payload = json_load_strict(f)", 1),
    ("R308", "backend/rag/observability_runtime.py", "return json_loads_strict(value)", 1),
    ("R309", "backend/rag/observability_store.py", "return json_loads_strict(value)", 1),
    ("R310", "backend/services/chat_history.py", "data = json_loads_strict(path.read_text", 1),
    ("R311", "backend/services/entitlements.py", "data = json_load_strict(f)", 1),
    ("R312", "backend/services/financials_analyzer.py", "result = json_loads_strict(text)", 1),
    ("R313", "backend/services/memory.py", "data = json_load_strict(f)", 1),
    ("R314", "backend/services/news_sentiment.py", "sentiments: List[Dict[str, Any]] = json_loads_strict(text)", 1),
    ("R315", "backend/services/notes_rag.py", "doc_vec = json_loads_strict(vec_json)", 1),
    ("R316", "backend/services/notes_rag.py", "tags = json_loads_strict(tags_json or", 1),
    ("R317", "backend/services/portfolio_store.py", "parsed = json_loads_strict(value)", 1),
    ("R318", "backend/services/portfolio_store.py", "parsed = json_loads_strict(r[1])", 1),
    ("R319", "backend/services/rebalance_llm_enhancer.py", "parsed = json_loads_strict(text[start:end + 1])", 1),
    ("R320", "backend/services/risk_snapshots.py", "data = json_loads_strict(row[\"full_data\"])", 1),
    ("R321", "backend/services/subscription_service.py", "subscriptions = json_load_strict(f)", 1),
]


@pytest.mark.parametrize(
    ("_round", "relative_path", "needle", "occurrence"),
    STRICT_JSON_ENTRYPOINTS,
    ids=[item[0] for item in STRICT_JSON_ENTRYPOINTS],
)
def test_external_json_entrypoint_uses_strict_loader(_round, relative_path, needle, occurrence):
    source = (_ROOT / relative_path).read_text(encoding="utf-8")

    assert source.count(needle) >= occurrence


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_strict_json_loaders_reject_non_standard_constants(constant):
    payload = f'{{"value": {constant}}}'
    with pytest.raises(ValueError):
        json_loads_strict(payload)
    with pytest.raises(ValueError):
        json_load_strict(StringIO(payload))


def test_strict_json_loaders_reject_finite_syntax_that_overflows_to_infinity():
    payload = '{"value": 1e309}'

    with pytest.raises(ValueError):
        json_loads_strict(payload)
    with pytest.raises(ValueError):
        json_load_strict(StringIO(payload))


def test_strict_json_loader_cannot_be_overridden_to_accept_constants():
    with pytest.raises(ValueError):
        json_loads_strict('{"value": NaN}', parse_constant=lambda _value: 0.0)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_ensure_json_finite_rejects_nested_non_finite_values(value):
    with pytest.raises(ValueError):
        ensure_json_finite({"nested": [value]})


def test_api_principal_mapping_rejects_non_standard_json(monkeypatch):
    from backend.security.auth import principal_from_api_key

    monkeypatch.setenv(
        "API_AUTH_PRINCIPALS",
        '{"key":{"user_id":"privileged","role":NaN}}',
    )
    principal = principal_from_api_key("key")

    assert principal.user_id != "privileged"
    assert principal.role == "user"


def test_research_note_tags_reject_non_standard_json():
    from backend.services.research_notes import _parse_tags

    assert _parse_tags('["valid", NaN]') == []


def test_report_line_does_not_flatten_non_standard_json():
    from backend.graph.report_builder import _flatten_json_like_line

    line = '{"event": NaN, "impact": "private"}'
    assert _flatten_json_like_line(line) == line


def test_synthesize_line_does_not_flatten_non_standard_json():
    from backend.graph.nodes.synthesize import _normalize_llm_section_line

    line = '{"event": NaN, "impact": "private"}'
    assert _normalize_llm_section_line(line) == line
