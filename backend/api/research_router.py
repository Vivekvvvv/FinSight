"""
Research Report API Router
研究报告生成API端点
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["Research"])


class ReportGenerateRequest(BaseModel):
    """报告生成请求"""
    ticker: str = Field(..., description="股票代码")
    report_type: str = Field(default="comprehensive", description="报告类型：fundamental/technical/comprehensive")
    include_news: bool = Field(default=True, description="是否包含新闻分析")
    include_technical: bool = Field(default=True, description="是否包含技术分析")


class ReportResponse(BaseModel):
    """报告响应"""
    report_id: str
    ticker: str
    report_type: str
    title: str
    content: str
    generated_at: str
    data_sources: List[str]


@router.post("/report/generate", response_model=ReportResponse)
async def generate_report(request: ReportGenerateRequest):
    """
    生成研究报告

    - **ticker**: 股票代码（如AAPL、600519.SS）
    - **report_type**: 报告类型
      - fundamental: 基本面分析报告
      - technical: 技术面分析报告
      - comprehensive: 综合分析报告（默认）
    - **include_news**: 是否包含新闻分析
    - **include_technical**: 是否包含技术分析
    """
    try:
        from backend.services.report_generator import get_report_generator
        from backend.tools import (
            get_company_info,
            get_financial_statements,
            get_stock_historical_data,
            get_company_news,
        )

        generator = get_report_generator()

        # 收集数据上下文
        data_context: Dict[str, Any] = {}

        # 1. 获取公司基本信息
        try:
            company_info = get_company_info(request.ticker)
            if company_info and not company_info.get("error"):
                data_context["company_info"] = company_info
        except Exception as e:
            logger.warning(f"获取公司信息失败: {e}")

        # 2. 获取财务数据（基本面报告需要）
        if request.report_type in ["fundamental", "comprehensive"]:
            try:
                financials = get_financial_statements(request.ticker)
                if financials and not financials.get("error"):
                    data_context["financials"] = financials
            except Exception as e:
                logger.warning(f"获取财务数据失败: {e}")

        # 3. 获取历史价格数据（技术面报告需要）
        if request.include_technical and request.report_type in ["technical", "comprehensive"]:
            try:
                price_data = get_stock_historical_data(
                    ticker=request.ticker,
                    period="3mo",
                    interval="1d"
                )
                if price_data and not price_data.get("error"):
                    data_context["price_data"] = price_data
            except Exception as e:
                logger.warning(f"获取价格数据失败: {e}")

        # 4. 获取最近新闻（如果需要）
        if request.include_news and request.report_type == "comprehensive":
            try:
                news = get_company_news(request.ticker)
                if news and not news.get("error"):
                    data_context["news"] = news
            except Exception as e:
                logger.warning(f"获取新闻数据失败: {e}")

        # 生成报告
        report = await generator.generate_report(
            ticker=request.ticker,
            report_type=request.report_type,
            data_context=data_context
        )

        return ReportResponse(**report)

    except Exception as e:
        logger.exception(f"生成报告失败: {e}")
        raise HTTPException(status_code=500, detail=f"生成报告失败: {str(e)}")


@router.get("/report/{report_id}")
async def get_report(report_id: str):
    """
    获取已生成的报告

    - **report_id**: 报告ID
    """
    # TODO: 实现报告存储和检索
    raise HTTPException(status_code=501, detail="报告存储功能待实现")


@router.get("/reports/history")
async def list_reports(
    ticker: Optional[str] = None,
    limit: int = 20,
    offset: int = 0
):
    """
    获取历史报告列表

    - **ticker**: 可选，筛选特定股票的报告
    - **limit**: 返回数量限制
    - **offset**: 分页偏移
    """
    # TODO: 实现报告列表查询
    raise HTTPException(status_code=501, detail="报告列表功能待实现")
