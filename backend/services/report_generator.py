"""
Research Report Generator Service
使用GPT-4o生成股票研究报告
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ResearchReportGenerator:
    """研究报告生成器"""

    def __init__(self):
        self.report_templates = {
            "fundamental": self._fundamental_template,
            "technical": self._technical_template,
            "comprehensive": self._comprehensive_template,
        }

    async def generate_report(
        self,
        ticker: str,
        report_type: str = "comprehensive",
        data_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        生成研究报告

        Args:
            ticker: 股票代码
            report_type: 报告类型 (fundamental/technical/comprehensive)
            data_context: 数据上下文（基本面、技术面、新闻等）

        Returns:
            报告内容字典
        """
        template_func = self.report_templates.get(report_type, self._comprehensive_template)

        # 构建报告上下文
        context = data_context or {}
        context["ticker"] = ticker
        context["report_type"] = report_type
        context["generated_at"] = datetime.now().isoformat()

        # 使用模板生成报告提示词
        prompt = template_func(context)

        # 调用LLM生成报告
        report_content = await self._call_llm(prompt, ticker)

        return {
            "report_id": self._generate_report_id(ticker, report_type),
            "ticker": ticker,
            "report_type": report_type,
            "title": f"{ticker} 研究报告 - {report_type.upper()}",
            "content": report_content,
            "generated_at": context["generated_at"],
            "data_sources": self._extract_data_sources(context),
        }

    def _fundamental_template(self, context: Dict[str, Any]) -> str:
        """基本面分析报告模板"""
        ticker = context.get("ticker", "N/A")
        company_info = context.get("company_info", {})
        financials = context.get("financials", {})

        prompt = f"""请为股票 {ticker} 生成一份详细的基本面分析报告。

## 要求
1. 分析公司基本信息和业务模式
2. 评估财务健康状况（收入、利润、现金流）
3. 分析估值水平（P/E、P/B、PEG等）
4. 识别主要风险因素
5. 给出投资建议和目标价位

## 可用数据
公司信息：{company_info}
财务数据：{financials}

## 输出格式
使用Markdown格式，包含以下章节：
- # 执行摘要
- # 公司概况
- # 财务分析
- # 估值分析
- # 风险因素
- # 投资建议

请确保分析客观、数据支持充分、结论明确。"""

        return prompt

    def _technical_template(self, context: Dict[str, Any]) -> str:
        """技术面分析报告模板"""
        ticker = context.get("ticker", "N/A")
        price_data = context.get("price_data", {})
        indicators = context.get("indicators", {})

        prompt = f"""请为股票 {ticker} 生成一份详细的技术面分析报告。

## 要求
1. 分析价格趋势和形态
2. 评估技术指标（MA、MACD、RSI、布林带等）
3. 识别支撑位和阻力位
4. 分析成交量特征
5. 给出短期和中期交易建议

## 可用数据
价格数据：{price_data}
技术指标：{indicators}

## 输出格式
使用Markdown格式，包含以下章节：
- # 执行摘要
- # 趋势分析
- # 技术指标分析
- # 关键价位
- # 成交量分析
- # 交易建议

请确保分析基于技术图表、信号明确、建议可操作。"""

        return prompt

    def _comprehensive_template(self, context: Dict[str, Any]) -> str:
        """综合分析报告模板"""
        ticker = context.get("ticker", "N/A")
        company_info = context.get("company_info", {})
        financials = context.get("financials", {})
        price_data = context.get("price_data", {})
        news = context.get("news", [])

        prompt = f"""请为股票 {ticker} 生成一份详细的综合研究报告。

## 要求
1. 结合基本面和技术面进行全面分析
2. 评估公司财务健康和业务前景
3. 分析价格趋势和技术形态
4. 综合市场情绪和新闻事件
5. 提供多时间维度的投资建议

## 可用数据
公司信息：{company_info}
财务数据：{financials}
价格数据：{price_data}
最近新闻：{news[:3] if news else "无"}

## 输出格式
使用Markdown格式，包含以下章节：
- # 执行摘要
- # 公司概况与基本面
- # 财务分析
- # 技术面分析
- # 市场情绪与新闻
- # SWOT分析
- # 投资建议（短期/中期/长期）
- # 风险提示

请确保报告全面、逻辑严密、建议明确且有风险提示。"""

        return prompt

    async def _call_llm(self, prompt: str, ticker: str) -> str:
        """
        调用LLM生成报告内容

        Args:
            prompt: 提示词
            ticker: 股票代码

        Returns:
            生成的报告内容（Markdown格式）
        """
        try:
            from backend.llm_config import create_llm

            # 获取GPT-4o模型（优先使用高级模型生成报告）
            llm = create_llm(
                temperature=0.3,  # 较低温度确保输出稳定
                max_tokens=4096,  # 长报告需要更多token
                model="gpt-4o"  # 指定使用GPT-4o
            )

            # 生成报告
            response = await llm.ainvoke(prompt)

            if hasattr(response, 'content'):
                return response.content
            return str(response)

        except Exception as exc:
            logger.error("[ResearchReport] LLM调用失败")
            return self._fallback_report(ticker)

    def _fallback_report(self, ticker: str) -> str:
        """生成失败时的备用报告"""
        return f"""# {ticker} 研究报告生成失败

生成报告时遇到错误，请稍后重试。

请稍后重试，或检查以下事项：
1. LLM服务是否正常运行
2. API密钥是否配置正确
3. 数据源是否可用

---
*报告生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
"""

    def _generate_report_id(self, ticker: str, report_type: str) -> str:
        """生成报告ID"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"{ticker}_{report_type}_{timestamp}"

    def _extract_data_sources(self, context: Dict[str, Any]) -> List[str]:
        """提取数据源列表"""
        sources = []
        if context.get("company_info"):
            sources.append("公司基本信息")
        if context.get("financials"):
            sources.append("财务报表")
        if context.get("price_data"):
            sources.append("历史价格数据")
        if context.get("indicators"):
            sources.append("技术指标")
        if context.get("news"):
            sources.append("新闻资讯")
        return sources


# 全局实例
_report_generator: Optional[ResearchReportGenerator] = None


def get_report_generator() -> ResearchReportGenerator:
    """获取报告生成器单例"""
    global _report_generator
    if _report_generator is None:
        _report_generator = ResearchReportGenerator()
    return _report_generator
