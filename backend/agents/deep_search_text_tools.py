"""Text and document parsing helpers for DeepSearchAgent."""

from __future__ import annotations

from typing import Any
from datetime import datetime, timezone
import logging
import re

from bs4 import BeautifulSoup

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None

logger = logging.getLogger(__name__)


def _extract_html_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator=" ")
        return re.sub(r"\s+", " ", text).strip()


def _extract_pdf_text(data: bytes) -> str:
        if not PdfReader:
            return ""
        try:
            from io import BytesIO

            reader = PdfReader(BytesIO(data))
            pages = []
            for page in reader.pages[:8]:
                pages.append(page.extract_text() or "")
            return "\n".join(pages)
        except Exception as exc:
            logger.info("[DeepSearch] PDF parse failed")
            return ""


def _freshness_score(published_date: Any) -> float:
        text = str(published_date or "").strip()
        if not text:
            return 0.5
        try:
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            hours = max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600.0)
            if hours <= 24:
                return 1.0
            if hours <= 24 * 7:
                return 0.85
            if hours <= 24 * 30:
                return 0.7
            if hours <= 24 * 90:
                return 0.55
            return 0.4
        except Exception:
            return 0.5

