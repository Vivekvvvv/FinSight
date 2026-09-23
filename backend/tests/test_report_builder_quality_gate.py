# -*- coding: utf-8 -*-

from backend.graph.report_builder import _build_report_quality_hints, build_report_payload


def test_build_report_payload_adds_quality_gap_for_deep_report_when_requirements_missing():
    state = {
        "output_mode": "investment_report",
        "subject": {"subject_type": "company", "tickers": ["AAPL"]},
        "policy": {"allowed_agents": []},
        "plan_ir": {"steps": []},
        "artifacts": {
            "draft_markdown": "## 投资研报：AAPL\n\n",
            "evidence_pool": [
                {
                    "title": "Apple 10-K",
                    "url": "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm",
                    "snippet": "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm",
                    "source": "sec",
                    "published_date": "2026-02-05T00:00:00Z",
                    "confidence": 0.8,
                }
            ],
            "step_results": {},
            "errors": [],
            "render_vars": {"investment_summary": "测试摘要"},
        },
        "trace": {},
    }

    report = build_report_payload(
        state=state,
        query="请做 Apple 深度投资报告（deep report，filing document longform）",
        thread_id="t-quality-gap",
    )
    assert isinstance(report, dict)

    tags = report.get("tags") or []
    assert "quality_gap" in tags

    risks = report.get("risks") or []
    assert any("质量门槛未满足" in str(item) for item in risks)

    synthesis_report = report.get("synthesis_report") or ""
    assert "## 研究完整性校验" in synthesis_report

    hints = report.get("report_hints") or {}
    quality = hints.get("quality") or {}
    assert quality.get("deep_report_required") is True
    assert quality.get("qualified") is False
    assert isinstance(quality.get("missing_requirements"), list)
    assert quality.get("missing_requirements")
    report_quality = report.get("report_quality") or {}
    assert report_quality.get("state") in {"warn", "block"}
    assert isinstance(report_quality.get("reasons"), list)


def test_build_report_payload_no_quality_gap_when_deep_report_requirements_are_met():
    state = {
        "output_mode": "investment_report",
        "subject": {"subject_type": "company", "tickers": ["AAPL"]},
        "policy": {"allowed_agents": []},
        "plan_ir": {"steps": []},
        "artifacts": {
            "draft_markdown": "## 投资研报：AAPL\n\n",
            "evidence_pool": [
                {
                    "title": "Apple 10-K annual report",
                    "url": "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm",
                    "snippet": "Apple annual filing discusses revenue mix, gross margin trend, and capital allocation policy in detail.",
                    "source": "sec",
                    "published_date": "2026-02-05T00:00:00Z",
                    "confidence": 0.8,
                },
                {
                    "title": "Apple 10-Q quarterly report",
                    "url": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000008/aapl-20241228.htm",
                    "snippet": "Quarterly filing provides updated segment growth, cash flow changes, and working capital profile.",
                    "source": "sec",
                    "published_date": "2026-02-05T00:00:00Z",
                    "confidence": 0.8,
                },
                {
                    "title": "Apple earnings call transcript",
                    "url": "https://www.cnbc.com/2026/02/10/apple-earnings-call-transcript.html",
                    "snippet": "Management answered questions on guidance, iPhone demand, AI roadmap, and margin outlook.",
                    "source": "cnbc",
                    "published_date": "2026-02-05T00:00:00Z",
                    "confidence": 0.8,
                },
                {
                    "title": "CNBC Apple coverage",
                    "url": "https://www.cnbc.com/quotes/AAPL",
                    "snippet": "CNBC coverage summarizes analyst rating changes and short-term risk sentiment after earnings.",
                    "source": "cnbc",
                    "published_date": "2026-02-05T00:00:00Z",
                    "confidence": 0.8,
                },
            ],
            "step_results": {},
            "errors": [],
            "render_vars": {"investment_summary": "测试摘要"},
        },
        "trace": {},
    }

    report = build_report_payload(
        state=state,
        query="请做 Apple 深度投资报告（deep report，filing document longform）",
        thread_id="t-quality-pass",
    )
    assert isinstance(report, dict)

    tags = report.get("tags") or []
    assert "quality_gap" not in tags

    hints = report.get("report_hints") or {}
    quality = hints.get("quality") or {}
    assert quality.get("deep_report_required") is True
    assert quality.get("qualified") is True


def test_quality_hints_technical_query_does_not_require_10k_or_10q():
    quality = _build_report_quality_hints(
        query="AAPL technical analysis with RSI and MACD",
        citations=[
            {
                "title": "AAPL technical snapshot",
                "url": "https://www.cnbc.com/quotes/AAPL",
                "snippet": "RSI and MACD indicate neutral momentum while price stays near short-term support.",
            }
        ],
    )

    assert quality.get("report_type") == "technical"
    assert quality.get("deep_report_required") is False
    missing = quality.get("missing_requirements") or []
    assert all("10-K" not in str(item) and "10-Q" not in str(item) for item in missing)


def test_build_report_payload_quality_penalty_is_graded_not_hard_capped():
    state = {
        "output_mode": "investment_report",
        "subject": {"subject_type": "company", "tickers": ["AAPL"]},
        "policy": {"allowed_agents": ["price_agent", "news_agent"]},
        "plan_ir": {
            "steps": [
                {"id": "s1", "kind": "agent", "name": "price_agent", "inputs": {}},
                {"id": "s2", "kind": "agent", "name": "news_agent", "inputs": {}},
            ]
        },
        "artifacts": {
            "draft_markdown": "## 投资研报：AAPL\n\n",
            "evidence_pool": [
                {
                    "title": "Apple 10-K annual report",
                    "url": "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm",
                    "snippet": "short",
                    "source": "sec",
                    "published_date": "2026-02-05T00:00:00Z",
                    "confidence": 0.8,
                },
                {
                    "title": "Apple 10-Q quarterly report",
                    "url": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000008/aapl-20241228.htm",
                    "snippet": "short",
                    "source": "sec",
                    "published_date": "2026-02-05T00:00:00Z",
                    "confidence": 0.8,
                },
                {
                    "title": "Apple earnings call transcript",
                    "url": "https://www.cnbc.com/2026/02/10/apple-earnings-call-transcript.html",
                    "snippet": "short",
                    "source": "cnbc",
                    "published_date": "2026-02-10T00:00:00Z",
                    "confidence": 0.8,
                },
            ],
            "step_results": {
                "s1": {"output": {"summary": "price ok", "confidence": 0.95}},
                "s2": {"output": {"summary": "news ok", "confidence": 0.95}},
            },
            "errors": [],
            "render_vars": {"investment_summary": "测试摘要"},
        },
        "trace": {},
    }

    report = build_report_payload(
        state=state,
        query="AAPL deep report with filing and transcript checks",
        thread_id="t-quality-graded-penalty",
    )
    assert isinstance(report, dict)

    confidence = float(report.get("confidence_score") or 0.0)
    # Only snippet quality missing => minor penalty, should stay well above legacy hard cap 0.62.
    assert confidence > 0.85


def test_build_report_payload_populates_grounding_metadata():
    state = {
        "output_mode": "investment_report",
        "subject": {"subject_type": "company", "tickers": ["AAPL"]},
        "policy": {"allowed_agents": []},
        "plan_ir": {"steps": []},
        "artifacts": {
            "draft_markdown": "## 投资研报：AAPL\n\n",
            "evidence_pool": [
                {
                    "title": "AAPL valuation update",
                    "url": "https://example.com/aapl-valuation",
                    "snippet": "AAPL 当前 PE 28.5x，营收增长 12%，毛利率 44%。",
                    "source": "example",
                    "published_date": "2026-02-18T00:00:00Z",
                    "confidence": 0.8,
                }
            ],
            "step_results": {},
            "errors": [],
            "render_vars": {
                "investment_summary": "当前PE 28.5x，营收增长12%，估值仍有支撑。",
                "valuation": "估值面：PE 28.5x，毛利率44%，需关注盈利持续性。",
            },
        },
        "trace": {},
    }

    report = build_report_payload(
        state=state,
        query="请做 AAPL 投资分析",
        thread_id="t-grounding-ok",
    )
    assert isinstance(report, dict)

    grounding_rate = report.get("grounding_rate")
    assert isinstance(grounding_rate, float)
    assert 0.0 <= grounding_rate <= 1.0

    report_hints = report.get("report_hints") or {}
    grounding = report_hints.get("grounding") or {}
    assert grounding.get("claim_count", 0) > 0
    assert grounding.get("grounded_count", 0) >= 0

    meta = report.get("meta") or {}
    assert isinstance(meta.get("grounding"), dict)


def test_build_report_payload_adds_grounding_gap_when_rate_low():
    state = {
        "output_mode": "investment_report",
        "subject": {"subject_type": "company", "tickers": ["AAPL"]},
        "policy": {"allowed_agents": []},
        "plan_ir": {"steps": []},
        "artifacts": {
            "draft_markdown": "## 投资研报：AAPL\n\n",
            "evidence_pool": [
                {
                    "title": "AAPL basic snapshot",
                    "url": "https://example.com/aapl-basic",
                    "snippet": "当前仅包含基础价格与成交量摘要。",
                    "source": "example",
                    "published_date": "2026-02-18T00:00:00Z",
                    "confidence": 0.7,
                }
            ],
            "step_results": {},
            "errors": [],
            "render_vars": {
                "investment_summary": "预计2028Q4发布新产品并带来30%增长。",
                "valuation": "未来两年利润有望提升25%，但证据待验证。",
            },
        },
        "trace": {},
    }

    report = build_report_payload(
        state=state,
        query="请做 AAPL 投资分析",
        thread_id="t-grounding-gap",
    )
    assert isinstance(report, dict)

    tags = report.get("tags") or []
    assert "grounding_gap" in tags

    risks = report.get("risks") or []
    assert any("证据溯源率偏低" in str(item) for item in risks)


def test_build_report_payload_marks_verifier_gap_when_unsupported_claims_exist():
    state = {
        "output_mode": "investment_report",
        "subject": {"subject_type": "company", "tickers": ["GOOG"]},
        "policy": {"allowed_agents": []},
        "plan_ir": {"steps": []},
        "artifacts": {
            "draft_markdown": "## 投资研报：GOOG\n\n",
            "evidence_pool": [
                {
                    "title": "GOOG fundamentals",
                    "url": "https://example.com/goog-fundamentals",
                    "snippet": "Revenue growth 11%, PE 28x, cloud margin improving.",
                    "source": "example",
                    "published_date": "2026-02-18T00:00:00Z",
                    "confidence": 0.8,
                }
            ],
            "step_results": {},
            "errors": [],
            "render_vars": {
                "investment_summary": "基于当前估值与增长，维持中性偏多。",
                "conclusion": "结论偏中性，等待更多证据。",
            },
            "verifier_result": {
                "enabled": True,
                "checked": True,
                "unsupported_claims": [
                    {"claim": "Gemini 2.0 will launch in 2026Q2", "reason": "missing in evidence"}
                ],
            },
        },
        "trace": {},
    }

    report = build_report_payload(
        state=state,
        query="请做 GOOG 深度投资报告",
        thread_id="t-verifier-gap",
    )
    assert isinstance(report, dict)

    tags = report.get("tags") or []
    assert "verifier_gap" in tags

    risks = report.get("risks") or []
    assert any("二次事实核查发现" in str(item) for item in risks)

    hints = report.get("report_hints") or {}
    verifier_hint = hints.get("verifier") or {}
    assert verifier_hint.get("checked") is True
    assert verifier_hint.get("unsupported_count") == 1

    meta = report.get("meta") or {}
    verifier_meta = meta.get("verifier") or {}
    assert verifier_meta.get("checked") is True


def test_build_report_payload_uses_unresolved_verifier_claims_for_quality_gate():
    state = {
        "output_mode": "investment_report",
        "subject": {"subject_type": "company", "tickers": ["GOOG"]},
        "policy": {"allowed_agents": []},
        "plan_ir": {"steps": []},
        "artifacts": {
            "draft_markdown": "## 投资研报：GOOG\n\n",
            "evidence_pool": [
                {
                    "title": "GOOG fundamentals",
                    "url": "https://example.com/goog-fundamentals",
                    "snippet": "Revenue growth 11%, PE 28x, cloud margin improving.",
                    "source": "example",
                    "published_date": "2026-02-18T00:00:00Z",
                    "confidence": 0.8,
                }
            ],
            "step_results": {},
            "errors": [],
            "render_vars": {
                "investment_summary": "基于当前估值与增长，维持中性偏多。",
                "conclusion": "结论偏中性，等待更多证据。",
            },
            "verifier_result": {
                "enabled": True,
                "checked": True,
                "unsupported_claims": [
                    {"claim": "Gemini 2.0 will launch in 2026Q2", "reason": "missing evidence"}
                ],
                "unresolved_unsupported_claims": [],
            },
        },
        "trace": {},
    }

    report = build_report_payload(
        state=state,
        query="请做 GOOG 深度投资报告",
        thread_id="t-verifier-unresolved-empty",
    )
    assert isinstance(report, dict)

    tags = report.get("tags") or []
    assert "verifier_gap" not in tags

    hints = report.get("report_hints") or {}
    verifier_hint = hints.get("verifier") or {}
    assert verifier_hint.get("unsupported_count") == 1
    assert verifier_hint.get("unresolved_unsupported_count") == 0

    quality = report.get("report_quality") or {}
    reasons = quality.get("reasons") or []
    reason_codes = {str(item.get("code")) for item in reasons if isinstance(item, dict)}
    assert "VERIFIER_UNSUPPORTED_CLAIMS_BLOCK" not in reason_codes
    assert "VERIFIER_UNSUPPORTED_CLAIMS_WARN" not in reason_codes


def test_build_report_payload_excludes_not_run_agents_from_sections_and_quality_coverage():
    state = {
        "output_mode": "investment_report",
        "subject": {"subject_type": "company", "tickers": ["AAPL"]},
        "policy": {"allowed_agents": ["price_agent", "news_agent", "fundamental_agent"]},
        "plan_ir": {
            "steps": [
                {"id": "s_price", "kind": "agent", "name": "price_agent"},
            ]
        },
        "artifacts": {
            "draft_markdown": "## 投资研报：AAPL\n\n",
            "evidence_pool": [
                {
                    "title": "AAPL valuation note",
                    "url": "https://example.com/aapl/valuation",
                    "snippet": "估值与增长指标更新。",
                    "source": "example",
                    "published_date": "2026-02-18T00:00:00Z",
                    "confidence": 0.8,
                },
                {
                    "title": "AAPL revenue outlook",
                    "url": "https://example.com/aapl/revenue",
                    "snippet": "收入预期与利润率趋势。",
                    "source": "example",
                    "published_date": "2026-02-18T00:00:00Z",
                    "confidence": 0.8,
                },
            ],
            "step_results": {
                "s_price": {
                    "output": {
                        "summary": "价格与估值结论稳定。",
                        "confidence": 0.86,
                        "evidence": [
                            {"url": "https://example.com/aapl/valuation/"},
                            {"url": "https://example.com/aapl/revenue?utm_source=test"},
                        ],
                    }
                }
            },
            "errors": [],
            "render_vars": {"investment_summary": "测试摘要"},
        },
        "trace": {},
    }

    report = build_report_payload(
        state=state,
        query="请做 AAPL 投资分析",
        thread_id="t-not-run-coverage",
    )
    assert isinstance(report, dict)

    sections = report.get("sections") or []
    agent_names = [str(section.get("agent_name") or "") for section in sections]
    assert "news_agent" not in agent_names
    assert "fundamental_agent" not in agent_names

    quality = report.get("report_quality") or {}
    assert quality.get("state") == "pass"
    metrics = quality.get("metrics") or {}
    assert metrics.get("total_blocks") == 1
    assert metrics.get("covered_blocks") == 1


def test_build_report_payload_uses_internal_citations_when_agent_evidence_has_no_url():
    state = {
        "output_mode": "investment_report",
        "subject": {"subject_type": "company", "tickers": ["AAPL"]},
        "policy": {"allowed_agents": ["risk_agent"]},
        "plan_ir": {"steps": [{"id": "s_risk", "kind": "agent", "name": "risk_agent"}]},
        "artifacts": {
            "draft_markdown": "## 投资研报：AAPL\n\n",
            "evidence_pool": [],
            "step_results": {
                "s_risk": {
                    "output": {
                        "summary": "风险评分上升，需关注因子暴露和压力场景。",
                        "confidence": 0.72,
                        "as_of": "2026-02-20T12:00:00Z",
                        "evidence": [
                            {
                                "title": "Risk score snapshot",
                                "text": "Risk score: 67 (high). Primary driver: macro stress.",
                                "source": "risk_rule_engine",
                                "timestamp": "2026-02-20T12:00:00Z",
                            },
                            {
                                "title": "Factor beta exposure",
                                "text": "Market beta 1.31, growth factor beta 0.94.",
                                "source": "factor_model",
                                "timestamp": "2026-02-20T12:00:00Z",
                            },
                        ],
                    }
                }
            },
            "errors": [],
            "render_vars": {"investment_summary": "测试摘要"},
        },
        "trace": {},
    }

    report = build_report_payload(
        state=state,
        query="请做 AAPL 风险分析简报",
        thread_id="t-risk-internal-citations",
    )
    assert isinstance(report, dict)

    sections = report.get("sections") or []
    risk_section = next((section for section in sections if section.get("agent_name") == "risk_agent"), None)
    assert isinstance(risk_section, dict)
    contents = risk_section.get("contents") or []
    refs = contents[0].get("citation_refs") if contents and isinstance(contents[0], dict) else []
    assert isinstance(refs, list)
    assert len(refs) >= 2

    citations = report.get("citations") or []
    citation_url_by_id = {
        str(item.get("source_id")): str(item.get("url") or "")
        for item in citations
        if isinstance(item, dict) and item.get("source_id")
    }
    assert all(ref in citation_url_by_id for ref in refs)
    assert any(citation_url_by_id[ref].startswith("internal://") for ref in refs)

    quality = report.get("report_quality") or {}
    codes = {
        str(item.get("code"))
        for item in (quality.get("reasons") or [])
        if isinstance(item, dict)
    }
    assert "EVIDENCE_COVERAGE_BELOW_MIN" not in codes
    assert "KEY_SECTION_SOURCES_BELOW_MIN" not in codes


def test_quality_hints_counts_www_wsj_as_authoritative_media():
    """R20 回归：lstrip("www.") 按字符集合剥除，"www.wsj.com" 被剥成 "sj.com"，
    WSJ 是权威域名单里唯一以 w 开头的——被系统性漏计，报告被误罚质量分。"""
    quality = _build_report_quality_hints(
        query="AAPL 深度财报研究",
        citations=[
            {
                "title": "Apple annual results coverage",
                "url": "https://www.wsj.com/tech/apple-earnings-2026",
                "snippet": "Apple reported quarterly revenue and margin details in its annual report.",
            }
        ],
        tickers=["AAPL"],
    )

    assert (quality.get("stats") or {}).get("authoritative_media_count") == 1
    # 旧代码 WSJ 漏计会插入 important 级"缺权威媒体交叉引用"缺口
    assert (quality.get("missing_counts") or {}).get("important") == 0


def test_freshness_hours_treats_naive_dates_as_utc():
    """R21 回归：naive published_date 按 UTC 取 now。旧代码用本地墙钟，
    东八区机器上 1 小时前的文章会被算成约 9 小时旧。"""
    from datetime import datetime, timedelta, timezone

    from backend.graph.report_builder import _freshness_hours

    one_hour_ago_utc_naive = (
        datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
    ).isoformat()
    hours = _freshness_hours(one_hour_ago_utc_naive)
    assert 0.9 <= hours <= 1.5  # 旧代码在东八区得约 9.0


def test_grounding_number_tokens_require_digit_boundaries():
    """_is_claim_grounded 的数字核对用裸子串匹配：claim "12亿美元" 会撞上
    语料里的 "312亿美元" 被误判 grounded，grounding_rate 虚高，
    质量门控放行编造数字。"""
    from backend.graph.report_grounding import _is_claim_grounded, _normalize_for_grounding

    corpus = _normalize_for_grounding("苹果营收312亿美元，同比增长8%")

    # 数字在语料中真实出现（非字面整句包含，走数字边界核对路径）
    assert _is_claim_grounded("312亿美元营收", corpus)
    # "12" 只是 "312" 的子串 → 不得判 grounded
    assert not _is_claim_grounded("净利润12亿美元", corpus)
    # 右边界同样生效："31" 撞上 "312" 的前缀
    assert not _is_claim_grounded("营收31亿美元", corpus)


def test_quality_hints_sec_lookalike_and_url_substring_do_not_count():
    """R83: domain.endswith("sec.gov") 无点边界——notsec.gov 这类仿冒主机被计成
    SEC filing；"sec.gov/" in url 对整条 URL 做裸子串，任意主机 query 里携带
    sec.gov/ 也吃 filing credit。两条都会虚增 sec_filing_count/has_10k/has_10q，
    压制 critical 级"缺 10-K/10-Q"缺口，深报质量门控被放行。"""
    quality = _build_report_quality_hints(
        query="AAPL 深度财报研究",
        citations=[
            {
                "title": "Apple 10-K annual report",
                "url": "https://notsec.gov/Archives/edgar/data/320193/aapl-20240928.htm",
                "snippet": "Annual filing discusses revenue and margin.",
            },
            {
                "title": "Apple 10-Q quarterly report",
                "url": "https://evil.example/article?ref=sec.gov/x",
                "snippet": "Quarterly filing update.",
            },
        ],
        tickers=["AAPL"],
    )

    stats = quality.get("stats") or {}
    assert stats.get("sec_filing_count") == 0
    assert stats.get("has_10k") is False
    assert stats.get("has_10q") is False
    missing = quality.get("missing_requirements") or []
    assert any("10-K" in str(item) for item in missing)
    assert any("10-Q" in str(item) for item in missing)


def test_quality_hints_media_lookalike_suffixes_do_not_count():
    """R83: endswith("ft.com") 无点边界——microsoft.com/swift.com/draft.com 都以
    "ft.com" 结尾，微软 IR 页、SWIFT 公告被误计成 FT 权威媒体引用，
    "缺权威媒体交叉引用" important 缺口被压制。"""
    quality = _build_report_quality_hints(
        query="AAPL 深度财报研究",
        citations=[
            {
                "title": "Microsoft investor relations earnings release",
                "url": "https://www.microsoft.com/en-us/investor/earnings/fy-2026-q1",
                "snippet": "Microsoft investor relations earnings release details.",
            },
            {
                "title": "SWIFT network integration notice",
                "url": "https://www.swift.com/news-events/apple-pay",
                "snippet": "SWIFT announces payment network integration details.",
            },
        ],
        tickers=["AAPL"],
    )

    stats = quality.get("stats") or {}
    assert stats.get("authoritative_media_count") == 0
    assert any("权威媒体" in str(item) for item in quality.get("missing_requirements") or [])


def test_quality_hints_cn_filing_lookalike_domain_does_not_count():
    """R83: CN 深报要求本地披露引用——notcninfo.com.cn 以 cninfo.com.cn 结尾，
    endswith 无点边界时被计成巨潮披露，压制 critical 级"缺本地市场披露"缺口。"""
    quality = _build_report_quality_hints(
        query="贵州茅台 深度财报研究",
        citations=[
            {
                "title": "贵州茅台年度报告全文",
                "url": "https://notcninfo.com.cn/disclosure/annual.pdf",
                "snippet": "年度报告披露正文。",
            },
        ],
        tickers=["600519.SS"],
    )

    stats = quality.get("stats") or {}
    assert stats.get("local_filing_count") == 0
    assert any("本地市场披露" in str(item) for item in quality.get("missing_requirements") or [])


def test_quality_hints_legit_subdomain_and_schemeless_sec_still_count():
    """R83 正例回归：真实子域（markets.ft.com）与无 scheme 的 sec.gov 直链
    仍应命中——修复只掐仿冒，不能把合法引用一起丢掉。"""
    quality = _build_report_quality_hints(
        query="AAPL 深度财报研究",
        citations=[
            {
                "title": "Apple 10-K annual report",
                "url": "sec.gov/Archives/edgar/data/320193/aapl-20240928.htm",
                "snippet": "Annual filing discusses revenue and margin.",
            },
            {
                "title": "FT markets tearsheet",
                "url": "https://markets.ft.com/data/equities/tearsheet/s=AAPL:NSQ",
                "snippet": "FT markets data tearsheet for Apple.",
            },
        ],
        tickers=["AAPL"],
    )

    stats = quality.get("stats") or {}
    assert stats.get("sec_filing_count") == 1
    assert stats.get("has_10k") is True
    assert stats.get("authoritative_media_count") == 1


def test_classify_report_type_rsi_phantom_does_not_hijack_deep_report():
    """R84: "rsi" 是 technical_tokens 里唯一 ≤3 字符的 ASCII token，裸子串撞上
    university/diversification/diversified/adversity——'diversified portfolio
    深度研报' 被误判 technical（technical 分支先于 deep 检查），深报质量门槛
    （10-K/10-Q/本地披露/权威媒体/摘录）整体跳过。"""
    from backend.graph.report_builder import _classify_report_type

    assert _classify_report_type("diversified portfolio 深度研报") == "deep_financial"
    assert _classify_report_type("university endowment fund 深度研究") == "deep_financial"
    # 正例：真实 RSI 技术面查询仍归 technical
    assert _classify_report_type("AAPL RSI 和 MACD 技术分析") == "technical"


def test_quality_hints_deep_gate_not_bypassed_by_diversified_wording():
    """R84 端到端：query 提到 diversification 时深报门槛仍应生效——
    无 10-K 引用时 missing_requirements 必须报 critical 缺口。"""
    quality = _build_report_quality_hints(
        query="AAPL diversified portfolio 深度研报",
        citations=[
            {
                "title": "AAPL snapshot",
                "url": "https://example.com/aapl",
                "snippet": "Basic price and volume snapshot for Apple.",
            }
        ],
        tickers=["AAPL"],
    )

    assert quality.get("deep_report_required") is True
    assert any("10-K" in str(item) for item in quality.get("missing_requirements") or [])
