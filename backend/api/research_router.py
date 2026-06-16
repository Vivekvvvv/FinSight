"""
Research API Router
研究助手相关端点：报告生成、财报分析、新闻情绪
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["Research"])


# ── 数据模型 ──────────────────────────────────────────────────────────────────

class ReportGenerateRequest(BaseModel):
    ticker: str = Field(..., description="股票代码")
    report_type: str = Field(default="comprehensive", description="fundamental/technical/comprehensive")
    include_news: bool = Field(default=True)
    include_technical: bool = Field(default=True)


class ReportResponse(BaseModel):
    report_id: str
    ticker: str
    report_type: str
    title: str
    content: str
    generated_at: str
    data_sources: List[str]


class FinancialsAnalyzeRequest(BaseModel):
    ticker: str = Field(..., description="股票代码")


class NewsSentimentRequest(BaseModel):
    ticker: str = Field(..., description="股票代码")
    news: Optional[List[Dict[str, Any]]] = Field(None, description="直接传入新闻列表（可选，不传则自动拉取）")


class SmartQARequest(BaseModel):
    question: str = Field(..., description="问题内容")
    ticker: Optional[str] = Field(None, description="关联股票代码")
    use_cn_data: bool = Field(default=True, description="是否注入A股特色数据（龙虎榜/北向/融资融券）")


# ── 研究报告生成 ───────────────────────────────────────────────────────────────

@router.post("/report/generate", response_model=ReportResponse)
async def generate_report(request: ReportGenerateRequest):
    """生成研究报告（fundamental / technical / comprehensive）"""
    try:
        from backend.services.report_generator import get_report_generator
        from backend.tools import (
            get_company_info,
            get_financial_statements,
            get_stock_historical_data,
            get_company_news,
        )

        generator = get_report_generator()
        data_context: Dict[str, Any] = {}

        try:
            info = get_company_info(request.ticker)
            if info and not info.get("error"):
                data_context["company_info"] = info
        except Exception:
            pass

        if request.report_type in ["fundamental", "comprehensive"]:
            try:
                fin = get_financial_statements(request.ticker)
                if fin and not fin.get("error"):
                    data_context["financials"] = fin
            except Exception:
                pass

        if request.include_technical and request.report_type in ["technical", "comprehensive"]:
            try:
                price = get_stock_historical_data(ticker=request.ticker, period="3mo", interval="1d")
                if price and not price.get("error"):
                    data_context["price_data"] = price
            except Exception:
                pass

        if request.include_news and request.report_type == "comprehensive":
            try:
                news = get_company_news(request.ticker)
                if news and not news.get("error"):
                    data_context["news"] = news
            except Exception:
                pass

        report = await generator.generate_report(
            ticker=request.ticker,
            report_type=request.report_type,
            data_context=data_context,
        )
        return ReportResponse(**report)

    except Exception as e:
        logger.exception("生成报告失败: %s", e)
        raise HTTPException(status_code=500, detail=f"生成报告失败: {e}")


# ── 财报分析 ───────────────────────────────────────────────────────────────────

@router.post("/financials/analyze")
async def analyze_financials(request: FinancialsAnalyzeRequest):
    """
    财报分析助手

    自动拉取财报数据，用LLM提取：
    - 营收/利润趋势
    - 盈利能力（毛利率、ROE）
    - 现金流质量
    - 投资亮点与风险点
    - 综合评分（1-10）
    """
    try:
        from backend.services.financials_analyzer import analyze_financials as _analyze
        from backend.tools import get_financial_statements, get_company_info

        financials: Dict[str, Any] = {}
        company_info: Dict[str, Any] = {}

        try:
            financials = get_financial_statements(request.ticker) or {}
        except Exception as e:
            logger.warning("获取财报失败 %s: %s", request.ticker, e)

        try:
            company_info = get_company_info(request.ticker) or {}
        except Exception:
            pass

        if not financials or financials.get("error"):
            raise HTTPException(status_code=422, detail="无法获取该股票财报数据，请确认代码正确")

        result = await _analyze(
            ticker=request.ticker,
            financials=financials,
            company_info=company_info,
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("财报分析失败: %s", e)
        raise HTTPException(status_code=500, detail=f"财报分析失败: {e}")


# ── 新闻情绪分析 ───────────────────────────────────────────────────────────────

@router.post("/news/sentiment")
async def news_sentiment(request: NewsSentimentRequest):
    """
    新闻情绪分析

    对股票最新新闻逐条标注情绪（利好/中性/利空），
    并汇总综合情绪分数。
    """
    try:
        from backend.services.news_sentiment import analyze_news_sentiment, aggregate_sentiment
        from backend.tools import get_company_news

        news_list = request.news
        if not news_list:
            try:
                raw = get_company_news(request.ticker)
                # 不同工具返回格式不一，兼容处理
                if isinstance(raw, dict):
                    news_list = raw.get("news") or raw.get("items") or raw.get("data") or []
                elif isinstance(raw, list):
                    news_list = raw
            except Exception as e:
                logger.warning("获取新闻失败 %s: %s", request.ticker, e)

        if not news_list:
            return {"ticker": request.ticker, "news": [], "aggregate": {
                "overall_sentiment": "neutral", "score": 0,
                "positive": 0, "negative": 0, "neutral": 0,
            }}

        enriched = await analyze_news_sentiment(news_list, ticker=request.ticker)
        agg = aggregate_sentiment(enriched)

        return {
            "ticker": request.ticker,
            "news": enriched,
            "aggregate": agg,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("新闻情绪分析失败: %s", e)
        raise HTTPException(status_code=500, detail=f"新闻情绪分析失败: {e}")


# ── 智能股票问答 ───────────────────────────────────────────────────────────────

@router.post("/qa")
async def smart_qa(request: SmartQARequest):
    """
    智能股票问答

    当提问与特定股票相关时，自动注入多维数据上下文：
    - 最新行情（涨跌幅、成交量）
    - 今日新闻
    - A股特色数据（龙虎榜、北向资金、融资融券）

    然后调用LLM给出基于数据支撑的专业回答。
    """
    try:
        context_parts: List[str] = []
        ticker = (request.ticker or "").strip().upper()

        if ticker:
            # 1. 实时行情
            try:
                from backend.tools import get_stock_price
                quote = get_stock_price(ticker)
                if quote and not quote.get("error"):
                    price = quote.get("price") or quote.get("current_price", "N/A")
                    change = quote.get("change_percent") or quote.get("change_pct", "N/A")
                    context_parts.append(f"【最新行情】{ticker} 现价 {price}，涨跌幅 {change}%")
            except Exception:
                pass

            # 2. 最新新闻（最多3条）
            try:
                from backend.tools import get_company_news
                raw_news = get_company_news(ticker)
                news_items: List[Any] = []
                if isinstance(raw_news, dict):
                    news_items = raw_news.get("news") or raw_news.get("items") or []
                elif isinstance(raw_news, list):
                    news_items = raw_news
                if news_items:
                    titles = [n.get("title", "") for n in news_items[:3] if n.get("title")]
                    context_parts.append("【今日相关新闻】\n" + "\n".join(f"- {t}" for t in titles))
            except Exception:
                pass

            # 3. A股特色数据
            from backend.tools.baostock_provider import is_cn_symbol
            if request.use_cn_data and is_cn_symbol(ticker):
                # 龙虎榜
                try:
                    from backend.tools.tencent_provider import fetch_cn_top_list
                    top = fetch_cn_top_list(ticker, include_seats=False)
                    if top and not top.get("error"):
                        net_buy = top.get("net_buy", 0)
                        direction = "净买入" if net_buy >= 0 else "净卖出"
                        context_parts.append(
                            f"【龙虎榜】今日上榜，机构{direction} {abs(net_buy)/1e8:.2f}亿元"
                        )
                except Exception:
                    pass

                # 北向资金
                try:
                    from backend.tools.tencent_provider import fetch_north_flow
                    nf = fetch_north_flow()
                    if nf and not nf.get("error"):
                        north = nf.get("north_flow", 0)
                        direction = "净流入" if north >= 0 else "净流出"
                        context_parts.append(
                            f"【北向资金】今日{direction} {abs(north)/1e8:.2f}亿元"
                        )
                except Exception:
                    pass

                # 融资余额
                try:
                    from backend.tools.tencent_provider import fetch_margin_trading
                    margin = fetch_margin_trading(ticker)
                    if margin and not margin.get("error"):
                        bal = margin.get("margin_balance", 0)
                        context_parts.append(
                            f"【融资融券】融资余额 {bal/1e8:.2f}亿元"
                        )
                except Exception:
                    pass

        # 构建最终prompt
        context_block = ""
        if context_parts:
            context_block = "\n\n## 实时市场数据\n" + "\n".join(context_parts) + "\n"

        prompt = f"""你是一位专业的A股研究员，请基于以下数据回答用户问题。
{context_block}
## 用户问题
{request.question}

## 回答要求
- 数据支撑：优先引用上面的市场数据
- 简洁专业：回答200-400字，使用Markdown格式
- 风险提示：末尾附加"以上仅供研究参考，不构成投资建议"
"""

        from backend.llm_config import get_llm
        llm = get_llm(temperature=0.3, max_tokens=1024)
        response = await llm.ainvoke(prompt)
        answer = response.content if hasattr(response, "content") else str(response)

        return {
            "question": request.question,
            "ticker": ticker or None,
            "answer": answer,
            "context_used": context_parts,
        }

    except Exception as e:
        logger.exception("智能问答失败: %s", e)
        raise HTTPException(status_code=500, detail=f"智能问答失败: {e}")
