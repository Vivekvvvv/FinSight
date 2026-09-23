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
