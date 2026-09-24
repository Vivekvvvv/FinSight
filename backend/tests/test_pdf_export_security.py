from __future__ import annotations

import pytest

from backend.services import pdf_export


def test_pdf_paragraph_text_escapes_reportlab_markup():
    markup = '<img src="C:/private/server-image.png"/>'

    escaped = pdf_export._escape_paragraph_text(markup)

    assert "<img" not in escaped
    assert escaped == "&lt;img src=&quot;C:/private/server-image.png&quot;/&gt;"


@pytest.mark.skipif(not pdf_export.REPORTLAB_AVAILABLE, reason="reportlab unavailable")
def test_pdf_export_escapes_all_client_controlled_paragraph_markup(monkeypatch):
    captured: list[str] = []
    real_paragraph = pdf_export.Paragraph

    def capture_paragraph(text, style):
        captured.append(str(text))
        return real_paragraph(text, style)

    monkeypatch.setattr(pdf_export, "Paragraph", capture_paragraph)
    service = pdf_export.PDFExportService()
    image_markup = '<img src="C:/private/server-image.png"/>'

    result = service.export_with_charts(
        [
            {
                "role": image_markup,
                "timestamp": image_markup,
                "content": image_markup,
            }
        ],
        [{"ticker": image_markup, "chart_type": image_markup}],
        title=image_markup,
    )

    assert result.startswith(b"%PDF")
    assert all("<img" not in text for text in captured)
    assert sum(text.count("&lt;img") for text in captured) >= 6


@pytest.mark.skipif(not pdf_export.REPORTLAB_AVAILABLE, reason="reportlab unavailable")
def test_pdf_export_skips_non_dict_messages_and_charts():
    """/api/export/pdf 的 request 是裸 dict——messages/charts 只验 list 形状，
    非 dict 毒条目（str/None/int）直达 msg.get/chart.get → AttributeError
    逃逸到路由 except → 整个导出 500。一条毒消息毁 100 条合法消息的导出。
    按条跳过非 dict 条目（同 R107-R123 缺陷类）。"""
    service = pdf_export.PDFExportService()

    result = service.export_conversation(
        [
            {"role": "user", "content": "hello"},
            "poison-message",
            None,
            42,
            {"role": "assistant", "content": "world"},
        ],
        title="t",
    )
    assert result.startswith(b"%PDF")

    result2 = service.export_with_charts(
        [{"role": "user", "content": "hi"}, {"bad": "item"}],
        [{"ticker": "AAPL", "chart_type": "kline"}, "poison-chart", None],
        title="t",
    )
    assert result2.startswith(b"%PDF")
