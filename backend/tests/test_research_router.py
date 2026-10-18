# -*- coding: utf-8 -*-
"""research_router /api/research/report/generate 上下文注入回归。

bug：handler 对工具返回值一律调 ``.get("error")`` 判错，但
- ``get_company_info``（tools/financial.py）返回 ``str`` —— 非空字符串上
  ``.get`` 抛 AttributeError；
- ``get_company_news``（tools/news.py）返回 ``List[Dict]`` —— 非空 list 上
  ``.get`` 抛 AttributeError。
两处异常被各自的内层 ``except Exception`` 吞成 warning，结果是
``data_context["company_info"]`` 与 ``data_context["news"]`` 在任何一次成功
获取下都注不进来——comprehensive 研报 prompt 永远缺公司概况与最近新闻。
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.research_router import router as research_router


class _FakeGenerator:
    def __init__(self) -> None:
        self.seen_context: dict | None = None

    async def generate_report(self, *, ticker, report_type, data_context):
        self.seen_context = data_context
        return {
            "report_id": "r1",
            "ticker": ticker,
            "report_type": report_type,
            "title": "t",
            "content": "c",
            "generated_at": "2026-09-23T00:00:00Z",
            "data_sources": [],
        }


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(research_router)
    return TestClient(app)


def test_news_sentiment_surfaces_fetch_failure_instead_of_neutral(monkeypatch):
    """新闻拉取异常旧代码只打 warning，然后返回 overall=neutral/score=0 的
    200 结果——与“确实没有新闻”不可区分，用户会当成真实分析。"""
    import backend.tools as tools_pkg

    def boom(*_args, **_kwargs):
        raise RuntimeError("news provider down")

    monkeypatch.setattr(tools_pkg, "get_company_news", boom)

    with _client() as client:
        response = client.post(
            "/api/research/news/sentiment",
            json={"ticker": "AAPL"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "News data unavailable"
    assert "news provider down" not in response.text


def test_news_sentiment_surfaces_analysis_failure_instead_of_neutral(monkeypatch):
    """LLM 分析失败旧代码返回全中性/0 分的 200 结果，与真实分析不可区分。"""
    import backend.services.news_sentiment as sentiment_module

    async def boom(*_args, **_kwargs):
        raise sentiment_module.SentimentAnalysisUnavailable("llm down")

    monkeypatch.setattr(sentiment_module, "analyze_news_sentiment", boom)

    with _client() as client:
        response = client.post(
            "/api/research/news/sentiment",
            json={"ticker": "AAPL", "news": [{"title": "公司发布季报", "summary": "净利润增长"}]},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Sentiment analysis unavailable"


def test_comprehensive_report_injects_company_info_and_news(monkeypatch):
    """工具按真实返回类型给值（str / list）时，两个上下文键都必须落进
    data_context。修复前因 AttributeError 被吞恒为空。"""
    import backend.services.report_generator as rg
    import backend.tools as tools_pkg

    fake = _FakeGenerator()
    monkeypatch.setattr(rg, "get_report_generator", lambda: fake)
    # 与 tools/financial.py 一致：返回 str
    monkeypatch.setattr(
        tools_pkg, "get_company_info",
        lambda ticker: f"Company Profile ({ticker}):\n- Name: Apple",
    )
    # 与 tools/news.py 一致：返回 List[Dict]
    monkeypatch.setattr(
        tools_pkg, "get_company_news",
        lambda ticker, limit=5: [{"title": "Apple beats estimates"}],
    )
    monkeypatch.setattr(tools_pkg, "get_financial_statements", lambda ticker: {})
    monkeypatch.setattr(
        tools_pkg, "get_stock_historical_data",
        lambda ticker, period="1y", interval="1d": {},
    )

    resp = _client().post(
        "/api/research/report/generate",
        json={
            "ticker": "AAPL",
            "report_type": "comprehensive",
            "include_news": True,
            "include_technical": True,
        },
    )
    assert resp.status_code == 200, resp.text

    assert fake.seen_context is not None
    assert "Company Profile" in fake.seen_context.get("company_info", "")
    news = fake.seen_context.get("news")
    assert isinstance(news, list) and news and news[0]["title"] == "Apple beats estimates"


def test_report_survives_tool_failures(monkeypatch):
    """工具异常时仅降级对应上下文，不拖垮整个报告生成。"""
    import backend.services.report_generator as rg
    import backend.tools as tools_pkg

    fake = _FakeGenerator()
    monkeypatch.setattr(rg, "get_report_generator", lambda: fake)

    def _boom(*a, **k):
        raise RuntimeError("provider down")

    monkeypatch.setattr(tools_pkg, "get_company_info", _boom)
    monkeypatch.setattr(tools_pkg, "get_company_news", _boom)
    monkeypatch.setattr(tools_pkg, "get_financial_statements", _boom)
    monkeypatch.setattr(tools_pkg, "get_stock_historical_data", _boom)

    resp = _client().post(
        "/api/research/report/generate",
        json={"ticker": "AAPL", "report_type": "comprehensive"},
    )
    assert resp.status_code == 200, resp.text
    assert fake.seen_context == {}


def test_financials_analyze_survives_str_company_info(monkeypatch):
    """get_company_info 返回 str 时 /financials/analyze 不得 500。

    bug：路由把 str 原样塞进 ``analyze_financials(company_info=...)``，
    analyzer 首行 ``(company_info or {}).get("name")`` 对 str 抛
    AttributeError——且在 try 之外，直接冒泡成 500。只要公司概况接口
    正常返回（恒为 str），财报分析端点必挂。
    """
    from types import SimpleNamespace

    import backend.services.financials_analyzer as fa
    import backend.tools as tools_pkg
    import backend.llm_config as llm_config

    monkeypatch.setattr(
        tools_pkg, "get_financial_statements",
        lambda ticker: {"income": {"revenue": 100}},
    )
    # 与 tools/financial.py 一致：返回 str
    monkeypatch.setattr(
        tools_pkg, "get_company_info",
        lambda ticker: f"Company Profile ({ticker}):\n- Name: Apple",
    )

    seen: dict = {}
    orig = fa.analyze_financials

    async def _spy(**kwargs):
        seen["company_info"] = kwargs.get("company_info")
        return await orig(**kwargs)

    monkeypatch.setattr(fa, "analyze_financials", _spy)

    class _FakeLLM:
        async def ainvoke(self, _prompt):
            return SimpleNamespace(
                content='{"overall_rating": {"score": 7, "label": "良好", "summary": "ok"}}'
            )

    monkeypatch.setattr(llm_config, "create_llm", lambda **_kw: _FakeLLM())

    resp = _client().post(
        "/api/research/financials/analyze", json={"ticker": "AAPL"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "success"
    # analyzer 契约是 Optional[Dict]——str 必须被归一/丢弃，不得原样透传
    assert isinstance(seen["company_info"], dict)


def test_smart_qa_flat_day_change_not_rendered_as_na(monkeypatch):
    """R81：quote.get("change_percent") or quote.get("change_pct","N/A")
    把真实 0.0%（平盘）当缺失顶替成 "N/A%"——平盘日 /qa 上下文显示
    "涨跌幅 N/A%"。修后显式 is not None 判定，0.0 如实展示。"""
    from types import SimpleNamespace

    import backend.llm_config as llm_config
    import backend.tools as tools_pkg

    monkeypatch.setattr(
        tools_pkg,
        "get_stock_price",
        lambda ticker: {"price": 185.2, "change_percent": 0.0},
    )
    monkeypatch.setattr(tools_pkg, "get_company_news", lambda ticker, limit=5: [])

    class _FakeLLM:
        async def ainvoke(self, _prompt):
            return SimpleNamespace(content="ok")

    monkeypatch.setattr(llm_config, "create_llm", lambda **_kw: _FakeLLM())

    resp = _client().post(
        "/api/research/qa", json={"question": "走势如何", "ticker": "AAPL"}
    )
    assert resp.status_code == 200, resp.text
    ctx = resp.json()["context_used"]
    assert any("涨跌幅 0.0%" in part for part in ctx), ctx


def _qa_context(monkeypatch, quote_payload):
    """跑一次 /qa，返回 context_used。get_stock_price 按 quote_payload 打桩。"""
    from types import SimpleNamespace

    import backend.llm_config as llm_config
    import backend.tools as tools_pkg

    monkeypatch.setattr(tools_pkg, "get_stock_price", lambda ticker: quote_payload)
    monkeypatch.setattr(tools_pkg, "get_company_news", lambda ticker, limit=5: [])

    class _FakeLLM:
        async def ainvoke(self, _prompt):
            return SimpleNamespace(content="ok")

    monkeypatch.setattr(llm_config, "create_llm", lambda **_kw: _FakeLLM())

    resp = _client().post(
        "/api/research/qa", json={"question": "走势如何", "ticker": "AAPL"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["context_used"]


def test_smart_qa_injects_price_context_for_real_str_quote(monkeypatch):
    """tools/price.get_stock_price 的真实返回类型是 str（签名 `-> str`：成功是
    源函数的格式化文本，失败只有 price.py:160 一处 "Error: ..."）。

    旧代码 `if quote and not quote.get("error")` 对 str 调 .get 必抛
    AttributeError，被紧邻的 `except Exception` 吞成一条 warning——
    【最新行情】永远注不进 /qa 的 prompt，且是 100% 必触发（成功路径也是 str）。

    同文件对完全相同的 bug 已修过两次并留了注释（:93-100 company_info、
    :123-130 news），唯独 price 漏了。既有 /qa 用例喂的全是 dict，
    是生产环境不存在的形状，所以测试面测不到这条路。"""
    quote = "AAPL Current Price: $255.46 | Change: +1.20 (+0.47%)"

    ctx = _qa_context(monkeypatch, quote)

    assert any("最新行情" in part for part in ctx), ctx
    assert any("255.46" in part for part in ctx), ctx


def test_smart_qa_omits_price_context_for_error_string(monkeypatch):
    """失败字符串与成功字符串同类型，必须按 "Error:" 前缀判错后丢弃，
    不得把 "Error: All data sources failed..." 当行情注进模型上下文。"""
    quote = "Error: All data sources failed to retrieve the price for AAPL. Please try again later."

    ctx = _qa_context(monkeypatch, quote)

    assert not any("最新行情" in part for part in ctx), ctx
    assert not any("Error:" in part for part in ctx), ctx

