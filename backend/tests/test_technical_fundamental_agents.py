import pytest
from unittest.mock import MagicMock

from backend.agents.technical_agent import TechnicalAgent
from backend.agents.fundamental_agent import FundamentalAgent


class DummyCache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ttl=None):
        self.store[key] = value


def _build_kline(count=120, start=100.0):
    data = []
    for i in range(count):
        close = start + i * 0.5
        day = (i % 28) + 1
        data.append({
            "time": f"2025-01-{day:02d} 00:00",
            "open": close - 1,
            "high": close + 1,
            "low": close - 2,
            "close": close,
            "volume": 1000,
        })
    return data


@pytest.mark.asyncio
async def test_technical_agent_indicators():
    mock_llm = MagicMock()
    cache = DummyCache()
    tools = MagicMock()
    tools.get_stock_historical_data = MagicMock(return_value={
        "ticker": "AAPL",
        "kline_data": _build_kline(),
        "source": "mock_source",
    })

    agent = TechnicalAgent(mock_llm, cache, tools)
    result = await agent.research("technical analysis", "AAPL")

    assert result.agent_name == "technical"
    assert "RSI" in result.summary
    assert result.evidence
    assert "mock_source" in result.data_sources


@pytest.mark.asyncio
async def test_fundamental_agent_financials():
    mock_llm = MagicMock()
    cache = DummyCache()
    tools = MagicMock()
    tools.get_company_info = MagicMock(return_value=(
        "Company Profile (AAPL):\n"
        "- Name: Apple Inc\n"
        "- Sector: Technology\n"
        "- Industry: Consumer Electronics\n"
        "- Market Cap: $1.2T\n"
    ))

    tools.get_financial_statements = MagicMock(return_value={
        "ticker": "AAPL",
        "timestamp": "2026-01-10T00:00:00",
        "financials": {
            "columns": ["2025-12-31", "2024-12-31"],
            "index": ["Total Revenue", "Net Income", "Operating Income"],
            "data": [
                {"2025-12-31": 120000000000, "2024-12-31": 100000000000},
                {"2025-12-31": 20000000000, "2024-12-31": 18000000000},
                {"2025-12-31": 25000000000, "2024-12-31": 20000000000},
            ],
        },
        "balance_sheet": {
            "columns": ["2025-12-31", "2024-12-31"],
            "index": ["Total Assets", "Total Liabilities"],
            "data": [
                {"2025-12-31": 350000000000, "2024-12-31": 330000000000},
                {"2025-12-31": 190000000000, "2024-12-31": 180000000000},
            ],
        },
        "cashflow": {
            "columns": ["2025-12-31", "2024-12-31"],
            "index": ["Operating Cash Flow"],
            "data": [
                {"2025-12-31": 28000000000, "2024-12-31": 26000000000},
            ],
        },
        "error": None,
    })
    tools.get_earnings_estimates = MagicMock(return_value={
        "ticker": "AAPL",
        "source": "yfinance",
        "as_of": "2026-01-10T00:00:00",
        "earnings_estimate": [{"period": "0q", "avg": 2.15}],
        "eps_trend": [{"period": "0q", "current": 2.15}],
        "eps_revisions": [{"period": "0q", "upLast7days": 3, "downLast7Days": 0}],
        "calendar": {"Earnings Date": ["2026-01-30"]},
        "revision_signal": "positive",
        "error": None,
    })
    tools.get_eps_revisions = MagicMock(return_value={
        "ticker": "AAPL",
        "source": "yfinance",
        "as_of": "2026-01-10T00:00:00",
        "eps_revisions": [{"period": "0q", "upLast7days": 3, "downLast7Days": 0}],
        "eps_trend": [{"period": "0q", "current": 2.15}],
        "revision_signal": "positive",
        "error": None,
    })

    agent = FundamentalAgent(mock_llm, cache, tools)
    result = await agent.research("fundamental analysis", "AAPL")

    assert result.agent_name == "fundamental"
    assert "营收" in result.summary or "Revenue" in result.summary
    assert result.evidence
    revenue_item = next((item for item in result.evidence if item.meta.get("metric_key") == "revenue"), None)
    assert revenue_item is not None
    assert "yoy" in revenue_item.meta
    assert "qoq" in revenue_item.meta
    eps_item = next((item for item in result.evidence if item.meta.get("metric_key") == "eps_revision_signal"), None)
    assert eps_item is not None
    assert result.evidence_quality.get("overall_score", 0) > 0
    assert result.evidence_quality.get("metric_coverage", 0) > 0


@pytest.mark.asyncio
async def test_fundamental_agent_quarterly_growth_consistency():
    mock_llm = MagicMock()
    cache = DummyCache()
    tools = MagicMock()
    tools.get_company_info = MagicMock(return_value="Company Profile (AAPL):\n- Name: Apple Inc\n")
    tools.get_financial_statements = MagicMock(return_value={
        "ticker": "AAPL",
        "timestamp": "2026-01-10T00:00:00",
        "financials": {
            "columns": ["2025-12-31", "2025-09-30", "2025-06-30", "2025-03-31", "2024-12-31"],
            "index": ["Total Revenue", "Net Income"],
            "data": [
                {"2025-12-31": 125, "2025-09-30": 120, "2025-06-30": 118, "2025-03-31": 115, "2024-12-31": 110},
                {"2025-12-31": 30, "2025-09-30": 28, "2025-06-30": 27, "2025-03-31": 25, "2024-12-31": 24},
            ],
        },
        "balance_sheet": {"columns": [], "index": [], "data": []},
        "cashflow": {"columns": [], "index": [], "data": []},
        "error": None,
    })

    agent = FundamentalAgent(mock_llm, cache, tools)
    result = await agent.research("fundamental analysis", "AAPL")

    revenue_item = next((item for item in result.evidence if item.meta.get("metric_key") == "revenue"), None)
    assert revenue_item is not None
    assert revenue_item.meta.get("period_type") == "quarterly"
    assert isinstance(revenue_item.meta.get("qoq"), float)
    assert isinstance(revenue_item.meta.get("yoy"), float)
    assert ("QoQ" in result.summary or "环比" in result.summary) and ("YoY" in result.summary or "同比" in result.summary)


@pytest.mark.asyncio
async def test_fundamental_agent_quarterly_insufficient_history_no_fake_yoy():
    """R63：季度数据不足 4 季（如次新股）时不得把环比值标成同比。"""
    mock_llm = MagicMock()
    cache = DummyCache()
    tools = MagicMock()
    tools.get_company_info = MagicMock(return_value="Company Profile (NEW):\n- Name: NewCo\n")
    tools.get_financial_statements = MagicMock(return_value={
        "ticker": "NEW",
        "timestamp": "2026-01-10T00:00:00",
        "financials": {
            # 仅 3 季 → 不足以算真同比（需要 series[4]，即 4 季前）
            "columns": ["2025-09-30", "2025-06-30", "2025-03-31"],
            "index": ["Total Revenue", "Net Income"],
            "data": [
                {"2025-09-30": 120, "2025-06-30": 110, "2025-03-31": 100},
                {"2025-09-30": 30, "2025-06-30": 27, "2025-03-31": 25},
            ],
        },
        "balance_sheet": {"columns": [], "index": [], "data": []},
        "cashflow": {"columns": [], "index": [], "data": []},
        "error": None,
    })

    agent = FundamentalAgent(mock_llm, cache, tools)
    result = await agent.research("fundamental analysis", "NEW")

    revenue_item = next((item for item in result.evidence if item.meta.get("metric_key") == "revenue"), None)
    assert revenue_item is not None
    # 环比可算（有上一季），同比必须为 None（不足 4 季）
    assert isinstance(revenue_item.meta.get("qoq"), float)
    assert revenue_item.meta.get("yoy") is None, "数据不足 4 季不应伪造同比"
    # 摘要不得出现"同比"（避免把环比误标）
    assert "同比" not in result.summary and "YoY" not in result.summary


@pytest.mark.asyncio
async def test_fundamental_agent_sec_fallback_evidence_not_labeled_yfinance():
    """SEC companyfacts 兜底时，指标证据 source/url 不得标成 yfinance——
    旧代码硬编码 source="yfinance" + Yahoo 财报页链接，把 SEC EDGAR 数据
    的出处标错（恰好发生在 yfinance 取不到数据的标的上）。"""
    mock_llm = MagicMock()
    cache = DummyCache()
    tools = MagicMock()
    tools.get_company_info = MagicMock(return_value="")
    tools.get_financial_statements = MagicMock(return_value={
        "ticker": "BRX",
        "timestamp": "2026-01-10T00:00:00",
        "financials": {
            "columns": ["2025-12-31", "2025-09-30", "2025-06-30", "2025-03-31", "2024-12-31"],
            "index": ["Total Revenue", "Net Income"],
            "data": [
                {"2025-12-31": 125, "2025-09-30": 120, "2025-06-30": 118, "2025-03-31": 115, "2024-12-31": 110},
                {"2025-12-31": 30, "2025-09-30": 28, "2025-06-30": 27, "2025-03-31": 25, "2024-12-31": 24},
            ],
        },
        "balance_sheet": {"columns": [], "index": [], "data": []},
        "cashflow": {"columns": [], "index": [], "data": []},
        "error": None,
        "warnings": ["fallback:sec_companyfacts"],
        "source": "sec_companyfacts",
    })

    agent = FundamentalAgent(mock_llm, cache, tools)
    result = await agent.research("fundamental analysis", "BRX")

    metric_items = [
        item for item in result.evidence
        if item.meta.get("metric_key") in {
            "revenue", "net_income", "operating_income",
            "operating_cash_flow", "total_assets", "total_liabilities",
        }
    ]
    assert metric_items
    assert all(item.source == "sec_companyfacts" for item in metric_items)
    assert all("finance.yahoo.com" not in (item.url or "") for item in metric_items)


def _annual_financials(revenue_latest, revenue_prev, op_income_latest, op_income_prev):
    """两期年报数据：columns 相差 ~365 天 → period_type=annual → yoy 有值。"""
    return {
        "ticker": "T",
        "timestamp": "2026-01-10T00:00:00",
        "financials": {
            "columns": ["2025-12-31", "2024-12-31"],
            "index": ["Total Revenue", "Operating Income", "Net Income"],
            "data": [
                {"2025-12-31": revenue_latest, "2024-12-31": revenue_prev},
                {"2025-12-31": op_income_latest, "2024-12-31": op_income_prev},
                {"2025-12-31": 10, "2024-12-31": 10},
            ],
        },
        "balance_sheet": {"columns": [], "index": [], "data": []},
        "cashflow": {"columns": [], "index": [], "data": []},
        "error": None,
    }


@pytest.mark.asyncio
async def test_fundamental_conflict_flags_revenue_up_margin_down():
    """营收同比高增长 + 营业利润率下滑 >5pp 应产生冲突标记。

    旧代码在 metric_map 里查 "total_revenue"/"gross_margin"——这两个 key
    从未存在（实际 key 是 revenue/operating_income 等），恒得 {} →
    conflict_flags/conflicting_claims 永远为空。且 _growth_pct 返回比值
    （0.15），旧阈值按百分数写（10/-5）也无法命中。"""
    mock_llm = MagicMock()
    cache = DummyCache()
    tools = MagicMock()
    tools.get_company_info = MagicMock(return_value="")
    tools.get_financial_statements = MagicMock(return_value=_annual_financials(
        revenue_latest=120, revenue_prev=100,   # yoy = +20%
        op_income_latest=10, op_income_prev=20,  # margin 8.3% vs 20% → -11.7pp
    ))

    agent = FundamentalAgent(mock_llm, cache, tools)
    result = await agent.research("fundamental analysis", "T")

    assert "营收高增长 vs 营业利润率下滑" in result.conflict_flags
    assert len(result.conflicting_claims) == 1
    claim = result.conflicting_claims[0]
    assert claim.severity == "medium"
    assert "+20.0%" in claim.value_a
    assert "pp" in claim.value_b


@pytest.mark.asyncio
async def test_fundamental_conflict_flags_revenue_down_margin_up():
    """反向：营收下滑 + 营业利润率扩张 >5pp → low severity 冲突。"""
    mock_llm = MagicMock()
    cache = DummyCache()
    tools = MagicMock()
    tools.get_company_info = MagicMock(return_value="")
    tools.get_financial_statements = MagicMock(return_value=_annual_financials(
        revenue_latest=90, revenue_prev=100,    # yoy = -10%
        op_income_latest=27, op_income_prev=20,  # margin 30% vs 20% → +10pp
    ))

    agent = FundamentalAgent(mock_llm, cache, tools)
    result = await agent.research("fundamental analysis", "T")

    assert "营收下滑 vs 营业利润率扩张" in result.conflict_flags
    assert len(result.conflicting_claims) == 1
    assert result.conflicting_claims[0].severity == "low"


@pytest.mark.asyncio
async def test_fundamental_conflict_flags_aligned_growth_no_flag():
    """营收和利润率同向改善 → 不应误报冲突。"""
    mock_llm = MagicMock()
    cache = DummyCache()
    tools = MagicMock()
    tools.get_company_info = MagicMock(return_value="")
    tools.get_financial_statements = MagicMock(return_value=_annual_financials(
        revenue_latest=120, revenue_prev=100,   # yoy = +20%
        op_income_latest=30, op_income_prev=20,  # margin 25% vs 20% → +5pp
    ))

    agent = FundamentalAgent(mock_llm, cache, tools)
    result = await agent.research("fundamental analysis", "T")

    assert result.conflict_flags == []
    assert result.conflicting_claims == []


def _flat_kline(count=120, close=50.0):
    """停牌/重复收盘价的平线序列：每日 close 完全相等。"""
    return [
        {"time": f"2025-03-{(i % 28) + 1:02d} 00:00", "close": close}
        for i in range(count)
    ]


def test_technical_flat_kline_rsi_neutral_not_100():
    """R58：平线序列 delta 全 0 → avg_gain=avg_loss=0（0/0 无意义）。
    旧代码 `last_loss==0 → return 100.0` 把停牌股标成 RSI=100 超买，
    rsi_state=overbought。按惯例应取中性 50。"""
    agent = TechnicalAgent(MagicMock(), DummyCache(), MagicMock())
    indicators = agent._compute_indicators(_flat_kline())
    assert indicators is not None
    assert indicators["rsi_state"] == "neutral"
    assert indicators["rsi"] == 50.0


def test_technical_rising_kline_rsi_still_100():
    """单边上涨：avg_gain>0 且 avg_loss=0 → RSI=100 是正确约定，回归保护。"""
    agent = TechnicalAgent(MagicMock(), DummyCache(), MagicMock())
    indicators = agent._compute_indicators(_build_kline())
    assert indicators is not None
    assert indicators["rsi"] == 100.0
    assert indicators["rsi_state"] == "overbought"


def test_technical_flat_kline_no_fake_overbought_wording():
    """平线不应产出"超买/超卖"文案：_build_risks 伪造回撤风险、
    _deterministic_summary 输出"RSI进入超买区"都会误导下游合成。"""
    agent = TechnicalAgent(MagicMock(), DummyCache(), MagicMock())
    flat_data = {"ticker": "HALT", "kline_data": _flat_kline(), "source": "test"}

    risks = agent._build_risks(flat_data, ["dummy"])
    assert not any("超买" in r or "超卖" in r for r in risks)

    summary = agent._deterministic_summary(flat_data)
    assert "超买" not in summary and "超卖" not in summary

