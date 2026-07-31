import logging
import re
from datetime import datetime
from typing import Dict, Any

import requests

from .env import FRED_API_KEY
from .http import _http_get
from .search import search
from backend.utils.quote import safe_float

logger = logging.getLogger(__name__)

def get_market_sentiment() -> str:
    """
    获取市场情绪指标 - CNN Fear & Greed Index
    使用更完整的请求头来模拟浏览器，提高成功率。
    """
    try:
        # 主要API地址
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        
        # 伪装成一个从CNN官网页面发出请求的真实浏览器
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
            # 'Referer' 是最关键的头信息，告诉服务器请求的来源页面
            'Referer': 'https://www.cnn.com/markets/fear-and-greed',
            'Origin': 'https://www.cnn.com',
        }
        
        logger.info("Attempting to fetch from CNN API with full headers...")
        response = _http_get(url, headers=headers, timeout=10)
        
        # 如果状态码不是 2xx，则会引发 HTTPError 异常
        response.raise_for_status() 
        
        data = response.json()
        score = safe_float(data['fear_and_greed']['score'])
        if score is None:
            raise ValueError("invalid fear and greed score")
        rating = data['fear_and_greed']['rating']
        
        logger.info("CNN API fetch successful!")
        return f"CNN Fear & Greed Index: {score:.1f} ({rating})"
    
    except requests.exceptions.HTTPError as http_err:
        logger.info("CNN API failed with HTTP error: %s. Trying fallback search...", type(http_err).__name__)
    except Exception as e:
        # 捕获其他所有可能的异常，例如网络问题、JSON解析错误等
        logger.info("CNN API failed with other error: %s. Trying fallback search...", type(e).__name__)
    # --- 如果上面的 try 代码块出现任何异常，则执行下面的回退逻辑 ---
    try:
        search_result = search("CNN Fear and Greed Index current value today")
        # 使用正则表达式从搜索结果中提取数值和评级
        match = re.search(r'(?:Index|Score)[:\s]*(\d+\.?\d*)\s*\((\w+\s?\w*)\)', search_result, re.IGNORECASE)
        if match:
            score = safe_float(match.group(1))
            if score is None:
                raise ValueError("invalid fear and greed score")
            rating = match.group(2)
            logger.info("Fallback search successful!")
            return f"CNN Fear & Greed Index (via search): {score:.1f} ({rating})"
    except Exception as search_e:
            logger.info("Search fallback also failed: %s", type(search_e).__name__)
    
    # 如果所有方法都失败了，返回一个通用错误信息
    return "Fear & Greed Index: Unable to fetch. Please check manually."

def get_economic_events() -> str:
    """搜索当前月份的主要美国经济事件"""
    now = datetime.now()
    query = f"major upcoming US economic events {now.strftime('%B %Y')} (FOMC, CPI, jobs report)"
    return search(query)


def get_fred_data(series_id: str = None) -> Dict[str, Any]:
    """
    从 FRED (Federal Reserve Economic Data) 获取宏观经济数据

    常用 series_id:
    - CPIAUCSL: CPI (Consumer Price Index)
    - FEDFUNDS: Federal Funds Rate
    - GDP: Gross Domestic Product
    - UNRATE: Unemployment Rate
    - DGS10: 10-Year Treasury Rate
    - T10Y2Y: 10Y-2Y Treasury Spread (衰退指标)
    """
    result = {
        "cpi": None,
        "fed_rate": None,
        "gdp_growth": None,
        "unemployment": None,
        "treasury_10y": None,
        "yield_spread": None,
        "status": "success",
        "source": "FRED",
        "as_of": datetime.now().isoformat()
    }

    # FRED API 配置
    api_key = FRED_API_KEY
    base_url = "https://api.stlouisfed.org/fred/series/observations"

    # 要获取的指标
    series_map = {
        "cpi": "CPIAUCSL",
        "fed_rate": "FEDFUNDS",
        "gdp_growth": "A191RL1Q225SBEA",  # Real GDP Growth Rate
        "unemployment": "UNRATE",
        "treasury_10y": "DGS10",
        "yield_spread": "T10Y2Y"
    }

    # 如果指定了单个 series_id，只获取该数据
    if series_id:
        series_map = {"custom": series_id}

    # 无 FRED API key：不伪造宏观数据。此前无 key 分支硬编码 cpi=3.0 /
    # fed_rate=4.5 / unemployment=4.0（2024 估计值），却仍返回 status="success"，
    # 被 dashboard 快照（fetch_macro_snapshot 只取数值不看 status）与 MacroAgent
    # 当真实数据消费（R22 同类，R49）。改为明确标记不可用、数值保持 None，
    # 让调用方走降级路径。
    if not api_key:
        result["status"] = "unavailable"
        result["source"] = "no_api_key"
        return result

    for key, sid in series_map.items():
        try:
            params = {
                "series_id": sid,
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 1
            }

            response = _http_get(base_url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                observations = data.get("observations", [])
                if observations:
                    value = observations[0].get("value", ".")
                    if value != ".":
                        result[key] = safe_float(value)

        except Exception as e:
            logger.info("[FRED] Failed to fetch %s: %s", sid, type(e).__name__)
            continue

    # 格式化输出
    if result.get("cpi"):
        result["cpi_formatted"] = f"{result['cpi']:.1f}"
    if result.get("fed_rate"):
        result["fed_rate_formatted"] = f"{result['fed_rate']:.2f}%"
    if result.get("unemployment"):
        result["unemployment_formatted"] = f"{result['unemployment']:.1f}%"
    if result.get("gdp_growth"):
        result["gdp_growth_formatted"] = f"{result['gdp_growth']:.1f}%"
    if result.get("treasury_10y"):
        result["treasury_10y_formatted"] = f"{result['treasury_10y']:.2f}%"
    if result.get("yield_spread"):
        result["yield_spread_formatted"] = f"{result['yield_spread']:.2f}%"
        # 收益率曲线倒挂警告
        if result["yield_spread"] < 0:
            result["recession_warning"] = True

    return result
