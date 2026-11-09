"""
财报分析助手
用LLM从财报数据中提取关键指标、风险点、投资亮点
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from backend.utils.strict_json import json_loads_strict
from backend.utils.quote import safe_float

logger = logging.getLogger(__name__)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")

# 财报分析prompt模板
_FINANCIALS_PROMPT = """你是一位专业的A股财报分析师。请根据以下财报数据，生成结构化的财报解读报告。

## 公司信息
股票代码：{ticker}
公司名称：{company_name}

## 财报数据
{financials_json}

## 任务
请从以下维度进行分析，输出JSON格式结果：

1. **revenue_analysis**（营收分析）
   - trend: 趋势描述（增长/持平/下滑）
   - yoy_growth: 同比增速（如有数据）
   - highlight: 主要亮点

2. **profitability**（盈利能力）
   - gross_margin: 毛利率水平及变化
   - net_margin: 净利率水平及变化
   - roe: 净资产收益率
   - assessment: 综合评价

3. **cash_flow**（现金流状况）
   - operating_cf: 经营现金流情况
   - free_cf: 自由现金流情况
   - quality: 盈利质量（高/中/低）

4. **risk_factors**（风险因素）
   - list: [风险点1, 风险点2, ...]（最多5条）

5. **investment_highlights**（投资亮点）
   - list: [亮点1, 亮点2, ...]（最多3条）

6. **overall_rating**（综合评级）
   - score: 1-10分
   - label: 优秀/良好/一般/较差
   - summary: 一句话总结（50字以内）

请严格输出JSON，不要包含markdown代码块标记。"""


async def analyze_financials(
    ticker: str,
    financials: Dict[str, Any],
    company_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    用LLM分析财报数据，返回结构化分析结果

    Args:
        ticker: 股票代码
        financials: 财报数据字典
        company_info: 公司基本信息（可选）

    Returns:
        结构化财报分析字典
    """
    if (not isinstance(financials, dict) or not financials
        or financials.get("error") or financials.get("success") is False
        or str(financials.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
        logger.warning("[FinancialsAnalyzer] 财报数据不可用")
        return _fallback_result(ticker, "Internal server error")

    if any(value is not None and str(value).strip().upper() != ticker.strip().upper()
           for value in (financials.get("ticker"), financials.get("symbol"))):
        return _fallback_result(ticker, "Internal server error")

    company_info = company_info if isinstance(company_info, dict) else {}
    if any(value is not None and str(value).strip().upper() != ticker.strip().upper()
           for value in (company_info.get("ticker"), company_info.get("symbol"))):
        return _fallback_result(ticker, "Internal server error")
    raw_name = company_info.get("name")
    company_name = raw_name.strip() if isinstance(raw_name, str) else ""
    company_name = company_name or ticker

    # 截断过大的财报数据，避免超token
    try:
        financials_str = json.dumps(financials, ensure_ascii=False, indent=2, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        logger.warning("[FinancialsAnalyzer] 财报数据不可用")
        return _fallback_result(ticker, "Internal server error")
    if len(financials_str) > 8000:
        financials_str = financials_str[:8000] + "\n... (已截断)"

    prompt = _FINANCIALS_PROMPT.format(
        ticker=ticker,
        company_name=company_name,
        financials_json=financials_str,
    )

    try:
        from backend.llm_config import create_llm

        llm = create_llm(temperature=0.1, max_tokens=2048)
        response = await llm.ainvoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)

        # 去掉可能的markdown代码块
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])

        result = json_loads_strict(text)
        if (not isinstance(result, dict) or result.get("error") or result.get("success") is False
            or str(result.get("status") or "").strip().lower() in {"error", "failed", "unavailable"}):
            raise ValueError("financial analysis failed")
        if any(value is not None and str(value).strip().upper() != ticker.strip().upper()
               for value in (result.get("ticker"), result.get("symbol"))):
            raise ValueError("financial analysis instrument mismatch")
        rating = result.get("overall_rating") if isinstance(result, dict) else None
        score = safe_float(rating.get("score")) if isinstance(rating, dict) else None
        if score is None or not 1 <= score <= 10:
            raise ValueError("invalid financial analysis rating")
        rating["score"] = score
        label = rating.get("label")
        label = label.strip() if isinstance(label, str) else ""
        rating["label"] = label if label in {"优秀", "良好", "一般", "较差"} else "未评级"
        summary = rating.get("summary")
        rating["summary"] = summary.strip()[:50] if isinstance(summary, str) else ""
        for section in ("revenue_analysis", "profitability", "cash_flow"):
            if not isinstance(result.get(section), dict):
                result[section] = {}
        for section, maximum in (("risk_factors", 5), ("investment_highlights", 3)):
            value = result.get(section)
            items = value.get("list") if isinstance(value, dict) else None
            result[section] = {"list": [item.strip() for item in items if isinstance(item, str) and item.strip()][:maximum]
                               if isinstance(items, list) else []}
        result["ticker"] = ticker
        result["status"] = "success"
        return result

    except json.JSONDecodeError as exc:
        logger.warning("[FinancialsAnalyzer] LLM返回非JSON，fallback")
        return _fallback_result(ticker, "Internal server error")
    except Exception as exc:
        logger.error("[FinancialsAnalyzer] 分析失败")
        return _fallback_result(ticker, "Internal server error")


def _fallback_result(ticker: str, error: str) -> Dict[str, Any]:
    return {
        "ticker": ticker,
        "status": "error",
        "error": error,
        "overall_rating": {
            "score": 0,
            "label": "数据不足",
            "summary": "财报分析暂时不可用，请稍后重试",
        },
        "revenue_analysis": {"trend": "未知", "highlight": "数据获取失败"},
        "profitability": {"assessment": "数据获取失败"},
        "cash_flow": {"quality": "未知"},
        "risk_factors": {"list": []},
        "investment_highlights": {"list": []},
    }
