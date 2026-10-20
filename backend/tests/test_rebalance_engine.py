import pytest
from types import SimpleNamespace

from backend.services.rebalance_llm_enhancer import AgentBackedEnhancer

from backend.api.rebalance_schemas import ActionType, RebalanceAction, RebalanceConstraints, RiskTier
from backend.services.rebalance_engine import RebalanceContext, RebalanceEngine


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

    assert result == {"AAPL": {}}
    assert secret not in caplog.text
    assert "[rebalance-enhancer] info fetch failed" in caplog.text


@pytest.mark.asyncio
async def test_news_tool_returning_none_is_marked_unavailable():
    """工具用 None 表示"没取到"，不能落成空列表（否则 prompt 写成"无近期新闻"）。"""
    enhancer = AgentBackedEnhancer(get_company_news=lambda _ticker, _limit: None)

    result = await enhancer._gather_agent_data(["AAPL"])

    assert result == {"AAPL": {"news_unavailable": True}}


@pytest.mark.asyncio
async def test_llm_enhancer_switch_is_respected():
    calls = {"count": 0}

    async def enhancer(_candidates, _diag, _ctx):
        calls["count"] += 1
        return []

    engine = RebalanceEngine(llm_enhancer=enhancer)
    suggestion = await engine.generate(_base_context(use_llm_enhancement=True))

    assert calls["count"] == 1
    assert suggestion.actions == []


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
