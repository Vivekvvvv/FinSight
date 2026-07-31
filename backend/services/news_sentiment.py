"""
新闻情绪分析服务
对股票新闻批量打情绪标签，提取关键事件
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")

# 情绪分析prompt
_SENTIMENT_PROMPT = """你是一位专业的金融新闻分析师，请分析以下股票相关新闻列表并输出情绪标签。

## 新闻列表
{news_json}

## 任务
对每条新闻输出以下字段（严格JSON数组，与输入顺序一致）：
- sentiment: "positive" | "neutral" | "negative"
- sentiment_cn: "利好" | "中性" | "利空"
- confidence: 0.0-1.0（置信度）
- key_event: 核心事件一句话摘要（30字以内）
- impact_level: "high" | "medium" | "low"（对股价影响程度）

输出示例：
[
  {{
    "sentiment": "positive",
    "sentiment_cn": "利好",
    "confidence": 0.85,
    "key_event": "公司发布超预期季报，净利润同比增长45%",
    "impact_level": "high"
  }}
]

请严格输出JSON数组，不要包含markdown代码块标记，数组长度必须与输入新闻数量一致。"""


async def analyze_news_sentiment(
    news_list: List[Dict[str, Any]],
    ticker: str = "",
) -> List[Dict[str, Any]]:
    """
    批量分析新闻情绪

    Args:
        news_list: 新闻列表，每条含title和summary字段
        ticker: 相关股票代码（可选，用于上下文）

    Returns:
        原新闻列表，每条追加sentiment等字段
    """
    if not news_list:
        return []

    # 只取标题+摘要，控制token
    slim_news = [
        {"index": i, "title": n.get("title", ""), "summary": (n.get("summary") or n.get("content") or "")[:200]}
        for i, n in enumerate(news_list[:15])  # 最多分析15条
    ]

    news_json = json.dumps(slim_news, ensure_ascii=False, indent=2)
    prompt = _SENTIMENT_PROMPT.format(news_json=news_json)

    try:
        from backend.llm_config import create_llm

        llm = create_llm(temperature=0.0, max_tokens=2048)
        response = await llm.ainvoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)

        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])

        sentiments: List[Dict[str, Any]] = json.loads(
            text,
            parse_constant=_reject_json_constant,
        )

        # 合并回原新闻
        result = []
        for i, news in enumerate(news_list):
            enriched = dict(news)
            if i < len(sentiments):
                enriched.update(sentiments[i])
            else:
                enriched.update(_neutral_sentiment())
            result.append(enriched)
        return result

    except json.JSONDecodeError as exc:
        logger.warning("[NewsSentiment] LLM返回非JSON: %s", type(exc).__name__)
        return [dict(n, **_neutral_sentiment()) for n in news_list]
    except Exception as exc:
        logger.error("[NewsSentiment] 分析失败: %s", type(exc).__name__)
        return [dict(n, **_neutral_sentiment()) for n in news_list]


def _neutral_sentiment() -> Dict[str, Any]:
    return {
        "sentiment": "neutral",
        "sentiment_cn": "中性",
        "confidence": 0.5,
        "key_event": "暂无分析",
        "impact_level": "low",
    }


def aggregate_sentiment(enriched_news: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    汇总多条新闻的综合情绪

    Returns:
        overall_sentiment, positive_count, negative_count, neutral_count, score
    """
    if not enriched_news:
        return {"overall_sentiment": "neutral", "score": 0, "positive": 0, "negative": 0, "neutral": 0}

    counts = {"positive": 0, "negative": 0, "neutral": 0}
    weighted_score = 0.0
    weight_map = {"high": 3, "medium": 2, "low": 1}
    score_map = {"positive": 1, "neutral": 0, "negative": -1}

    for n in enriched_news:
        s = n.get("sentiment", "neutral")
        w = weight_map.get(n.get("impact_level", "low"), 1)
        counts[s] = counts.get(s, 0) + 1
        weighted_score += score_map.get(s, 0) * w

    total = sum(counts.values()) or 1
    norm_score = round(weighted_score / (total * 3) * 100, 1)  # -100到100

    if norm_score > 20:
        overall = "positive"
    elif norm_score < -20:
        overall = "negative"
    else:
        overall = "neutral"

    return {
        "overall_sentiment": overall,
        "score": norm_score,
        "positive": counts["positive"],
        "negative": counts["negative"],
        "neutral": counts["neutral"],
    }
