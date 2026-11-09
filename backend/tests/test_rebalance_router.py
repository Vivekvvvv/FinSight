import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.rebalance_router import RebalanceRouterDeps, create_rebalance_router
from backend.services.rebalance_engine import RebalanceEngine


def _build_client(
    *,
    get_stock_price,
    get_company_info,
) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_rebalance_router(
            RebalanceRouterDeps(
                rebalance_engine=RebalanceEngine(),
                get_stock_price=get_stock_price,
                get_company_info=get_company_info,
            )
        )
    )
    return TestClient(app)


def test_generate_rebalance_degrades_when_live_price_missing():
    client = _build_client(
        get_stock_price=lambda _ticker: {},
        get_company_info=lambda _ticker: "- Sector: Technology",
    )

    payload = {
        "session_id": "public:test_user:thread-1",
        "portfolio": [
            {"ticker": "AAPL", "shares": 10},
            {"ticker": "MSFT", "shares": 5},
        ],
    }
    response = client.post("/api/rebalance/suggestions/generate", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["degraded_mode"] is True
    assert data["actions"] == []
    assert "missing_live_prices" in (data.get("fallback_reason") or "")


def test_generate_rebalance_returns_actions_when_inputs_complete():
    price_map = {"AAPL": 200.0, "MSFT": 100.0}
    client = _build_client(
        get_stock_price=lambda ticker: {"price": price_map[ticker]},
        get_company_info=lambda _ticker: "- Sector: Technology",
    )

    payload = {
        "session_id": "public:test_user:thread-2",
        "portfolio": [
            {"ticker": "AAPL", "shares": 10},
            {"ticker": "MSFT", "shares": 5},
        ],
        "constraints": {
            "max_single_position_pct": 55,
            "max_turnover_pct": 30,
            "sector_concentration_limit": 100,
            "min_action_delta_pct": 1,
        },
    }
    response = client.post("/api/rebalance/suggestions/generate", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["degraded_mode"] is False
    assert data.get("fallback_reason") in (None, "")
    assert len(data["actions"]) >= 1


def _complete_payload(session_id: str) -> dict:
    return {
        "session_id": session_id,
        "portfolio": [
            {"ticker": "AAPL", "shares": 10},
            {"ticker": "MSFT", "shares": 5},
        ],
        "constraints": {
            "max_single_position_pct": 55,
            "max_turnover_pct": 30,
            "sector_concentration_limit": 100,
            "min_action_delta_pct": 1,
        },
    }


def _complete_client() -> TestClient:
    price_map = {"AAPL": 200.0, "MSFT": 100.0}
    return _build_client(
        get_stock_price=lambda ticker: {"price": price_map[ticker]},
        get_company_info=lambda _ticker: "- Sector: Technology",
    )


def _suggestion_result(response, stream):
    assert response.status_code == 200
    if not stream:
        return response.json()
    for frame in response.text.split("\n\n"):
        if frame.startswith("event: result\n"):
            return json.loads(frame.split("data: ", 1)[1])
    raise AssertionError(response.text)


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("sector", [None, True, {"name": "Technology"}, ["Technology"]])
def test_invalid_sector_inputs_require_diagnostics(monkeypatch, stream, sector):
    import backend.api.rebalance_router as module

    monkeypatch.setattr(module, "save_suggestion", lambda **kwargs: None)
    client = _build_client(
        get_stock_price=lambda ticker: {"price": 100.0},
        get_company_info=lambda ticker: {"sector": sector},
    )
    payload = _complete_payload("public:test_user:sector-invalid")
    for position in payload["portfolio"]:
        position["sector"] = None
    suffix = "generate-stream" if stream else "generate"
    data = _suggestion_result(client.post(f"/api/rebalance/suggestions/{suffix}", json=payload), stream)

    assert data["degraded_mode"] is True
    assert data["actions"] == []
    assert "missing_sector_map:AAPL,MSFT" in data["fallback_reason"]


@pytest.mark.parametrize("stream", [False, True])
def test_null_sector_uses_valid_provider_fallback(monkeypatch, stream):
    import backend.api.rebalance_router as module

    monkeypatch.setattr(module, "save_suggestion", lambda **kwargs: None)
    payload = _complete_payload("public:test_user:sector-fallback")
    for position in payload["portfolio"]:
        position["sector"] = None
    suffix = "generate-stream" if stream else "generate"
    data = _suggestion_result(_complete_client().post(f"/api/rebalance/suggestions/{suffix}", json=payload), stream)

    assert data["degraded_mode"] is False
    assert data["actions"]


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("nested", [False, True])
def test_rebalance_rejects_unrelated_quote_identity(monkeypatch, stream, nested):
    import backend.api.rebalance_router as module

    monkeypatch.setattr(module, "save_suggestion", lambda **kwargs: None)
    quote = {"price": 100.0, "ticker": "TSLA"}
    client = _build_client(
        get_stock_price=lambda ticker: {"data": quote} if nested else quote,
        get_company_info=lambda ticker: {"sector": "Technology"},
    )
    suffix = "generate-stream" if stream else "generate"
    data = _suggestion_result(client.post(f"/api/rebalance/suggestions/{suffix}",
        json=_complete_payload("public:test_user:quote-mismatch")), stream)

    assert data["degraded_mode"] is True
    assert data["actions"] == []
    assert "missing_live_prices:AAPL,MSFT" in data["fallback_reason"]


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("freshness", ["cached", "stale", "demo", "unknown", "fallback", "delayed_15min"])
def test_rebalance_non_live_quotes_require_diagnostics(monkeypatch, stream, freshness):
    import backend.api.rebalance_router as module

    monkeypatch.setattr(module, "save_suggestion", lambda **kwargs: None)
    client = _build_client(
        get_stock_price=lambda ticker: {"data": {"price": 100.0, "freshness_status": freshness}},
        get_company_info=lambda ticker: {"sector": "Technology"},
    )
    suffix = "generate-stream" if stream else "generate"
    data = _suggestion_result(client.post(f"/api/rebalance/suggestions/{suffix}",
        json=_complete_payload("public:test_user:quote-freshness")), stream)

    assert data["degraded_mode"] is True
    assert data["actions"] == []
    assert "missing_live_prices" in data["fallback_reason"]


def test_generate_rebalance_returns_500_when_persist_fails(monkeypatch):
    """落盘失败不能回 200 + suggestion_id：用户会以为建议已保存。"""
    import backend.api.rebalance_router as rebalance_router

    def _boom(**_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(rebalance_router, "save_suggestion", _boom)

    response = _complete_client().post(
        "/api/rebalance/suggestions/generate",
        json=_complete_payload("public:test_user:persist-fail"),
    )

    assert response.status_code == 500
    assert "suggestion_id" not in response.json()


def test_generate_rebalance_stream_marks_persisted_false_when_save_fails(monkeypatch):
    """SSE 无法改状态码，但结果里必须显式标记未落盘。"""
    import backend.api.rebalance_router as rebalance_router

    def _boom(**_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(rebalance_router, "save_suggestion", _boom)

    response = _complete_client().post(
        "/api/rebalance/suggestions/generate-stream",
        json=_complete_payload("public:test_user:stream-persist-fail"),
    )

    assert response.status_code == 200
    assert "event: result" in response.text
    assert '"persisted": false' in response.text


def test_rebalance_endpoints_reject_oversized_portfolio_before_fetching():
    calls = []

    def get_stock_price(ticker):
        calls.append(ticker)
        return {"price": 1.0}

    client = _build_client(
        get_stock_price=get_stock_price,
        get_company_info=lambda _ticker: "- Sector: Technology",
    )
    payload = {
        "session_id": "public:test_user:thread-limit",
        "portfolio": [{"ticker": f"T{index}", "shares": 1} for index in range(201)],
    }

    for path in (
        "/api/rebalance/suggestions/generate",
        "/api/rebalance/suggestions/generate-stream",
    ):
        response = client.post(path, json=payload)
        assert response.status_code == 422

    assert calls == []


@pytest.mark.parametrize(
    "portfolio",
    [
        [{"ticker": "A" * 33, "shares": 1}],
        [{"ticker": "AAPL", "shares": -1}],
        [{"ticker": "AAPL", "shares": 1}, {"ticker": " aapl ", "shares": 2}],
        [{"ticker": "AAPL", "shares": 1, "sector": "x" * 129}],
        [{"ticker": "AAPL", "shares": 1, "metadata": "x" * (256 * 1024)}],
    ],
)
def test_rebalance_endpoints_reject_invalid_positions_before_fetching(portfolio):
    calls: list[str] = []
    client = _build_client(
        get_stock_price=lambda ticker: calls.append(ticker) or {"price": 1.0},
        get_company_info=lambda ticker: calls.append(ticker) or "- Sector: Technology",
    )
    payload = {
        "session_id": "public:test_user:thread-validation",
        "portfolio": portfolio,
    }

    for path in (
        "/api/rebalance/suggestions/generate",
        "/api/rebalance/suggestions/generate-stream",
    ):
        response = client.post(path, json=payload)
        assert response.status_code == 422

    assert calls == []


@pytest.mark.parametrize("limit", [-1, 0, 51])
def test_rebalance_list_rejects_out_of_range_limit_before_store(monkeypatch, limit):
    from backend.api import rebalance_router as module

    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        module,
        "list_suggestions",
        lambda session_id, limit: calls.append((session_id, limit)) or [],
    )
    client = _build_client(
        get_stock_price=lambda _ticker: {},
        get_company_info=lambda _ticker: {},
    )

    response = client.get(
        "/api/rebalance/suggestions",
        params={"session_id": "public:test_user:thread-list", "limit": limit},
    )

    assert response.status_code == 422
    assert calls == []


def test_rebalance_patch_rejects_oversized_suggestion_id_before_store(monkeypatch):
    from backend.api import rebalance_router as module

    calls = []
    monkeypatch.setattr(
        module,
        "patch_suggestion",
        lambda *args, **kwargs: calls.append((args, kwargs)) or True,
    )
    client = _build_client(
        get_stock_price=lambda _ticker: {},
        get_company_info=lambda _ticker: {},
    )

    response = client.patch(
        f"/api/rebalance/suggestions/{'x' * 129}",
        json={"status": "viewed"},
    )

    assert response.status_code == 422
    assert calls == []


def _fake_store_positions(monkeypatch, positions, invalid):
    from backend.api import rebalance_router as module

    def _get_positions(_session_id, diagnostics=None):
        if diagnostics is not None and invalid:
            diagnostics["invalid_positions"] = list(invalid)
        return positions

    monkeypatch.setattr(module, "get_positions", _get_positions)


def test_rebalance_does_not_read_unreadable_rows_as_no_positions(monkeypatch):
    """库里只有解析不出的行：不能回 400「请先添加持仓」。"""
    _fake_store_positions(monkeypatch, [], ["BADROW"])
    client = _build_client(
        get_stock_price=lambda _ticker: {},
        get_company_info=lambda _ticker: {},
    )

    response = client.post(
        "/api/rebalance/suggestions/generate",
        json={"session_id": "public:test_user:invalid-only"},
    )

    assert response.status_code == 500
    assert "unreadable" in response.json()["detail"]


def test_rebalance_stream_explains_unreadable_rows(monkeypatch):
    _fake_store_positions(monkeypatch, [], ["BADROW"])
    client = _build_client(
        get_stock_price=lambda _ticker: {},
        get_company_info=lambda _ticker: {},
    )

    response = client.post(
        "/api/rebalance/suggestions/generate-stream",
        json={"session_id": "public:test_user:invalid-only-stream"},
    )

    assert response.status_code == 200
    assert "持仓数据无法读取" in response.text
    assert "请先添加持仓" not in response.text


def test_rebalance_marks_partially_dropped_positions(monkeypatch):
    """坏行被跳过后权重重新归一：建议必须标注它只覆盖了部分组合。"""
    _fake_store_positions(monkeypatch, [{"ticker": "AAPL", "shares": 10}], ["BADROW"])
    client = _build_client(
        get_stock_price=lambda _ticker: {"price": 200.0},
        get_company_info=lambda _ticker: "- Sector: Technology",
    )

    response = client.post(
        "/api/rebalance/suggestions/generate",
        json={
            "session_id": "public:test_user:invalid-partial",
            "constraints": {"sector_concentration_limit": 100},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["degraded_mode"] is True
    assert "invalid_stored_positions:BADROW" in (data.get("fallback_reason") or "")
