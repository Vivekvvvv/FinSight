from backend.services import email_service as email_module
from backend.services.email_service import EmailService


def _configured_service() -> EmailService:
    service = EmailService()
    service.smtp_user = "test-user"
    service.smtp_password = "test-password"
    service.email_from = "sender@example.com"
    return service


def test_email_transient_error_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE postgres://email:secret@db/network"
    private_email = "private-recipient@example.com"

    def _fail_smtp(*_args, **_kwargs):
        raise ConnectionError(secret)

    monkeypatch.setattr(email_module.smtplib, "SMTP", _fail_smtp)

    result = _configured_service().send_email(private_email, "subject", "<p>body</p>")

    assert result == (False, "transient", "Email delivery unavailable")
    assert secret not in str(result)
    assert secret not in caplog.text
    assert private_email not in caplog.text
    assert "[EmailService] Transient network error" in caplog.text


def test_email_permanent_error_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE smtp-password email-secret"

    def _fail_smtp(*_args, **_kwargs):
        raise email_module.smtplib.SMTPAuthenticationError(535, secret.encode())

    monkeypatch.setattr(email_module.smtplib, "SMTP", _fail_smtp)

    result = _configured_service().send_email("user@example.com", "subject", "<p>body</p>")

    assert result == (False, "permanent", "Email delivery rejected")
    assert secret not in str(result)
    assert secret not in caplog.text
    assert "[EmailService] Permanent SMTP error" in caplog.text


def test_email_unexpected_error_is_redacted(monkeypatch, caplog):
    secret = "PRIVATE postgres://email:secret@db/unexpected"

    def _fail_smtp(*_args, **_kwargs):
        raise ValueError(secret)

    monkeypatch.setattr(email_module.smtplib, "SMTP", _fail_smtp)

    result = _configured_service().send_email("user@example.com", "subject", "<p>body</p>")

    assert result == (False, "transient", "Email delivery unavailable")
    assert secret not in str(result)
    assert secret not in caplog.text
    assert "[EmailService] Unexpected error" in caplog.text


def test_stock_alert_escapes_untrusted_html(monkeypatch):
    service = _configured_service()
    captured = {}

    def _capture_send(to_email, subject, html_content, text_content=None):
        captured.update(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )
        return True, "none", None

    monkeypatch.setattr(service, "send_email", _capture_send)

    result = service.send_stock_alert(
        "user@example.com",
        "<b>AAPL</b>",
        "news",
        '<script>alert("x")</script>',
    )

    assert result == (True, "none", None)
    assert "<script>" not in captured["html_content"]
    assert "<b>AAPL</b>" not in captured["html_content"]
    assert "&lt;script&gt;" in captured["html_content"]
    assert "&lt;b&gt;AAPL&lt;/b&gt;" in captured["html_content"]
