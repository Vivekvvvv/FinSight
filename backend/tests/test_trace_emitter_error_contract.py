from __future__ import annotations

import pytest

from backend.orchestration.trace_emitter import (
    TraceCategory,
    TraceEmitter,
    TraceEvent,
)


def test_trace_sse_dict_replaces_non_finite_metadata():
    event = TraceEvent(
        event_type="metric",
        category=TraceCategory.SYSTEM,
        message="metric",
        metadata={"score": float("nan"), "values": [float("inf")]},
    )

    assert event.to_sse_dict()["score"] is None
    assert event.to_sse_dict()["values"] == [None]


@pytest.mark.parametrize("context_name", ["trace_tool", "trace_llm"])
def test_trace_context_redacts_exception_message(context_name):
    sentinel = "PRIVATE_TRACE_PROVIDER_DETAIL"
    events = []
    emitter = TraceEmitter()
    emitter.add_listener(events.append)
    context_factory = getattr(emitter, context_name)

    with pytest.raises(RuntimeError, match=sentinel):
        with context_factory("provider"):
            raise RuntimeError(sentinel)

    payload = events[-1].to_sse_dict()
    assert payload["error"] == "RuntimeError"
    assert sentinel not in str(payload)
