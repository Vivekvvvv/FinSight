import pytest
from types import SimpleNamespace

from backend.services.rebalance_llm_enhancer import AgentBackedEnhancer


@pytest.mark.asyncio
async def test_rebalance_news_budget_preserves_candidate_order_and_unique_tickers(monkeypatch):
    gathered = []
    enhancer = AgentBackedEnhancer()
    async def gather(tickers):
        gathered.extend(tickers)
        return {}
    monkeypatch.setattr(enhancer, "_gather_agent_data", gather)
    tickers = ["AAPL", "MSFT", "AAPL", "TSLA", "GOOGL", "NVDA", "META", "AMZN"]
    candidates = [RebalanceAction(ticker=ticker, action=ActionType.REDUCE,
                    current_weight=60, target_weight=50, delta_weight=-10) for ticker in tickers]
    assert await enhancer(candidates, None, None) is candidates
    assert gathered == ["AAPL", "MSFT", "TSLA", "GOOGL", "NVDA", "META"]


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", [{"ticker": "MSFT"}, {"symbol": "MSFT"}, {"ticker": {}},
                                     {"ticker": "AAPL", "symbol": "MSFT"}])
async def test_other_instrument_news_cannot_supply_rebalance_evidence(identity):
    enhancer = AgentBackedEnhancer(get_company_news=lambda ticker, limit: [
        {**identity, "title": "Wrong instrument headline"},
        {"ticker": " aapl ", "symbol": "AAPL", "title": "Valid AAPL headline"},
    ])
    assert await enhancer._gather_agent_data(["AAPL"]) == {"AAPL": {"news": ["Valid AAPL headline"]}}

from backend.api.rebalance_schemas import ActionType, RebalanceAction, RebalanceConstraints, RiskTier
from backend.services.rebalance_engine import RebalanceContext, RebalanceEngine


@pytest.mark.asyncio
@pytest.mark.parametrize("symbol", ["TSLA", True, {}, 123])
async def test_conflicting_position_symbols_cannot_supply_rebalance_values_or_fallbacks(symbol, monkeypatch):
    monkeypatch.setenv("REBALANCE_USE_MOCK_PRICES", "false")
    ctx = _base_context(portfolio=[{"ticker": "TSLA", "symbol": "MSFT", "shares": 10},
                                  {"ticker": "AAPL", "symbol": symbol, "shares": 100},
                                  {"ticker": "MSFT", "symbol": " msft ", "shares": 5}])
    engine = RebalanceEngine()
    assert engine._diagnose_portfolio(ctx).position_values == {"MSFT": 500.0}
    result = await engine.generate(ctx)
    assert result.degraded_mode is False
    assert {action.ticker for action in result.actions} == {"MSFT"}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [{"error": "failed"}, {"success": False}, {"status": " Failed "}])
@pytest.mark.parametrize("failed_price", [None, 500.0])
async def test_failed_position_rows_neither_change_weights_nor_disable_rebalancing(failure, failed_price, monkeypatch):
    monkeypatch.setenv("REBALANCE_USE_MOCK_PRICES", "false")
    prices = {"AAPL": 200.0, "MSFT": 100.0}
    if failed_price is not None:
        prices["TSLA"] = failed_price
    ctx = _base_context(portfolio=[{"ticker": "AAPL", "shares": 10},
                                  {"ticker": "MSFT", "shares": 5},
                                  {**failure, "ticker": "TSLA", "shares": 100}],
                        live_prices=prices)
    engine = RebalanceEngine()
    assert engine._diagnose_portfolio(ctx).position_values == {"AAPL": 2000.0, "MSFT": 500.0}
    suggestion = await engine.generate(ctx)
    assert suggestion.degraded_mode is False
    assert {action.ticker for action in suggestion.actions} <= {"AAPL", "MSFT"}


@pytest.mark.asyncio
@pytest.mark.parametrize("ticker", [123, [], {}, True, ["MSFT"]])
async def test_invalid_position_tickers_do_not_disable_valid_rebalance_actions(ticker, monkeypatch):
    monkeypatch.setenv("REBALANCE_USE_MOCK_PRICES", "false")
    ctx = _base_context(portfolio=[{"ticker": ticker, "shares": 10},
                                  {"ticker": "AAPL", "shares": 10},
                                  {"ticker": "MSFT", "shares": 5}])
    result = await RebalanceEngine().generate(ctx)
    assert result.degraded_mode is False
    assert result.fallback_reason is None
    assert result.actions


@pytest.mark.asyncio
async def test_empty_model_enhancement_cannot_remove_all_existing_risk_actions():
    original = [RebalanceAction(ticker="AAPL", action=ActionType.REDUCE,
                               current_weight=80, target_weight=50, delta_weight=-30)]
    ctx = _base_context(use_llm_enhancement=True)
    engine = RebalanceEngine(llm_enhancer=lambda *args: [])
    result = await engine._maybe_enhance_candidates(original, engine._diagnose_portfolio(ctx), ctx)
    assert result is original


@pytest.mark.asyncio
async def test_enhancer_cannot_increase_a_position_above_the_single_stock_cap():
    original = [RebalanceAction(ticker="MSFT", action=ActionType.INCREASE,
                               current_weight=20, target_weight=25, delta_weight=5)]
    def enhancer(*args):
        return [RebalanceAction(ticker="MSFT", action=ActionType.INCREASE,
                                current_weight=20, target_weight=50, delta_weight=30)]
    ctx = _base_context(use_llm_enhancement=True, constraints=RebalanceConstraints(max_single_position_pct=25))
    engine = RebalanceEngine(llm_enhancer=enhancer)
    result = await engine._maybe_enhance_candidates(original, engine._diagnose_portfolio(ctx), ctx)
    assert result is original


@pytest.mark.asyncio
async def test_enhancer_cannot_replace_measured_current_weights():
    original = [RebalanceAction(ticker="AAPL", action=ActionType.REDUCE,
                               current_weight=80, target_weight=50, delta_weight=-30)]
    def enhancer(*args):
        return [RebalanceAction(ticker="AAPL", action=ActionType.REDUCE,
                                current_weight=50, target_weight=40, delta_weight=-10)]
    ctx = _base_context(use_llm_enhancement=True)
    engine = RebalanceEngine(llm_enhancer=enhancer)
    result = await engine._maybe_enhance_candidates(original, engine._diagnose_portfolio(ctx), ctx)
    assert result is original


@pytest.mark.asyncio
async def test_enhancer_cannot_introduce_a_stock_outside_the_valued_portfolio():
    original = [RebalanceAction(ticker="AAPL", action=ActionType.REDUCE,
                               current_weight=80, target_weight=50, delta_weight=-30)]
    def enhancer(*args):
        return [RebalanceAction(ticker="TSLA", action=ActionType.BUY,
                                current_weight=0, target_weight=20, delta_weight=20)]
    ctx = _base_context(use_llm_enhancement=True)
    engine = RebalanceEngine(llm_enhancer=enhancer)
    result = await engine._maybe_enhance_candidates(original, engine._diagnose_portfolio(ctx), ctx)
    assert result is original


@pytest.mark.asyncio
async def test_zero_valid_holdings_enter_diagnostics_instead_of_claiming_balance(monkeypatch):
    monkeypatch.setenv("REBALANCE_USE_MOCK_PRICES", "false")
    ctx = _base_context(portfolio=[{"ticker": "AAPL", "shares": 0}], live_prices={"AAPL": 200})
    result = await RebalanceEngine().generate(ctx)
    assert result.degraded_mode is True
    assert result.actions == []
    assert "invalid_portfolio" in result.fallback_reason


def test_sector_whitespace_cannot_split_the_same_rebalance_exposure():
    ctx = _base_context(sector_map={"AAPL": " Technology ", "MSFT": "Technology"})
    diagnosis = RebalanceEngine()._diagnose_portfolio(ctx)
    assert diagnosis.sector_weights == {"Technology": 100.0}


@pytest.mark.parametrize("ticker", [None, 123, [], {"symbol": "AAPL"}])
def test_invalid_position_identities_are_not_turned_into_stock_names(ticker):
    ctx = _base_context(portfolio=[{"ticker": ticker, "shares": 10}, {"ticker": "MSFT", "shares": 5}],
                        live_prices={"NONE": 100, "123": 100, "[]": 100, "{'SYMBOL': 'AAPL'}": 100, "MSFT": 100})
    assert set(RebalanceEngine()._diagnose_portfolio(ctx).weights) == {"MSFT"}


def test_duplicate_position_rows_are_aggregated_instead_of_overwriting_holdings():
    ctx = _base_context(portfolio=[{"ticker": "AAPL", "shares": 10}, {"ticker": " aapl ", "shares": 5},
                                   {"ticker": "MSFT", "shares": 5}])
    diagnosis = RebalanceEngine()._diagnose_portfolio(ctx)
    assert diagnosis.position_values["AAPL"] == 3000.0
    assert diagnosis.total_value == 3500.0


def test_boolean_share_rows_cannot_inflate_rebalance_weights():
    ctx = _base_context(portfolio=[{"ticker": "AAPL", "shares": True}, {"ticker": "MSFT", "shares": 5}])
    diagnosis = RebalanceEngine()._diagnose_portfolio(ctx)
    assert set(diagnosis.weights) == {"MSFT"}


@pytest.mark.asyncio
async def test_zero_turnover_budget_does_not_claim_a_risky_portfolio_needs_no_changes():
    ctx = _base_context(constraints=RebalanceConstraints(max_single_position_pct=55, max_turnover_pct=0,
                                                        sector_concentration_limit=100))
    suggestion = await RebalanceEngine().generate(ctx)
    assert suggestion.actions == []
    assert "无需调整" not in suggestion.summary
    assert "约束" in suggestion.summary
    assert "风险" in suggestion.summary


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_kind", ["duplicate", "mutated"])
async def test_invalid_enhanced_actions_fall_back_to_the_original_candidate(bad_kind):
    candidate = RebalanceAction(ticker="AAPL", action=ActionType.REDUCE, current_weight=60, target_weight=50, delta_weight=-10)
    original = [candidate]
    def enhancer(actions, diagnosis, context):
        if bad_kind == "duplicate":
            return [actions[0], actions[0].model_copy()]
        return [actions[0].model_copy(update={"delta_weight": 10})]
    ctx = _base_context(use_llm_enhancement=True)
    engine = RebalanceEngine(llm_enhancer=enhancer)
    result = await engine._maybe_enhance_candidates(original, engine._diagnose_portfolio(ctx), ctx)
    assert result is original


@pytest.mark.asyncio
async def test_failed_enhancer_cannot_mutate_fallback_actions_or_constraints():
    candidate = RebalanceAction(ticker="AAPL", action=ActionType.REDUCE, current_weight=60, target_weight=50, delta_weight=-10)
    candidates = [candidate]
    ctx = _base_context(use_llm_enhancement=True)
    def enhancer(actions, diagnosis, context):
        actions.clear()
        context.constraints.max_turnover_pct = 100
        raise RuntimeError("enhancer failed")
    engine = RebalanceEngine(llm_enhancer=enhancer)
    result = await engine._maybe_enhance_candidates(candidates, engine._diagnose_portfolio(ctx), ctx)
    assert result == [candidate]
    assert candidates == [candidate]
    assert ctx.constraints.max_turnover_pct == 30


def test_turnover_capped_action_evidence_matches_the_final_target():
    from backend.api.rebalance_schemas import EvidenceSnapshot
    evidence = EvidenceSnapshot(evidence_id="weights", source="portfolio_diagnosis",
                                quote="AAPL current_weight=60.00% target_weight=40.00%")
    candidate = RebalanceAction(ticker="AAPL", action=ActionType.REDUCE, current_weight=60,
                                target_weight=40, delta_weight=-20, evidence_snapshots=[evidence])
    solved = RebalanceEngine()._solve_constraints([candidate], RebalanceConstraints(max_turnover_pct=10))
    assert solved[0].target_weight == 50.0
    assert "target_weight=50.00%" in solved[0].evidence_snapshots[0].quote
    assert "target_weight=40.00%" in evidence.quote


def test_increase_candidates_respect_the_single_position_cap():
    ctx = _base_context(portfolio=[{"ticker": "AAPL", "shares": 45}, {"ticker": "MSFT", "shares": 45}, {"ticker": "NVDA", "shares": 10}],
                        live_prices={"AAPL": 1.0, "MSFT": 1.0, "NVDA": 1.0},
                        constraints=RebalanceConstraints(max_single_position_pct=25, max_turnover_pct=100))
    engine = RebalanceEngine()
    candidates = engine._generate_candidates(engine._diagnose_portfolio(ctx), ctx)
    increase = next(action for action in candidates if action.action == ActionType.INCREASE)
    assert increase.target_weight == 25.0


@pytest.mark.asyncio
async def test_missing_price_does_not_create_targets_from_a_partial_portfolio(monkeypatch):
    monkeypatch.setenv("REBALANCE_USE_MOCK_PRICES", "false")
    ctx = _base_context(live_prices={"AAPL": 200.0})
    suggestion = await RebalanceEngine().generate(ctx)
    assert suggestion.degraded_mode is True
    assert suggestion.actions == []
    assert "MSFT" in suggestion.fallback_reason
    assert ctx.diagnostics_only is False


def test_quote_and_sector_keys_match_normalized_portfolio_tickers(monkeypatch):
    monkeypatch.setenv("REBALANCE_USE_MOCK_PRICES", "false")
    ctx = _base_context(live_prices={" aapl ": 200.0, " msft ": 100.0},
                        sector_map={"aapl": "Technology", "msft": "Technology"})
    diagnosis = RebalanceEngine()._diagnose_portfolio(ctx)
    assert diagnosis.total_value == 2500.0
    assert diagnosis.sector_weights == {"Technology": 100.0}


@pytest.mark.parametrize("action, target, delta", [(ActionType.REDUCE, 40, 10),
                                                   (ActionType.REDUCE, 60, 10),
                                                   (ActionType.INCREASE, 40, -10),
                                                   (ActionType.HOLD, 60, 10)])
def test_rebalance_action_changes_agree_with_weights_and_direction(action, target, delta):
    with pytest.raises(ValueError):
        RebalanceAction(ticker="AAPL", action=action, current_weight=50, target_weight=target, delta_weight=delta)


@pytest.mark.parametrize("field, value", [("current_weight", -1), ("current_weight", 101),
                                          ("target_weight", -1), ("target_weight", 101),
                                          ("delta_weight", -101), ("delta_weight", 101)])
def test_rebalance_action_weights_stay_in_percentage_bounds(field, value):
    weights = {"current_weight": 50.0, "target_weight": 50.0, "delta_weight": 0.0, field: value}
    with pytest.raises(ValueError):
        RebalanceAction(ticker="AAPL", action=ActionType.HOLD, **weights)


def _base_context(**overrides) -> RebalanceContext:
    params = {
        "session_id": "public:test_user:thread-1",
        "portfolio": [
            {"ticker": "AAPL", "shares": 10},
            {"ticker": "MSFT", "shares": 5},
        ],
        "risk_tier": RiskTier.MODERATE,
        "constraints": RebalanceConstraints(
            max_single_position_pct=55,
            max_turnover_pct=30,
            sector_concentration_limit=100,
            min_action_delta_pct=1,
        ),
        "live_prices": {"AAPL": 200.0, "MSFT": 100.0},
        "sector_map": {"AAPL": "Technology", "MSFT": "Technology"},
    }
    params.update(overrides)
    return RebalanceContext(**params)


@pytest.mark.parametrize(
    "portfolio, prices",
    [
        ([{"ticker": "AAPL", "shares": 1e308}], {"AAPL": 100.0}),
        ([{"ticker": "AAPL", "shares": 1e308}, {"ticker": "MSFT", "shares": 1e308}],
         {"AAPL": 1.0, "MSFT": 1.0}),
    ],
)
def test_rebalance_rejects_overflowing_portfolio_values(portfolio, prices):
    ctx = _base_context(portfolio=portfolio, live_prices=prices)
    with pytest.raises(ValueError, match="portfolio value must be finite"):
        RebalanceEngine()._diagnose_portfolio(ctx)


@pytest.mark.parametrize("budget", [0.0, 0.015, 0.016])
def test_turnover_solver_never_exceeds_budget_or_emits_zero_trades(budget):
    candidates = [
        RebalanceAction(ticker=ticker, action=ActionType.REDUCE,
            current_weight=10, target_weight=9.99, delta_weight=-0.01)
        for ticker in ("AAPL", "MSFT")
    ]
    constraints = RebalanceConstraints(max_turnover_pct=budget, min_action_delta_pct=0)
    solved = RebalanceEngine()._solve_constraints(candidates, constraints)

    assert sum(abs(action.delta_weight) for action in solved) <= budget + 1e-9
    assert all(action.delta_weight != 0 for action in solved)


@pytest.mark.parametrize("field", ["current_weight", "target_weight", "delta_weight", "estimated_turnover_pct"])
@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
def test_rebalance_output_models_reject_non_finite_numbers(field, invalid):
    from backend.api.rebalance_schemas import ExpectedImpact

    with pytest.raises(ValueError, match="finite"):
        if field == "estimated_turnover_pct":
            ExpectedImpact(estimated_turnover_pct=invalid)
        else:
            weights = {"current_weight": 60, "target_weight": 50, "delta_weight": -10, field: invalid}
            RebalanceAction(ticker="AAPL", action=ActionType.REDUCE, **weights)


@pytest.mark.asyncio
async def test_rebalance_actions_include_evidence_snapshots():
    engine = RebalanceEngine()
    suggestion = await engine.generate(_base_context())

    assert suggestion.degraded_mode is False
    assert len(suggestion.actions) >= 1
    first_action = suggestion.actions[0]
    assert len(first_action.evidence_ids) >= 1
    assert len(first_action.evidence_snapshots) >= 1
    assert all(item.evidence_id for item in first_action.evidence_snapshots)


@pytest.mark.asyncio
async def test_llm_enhancer_failure_falls_back_to_deterministic(caplog):
    secret = "PRIVATE postgres://rebalance:secret@db/enhancer"

    async def failing_enhancer(*_args, **_kwargs):
        raise RuntimeError(secret)

    engine = RebalanceEngine(llm_enhancer=failing_enhancer)
    caplog.set_level("WARNING")
    suggestion = await engine.generate(_base_context(use_llm_enhancement=True))

    assert len(suggestion.actions) >= 1
    assert any("fallback to deterministic" in rec.message for rec in caplog.records)
    assert secret not in caplog.text
    assert "[rebalance] enhancer failed, fallback to deterministic" in caplog.text


@pytest.mark.asyncio
async def test_rebalance_llm_initialization_error_log_is_redacted(caplog):
    secret = "PRIVATE postgres://rebalance:secret@db/llm"

    def _fail_llm(**_kwargs):
        raise RuntimeError(secret)

    enhancer = AgentBackedEnhancer(create_llm_fn=_fail_llm)
    candidates = [object()]

    result = await enhancer._llm_enhance(candidates, None, None, {})

    assert result is candidates
    assert secret not in caplog.text
    assert "[rebalance-enhancer] LLM init failed" in caplog.text


@pytest.mark.asyncio
async def test_rebalance_llm_call_error_log_is_redacted(caplog):
    secret = "PRIVATE postgres://rebalance:secret@db/invoke"

    class _FailingLLM:
        async def ainvoke(self, _messages):
            raise RuntimeError(secret)

    enhancer = AgentBackedEnhancer(create_llm_fn=lambda **_kwargs: _FailingLLM())
    candidates = [
        RebalanceAction(
            ticker="AAPL",
            action=ActionType.REDUCE,
            current_weight=60,
            target_weight=50,
            delta_weight=-10,
            reason="concentration",
        )
    ]
    diag = SimpleNamespace(weights={"AAPL": 60.0}, risk_flags=[])

    result = await enhancer._llm_enhance(candidates, diag, _base_context(), {})

    assert result is candidates
    assert secret not in caplog.text
    assert "[rebalance-enhancer] LLM call failed" in caplog.text


@pytest.mark.asyncio
async def test_rebalance_news_fetch_error_log_is_redacted(caplog):
    secret = "PRIVATE postgres://rebalance:secret@db/news"

    def _fail_news(_ticker, _limit):
        raise RuntimeError(secret)

    caplog.set_level("DEBUG")
    enhancer = AgentBackedEnhancer(get_company_news=_fail_news)

    result = await enhancer._gather_agent_data(["AAPL"])

    assert result == {"AAPL": {"news_unavailable": True}}
    assert secret not in caplog.text
    assert "[rebalance-enhancer] news fetch failed" in caplog.text


@pytest.mark.asyncio
async def test_rebalance_company_info_error_log_is_redacted(caplog):
    secret = "PRIVATE postgres://rebalance:secret@db/company"

    def _fail_info(_ticker):
        raise RuntimeError(secret)

    caplog.set_level("DEBUG")
    enhancer = AgentBackedEnhancer(get_company_info=_fail_info)

    result = await enhancer._gather_agent_data(["AAPL"])

    assert result == {"AAPL": {"news_unavailable": True}}
    assert secret not in caplog.text
    assert "[rebalance-enhancer] info fetch failed" in caplog.text


@pytest.mark.asyncio
async def test_news_tool_returning_none_is_marked_unavailable():
    """工具用 None 表示"没取到"，不能落成空列表（否则 prompt 写成"无近期新闻"）。"""
    enhancer = AgentBackedEnhancer(get_company_news=lambda _ticker, _limit: None)

    result = await enhancer._gather_agent_data(["AAPL"])

    assert result == {"AAPL": {"news_unavailable": True}}


@pytest.mark.asyncio
async def test_unconfigured_news_provider_is_not_reported_as_no_news():
    enhancer = AgentBackedEnhancer()

    assert await enhancer._gather_agent_data(["AAPL"]) == {"AAPL": {"news_unavailable": True}}


@pytest.mark.asyncio
async def test_news_enhancement_filters_bad_titles_before_applying_limit():
    enhancer = AgentBackedEnhancer(get_company_news=lambda ticker, limit: [
        {"title": {}}, {"title": "   "}, False,
        {"headline": True, "title": "  Valid fallback title  "},
        "  Second valid title  ", {"title": "Third valid title"}, "Fourth valid title",
    ])

    result = await enhancer._gather_agent_data(["AAPL"])

    assert result == {"AAPL": {"news": ["Valid fallback title", "Second valid title", "Third valid title"]}}


@pytest.mark.asyncio
async def test_unusable_news_rows_are_marked_unavailable():
    enhancer = AgentBackedEnhancer(get_company_news=lambda ticker, limit: [
        {"title": True}, {"headline": {}}, "   ", None,
    ])

    assert await enhancer._gather_agent_data(["AAPL"]) == {"AAPL": {"news_unavailable": True}}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [{"error": "failed"}, {"success": False}, {"status": " ERROR "}])
async def test_failed_news_rows_cannot_become_rebalance_evidence(failure):
    enhancer = AgentBackedEnhancer(get_company_news=lambda ticker, limit: [
        {**failure, "title": "Failed headline"}, {"title": "Valid headline"},
    ])

    assert await enhancer._gather_agent_data(["AAPL"]) == {"AAPL": {"news": ["Valid headline"]}}


@pytest.mark.asyncio
async def test_llm_enhancer_switch_is_respected():
    calls = {"count": 0}

    async def enhancer(_candidates, _diag, _ctx):
        calls["count"] += 1
        return []

    engine = RebalanceEngine(llm_enhancer=enhancer)
    suggestion = await engine.generate(_base_context(use_llm_enhancement=True))

    assert calls["count"] == 1
    assert suggestion.actions
    assert suggestion.actions[0].ticker == "AAPL"
    assert suggestion.actions[0].action == ActionType.REDUCE


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_ticker", [[], {}, None, True, 7])
async def test_llm_enhancer_keeps_valid_rows_beside_malformed_tickers(bad_ticker):
    import json

    class ResponseLLM:
        async def ainvoke(self, messages):
            return SimpleNamespace(content=json.dumps([
                {"ticker": bad_ticker, "enhanced_reason": "invalid row"},
                {"ticker": " aapl ", "adjusted_priority": 2, "enhanced_reason": "Valid reason"},
            ]))

    enhancer = AgentBackedEnhancer(create_llm_fn=lambda **kwargs: ResponseLLM())
    candidate = RebalanceAction(ticker="AAPL", action=ActionType.REDUCE,
        current_weight=60, target_weight=50, delta_weight=-10, reason="Original reason")
    result = await enhancer._llm_enhance([candidate],
        SimpleNamespace(weights={"AAPL": 60}, risk_flags=[]), _base_context(), {})

    assert result[0].reason == "Valid reason"
    assert result[0].priority == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [{"error": "failed"}, {"success": False}, {"status": " ERROR "}])
async def test_failed_model_enhancement_keeps_the_deterministic_candidate(failure):
    import json

    class ResponseLLM:
        async def ainvoke(self, messages):
            return SimpleNamespace(content=json.dumps([{
                **failure, "ticker": "AAPL", "adjusted_priority": 1, "enhanced_reason": "Failed reasoning",
            }]))

    candidate = RebalanceAction(ticker="AAPL", action=ActionType.REDUCE,
        current_weight=60, target_weight=50, delta_weight=-10, priority=3, reason="Original reason")
    enhancer = AgentBackedEnhancer(create_llm_fn=lambda **kwargs: ResponseLLM())

    result = await enhancer._llm_enhance([candidate],
        SimpleNamespace(weights={"AAPL": 60}, risk_flags=[]), _base_context(), {})

    assert result[0] is candidate
    assert result[0].priority == 3
    assert result[0].reason == "Original reason"
    assert result[0].evidence_ids == []


@pytest.mark.asyncio
@pytest.mark.parametrize("priority", [-1, 0, 6, 1.5, 2.5, "0", "6"])
async def test_invalid_model_priorities_preserve_deterministic_order(priority):
    import json

    class ResponseLLM:
        async def ainvoke(self, messages):
            return SimpleNamespace(content=json.dumps([{"ticker": "AAPL", "adjusted_priority": priority}]))

    candidate = RebalanceAction(ticker="AAPL", action=ActionType.REDUCE,
        current_weight=60, target_weight=50, delta_weight=-10, priority=3)
    enhancer = AgentBackedEnhancer(create_llm_fn=lambda **kwargs: ResponseLLM())
    result = await enhancer._llm_enhance([candidate],
        SimpleNamespace(weights={"AAPL": 60}, risk_flags=[]), _base_context(), {})

    assert result[0].priority == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", [None, True, {}, [], "", "   "])
async def test_invalid_model_reasons_do_not_create_fake_evidence(reason):
    import json
    from backend.api.rebalance_schemas import EvidenceSnapshot

    class ResponseLLM:
        async def ainvoke(self, messages):
            return SimpleNamespace(content=json.dumps([
                {"ticker": "AAPL", "adjusted_priority": 2, "enhanced_reason": reason},
            ]))

    evidence = EvidenceSnapshot(evidence_id="original", source="constraint_rule", quote="Valid evidence")
    candidate = RebalanceAction(ticker="AAPL", action=ActionType.REDUCE,
        current_weight=60, target_weight=50, delta_weight=-10, reason="Original reason",
        evidence_ids=["original"], evidence_snapshots=[evidence])
    enhancer = AgentBackedEnhancer(create_llm_fn=lambda **kwargs: ResponseLLM())
    result = await enhancer._llm_enhance([candidate],
        SimpleNamespace(weights={"AAPL": 60}, risk_flags=[]), _base_context(), {})

    assert result[0].reason == "Original reason"
    assert result[0].priority == 2
    assert result[0].evidence_ids == candidate.evidence_ids
    assert result[0].evidence_snapshots == candidate.evidence_snapshots


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_rebalance_llm_parser_rejects_non_finite_priority(constant):
    content = '[{"ticker":"AAPL","adjusted_priority":' + constant + "}]"

    assert AgentBackedEnhancer._parse_llm_response(content) == []


@pytest.mark.asyncio
async def test_news_fetch_failure_is_not_prompted_as_no_news():
    """抓取失败 ≠ 没有新闻：prompt 里必须写成"取不到"，不能喂给 LLM 一个事实。"""
    captured = {}

    class _CapturingLLM:
        async def ainvoke(self, messages):
            captured["prompt"] = messages[0].content
            return SimpleNamespace(content="[]")

    def _fail_news(_ticker, _limit):
        raise RuntimeError("boom")

    enhancer = AgentBackedEnhancer(
        get_company_news=_fail_news,
        create_llm_fn=lambda **_kwargs: _CapturingLLM(),
    )
    candidates = [
        RebalanceAction(
            ticker="AAPL",
            action=ActionType.REDUCE,
            current_weight=60,
            target_weight=50,
            delta_weight=-10,
            reason="concentration",
        )
    ]
    diag = SimpleNamespace(weights={"AAPL": 60.0}, risk_flags=[])

    agent_context = await enhancer._gather_agent_data(["AAPL"])
    await enhancer._llm_enhance(candidates, diag, _base_context(), agent_context)

    aapl_line = next(
        line for line in captured["prompt"].splitlines() if line.startswith("- AAPL:")
    )
    assert "新闻获取失败" in aapl_line
    assert "无近期新闻" not in aapl_line


@pytest.mark.asyncio
async def test_news_fetched_empty_still_reads_as_no_news():
    """真的抓到了、但确实没有新闻时，措辞保持原样（不能把守卫扩大成永远报错）。"""
    captured = {}

    class _CapturingLLM:
        async def ainvoke(self, messages):
            captured["prompt"] = messages[0].content
            return SimpleNamespace(content="[]")

    enhancer = AgentBackedEnhancer(
        get_company_news=lambda _ticker, _limit: [],
        create_llm_fn=lambda **_kwargs: _CapturingLLM(),
    )
    candidates = [
        RebalanceAction(
            ticker="AAPL",
            action=ActionType.REDUCE,
            current_weight=60,
            target_weight=50,
            delta_weight=-10,
            reason="concentration",
        )
    ]
    diag = SimpleNamespace(weights={"AAPL": 60.0}, risk_flags=[])

    agent_context = await enhancer._gather_agent_data(["AAPL"])
    await enhancer._llm_enhance(candidates, diag, _base_context(), agent_context)

    aapl_line = next(
        line for line in captured["prompt"].splitlines() if line.startswith("- AAPL:")
    )
    assert "无近期新闻" in aapl_line
    assert "新闻获取失败" not in aapl_line
