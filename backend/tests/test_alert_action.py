# -*- coding: utf-8 -*-
import asyncio
import threading

import pytest

import importlib
from backend.services.alert_scheduler import PriceSnapshot

alert_action_module = importlib.import_module("backend.graph.nodes.alert_action")


class StubSubscriptionService:
    def __init__(self):
        self._subscriptions = []
        self.last_subscribe_kwargs = None

    def get_subscriptions(self, email=None):
        if email is None:
            return list(self._subscriptions)
        return [item for item in self._subscriptions if item.get("email") == email]

    def subscribe(self, **kwargs):
        self.last_subscribe_kwargs = dict(kwargs)
        self._subscriptions = [
            item
            for item in self._subscriptions
            if not (
                str(item.get("email") or "").strip().lower() == str(kwargs.get("email") or "").strip().lower()
                and str(item.get("ticker") or "").strip().upper() == str(kwargs.get("ticker") or "").strip().upper()
            )
        ]
        self._subscriptions.append(dict(kwargs))
        return True


@pytest.mark.asyncio
async def test_alert_action_requires_email(monkeypatch):
    svc = StubSubscriptionService()
    monkeypatch.setattr(alert_action_module, "get_subscription_service", lambda: svc)
    monkeypatch.setattr(alert_action_module, "fetch_price_snapshot", lambda _ticker: PriceSnapshot(ticker=_ticker, price=100.0, change_percent=0.0))

    result = await alert_action_module.alert_action(
        {
            "alert_params": {"ticker": "AAPL", "alert_mode": "price_change_pct", "price_threshold": 3.0},
            "subject": {"tickers": ["AAPL"]},
            "ui_context": {},
        }
    )
    assert result["alert_valid"] is False
    assert "邮箱" in ((result.get("artifacts") or {}).get("draft_markdown") or "")


@pytest.mark.asyncio
async def test_alert_action_merges_alert_types_and_subscribes(alert_storage):
    _, svc = alert_storage
    assert svc.subscribe("user@example.com", "AAPL", alert_types=["news"], risk_threshold="high")

    result = await alert_action_module.alert_action(
        {
            "user_email": "user@example.com",
            "alert_params": {"ticker": "AAPL", "alert_mode": "price_change_pct", "price_threshold": 4.0},
            "subject": {"tickers": ["AAPL"]},
        }
    )

    assert result["alert_valid"] is True
    saved = svc.get_subscriptions("user@example.com")[0]
    assert saved["ticker"] == "AAPL"
    assert saved["price_threshold"] == 4.0
    assert sorted(saved["alert_types"]) == ["news", "price_change"]


@pytest.mark.asyncio
@pytest.mark.parametrize("target,expected_direction", [(80.0, "below"), (100.0, "above"), (120.0, "above")])
async def test_alert_action_infers_direction_for_target_mode(monkeypatch, target, expected_direction):
    svc = StubSubscriptionService()
    monkeypatch.setattr(alert_action_module, "get_subscription_service", lambda: svc)
    monkeypatch.setattr(alert_action_module, "fetch_price_snapshot", lambda _ticker: PriceSnapshot(ticker=_ticker, price=100.0, change_percent=0.0))

    result = await alert_action_module.alert_action(
        {
            "user_email": "user@example.com",
            "alert_params": {
                "ticker": "AAPL",
                "alert_mode": "price_target",
                "price_target": target,
                "direction": None,
            },
            "subject": {"tickers": ["AAPL"]},
        }
    )

    assert result["alert_valid"] is True
    payload = svc.last_subscribe_kwargs or {}
    assert payload.get("direction") == expected_direction


@pytest.fixture
def alert_storage(tmp_path, monkeypatch):
    from backend.services import entitlements, subscription_service

    monkeypatch.setattr(entitlements, "PLANS_FILE", tmp_path / "plans.json")
    plans = entitlements.EntitlementsService()
    monkeypatch.setattr(entitlements, "_service_instance", plans)
    monkeypatch.setattr(subscription_service, "SUBSCRIPTIONS_FILE", tmp_path / "subscriptions.json")
    svc = subscription_service.SubscriptionService()
    monkeypatch.setattr(alert_action_module, "get_subscription_service", lambda: svc)
    return plans, svc


def _alert_state(ticker="TSLA", *, user_id="alice", role="user"):
    return {
        "user_email": "alice@example.invalid",
        "thread_id": "private:unrelated_user:default",
        "ui_context": {"_authenticated_user": {"user_id": user_id, "role": role}},
        "alert_params": {"ticker": ticker, "alert_mode": "price_change_pct", "price_threshold": 4.0},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("ticker", ["BAD TICKER", ".AAPL", "A" * 21])
async def test_chat_invalid_ticker_cannot_consume_remaining_quota(alert_storage, ticker):
    plans, svc = alert_storage
    plans.set_plan("alice", "free")
    email = "alice@example.invalid"
    for existing in ("AAPL", "MSFT"):
        assert svc.subscribe(email, existing)
    before = svc.subscriptions_file.read_bytes()

    result = await alert_action_module.alert_action(_alert_state(ticker))

    assert result["alert_valid"] is False
    assert svc.subscriptions_file.read_bytes() == before
    valid = await alert_action_module.alert_action(_alert_state("NVDA"))
    assert valid["alert_valid"] is True
    assert len(svc.get_subscriptions(email)) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,field", [
    ("price_target", "price_target"), ("price_change_pct", "price_threshold"),
])
@pytest.mark.parametrize("value", [None, 0, -1, "0", "bad", True, float("inf"), float("nan")])
async def test_invalid_chat_alert_threshold_preserves_subscription(alert_storage, monkeypatch, mode, field, value):
    _, svc = alert_storage
    email = "alice@example.invalid"
    assert svc.subscribe(email, "AAPL", alert_types=["news", "risk"], risk_threshold="critical")
    before = svc.subscriptions_file.read_bytes()

    def unexpected_quote(_ticker):
        raise AssertionError("invalid thresholds must be rejected before fetching quotes")

    monkeypatch.setattr(alert_action_module, "fetch_price_snapshot", unexpected_quote)
    state = _alert_state("AAPL")
    state["alert_params"] = {"ticker": "AAPL", "alert_mode": mode, field: value}

    result = await alert_action_module.alert_action(state)

    assert result["alert_valid"] is False
    assert result["skip_session_context"] is True
    assert "已为" not in result["artifacts"]["draft_markdown"]
    assert svc.subscriptions_file.read_bytes() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,field", [
    ("price_target", "price_target"), ("price_change_pct", "price_threshold"),
])
@pytest.mark.parametrize("value", [0.01, "0.5"])
async def test_chat_alert_accepts_positive_thresholds(alert_storage, mode, field, value):
    _, svc = alert_storage
    state = _alert_state()
    state["alert_params"] = {"ticker": "TSLA", "alert_mode": mode, field: value, "direction": "above"}

    result = await alert_action_module.alert_action(state)

    assert result["alert_valid"] is True
    saved = svc.get_subscriptions("alice@example.invalid")[0]
    assert saved["alert_mode"] == mode
    assert saved[field] == float(value)


@pytest.mark.asyncio
@pytest.mark.parametrize("price", [None, 0, -1, True, "bad", float("inf"), float("nan")])
async def test_missing_valid_quote_cannot_overwrite_alert_direction(alert_storage, monkeypatch, price):
    _, svc = alert_storage
    email = "alice@example.invalid"
    assert svc.subscribe(
        email, "AAPL", alert_types=["news", "risk", "price_change"],
        alert_mode="price_target", price_target=80.0, direction="below", risk_threshold="critical",
    )
    before = svc.subscriptions_file.read_bytes()
    snapshot = None if price is None else PriceSnapshot(ticker="AAPL", price=price, change_percent=0.0)
    monkeypatch.setattr(alert_action_module, "fetch_price_snapshot", lambda _ticker: snapshot)
    state = _alert_state("AAPL")
    state["alert_params"] = {"ticker": "AAPL", "alert_mode": "price_target", "price_target": 90.0}

    result = await alert_action_module.alert_action(state)

    assert result["alert_valid"] is False
    assert result["skip_session_context"] is True
    markdown = result["artifacts"]["draft_markdown"]
    assert "涨到" in markdown and "跌到" in markdown
    assert "已为" not in markdown
    assert svc.subscriptions_file.read_bytes() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("direction", ["above", "below"])
async def test_explicit_alert_direction_does_not_need_a_quote(alert_storage, monkeypatch, direction):
    _, svc = alert_storage

    def unexpected_quote(_ticker):
        raise AssertionError("explicit directions must not depend on quote availability")

    monkeypatch.setattr(alert_action_module, "fetch_price_snapshot", unexpected_quote)
    state = _alert_state("AAPL")
    state["alert_params"] = {
        "ticker": "AAPL", "alert_mode": "price_target", "price_target": 90.0, "direction": direction,
    }

    result = await alert_action_module.alert_action(state)

    assert result["alert_valid"] is True
    saved = svc.get_subscriptions("alice@example.invalid")[0]
    assert saved["price_target"] == 90.0
    assert saved["direction"] == direction


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_subscription", [False, True])
async def test_unrelated_quote_cannot_supply_chat_alert_direction(alert_storage, monkeypatch, existing_subscription):
    _, svc = alert_storage
    email = "alice@example.invalid"
    for ticker in ("MSFT", "NVDA"):
        assert svc.subscribe(email, ticker)
    if existing_subscription:
        assert svc.subscribe(email, "AAPL", alert_mode="price_target", price_target=80.0, direction="below")
    before = svc.subscriptions_file.read_bytes()
    monkeypatch.setattr(
        alert_action_module, "fetch_price_snapshot",
        lambda _ticker: PriceSnapshot(ticker="TSLA", price=100.0, change_percent=0.0),
    )
    state = _alert_state("AAPL")
    state["alert_params"] = {"ticker": "AAPL", "alert_mode": "price_target", "price_target": 220.0}

    result = await alert_action_module.alert_action(state)

    assert result["alert_valid"] is False
    assert result["skip_session_context"] is True
    assert svc.subscriptions_file.read_bytes() == before


@pytest.mark.asyncio
async def test_quote_ticker_case_and_spaces_do_not_block_direction_inference(alert_storage, monkeypatch):
    _, svc = alert_storage
    monkeypatch.setattr(
        alert_action_module, "fetch_price_snapshot",
        lambda _ticker: PriceSnapshot(ticker=" aapl ", price=100.0, change_percent=0.0),
    )
    state = _alert_state("AAPL")
    state["alert_params"] = {"ticker": "AAPL", "alert_mode": "price_target", "price_target": 80.0}

    result = await alert_action_module.alert_action(state)

    assert result["alert_valid"] is True
    assert svc.get_subscriptions("alice@example.invalid")[0]["direction"] == "below"


@pytest.mark.asyncio
@pytest.mark.parametrize("plan,limit", [("free", 3), ("pro", 50), ("team", 200)])
async def test_chat_alert_cannot_exceed_plan_limit(alert_storage, plan, limit):
    plans, svc = alert_storage
    plans.set_plan("alice", plan)
    for index in range(limit):
        assert svc.subscribe("alice@example.invalid", f"T{index}")
    before = svc.subscriptions_file.read_bytes()

    result = await alert_action_module.alert_action(_alert_state())

    assert result["alert_valid"] is False
    assert result["skip_session_context"] is True
    markdown = result["artifacts"]["draft_markdown"]
    assert "上限" in markdown
    assert str(limit) in markdown
    assert "已为" not in markdown
    assert len(svc.get_subscriptions("alice@example.invalid")) == limit
    assert svc.subscriptions_file.read_bytes() == before


@pytest.mark.asyncio
async def test_chat_alert_can_update_existing_ticker_at_limit(alert_storage):
    plans, svc = alert_storage
    plans.set_plan("alice", "free")
    for ticker in ("AAPL", "MSFT", "NVDA"):
        assert svc.subscribe("alice@example.invalid", ticker, alert_types=["news"])

    result = await alert_action_module.alert_action(_alert_state("AAPL"))

    assert result["alert_valid"] is True
    subscriptions = svc.get_subscriptions("alice@example.invalid")
    assert len(subscriptions) == 3
    updated = next(sub for sub in subscriptions if sub["ticker"] == "AAPL")
    assert updated["price_threshold"] == 4.0
    assert sorted(updated["alert_types"]) == ["news", "price_change"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["price_change_pct", "price_target"])
async def test_chat_alert_preserves_subscription_update_before_write(alert_storage, monkeypatch, mode):
    from backend.services.subscription_service import SubscriptionService

    _, svc = alert_storage
    email = "alice@example.invalid"
    assert svc.subscribe(email, "AAPL", alert_types=["news"], risk_threshold="medium")
    other_svc = SubscriptionService()
    original_subscribe = svc.subscribe

    def subscribe_after_other_update(**kwargs):
        # 模拟另一实例在价格提醒写入前更新风险提醒。
        assert other_svc.subscribe(
            email, "AAPL", alert_types=["news", "risk"], risk_threshold="critical",
        )
        return original_subscribe(**kwargs)

    monkeypatch.setattr(svc, "subscribe", subscribe_after_other_update)
    state = _alert_state("AAPL")
    if mode == "price_target":
        state["alert_params"] = {
            "ticker": "AAPL", "alert_mode": mode, "price_target": 120.0, "direction": "above",
        }

    result = await alert_action_module.alert_action(state)

    assert result["alert_valid"] is True
    saved = other_svc.get_subscriptions(email)[0]
    assert sorted(saved["alert_types"]) == ["news", "price_change", "risk"]
    assert saved["risk_threshold"] == "critical"
    assert saved["alert_mode"] == mode
    price_field = "price_target" if mode == "price_target" else "price_threshold"
    assert saved[price_field] == state["alert_params"][price_field]
    assert "risk" in result["artifacts"]["draft_markdown"]


@pytest.mark.asyncio
@pytest.mark.parametrize("plan,role", [("pro", "user"), ("team", "user"), ("free", "admin"), ("free", "internal")])
async def test_chat_alert_respects_paid_and_privileged_identity(alert_storage, plan, role):
    plans, svc = alert_storage
    plans.set_plan("alice", plan)
    for ticker in ("AAPL", "MSFT", "NVDA"):
        assert svc.subscribe("alice@example.invalid", ticker)

    result = await alert_action_module.alert_action(_alert_state(role=role))

    assert result["alert_valid"] is True
    assert len(svc.get_subscriptions("alice@example.invalid")) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("ui_context", [None, {}, {"user_id": "unrelated_user", "role": "admin", "max_subscriptions": -1}, {"_authenticated_user": {"role": "admin"}}])
async def test_chat_alert_without_authenticated_identity_uses_free_limit(alert_storage, ui_context):
    plans, svc = alert_storage
    plans.set_plan("unrelated_user", "admin")
    for ticker in ("AAPL", "MSFT", "NVDA"):
        assert svc.subscribe("alice@example.invalid", ticker)
    state = _alert_state()
    state["ui_context"] = ui_context

    result = await alert_action_module.alert_action(state)

    assert result["alert_valid"] is False
    assert len(svc.get_subscriptions("alice@example.invalid")) == 3


@pytest.mark.asyncio
async def test_concurrent_chat_alerts_cannot_claim_the_same_remaining_slot(alert_storage, monkeypatch):
    from backend.services.subscription_service import SubscriptionService

    plans, svc = alert_storage
    plans.set_plan("alice", "free")
    for ticker in ("AAPL", "MSFT"):
        assert svc.subscribe("alice@example.invalid", ticker)
    other_svc = SubscriptionService()
    services = iter((svc, other_svc))
    monkeypatch.setattr(alert_action_module, "get_subscription_service", lambda: next(services))

    both_writing = threading.Barrier(2)
    original_subscribe = SubscriptionService.subscribe

    def subscribe_after_both_attempt(service, **kwargs):
        both_writing.wait(timeout=10)
        return original_subscribe(service, **kwargs)

    with monkeypatch.context() as concurrent_writes:
        concurrent_writes.setattr(SubscriptionService, "subscribe", subscribe_after_both_attempt)
        results = await asyncio.gather(
            alert_action_module.alert_action(_alert_state("NVDA")),
            alert_action_module.alert_action(_alert_state("TSLA")),
        )

    assert sorted(result["alert_valid"] for result in results) == [False, True]
    assert len(svc.get_subscriptions("alice@example.invalid")) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("plan,expected", [("free", False), ("pro", True)])
async def test_graph_alert_uses_authenticated_plan_after_context_normalization(alert_storage, monkeypatch, plan, expected):
    from backend.graph.runner import GraphRunner

    initial_state = importlib.import_module("backend.graph.nodes.build_initial_state")
    monkeypatch.setattr(initial_state, "load_memory_context", lambda **_kwargs: {})
    plans, svc = alert_storage
    plans.set_plan("alice", plan)
    for ticker in ("AAPL", "MSFT", "NVDA"):
        assert svc.subscribe("alice@example.invalid", ticker)
    identity = {"user_id": "alice", "role": "user"}

    state = await GraphRunner.create().ainvoke(
        thread_id="private:unrelated_user:default",
        query="TSLA 涨跌超过 4% 提醒我",
        ui_context={"user_email": "alice@example.invalid", "_authenticated_user": identity},
        confirmation_mode="skip",
    )

    assert state["ui_context"]["_authenticated_user"] == identity
    assert state["alert_valid"] is expected
    assert len(svc.get_subscriptions("alice@example.invalid")) == 3 + int(expected)


@pytest.mark.asyncio
@pytest.mark.parametrize("unit", ["%", "％", " per cent"])
@pytest.mark.parametrize("threshold,expected_threshold", [("12.5", 12.5), (".5", 0.5), ("+3", 3.0), ("+.5", 0.5)])
async def test_graph_percentage_alert_persists_percentage_trigger(alert_storage, monkeypatch, unit, threshold, expected_threshold):
    from backend.graph.runner import GraphRunner

    initial_state = importlib.import_module("backend.graph.nodes.build_initial_state")
    monkeypatch.setattr(initial_state, "load_memory_context", lambda **_kwargs: {})
    _, svc = alert_storage

    state = await GraphRunner.create().ainvoke(
        thread_id="private:alice:default",
        query=f"Notify me if AAPL moves over {threshold}{unit}",
        ui_context={
            "active_symbol": "AAPL", "user_email": "alice@example.invalid",
            "_authenticated_user": {"user_id": "alice", "role": "user"},
        },
        confirmation_mode="skip",
    )

    assert state["alert_valid"] is True
    saved = svc.get_subscriptions("alice@example.invalid")[0]
    assert saved["alert_mode"] == "price_change_pct"
    assert saved["price_threshold"] == expected_threshold
    assert saved["price_target"] is None
    assert f"{expected_threshold}%" in state["artifacts"]["draft_markdown"]


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_subscription", [False, True])
async def test_graph_multiple_tickers_cannot_partially_write_subscriptions(alert_storage, monkeypatch, existing_subscription):
    from backend.graph.runner import GraphRunner

    initial_state = importlib.import_module("backend.graph.nodes.build_initial_state")
    monkeypatch.setattr(initial_state, "load_memory_context", lambda **_kwargs: {})
    plans, svc = alert_storage
    plans.set_plan("alice", "free")
    email = "alice@example.invalid"
    for ticker in ("MSFT", "NVDA"):
        assert svc.subscribe(email, ticker)
    if existing_subscription:
        assert svc.subscribe(email, "AAPL", alert_mode="price_target", price_target=80.0, direction="below")
    before = svc.subscriptions_file.read_bytes()
    runner = GraphRunner.create()
    ui_context = {
        "user_email": email,
        "_authenticated_user": {"user_id": "alice", "role": "user"},
    }

    result = await runner.ainvoke(
        thread_id="private:alice:default", query="AAPL 和 TSLA 涨到 220 时提醒我",
        ui_context=ui_context, confirmation_mode="skip",
    )

    assert svc.subscriptions_file.read_bytes() == before
    assert result["alert_valid"] is False
    assert result["clarify"]["reason"] == "alert_multiple_tickers"
    spans = [span.get("node") for span in result["trace"]["spans"]]
    assert "alert_action" not in spans
    if not existing_subscription:
        valid = await runner.ainvoke(
            thread_id="private:alice:default", query="AAPL 涨到 220 时提醒我",
            ui_context=ui_context, confirmation_mode="skip",
        )
        assert valid["alert_valid"] is True
        assert len(svc.get_subscriptions(email)) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("query", [
    "TSLA 涨到 0 美元提醒我",
    "TSLA 涨跌超过 0% 提醒我",
    "TSLA 涨到 1,00 美元时提醒我",
    "TSLA 涨到 1,0000 美元时提醒我",
    "TSLA 涨到 1，000 美元时提醒我",
    "TSLA 涨到 1万元时提醒我",
    "Notify me when TSLA goes above $2k",
    "Notify me when TSLA goes above 220-230",
    "Notify me when TSLA goes above 220 to $230",
    "Notify me when TSLA goes above .5 to $.75",
    "TSLA 涨到 1/2 元时提醒我",
    "Notify me when TSLA drops below -80",
    "TSLA 跌到-.5元时提醒我",
    "Notify me when TSLA goes above 220 cents",
    "TSLA 涨到220美分时提醒我",
    "TSLA 涨到220分钱时提醒我",
    "Notify me when TSLA goes above 220 eurocents",
    "Notify me when TSLA goes above 220 US cents",
    "TSLA 涨到220元与230元时提醒我",
    "Notify me when TSLA goes above 220 and 230",
    "Notify me when TSLA goes above 220 EUR",
    "Notify me when TSLA goes above 220 £",
    "TSLA 涨幅不超过3%时提醒我",
    "Notify me if TSLA does not move over 3%",
    "Notify me if TSLA moves 3% to 5%",
    "TSLA 涨跌超过3％～5％时提醒我",
    "Notify me when TSLA goes above 220 USD to 230 USD",
    "TSLA 涨到220元～230元时提醒我",
    "Notify me if TSLA moves 3 percentiles",
    "Notify me if TSLA changes 3 pct_change",
    "Notify me when TSLA rises to 220 dollars and 50 cents",
    "TSLA 涨到220元5角时提醒我",
    "TSLA 涨到220日元时提醒我",
    "TSLA 涨到220港元时提醒我",
    "Notify me if TSLA falls -3%",
    "TSLA 不 超过3%时提醒我",
    "TSLA 不涨到220元时提醒我",
    "TSLA 没有跌到220元时提醒我",
    "Notify me when TSLA does not reach 220",
    "TSLA 没有 涨3%时提醒我",
    "Notify me if TSLA moves over -.5%",
    "Notify me if TSLA moves 3% to -5%",
    "Notify me if TSLA moves .5% to +.75%",
    "Notify me when TSLA goes above 220 to -80",
    "Notify me when TSLA goes above 220 to +230",
    "Notify me when TSLA goes above 220 USD to $-80 USD",
])
async def test_graph_invalid_threshold_does_not_consume_remaining_quota(alert_storage, monkeypatch, query):
    from backend.graph.runner import GraphRunner

    initial_state = importlib.import_module("backend.graph.nodes.build_initial_state")
    monkeypatch.setattr(initial_state, "load_memory_context", lambda **_kwargs: {})
    plans, svc = alert_storage
    plans.set_plan("alice", "free")
    for ticker in ("AAPL", "MSFT"):
        assert svc.subscribe("alice@example.invalid", ticker, price_threshold=4.0)
    before = svc.subscriptions_file.read_bytes()
    runner = GraphRunner.create()
    ui_context = {
        "user_email": "alice@example.invalid",
        "_authenticated_user": {"user_id": "alice", "role": "user"},
    }

    invalid = await runner.ainvoke(
        thread_id="private:alice:default", query=query,
        ui_context=ui_context, confirmation_mode="skip",
    )

    assert invalid["alert_valid"] is False
    assert svc.subscriptions_file.read_bytes() == before
    valid = await runner.ainvoke(
        thread_id="private:alice:default", query="NVDA 涨跌超过 4% 提醒我",
        ui_context=ui_context, confirmation_mode="skip",
    )
    assert valid["alert_valid"] is True
    assert {sub["ticker"] for sub in svc.get_subscriptions("alice@example.invalid")} == {"AAPL", "MSFT", "NVDA"}


@pytest.mark.asyncio
async def test_graph_currency_only_subject_cannot_consume_alert_quota(alert_storage, monkeypatch):
    from backend.graph.runner import GraphRunner

    initial_state = importlib.import_module("backend.graph.nodes.build_initial_state")
    monkeypatch.setattr(initial_state, "load_memory_context", lambda **_kwargs: {})
    monkeypatch.setattr(
        alert_action_module, "fetch_price_snapshot",
        lambda ticker: PriceSnapshot(ticker=ticker, price=100.0, change_percent=0.0),
    )
    plans, svc = alert_storage
    plans.set_plan("alice", "free")
    email = "alice@example.invalid"
    for ticker in ("AAPL", "MSFT"):
        assert svc.subscribe(email, ticker)
    before = svc.subscriptions_file.read_bytes()

    state = await GraphRunner.create().ainvoke(
        thread_id="private:alice:default", query="Notify me at 220 USD",
        ui_context={
            "user_email": email,
            "_authenticated_user": {"user_id": "alice", "role": "user"},
        },
        confirmation_mode="skip",
    )

    assert state["alert_valid"] is False
    assert state["clarify"]["needed"] is True
    assert svc.subscriptions_file.read_bytes() == before
    assert "alert_action" not in [span.get("node") for span in state["trace"]["spans"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_subscription", [False, True])
@pytest.mark.parametrize("query", [
    "Notify me about TSLA turnover 220",
    "Notify me about TSLA rollover 5%",
])
async def test_graph_embedded_english_trigger_cannot_write_subscriptions(alert_storage, monkeypatch, query, existing_subscription):
    from backend.graph.runner import GraphRunner

    initial_state = importlib.import_module("backend.graph.nodes.build_initial_state")
    monkeypatch.setattr(initial_state, "load_memory_context", lambda **_kwargs: {})
    plans, svc = alert_storage
    plans.set_plan("alice", "free")
    email = "alice@example.invalid"
    for ticker in ("AAPL", "MSFT"):
        assert svc.subscribe(email, ticker)
    if existing_subscription:
        assert svc.subscribe(email, "TSLA", alert_mode="price_target", price_target=80.0, direction="below")
    before = svc.subscriptions_file.read_bytes()
    runner = GraphRunner.create()
    ui_context = {
        "active_symbol": "TSLA", "user_email": email,
        "_authenticated_user": {"user_id": "alice", "role": "user"},
    }

    state = await runner.ainvoke(
        thread_id="private:alice:default", query=query,
        ui_context=ui_context, confirmation_mode="skip",
    )

    assert svc.subscriptions_file.read_bytes() == before
    assert state["alert_valid"] is False
    assert state["clarify"]["needed"] is True
    spans = [span.get("node") for span in state["trace"]["spans"]]
    assert "alert_action" not in spans

    if not existing_subscription:
        valid = await runner.ainvoke(
            thread_id="private:alice:default", query="TSLA 涨跌超过 4% 提醒我",
            ui_context=ui_context, confirmation_mode="skip",
        )
        assert valid["alert_valid"] is True
        assert len(svc.get_subscriptions(email)) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_subscription", [False, True])
@pytest.mark.parametrize("query", [
    "Notify me when TSLA goes above 1e3 USD",
    "TSLA 涨到 2e-3 元时提醒我",
])
async def test_graph_scientific_target_cannot_write_subscriptions(alert_storage, monkeypatch, query, existing_subscription):
    from backend.graph.runner import GraphRunner

    initial_state = importlib.import_module("backend.graph.nodes.build_initial_state")
    monkeypatch.setattr(initial_state, "load_memory_context", lambda **_kwargs: {})
    plans, svc = alert_storage
    plans.set_plan("alice", "free")
    email = "alice@example.invalid"
    for ticker in ("AAPL", "MSFT"):
        assert svc.subscribe(email, ticker)
    if existing_subscription:
        assert svc.subscribe(email, "TSLA", alert_mode="price_target", price_target=80.0, direction="below")
    before = svc.subscriptions_file.read_bytes()
    runner = GraphRunner.create()
    ui_context = {
        "active_symbol": "TSLA", "user_email": email,
        "_authenticated_user": {"user_id": "alice", "role": "user"},
    }

    state = await runner.ainvoke(
        thread_id="private:alice:default", query=query,
        ui_context=ui_context, confirmation_mode="skip",
    )

    assert state["alert_valid"] is False
    assert state["clarify"]["needed"] is True
    assert svc.subscriptions_file.read_bytes() == before
    spans = [span.get("node") for span in state["trace"]["spans"]]
    assert "alert_action" not in spans

    if not existing_subscription:
        valid = await runner.ainvoke(
            thread_id="private:alice:default", query="TSLA 涨到 1000 元时提醒我",
            ui_context=ui_context, confirmation_mode="skip",
        )
        assert valid["alert_valid"] is True
        subscriptions = svc.get_subscriptions(email)
        assert len(subscriptions) == 3
        saved = next(sub for sub in subscriptions if sub["ticker"] == "TSLA")
        assert saved["price_target"] == 1000.0


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_subscription", [False, True])
@pytest.mark.parametrize("query", [
    "TSLA 涨到 220 或跌到 180 时提醒我",
    "TSLA 涨到220元或涨跌超过3%时提醒我",
    "Notify me if TSLA moves 3% or goes below 80",
    "Notify me if TSLA moves over 3% or falls 5%",
    "TSLA 涨到 220 或跌到 220 时提醒我",
    "TSLA 涨到 220 或跌至 220 时提醒我",
    "TSLA 涨至 220 或跌到 220 时提醒我",
    "Notify me when TSLA goes above $220 or below 180",
    "Notify me when TSLA goes above 220 or below $180",
    "Notify me when TSLA goes above $220 or below $220",
    "TSLA 低于220元或涨到220元时提醒我",
    "Notify me when TSLA is less than 220 or goes above 220",
    "Notify me when TSLA is <= 220 or above 220",
    "Notify me when TSLA is ≥ 220 or below 220",
    "Notify me when TSLA is not above 220 or above 220",
    "TSLA 不高于220元或高于220元时提醒我",
    "Notify me when TSLA goes above 220 or below .5",
    "Notify me when TSLA goes above 220 or below -80",
    "Notify me if TSLA moves .5% or rises 3%",
    "Notify me if TSLA moves 3% or rises .5%",
    "TSLA 涨跌超过.5%或涨跌超过3%时提醒我",
    "Notify me if TSLA moves +3% or falls 5%",
    "Notify me if TSLA moves over -3% or falls 5%",
    "Notify me if TSLA moves 5% or rises +3%",
    "TSLA 涨跌超过+3%或跌-5%时提醒我",
    "TSLA 不 高于220元或高于220元时提醒我",
    "TSLA 低于220元或不 低于220元时提醒我",
    "TSLA 没有高于220元或高于220元时提醒我",
    "TSLA 低于220元或未低于220元时提醒我",
    "Notify me when TSLA is not going above 220 or above 220",
    "Notify me when TSLA is below 220 or not going below 220",
    "Notify me when TSLA doesn't go above 220 or goes above 220",
    "Notify me when TSLA goes below 220 or does not fall below 220",
    "Notify me if TSLA moves 3% or rises 3-5%",
    "Notify me if TSLA rises 3-5% or moves 3%",
    "TSLA 涨跌超过3%或涨跌超过3至5%时提醒我",
])
async def test_graph_conflicting_thresholds_cannot_write_subscriptions(alert_storage, monkeypatch, query, existing_subscription):
    from backend.graph.runner import GraphRunner

    initial_state = importlib.import_module("backend.graph.nodes.build_initial_state")
    monkeypatch.setattr(initial_state, "load_memory_context", lambda **_kwargs: {})
    plans, svc = alert_storage
    plans.set_plan("alice", "free")
    email = "alice@example.invalid"
    for ticker in ("AAPL", "MSFT"):
        assert svc.subscribe(email, ticker)
    if existing_subscription:
        assert svc.subscribe(email, "TSLA", alert_mode="price_target", price_target=80.0, direction="below")
    before = svc.subscriptions_file.read_bytes()
    runner = GraphRunner.create()
    ui_context = {
        "active_symbol": "TSLA", "user_email": email,
        "_authenticated_user": {"user_id": "alice", "role": "user"},
    }

    state = await runner.ainvoke(
        thread_id="private:alice:default", query=query,
        ui_context=ui_context, confirmation_mode="skip",
    )

    assert svc.subscriptions_file.read_bytes() == before
    assert state["alert_valid"] is False
    assert state["clarify"]["reason"] == "alert_conflicting_thresholds"
    spans = [span.get("node") for span in state["trace"]["spans"]]
    assert "alert_action" not in spans

    if not existing_subscription:
        valid = await runner.ainvoke(
            thread_id="private:alice:default", query="TSLA 涨跌超过 4% 提醒我",
            ui_context=ui_context, confirmation_mode="skip",
        )
        assert valid["alert_valid"] is True
        assert len(svc.get_subscriptions(email)) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("query,expected_price", [
    ("TSLA 涨到 1,000 美元时提醒我", 1000.0),
    ("Notify me when TSLA goes below 12,500.75 USD", 12500.75),
    ("Notify me when TSLA goes below $12,500.75", 12500.75),
])
async def test_graph_grouped_target_price_uses_full_amount(alert_storage, monkeypatch, query, expected_price):
    from backend.graph.runner import GraphRunner

    initial_state = importlib.import_module("backend.graph.nodes.build_initial_state")
    monkeypatch.setattr(initial_state, "load_memory_context", lambda **_kwargs: {})
    plans, svc = alert_storage
    plans.set_plan("alice", "free")
    email = "alice@example.invalid"
    for ticker in ("AAPL", "MSFT"):
        assert svc.subscribe(email, ticker)

    state = await GraphRunner.create().ainvoke(
        thread_id="private:alice:default", query=query,
        ui_context={
            "active_symbol": "TSLA", "user_email": email,
            "_authenticated_user": {"user_id": "alice", "role": "user"},
        },
        confirmation_mode="skip",
    )

    assert state["alert_valid"] is True
    subscriptions = svc.get_subscriptions(email)
    assert len(subscriptions) == 3
    saved = next(sub for sub in subscriptions if sub["ticker"] == "TSLA")
    assert saved["alert_mode"] == "price_target"
    assert saved["price_target"] == expected_price


@pytest.mark.asyncio
@pytest.mark.parametrize("query,target,expected_direction", [
    ("Notify me when AAPL goes above 220 so I can understand the move", 220.0, "above"),
    ("Notify me when AAPL hits 80; give me an overview", 80.0, "below"),
    ("Notify me when AAPL drops to 220", 220.0, "below"),
    ("Notify me when AAPL falls to 220", 220.0, "below"),
    ("Notify me when AAPL dips to 220", 220.0, "below"),
    ("Notify me when AAPL rises to 80", 80.0, "above"),
    ("Notify me when AAPL climbs to 80", 80.0, "above"),
    ("Notify me when AAPL goes above 220; I am under my budget", 220.0, "above"),
    ("Notify me when AAPL rises to 80; costs are under control", 80.0, "above"),
    ("Notify me when AAPL hits 80; show performance over time", 80.0, "below"),
])
async def test_graph_english_prose_keeps_correct_direction_at_quota(alert_storage, monkeypatch, query, target, expected_direction):
    from backend.graph.runner import GraphRunner

    initial_state = importlib.import_module("backend.graph.nodes.build_initial_state")
    monkeypatch.setattr(initial_state, "load_memory_context", lambda **_kwargs: {})
    monkeypatch.setattr(
        alert_action_module, "fetch_price_snapshot",
        lambda ticker: PriceSnapshot(ticker=ticker, price=100.0, change_percent=0.0),
    )
    plans, svc = alert_storage
    plans.set_plan("alice", "free")
    email = "alice@example.invalid"
    assert svc.subscribe(email, "AAPL", alert_mode="price_target", price_target=80.0, direction="below")
    for ticker in ("MSFT", "NVDA"):
        assert svc.subscribe(email, ticker)

    state = await GraphRunner.create().ainvoke(
        thread_id="private:alice:default", query=query,
        ui_context={
            "active_symbol": "AAPL", "user_email": email,
            "_authenticated_user": {"user_id": "alice", "role": "user"},
        },
        confirmation_mode="skip",
    )

    assert state["alert_valid"] is True
    subscriptions = svc.get_subscriptions(email)
    assert len(subscriptions) == 3
    saved = next(sub for sub in subscriptions if sub["ticker"] == "AAPL")
    assert saved["price_target"] == target
    assert saved["direction"] == expected_direction


@pytest.mark.asyncio
async def test_graph_background_direction_without_quote_cannot_consume_quota(alert_storage, monkeypatch):
    from backend.graph.runner import GraphRunner

    initial_state = importlib.import_module("backend.graph.nodes.build_initial_state")
    monkeypatch.setattr(initial_state, "load_memory_context", lambda **_kwargs: {})
    monkeypatch.setattr(alert_action_module, "fetch_price_snapshot", lambda _ticker: None)
    plans, svc = alert_storage
    plans.set_plan("alice", "free")
    email = "alice@example.invalid"
    for ticker in ("MSFT", "NVDA"):
        assert svc.subscribe(email, ticker)
    before = svc.subscriptions_file.read_bytes()
    runner = GraphRunner.create()
    ui_context = {
        "active_symbol": "AAPL", "user_email": email,
        "_authenticated_user": {"user_id": "alice", "role": "user"},
    }

    ambiguous = await runner.ainvoke(
        thread_id="private:alice:default",
        query="Notify me when AAPL hits 80; show performance over time",
        ui_context=ui_context, confirmation_mode="skip",
    )

    assert ambiguous["alert_valid"] is False
    assert svc.subscriptions_file.read_bytes() == before

    explicit = await runner.ainvoke(
        thread_id="private:alice:default", query="Notify me when AAPL drops to 80",
        ui_context=ui_context, confirmation_mode="skip",
    )

    assert explicit["alert_valid"] is True
    subscriptions = svc.get_subscriptions(email)
    assert len(subscriptions) == 3
    saved = next(sub for sub in subscriptions if sub["ticker"] == "AAPL")
    assert saved["price_target"] == 80.0
    assert saved["direction"] == "below"


@pytest.mark.asyncio
@pytest.mark.parametrize("query,target,expected_direction", [
    ("AAPL 跌到 90 美元提醒我", 90.0, "below"),
    ("AAPL 跌至 90 美元提醒我", 90.0, "below"),
    ("AAPL 下跌至90美元提醒我", 90.0, "below"),
    ("AAPL 涨至 120 美元提醒我", 120.0, "above"),
    ("AAPL 上涨至120美元提醒我", 120.0, "above"),
    ("Notify me when AAPL drops to 90", 90.0, "below"),
    ("Notify me when AAPL falls to 90", 90.0, "below"),
    ("Notify me when AAPL dips to 90", 90.0, "below"),
    ("Notify me when AAPL rises to 120", 120.0, "above"),
    ("Notify me when AAPL climbs to 120", 120.0, "above"),
    ("Notify me when AAPL drops to $90", 90.0, "below"),
    ("Notify me when AAPL goes above $120", 120.0, "above"),
    ("AAPL 低于90美元提醒我", 90.0, "below"),
    ("AAPL 突破120美元提醒我", 120.0, "above"),
    ("Notify me when AAPL is less than 90", 90.0, "below"),
    ("Notify me when AAPL is greater than 120", 120.0, "above"),
    ("Notify me when AAPL < 90", 90.0, "below"),
    ("Notify me when AAPL >= 120", 120.0, "above"),
    ("Notify me when AAPL is not above 90", 90.0, "below"),
    ("Notify me when AAPL is no less than 120", 120.0, "above"),
    ("Notify me when AAPL is not >=90", 90.0, "below"),
    ("Notify me when AAPL is not <120", 120.0, "above"),
    ("Notify me when AAPL isn't above 90", 90.0, "below"),
    ("Notify me when AAPL isn’t <120", 120.0, "above"),
    ("AAPL 不高于90元时提醒我", 90.0, "below"),
    ("AAPL 不低于120元时提醒我", 120.0, "above"),
    ("AAPL 不 高于90元时提醒我", 90.0, "below"),
    ("AAPL 不 大于90元时提醒我", 90.0, "below"),
    ("AAPL 不 低于120元时提醒我", 120.0, "above"),
    ("AAPL 不 小于120元时提醒我", 120.0, "above"),
    ("AAPL 没有高于90元时提醒我", 90.0, "below"),
    ("AAPL 没 低于120元时提醒我", 120.0, "above"),
    ("AAPL 未高于90元时提醒我", 90.0, "below"),
    ("AAPL 未低于120元时提醒我", 120.0, "above"),
    ("Notify me when AAPL is not going above 90", 90.0, "below"),
    ("Notify me when AAPL does not go below 120", 120.0, "above"),
    ("Notify me when AAPL isn't going over 90", 90.0, "below"),
    ("Notify me when AAPL isn’t going under 120", 120.0, "above"),
    ("Notify me when AAPL doesn't go above 90", 90.0, "below"),
    ("Notify me when AAPL does not rise above 90", 90.0, "below"),
    ("Notify me when AAPL doesn’t fall below 120", 120.0, "above"),
    ("AAPL 不>=90元时提醒我", 90.0, "below"),
    ("AAPL 不<=120元时提醒我", 120.0, "above"),
    ("Notify me when AAPL drops below .5", 0.5, "below"),
    ("Set a reminder when AAPL drops below 90", 90.0, "below"),
    ("Create a notification when AAPL goes above 120", 120.0, "above"),
    ("Keep reminding me when AAPL goes above 120", 120.0, "above"),
])
async def test_graph_missing_quote_requires_explicit_direction_before_subscribing(alert_storage, monkeypatch, query, target, expected_direction):
    from backend.graph.runner import GraphRunner

    initial_state = importlib.import_module("backend.graph.nodes.build_initial_state")
    monkeypatch.setattr(initial_state, "load_memory_context", lambda **_kwargs: {})
    monkeypatch.setattr(alert_action_module, "fetch_price_snapshot", lambda _ticker: None)
    _, svc = alert_storage
    runner = GraphRunner.create()
    ui_context = {
        "active_symbol": "AAPL", "user_email": "alice@example.invalid",
        "_authenticated_user": {"user_id": "alice", "role": "user"},
    }

    ambiguous = await runner.ainvoke(
        thread_id="private:alice:default", query="AAPL 到 90 美元提醒我",
        ui_context=ui_context, confirmation_mode="skip",
    )
    assert ambiguous["alert_valid"] is False
    assert svc.get_subscriptions("alice@example.invalid") == []

    explicit = await runner.ainvoke(
        thread_id="private:alice:default", query=query,
        ui_context=ui_context, confirmation_mode="skip",
    )
    assert explicit["alert_valid"] is True
    saved = svc.get_subscriptions("alice@example.invalid")[0]
    assert saved["price_target"] == target
    assert saved["direction"] == expected_direction


@pytest.mark.asyncio
@pytest.mark.parametrize("query", [
    "不要在 AAPL 涨到 220 时提醒我",
    "Don't notify me when AAPL goes above 220",
    "我不需要 AAPL 涨跌超过 3% 的提醒",
])
async def test_graph_declined_alert_cannot_modify_subscriptions(alert_storage, monkeypatch, query):
    from backend.graph.runner import GraphRunner

    initial_state = importlib.import_module("backend.graph.nodes.build_initial_state")
    monkeypatch.setattr(initial_state, "load_memory_context", lambda **_kwargs: {})
    _, svc = alert_storage
    assert svc.subscribe(
        "alice@example.invalid", "AAPL", alert_types=["news", "risk"], risk_threshold="critical",
    )
    before = svc.subscriptions_file.read_bytes()

    state = await GraphRunner.create().ainvoke(
        thread_id="private:alice:default", query=query,
        ui_context={
            "active_symbol": "AAPL", "user_email": "alice@example.invalid",
            "_authenticated_user": {"user_id": "alice", "role": "user"},
        },
        confirmation_mode="skip",
    )

    assert state["alert_valid"] is False
    assert svc.subscriptions_file.read_bytes() == before
    spans = [span.get("node") for span in state["trace"]["spans"]]
    assert "alert_extractor" in spans
    assert "alert_action" not in spans
    assert "未创建" in state["artifacts"]["draft_markdown"]


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_disabled", [False, True])
@pytest.mark.parametrize("query", [
    "I do not want an alert when AAPL goes above 220",
    "I don't need price alerts if AAPL moves over 3%",
    "No need for an alert when AAPL goes above 220",
    "不要在 AAPL 涨到 1,000 美元时提醒我",
    "Do not create an AAPL above 125.5 alert",
    "I no longer want an alert when AAPL goes above 220",
    "I no longer need price alerts if AAPL moves over 3%",
    "I do not want an AAPL alert when it goes above 220",
    "I no longer want the AAPL reminder when it drops below 80",
    "Do not send me notifications when AAPL goes above 220",
    "Do not keep reminding me when AAPL goes above 220",
    "I do not want to set an alert when AAPL goes above 220",
    "I don't need to create a notification when AAPL drops below 80",
    "I no longer want to keep reminding me when AAPL goes above 220",
    "No notifications when AAPL goes above 220",
    "No alerts when AAPL drops below 80",
    "No price reminders if AAPL moves over 3%",
])
async def test_graph_unwanted_alert_cannot_write_subscriptions(alert_storage, monkeypatch, query, existing_disabled):
    from backend.graph.runner import GraphRunner

    initial_state = importlib.import_module("backend.graph.nodes.build_initial_state")
    monkeypatch.setattr(initial_state, "load_memory_context", lambda **_kwargs: {})
    plans, svc = alert_storage
    plans.set_plan("alice", "free")
    email = "alice@example.invalid"
    for ticker in ("MSFT", "NVDA"):
        assert svc.subscribe(email, ticker)
    if existing_disabled:
        assert svc.subscribe(
            email, "AAPL", alert_types=["news", "price_change"],
            alert_mode="price_target", price_target=80.0, direction="below",
        )
        assert svc.toggle_subscription(email, "AAPL", enabled=False)
    before = svc.subscriptions_file.read_bytes()
    runner = GraphRunner.create()
    ui_context = {
        "active_symbol": "AAPL", "user_email": email,
        "_authenticated_user": {"user_id": "alice", "role": "user"},
    }

    state = await runner.ainvoke(
        thread_id="private:alice:default", query=query,
        ui_context=ui_context, confirmation_mode="skip",
    )

    assert svc.subscriptions_file.read_bytes() == before
    assert state["alert_valid"] is False
    spans = [span.get("node") for span in state["trace"]["spans"]]
    assert "alert_action" not in spans
    assert "未创建" in state["artifacts"]["draft_markdown"]
    if existing_disabled:
        saved = next(sub for sub in svc.get_subscriptions(email) if sub["ticker"] == "AAPL")
        assert saved["disabled"] is True
    else:
        created = await runner.ainvoke(
            thread_id="private:alice:default", query="AAPL 涨到 220 时提醒我",
            ui_context=ui_context, confirmation_mode="skip",
        )
        assert created["alert_valid"] is True
        assert len(svc.get_subscriptions(email)) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("existing_disabled", [False, True])
@pytest.mark.parametrize("query", [
    "取消 AAPL 涨到 220 的提醒",
    "取消 AAPL 涨到 125.5 的提醒",
    "Cancel AAPL alerts when it goes above 220",
    "关闭 AAPL 涨跌超过 3% 的预警",
    "Turn off AAPL alerts when it goes above 220",
    "Switch off AAPL alerts when it falls below 80",
    "Turn AAPL alerts off when it goes above 220",
    "Switch AAPL alerts off when it falls below 80",
    "Turn AAPL reminders off when it falls below 80",
    "Remove my reminder when AAPL goes above 220",
    "Stop notifying me when AAPL goes above 220",
    "Stop alerting me when AAPL goes above 220",
    "Stop reminding me when AAPL goes above 220",
])
async def test_graph_cancellation_cannot_modify_subscriptions(alert_storage, monkeypatch, query, existing_disabled):
    from backend.graph.runner import GraphRunner

    initial_state = importlib.import_module("backend.graph.nodes.build_initial_state")
    monkeypatch.setattr(initial_state, "load_memory_context", lambda **_kwargs: {})
    plans, svc = alert_storage
    plans.set_plan("alice", "free")
    email = "alice@example.invalid"
    for ticker in ("MSFT", "NVDA"):
        assert svc.subscribe(email, ticker)
    if existing_disabled:
        assert svc.subscribe(
            email, "AAPL", alert_types=["news", "price_change"],
            alert_mode="price_target", price_target=220.0, direction="above",
        )
        assert svc.toggle_subscription(email, "AAPL", enabled=False)
    before = svc.subscriptions_file.read_bytes()
    runner = GraphRunner.create()
    ui_context = {
        "active_symbol": "AAPL", "user_email": email,
        "_authenticated_user": {"user_id": "alice", "role": "user"},
    }

    state = await runner.ainvoke(
        thread_id="private:alice:default", query=query,
        ui_context=ui_context, confirmation_mode="skip",
    )

    assert svc.subscriptions_file.read_bytes() == before
    assert state["alert_valid"] is False
    if existing_disabled:
        saved = next(sub for sub in svc.get_subscriptions(email) if sub["ticker"] == "AAPL")
        assert saved["disabled"] is True
    spans = [span.get("node") for span in state["trace"]["spans"]]
    assert "alert_action" not in spans
    assert "提醒设置" in state["artifacts"]["draft_markdown"]

    if not existing_disabled:
        created = await runner.ainvoke(
            thread_id="private:alice:default", query="AAPL 涨到 220 时提醒我",
            ui_context=ui_context, confirmation_mode="skip",
        )
        assert created["alert_valid"] is True
        assert len(svc.get_subscriptions(email)) == 3
