import logging
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from backend.security.pinned_http import safe_pinned_request

logger = logging.getLogger(__name__)


def _safe_log_host(url: str) -> str:
    try:
        return urlparse(url).hostname or "<invalid>"
    except ValueError:
        return "<invalid>"


def fetch_url_content(url: str, max_length: int = 5000) -> Optional[str]:
    """
    抓取 URL 内容并提取正文文本
    用于从新闻链接中提取内容供上下文分析

    Args:
        url: 要抓取的 URL
        max_length: 返回内容的最大长度

    Returns:
        提取的文本内容，失败返回 None
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        # safe_pinned_request 内置 resolve_safe_target 校验 + IP pin（强制连接到
        # 校验时锁定的公网 IP，防 DNS rebinding/TOCTOU）+ 逐跳重定向校验（禁自动
        # 重定向，每跳重新校验）。返回 None = URL 不安全或抓取失败。
        response = safe_pinned_request("GET", url, headers=headers, timeout=15)
        if response is None:
            logger.info("[fetch_url_content] Blocked unsafe url or fetch failed")
            return None
        response.raise_for_status()

        # 使用 BeautifulSoup 解析 HTML
        soup = BeautifulSoup(response.text, "html.parser")

        # 移除脚本和样式
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"]):
            tag.decompose()

        # 尝试找到主要内容区域
        main_content = None
        for selector in ["article", "main", ".article-content", ".post-content", ".entry-content", "#content", ".content"]:
            main_content = soup.select_one(selector)
            if main_content:
                break

        # 如果没找到主要内容，使用 body
        if not main_content:
            main_content = soup.body if soup.body else soup

        # 提取文本
        text = main_content.get_text(separator="\n", strip=True)

        # 清理多余空白
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        text = "\n".join(lines)

        # 截断到最大长度
        if len(text) > max_length:
            text = text[:max_length] + "..."

        logger.info("[fetch_url_content] 成功抓取 (%s 字符)", len(text))
        return text

    except requests.exceptions.Timeout:
        logger.info("[fetch_url_content] 超时")
        return None
    except requests.exceptions.RequestException as e:
        logger.info("[fetch_url_content] 请求失败: error=%s", type(e).__name__)
        return None
    except Exception as e:
        logger.info("[fetch_url_content] 解析失败: error=%s", type(e).__name__)
        return None
