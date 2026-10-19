# -*- coding: utf-8 -*-
import asyncio
import builtins
import logging
from datetime import datetime, timezone

import pytest


def _run(coro):
    return asyncio.run(coro)


def _deep_verifier_state():
    return {
        "query": "investment report",
        "output_mode": "investment_report",
        "ui_context": {"analysis_depth": "deep_research"},
        "operation": {"name": "investment_report", "confidence": 0.8, "params": {}},
        "subject": {"subject_type": "company", "tickers": ["AAPL"]},
        "artifacts": {"step_results": {}, "evidence_pool": []},
        "trace": {},
    }


def test_stub_render_vars_does_not_format_boolean_technical_metrics():
    from backend.graph.nodes.synthesize import _stub_render_vars

    state = {
        "query": "technical",
        "output_mode": "brief",
        "operation": {"name": "qa"},
        "subject": {"subject_type": "company", "tickers": ["AAPL"]},
        "plan_ir": {
            "steps": [{"id": "tech", "kind": "tool", "name": "get_technical_snapshot"}]
        },
        "artifacts": {
            "step_results": {
                "tech": {"output": {"ma20": True, "ma50": False, "ma200": 200.0}}
            }
        },
    }

    render_vars = _stub_render_vars(state)
    snapshot = render_vars["technical_snapshot"]

    assert "MA20 1.00" not in snapshot
    assert "MA50 0.00" not in snapshot


def test_stub_render_vars_ignores_boolean_fundamental_yoy():
    from backend.graph.nodes.synthesize import _stub_render_vars

    state = {
        "query": "fundamental",
        "output_mode": "brief",
        "operation": {"name": "qa"},
        "subject": {"subject_type": "company", "tickers": ["AAPL"]},
        "plan_ir": {"steps": [{"id": "fund", "kind": "agent", "name": "fundamental_agent"}]},
        "artifacts": {
            "step_results": {
                "fund": {
                    "output": {
                        "summary": "ok",
                        "evidence": [{"text": "revenue", "meta": {"yoy": True}}],
                    }
                }
            }
        },
    }

    render_vars = _stub_render_vars(state)

    assert "同比增长" not in render_vars["conclusion"]


def test_deep_verifier_import_error_is_redacted(monkeypatch, caplog):
    import importlib

    synth_mod = importlib.import_module("backend.graph.nodes.synthesize")
    verifier_mod = importlib.import_module("backend.graph.nodes.synthesize_verifier")

    sentinel = "PRIVATE_VERIFIER_IMPORT_DETAIL"
    real_import = builtins.__import__

    def _import(name, *args, **kwargs):
        if name == "backend.llm_config":
            raise ImportError(sentinel)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _import)
    caplog.set_level(logging.WARNING, logger=verifier_mod.__name__)

    result = _run(
        synth_mod._run_deep_report_verifier(
            state=_deep_verifier_state(),
            generated_text="report content",
            grounding_text="evidence",
        )
    )

    assert result["error"] == "ImportError"
    assert sentinel not in str(result)
    assert sentinel not in caplog.text


def test_deep_verifier_runtime_error_is_redacted(monkeypatch, caplog):
    import importlib
    import backend.llm_config as llm_config

    synth_mod = importlib.import_module("backend.graph.nodes.synthesize")
    verifier_mod = importlib.import_module("backend.graph.nodes.synthesize_verifier")

    sentinel = "PRIVATE_VERIFIER_RUNTIME_DETAIL"

    async def _fail_verification(*_args, **_kwargs):
        raise RuntimeError(sentinel)

    monkeypatch.setattr(llm_config, "create_llm", lambda **_kwargs: object())
    monkeypatch.setattr(verifier_mod, "ainvoke_with_rate_limit_retry", _fail_verification)
    caplog.set_level(logging.WARNING, logger=verifier_mod.__name__)

    result = _run(
        synth_mod._run_deep_report_verifier(
            state=_deep_verifier_state(),
            generated_text="report content",
            grounding_text="evidence",
        )
    )

    assert result["error"] == "RuntimeError"
    assert sentinel not in str(result)
    assert sentinel not in caplog.text


def test_narrative_llm_init_error_log_is_redacted(monkeypatch, caplog):
    import importlib
    import backend.llm_config as llm_config

    synth_mod = importlib.import_module("backend.graph.nodes.synthesize")
    narrative_mod = importlib.import_module("backend.graph.nodes.synthesize_narrative")
    sentinel = "PRIVATE_NARRATIVE_INIT_DETAIL"

    def _fail_create_llm(**_kwargs):
        raise RuntimeError(sentinel)

    monkeypatch.setattr(llm_config, "create_llm", _fail_create_llm)
    caplog.set_level(logging.WARNING, logger=narrative_mod.__name__)

    result = _run(synth_mod._generate_narrative_draft(_deep_verifier_state(), {}, {}))

    assert result == ("", None)
    assert sentinel not in caplog.text
    assert "[Synthesize/narrative] LLM init failed" in caplog.text


def test_narrative_llm_call_error_trace_and_log_are_redacted(monkeypatch, caplog):
    import importlib
    import backend.llm_config as llm_config

    synth_mod = importlib.import_module("backend.graph.nodes.synthesize")
    narrative_mod = importlib.import_module("backend.graph.nodes.synthesize_narrative")
    sentinel = "PRIVATE_NARRATIVE_CALL_DETAIL"
    trace = {}

    async def _fail_call(*_args, **_kwargs):
        raise RuntimeError(sentinel)

    monkeypatch.setattr(llm_config, "create_llm", lambda **_kwargs: object())
    monkeypatch.setattr(narrative_mod, "ainvoke_with_rate_limit_retry", _fail_call)
    caplog.set_level(logging.WARNING, logger=narrative_mod.__name__)

    result = _run(synth_mod._generate_narrative_draft(_deep_verifier_state(), {}, trace))

    assert result == ("", None)
    assert sentinel not in str(trace)
    assert sentinel not in caplog.text
    assert (trace.get("failures") or [])[-1]["error"] == "RuntimeError"


def test_synthesize_llm_init_error_trace_and_event_are_redacted(monkeypatch, caplog):
    import importlib
    import backend.llm_config as llm_config

    synth_mod = importlib.import_module("backend.graph.nodes.synthesize")
    sentinel = "PRIVATE_SYNTH_INIT_DETAIL"
    events = []

    def _fail_create_llm(**_kwargs):
        raise RuntimeError(sentinel)

    async def _capture_event(event):
        events.append(event)

    monkeypatch.setenv("LANGGRAPH_SYNTHESIZE_MODE", "llm")
    monkeypatch.setattr(llm_config, "create_llm", _fail_create_llm)
    monkeypatch.setattr(synth_mod, "emit_event", _capture_event)
    caplog.set_level(logging.WARNING, logger=synth_mod.__name__)

    result = _run(synth_mod.synthesize(_deep_verifier_state()))

    serialized = str({"result": result, "events": events})
    assert sentinel not in serialized
    assert sentinel not in caplog.text
    assert (result["trace"].get("failures") or [])[-1]["error"] == "RuntimeError"
    assert events[-1]["error"] == "RuntimeError"


def test_synthesize_llm_call_error_trace_event_and_log_are_redacted(monkeypatch, caplog):
    import importlib
    import backend.llm_config as llm_config

    synth_mod = importlib.import_module("backend.graph.nodes.synthesize")
    sentinel = "PRIVATE_SYNTH_CALL_DETAIL"
    events = []

    async def _fail_call(*_args, **_kwargs):
        raise RuntimeError(sentinel)

    async def _capture_event(event):
        events.append(event)

    monkeypatch.setenv("LANGGRAPH_SYNTHESIZE_MODE", "llm")
    monkeypatch.setattr(llm_config, "create_llm", lambda **_kwargs: object())
    monkeypatch.setattr(synth_mod, "ainvoke_with_rate_limit_retry", _fail_call)
    monkeypatch.setattr(synth_mod, "emit_event", _capture_event)
    caplog.set_level(logging.WARNING, logger=synth_mod.__name__)

    result = _run(synth_mod.synthesize(_deep_verifier_state()))

    serialized = str({"result": result, "events": events})
    assert sentinel not in serialized
    assert sentinel not in caplog.text
    assert (result["trace"].get("failures") or [])[-1]["error"] == "RuntimeError"
    assert events[-1]["error"] == "RuntimeError"


def test_synthesize_llm_mode_handles_datetime_in_inputs(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_SYNTHESIZE_MODE", "llm")

    class _FakeResp:
        def __init__(self, content: str):
            self.content = content

    class _FakeLLM:
        async def ainvoke(self, _messages):
            return _FakeResp('{"summary":"ok","risks":"- r"}')

    import backend.llm_config as llm_config_mod

    monkeypatch.setattr(llm_config_mod, "create_llm", lambda temperature=0.2: _FakeLLM())

    from backend.graph.nodes.synthesize import synthesize

    state = {
        "query": "NVDA 最新股价和技术面分析",
        "output_mode": "brief",
        "operation": {"name": "company_news_brief", "confidence": 0.8, "params": {}},
        "subject": {"subject_type": "company", "tickers": ["NVDA"], "selection_payload": []},
        "artifacts": {
            "step_results": {
                "s1": {
                    "cached": False,
                    "output": {
                        "as_of": datetime(2026, 2, 7, 21, 47, 39, tzinfo=timezone.utc),
                        "price": 132.6,
                    },
                }
            },
            "evidence_pool": [],
        },
        "trace": {},
    }

    out = _run(synthesize(state))
    render_vars = (out.get("artifacts") or {}).get("render_vars") or {}
    assert isinstance(render_vars, dict) and render_vars


def test_synthesize_stub_produces_render_vars_without_placeholders(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_SYNTHESIZE_MODE", "stub")

    from backend.graph.nodes.synthesize import synthesize

    state = {
        "query": "分析影响",
        "output_mode": "brief",
        "operation": {"name": "analyze_impact", "confidence": 0.7, "params": {}},
        "subject": {
            "subject_type": "news_item",
            "tickers": [],
            "selection_ids": ["n1"],
            "selection_types": ["news"],
            "selection_payload": [{"type": "news", "id": "n1", "title": "t", "snippet": "s"}],
        },
        "artifacts": {
            "evidence_pool": [{"title": "t", "url": None, "snippet": "s", "source": "x", "published_date": "2026-02-03"}]
        },
        "trace": {},
    }

    out = _run(synthesize(state))
    artifacts = out.get("artifacts") or {}
    render_vars = artifacts.get("render_vars") or {}
    assert isinstance(render_vars, dict) and render_vars

    assert render_vars.get("news_summary")
    assert render_vars.get("impact_analysis")

    for v in render_vars.values():
        assert "待实现" not in str(v)


def test_synthesize_llm_mode_includes_compare_keys_and_preserves_stub_defaults(monkeypatch):
    """
    Regression: when LANGGRAPH_SYNTHESIZE_MODE=llm, the LLM may omit compare-specific keys.
    We must (a) expose compare keys in the prompt schema and (b) fall back to stub defaults
    so the compare template never renders placeholder sections.
    """
    monkeypatch.setenv("LANGGRAPH_SYNTHESIZE_MODE", "llm")

    captured: dict[str, str] = {}

    class _FakeResp:
        def __init__(self, content: str):
            self.content = content

    class _FakeLLM:
        async def ainvoke(self, messages):
            captured["prompt"] = messages[0].content
            # LLM may omit compare keys or (worse) hallucinate metrics; we should preserve stub data sections.
            return _FakeResp('{"risks": "- risk from llm", "comparison_metrics": "PE 31x vs 35x"}')

    import backend.llm_config as llm_config_mod

    monkeypatch.setattr(llm_config_mod, "create_llm", lambda temperature=0.2: _FakeLLM())

    from backend.graph.nodes.synthesize import synthesize

    state = {
        "query": "Compare AAPL vs MSFT",
        "output_mode": "brief",
        "operation": {"name": "compare", "confidence": 0.8, "params": {}},
        "subject": {
            "subject_type": "company",
            "tickers": ["AAPL", "MSFT"],
            "selection_ids": [],
            "selection_types": [],
            "selection_payload": [],
        },
        "plan_ir": {
            "steps": [
                {
                    "id": "s1",
                    "kind": "tool",
                    "name": "get_performance_comparison",
                    "inputs": {"tickers": {"AAPL": "AAPL", "MSFT": "MSFT"}},
                    "optional": False,
                }
            ]
        },
        "artifacts": {
            "step_results": {
                "s1": {
                    "cached": False,
                    "output": "Performance Comparison:\\nAAPL ...\\nMSFT ...\\n",
                }
            },
            "evidence_pool": [],
        },
        "trace": {},
    }

    out = _run(synthesize(state))
    artifacts = out.get("artifacts") or {}
    render_vars = artifacts.get("render_vars") or {}

    assert "comparison_conclusion" in captured.get("prompt", "")
    assert "comparison_metrics" in captured.get("prompt", "")

    assert "AAPL" in str(render_vars.get("comparison_conclusion") or "")
    assert "PE 31x" not in str(render_vars.get("comparison_metrics") or "")
    risks = str(render_vars.get("risks") or "")
    assert "risk from llm" in risks
    assert "不构成投资建议" in risks


def test_synthesize_stub_compare_parses_label_rows_via_step_input_mapping(monkeypatch):
    """
    Regression: planner may call get_performance_comparison with a label->ticker mapping,
    producing a table with "Apple/Microsoft" rows. Synthesize must still emit explicit
    YTD/1Y compare lines for tickers (AAPL/MSFT).
    """
    monkeypatch.setenv("LANGGRAPH_SYNTHESIZE_MODE", "stub")

    from backend.graph.nodes.synthesize import synthesize

    state = {
        "query": "对比 AAPL 和 MSFT 哪个更值得投资",
        "output_mode": "brief",
        "operation": {"name": "compare", "confidence": 0.8, "params": {}},
        "subject": {
            "subject_type": "company",
            "tickers": ["AAPL", "MSFT"],
            "selection_ids": [],
            "selection_types": [],
            "selection_payload": [],
        },
        "plan_ir": {
            "steps": [
                {
                    "id": "s1",
                    "kind": "tool",
                    "name": "get_performance_comparison",
                    "inputs": {"tickers": {"Apple": "AAPL", "Microsoft": "MSFT"}},
                    "optional": False,
                }
            ]
        },
        "artifacts": {
            "step_results": {
                "s1": {
                    "cached": False,
                    "output": (
                        "Performance Comparison:\n\n"
                        "Ticker                    Current Price   YTD %        1-Year %\n"
                        "-------------------------------------------------------------------\n"
                        "Apple                     269.48          -0.56%       +15.92%\n"
                        "Microsoft                 411.21          -13.05%      -0.50%\n\n"
                        "Notes:\n"
                        "- Apple: used fallback price history\n"
                        "- Microsoft: used fallback price history\n"
                    ),
                }
            },
            "evidence_pool": [],
        },
        "trace": {},
    }

    out = _run(synthesize(state))
    artifacts = out.get("artifacts") or {}
    render_vars = artifacts.get("render_vars") or {}
    conclusion = str(render_vars.get("comparison_conclusion") or "")
    metrics = str(render_vars.get("comparison_metrics") or "")

    assert "结论（历史回报维度）" in conclusion and "AAPL" in conclusion and "MSFT" in conclusion
    assert "YTD：" in metrics and "AAPL" in metrics and "MSFT" in metrics
    assert "-0.56%" in metrics and "-13.05%" in metrics
    assert "1Y：" in metrics and "+15.92%" in metrics and "-0.50%" in metrics


def test_synthesize_stub_company_fetch_formats_news_summary(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_SYNTHESIZE_MODE", "stub")

    from backend.graph.nodes.synthesize import synthesize

    state = {
        "query": "特斯拉最近有什么重大新闻",
        "output_mode": "brief",
        "operation": {"name": "fetch", "confidence": 0.7, "params": {}},
        "subject": {
            "subject_type": "company",
            "tickers": ["TSLA"],
            "selection_ids": [],
            "selection_types": [],
            "selection_payload": [],
        },
        "plan_ir": {
            "steps": [
                {
                    "id": "s1",
                    "kind": "tool",
                    "name": "get_company_news",
                    "inputs": {"ticker": "TSLA"},
                    "optional": True,
                }
            ]
        },
        "artifacts": {
            "step_results": {
                "s1": {
                    "cached": False,
                    "output": '[{"title":"Tesla update","url":"https://example.com/a","source":"x","published_at":"2026-02-04"}]',
                }
            },
            "evidence_pool": [],
        },
        "trace": {"executor": {"type": "live_tools"}},
    }

    out = _run(synthesize(state))
    artifacts = out.get("artifacts") or {}
    render_vars = artifacts.get("render_vars") or {}
    news_summary = str(render_vars.get("news_summary") or "")
    conclusion = str(render_vars.get("conclusion") or "")

    assert "[Tesla update](https://example.com/a)" in news_summary
    assert "你想先看哪一条" in conclusion


def test_synthesize_llm_mode_formats_risks_dict(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_SYNTHESIZE_MODE", "llm")

    class _FakeResp:
        def __init__(self, content: str):
            self.content = content

    class _FakeLLM:
        async def ainvoke(self, messages):
            return _FakeResp(
                '{"risks": {"AAPL": "r1", "MSFT": "r2", "disclaimer": "past performance..."}}'
            )

    import backend.llm_config as llm_config_mod

    monkeypatch.setattr(llm_config_mod, "create_llm", lambda temperature=0.2: _FakeLLM())

    from backend.graph.nodes.synthesize import synthesize

    state = {
        "query": "Compare AAPL vs MSFT",
        "output_mode": "brief",
        "operation": {"name": "compare", "confidence": 0.8, "params": {}},
        "subject": {
            "subject_type": "company",
            "tickers": ["AAPL", "MSFT"],
            "selection_ids": [],
            "selection_types": [],
            "selection_payload": [],
        },
        "artifacts": {"step_results": {}, "evidence_pool": []},
        "trace": {},
    }

    out = _run(synthesize(state))
    artifacts = out.get("artifacts") or {}
    render_vars = artifacts.get("render_vars") or {}
    risks = str(render_vars.get("risks") or "")

    assert "AAPL" in risks and "MSFT" in risks
    assert "{" not in risks and "}" not in risks
    assert "不构成投资建议" in risks


def test_sanitize_llm_section_flattens_json_lines():
    from backend.graph.nodes.synthesize import _sanitize_llm_section

    raw = """
{"event": "iPhone 17 AI 换机周期", "impact": "Q4 iPhone 营收增长 6%"}
{"risk": "技术面回调风险", "detail": "RSI > 80，短期存在均值回归压力"}
""".strip()

    out = _sanitize_llm_section(raw)

    assert "iPhone 17 AI 换机周期：Q4 iPhone 营收增长 6%" in out
    assert "技术面回调风险：RSI > 80，短期存在均值回归压力" in out
    assert "{" not in out and "}" not in out


def test_scrub_unverified_future_claims_removes_unsupported_release_claim():
    from backend.graph.nodes.synthesize import _scrub_unverified_future_claims

    draft = "预计2026Q2发布Gemini 2.0并推动广告业务增长。"
    evidence = "当前仅有PE 28.5与RSI 55等指标，无产品发布时间信息。"

    out = _scrub_unverified_future_claims(draft, evidence)

    assert "未经证据验证" in out
    assert "Gemini 2.0" not in out


def test_scrub_unverified_future_claims_keeps_claim_when_grounded():
    from backend.graph.nodes.synthesize import _scrub_unverified_future_claims

    draft = "预计2026Q2发布Gemini 2.0并推动广告业务增长。"
    evidence = "公司公告提到：预计2026Q2发布Gemini 2.0，用于广告产品。"

    out = _scrub_unverified_future_claims(draft, evidence)

    assert out == draft


def test_synthesize_llm_deep_research_applies_verifier_redaction(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_SYNTHESIZE_MODE", "llm")

    class _FakeResp:
        def __init__(self, content: str):
            self.content = content

    class _FakeLLM:
        async def ainvoke(self, _messages):
            return _FakeResp(
                '{"summary":"Gemini 2.0 will launch in 2026Q2.","conclusion":"Gemini 2.0 will launch in 2026Q2 and accelerate ad growth.","risks":"- risk"}'
            )

    import importlib
    import backend.llm_config as llm_config_mod
    synth_mod = importlib.import_module("backend.graph.nodes.synthesize")

    monkeypatch.setattr(llm_config_mod, "create_llm", lambda temperature=0.2, **_kwargs: _FakeLLM())

    async def _fake_verifier(*, state, generated_text, grounding_text):
        assert "Gemini 2.0 will launch in 2026Q2" in generated_text
        assert isinstance(grounding_text, str)
        return {
            "enabled": True,
            "checked": True,
            "unsupported_claims": [
                {"claim": "Gemini 2.0 will launch in 2026Q2", "reason": "missing evidence"}
            ],
        }

    monkeypatch.setattr(synth_mod, "_run_deep_report_verifier", _fake_verifier)

    state = {
        "query": "deep report on GOOG",
        "output_mode": "investment_report",
        "ui_context": {"analysis_depth": "deep_research"},
        "operation": {"name": "investment_report", "confidence": 0.8, "params": {}},
        "subject": {
            "subject_type": "company",
            "tickers": ["GOOG"],
            "selection_ids": [],
            "selection_types": [],
            "selection_payload": [],
        },
        "artifacts": {"step_results": {}, "evidence_pool": []},
        "trace": {},
    }

    out = _run(synth_mod.synthesize(state))
    artifacts = out.get("artifacts") or {}
    render_vars = artifacts.get("render_vars") or {}
    conclusion = str(render_vars.get("conclusion") or "")

    assert "Gemini 2.0 will launch in 2026Q2" not in conclusion
    assert synth_mod._HALLUCINATION_SAFE_PLACEHOLDER in conclusion
    verifier = artifacts.get("verifier_result") or {}
    assert verifier.get("checked") is True
    assert len(verifier.get("unsupported_claims") or []) == 1
    assert len(verifier.get("unresolved_unsupported_claims") or []) == 0


def test_synthesize_narrative_persists_verifier_result(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_SYNTHESIZE_MODE", "narrative")

    import importlib
    synth_mod = importlib.import_module("backend.graph.nodes.synthesize")

    async def _fake_generate(_state, _render_vars, _trace):
        return (
            "## report\n\ncontent",
            {
                "enabled": True,
                "checked": True,
                "unsupported_claims": [{"claim": "c1", "reason": "r1"}],
            },
        )

    monkeypatch.setattr(synth_mod, "_generate_narrative_draft", _fake_generate)

    state = {
        "query": "investment report",
        "output_mode": "investment_report",
        "ui_context": {"analysis_depth": "deep_research"},
        "operation": {"name": "investment_report", "confidence": 0.8, "params": {}},
        "subject": {"subject_type": "company", "tickers": ["AAPL"]},
        "artifacts": {"step_results": {}, "evidence_pool": []},
        "trace": {},
    }

    out = _run(synth_mod.synthesize(state))
    artifacts = out.get("artifacts") or {}
    assert artifacts.get("draft_markdown")
    verifier = artifacts.get("verifier_result") or {}
    assert verifier.get("checked") is True
    assert len(verifier.get("unsupported_claims") or []) == 1


def _narrative_state(persona_id: str) -> dict:
    """narrative 模式的真实 state 形状。

    关键在 persona_id/persona_config 两项：build_initial_state:63-65 无条件
    写入它们（`get_persona(None).id == "neutral"` 也是真值），所以任何走完
    整管线的请求在 synthesize 里都带着真值 persona_id。既有的
    test_synthesize_narrative_persists_verifier_result 手搓 state 时漏了
    这两项，才让 persona 观测分支从未被执行过。
    """
    from backend.personas.registry import get_persona

    persona = get_persona(persona_id)
    return {
        "query": "investment report",
        "output_mode": "investment_report",
        "ui_context": {"analysis_depth": "deep_research"},
        "operation": {"name": "investment_report", "confidence": 0.8, "params": {}},
        "subject": {"subject_type": "company", "tickers": ["AAPL"]},
        "artifacts": {"step_results": {}, "evidence_pool": []},
        "trace": {},
        "persona_id": persona.id,
        "persona_config": persona.model_dump(),
    }


@pytest.mark.parametrize(
    ("persona_id", "expect_lens_applied"),
    [("neutral", False), ("value_investor", True)],
)
def test_synthesize_narrative_records_persona_lens_without_crashing(
    monkeypatch, persona_id, expect_lens_applied
):
    """narrative 模式 + 真值 persona_id 必须活着跑完并如实记录 lens 是否生效。

    synthesize.py:159 原本写的是 `bool(persona_lens_block)`，而该名字只在
    synthesize_narrative.py:191 里作为局部变量存在——本模块既没定义也没导入
    （:41 导入的是 `_format_persona_lens` 函数本身，且除此行外无处使用）。
    于是 `if _persona_id:` 为真时必抛 NameError，而该条件在真实管线里恒为真，
    narrative 模式 100% 崩在这一行。

    两种 persona 都钉住，避免"把表达式硬编码成 False"式的假修复：neutral 的
    synthesis_lens 为空串 → 未注入；value_investor 非空 → 已注入。
    """
    monkeypatch.setenv("LANGGRAPH_SYNTHESIZE_MODE", "narrative")

    import importlib
    synth_mod = importlib.import_module("backend.graph.nodes.synthesize")

    async def _fake_generate(_state, _render_vars, _trace):
        return ("## report\n\ncontent", {"enabled": True, "checked": True})

    monkeypatch.setattr(synth_mod, "_generate_narrative_draft", _fake_generate)

    state = _narrative_state(persona_id)
    out = _run(synth_mod.synthesize(state))

    runtime = (out.get("trace") or {}).get("synthesize_runtime") or {}
    assert runtime.get("persona_id") == persona_id
    assert runtime.get("persona_lens_applied") is expect_lens_applied
    assert (out.get("artifacts") or {}).get("draft_markdown")


def test_compute_unresolved_unsupported_claims_returns_residual_claims():
    from backend.graph.nodes.synthesize import _compute_unresolved_unsupported_claims

    claims = [
        {"claim": "Claim A", "reason": "missing evidence"},
        {"claim": "Claim B", "reason": "missing evidence"},
    ]
    unresolved = _compute_unresolved_unsupported_claims(
        "This text still contains Claim B only.",
        claims,
    )
    assert len(unresolved) == 1
    assert unresolved[0]["claim"] == "Claim B"


def test_extract_brief_headline_strips_numbered_prefixes():
    """R26 回归：lstrip("-•*0-9. ") 是字符集合（只含 0/-/9），"3. xxx" 的
    编号剥不掉，晨报标题带残留前缀。"""
    from backend.graph.nodes.synthesize import _extract_brief_headline

    news_text = "3. Apple beats earnings expectations this quarter\n4. other line"
    headline = _extract_brief_headline(news_text)
    assert headline == "Apple beats earnings expectations this quarter"

    assert _extract_brief_headline("- Bullet style headline here") == "Bullet style headline here"
    assert _extract_brief_headline("9. Nine prefixed headline text") == "Nine prefixed headline text"


def _company_render_vars_state(step_results):
    return {
        "query": "AAPL 投资报告",
        "output_mode": "investment_report",
        "ui_context": {"analysis_depth": "deep_research"},
        "operation": {"name": "investment_report"},
        "subject": {"subject_type": "company", "tickers": ["AAPL"]},
        "plan_ir": {"steps": step_results["steps"]},
        "artifacts": {"step_results": step_results["results"], "evidence_pool": []},
        "trace": {},
    }


def test_all_agents_failed_does_not_render_as_a_balanced_neutral_verdict():
    """全部 agent 无产出时，此前仍打印"中性（Neutral）/多空信号交织"——读起来
    像一份平衡结论，实际是一条证据都没有（finsight-silent-success-forbidden）。"""
    from backend.graph.nodes.synthesize import _stub_render_vars

    state = _company_render_vars_state(
        {
            "steps": [
                {"id": "a1", "kind": "agent", "name": "price_agent"},
                {"id": "a2", "kind": "agent", "name": "fundamental_agent"},
            ],
            "results": {
                "a1": {"output": {"skipped": True, "reason": "upstream_failed"}},
                "a2": {"output": {"error": "boom"}},
            },
        }
    )

    thesis = _stub_render_vars(state)["investment_thesis"]

    assert "中性（Neutral）" not in thesis
    assert "无法形成方向（数据缺失）" in thesis
    assert "数据置信度" not in thesis


def test_partial_evidence_still_renders_a_verdict_and_confidence_line():
    """有证据时结论照旧，且缺 confidence 不再把"数据置信度"整行吞掉。"""
    from backend.graph.nodes.synthesize import _stub_render_vars

    state = _company_render_vars_state(
        {
            "steps": [{"id": "a1", "kind": "agent", "name": "price_agent"}],
            "results": {"a1": {"output": {"summary": "近一月股价上涨 8%，成交温和放大"}}},
        }
    )

    thesis = _stub_render_vars(state)["investment_thesis"]

    assert "综合研判：中性偏多（Slightly Bullish）" in thesis
    assert "无法形成方向" not in thesis
    assert "数据置信度：** 无" in thesis
