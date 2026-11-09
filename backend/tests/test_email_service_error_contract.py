from backend.services import email_service as email_module
from backend.services.email_service import EmailService
import pytest


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
        raise email_module.smtplib.SMTPRecipientsRefused({"user@example.com": (550, secret.encode())})

    monkeypatch.setattr(email_module.smtplib, "SMTP", _fail_smtp)

    result = _configured_service().send_email("user@example.com", "subject", "<p>body</p>")

    assert result == (False, "permanent", "Email delivery rejected")
    assert secret not in str(result)
    assert secret not in caplog.text
    assert "[EmailService] Permanent SMTP error" in caplog.text


@pytest.mark.parametrize("error_kind,code,expected_type", [
    ("authentication", 450, "transient"), ("authentication", 550, "transient"),
    ("sender", 450, "transient"), ("sender", 550, "transient"),
    ("recipient", 450, "transient"), ("recipient", 550, "permanent"),
    ("data", 450, "transient"), ("data", 550, "permanent"),
])
def test_smtp_rejections_use_status_code_without_exposing_provider_details(
    monkeypatch, caplog, error_kind, code, expected_type,
):
    smtp = email_module.smtplib
    secret = b"PRIVATE recipient and SMTP credentials"
    error = {
        "authentication": smtp.SMTPAuthenticationError(code, secret),
        "recipient": smtp.SMTPRecipientsRefused({"user@example.com": (code, secret)}),
        "sender": smtp.SMTPSenderRefused(code, secret, "sender@example.com"),
        "data": smtp.SMTPDataError(code, secret),
    }[error_kind]

    def fail_smtp(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(smtp, "SMTP", fail_smtp)
    result = _configured_service().send_email("user@example.com", "subject", "<p>body</p>")

    assert result[0] is False
    assert result[1] == expected_type
    assert "PRIVATE" not in str(result)
    assert "PRIVATE" not in caplog.text


def test_smtp_temporary_rejection_does_not_disable_alert_subscription(monkeypatch, tmp_path):
    from backend.services import subscription_service as subs
    from backend.services.alert_scheduler import PriceChangeScheduler, PriceSnapshot

    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", tmp_path / "subscriptions.json")
    monkeypatch.setattr(subs, "ALERT_FAILURE_LIMIT", 1)
    service = subs.SubscriptionService()
    assert service.subscribe("user@example.com", "AAPL", alert_types=["price_change"], price_threshold=3.0)

    def fail_smtp(*_args, **_kwargs):
        raise email_module.smtplib.SMTPDataError(450, b"Temporary delivery refusal")

    monkeypatch.setattr(email_module.smtplib, "SMTP", fail_smtp)
    scheduler = PriceChangeScheduler(
        service, _configured_service(), lambda ticker: PriceSnapshot(ticker, 105.0, 5.0),
    )
    assert scheduler.run_once() == []
    saved = service.get_subscriptions("user@example.com")[0]
    assert saved["disabled"] is False
    assert saved["alert_failures"] == 0
    assert saved["last_alert_error"] == "transient_delivery_error"


@pytest.mark.parametrize("missing_field", ["smtp_user", "smtp_password"])
def test_missing_smtp_configuration_is_not_a_permanent_subscription_failure(monkeypatch, missing_field):
    service = _configured_service()
    setattr(service, missing_field, "")

    def unexpected_connection(*_args, **_kwargs):
        raise AssertionError("missing credentials must not open SMTP connections")

    monkeypatch.setattr(email_module.smtplib, "SMTP", unexpected_connection)

    assert service.send_email("user@example.com", "subject", "<p>body</p>") == (
        False, "transient", "SMTP credentials missing",
    )


@pytest.mark.parametrize("mode", ["price_change_pct", "price_target", "news", "risk"])
def test_missing_smtp_configuration_preserves_alerts_for_later_delivery(monkeypatch, tmp_path, mode):
    from datetime import datetime, timedelta, timezone
    from backend.services import subscription_service as subs
    from backend.services.alert_scheduler import NewsAlertScheduler, PriceChangeScheduler, PriceSnapshot, RiskAlertScheduler

    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", tmp_path / "subscriptions.json")
    monkeypatch.setattr(subs, "ALERT_FAILURE_LIMIT", 1)
    service = subs.SubscriptionService()
    price_mode = mode if mode in {"price_change_pct", "price_target"} else "price_change_pct"
    assert service.subscribe(
        "user@example.com", "AAPL", alert_types=[mode] if mode in {"news", "risk"} else ["price_change"],
        alert_mode=price_mode, price_threshold=3.0, price_target=110.0, direction="above",
    )
    email = _configured_service()
    email.smtp_password = ""
    quote = lambda ticker: PriceSnapshot(ticker, 120.0, -9.0)
    if mode == "news":
        scheduler = NewsAlertScheduler(service, email, lambda _ticker: [{
            "title": "Earnings release", "related_tickers": ["AAPL"],
            "published_at": datetime.now(timezone.utc) - timedelta(hours=1),
        }])
    elif mode == "risk":
        scheduler = RiskAlertScheduler(service, email, quote)
    else:
        scheduler = PriceChangeScheduler(service, email, quote)

    assert scheduler.run_once() == []
    saved = service.get_subscriptions("user@example.com")[0]
    assert saved["disabled"] is False
    assert saved["alert_failures"] == 0
    assert saved["price_target_fired"] is False
    assert saved["last_news_at"] is None
    assert saved["last_risk_at"] is None
    assert saved["last_alert_error"] == "transient_delivery_error"


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


@pytest.mark.parametrize("error_kind", ["authentication", "sender"])
@pytest.mark.parametrize("mode", ["price_change_pct", "price_target", "news", "risk"])
def test_smtp_configuration_rejection_does_not_disable_user_alerts(monkeypatch, tmp_path, error_kind, mode):
    from datetime import datetime, timedelta, timezone
    from backend.services import subscription_service as subs
    from backend.services.alert_scheduler import NewsAlertScheduler, PriceChangeScheduler, PriceSnapshot, RiskAlertScheduler

    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", tmp_path / "subscriptions.json")
    monkeypatch.setattr(subs, "ALERT_FAILURE_LIMIT", 1)
    service = subs.SubscriptionService()
    assert service.subscribe(
        "user@example.com", "AAPL", alert_types=[mode] if mode in {"news", "risk"} else ["price_change"],
        alert_mode="price_target" if mode == "price_target" else "price_change_pct",
        price_threshold=3.0, price_target=110.0, direction="above",
    )

    def fail_smtp(*_args, **_kwargs):
        if error_kind == "authentication":
            raise email_module.smtplib.SMTPAuthenticationError(535, b"PRIVATE credentials rejected")
        raise email_module.smtplib.SMTPSenderRefused(550, b"PRIVATE sender rejected", "sender@example.com")

    monkeypatch.setattr(email_module.smtplib, "SMTP", fail_smtp)
    email = _configured_service()
    quote = lambda ticker: PriceSnapshot(ticker, 120.0, -9.0)
    if mode == "news":
        scheduler = NewsAlertScheduler(service, email, lambda _ticker: [{
            "title": "Earnings release", "related_tickers": ["AAPL"],
            "published_at": datetime.now(timezone.utc) - timedelta(hours=1),
        }])
    elif mode == "risk":
        scheduler = RiskAlertScheduler(service, email, quote)
    else:
        scheduler = PriceChangeScheduler(service, email, quote)

    assert scheduler.run_once() == []
    saved = service.get_subscriptions("user@example.com")[0]
    assert saved["disabled"] is False
    assert saved["alert_failures"] == 0
    assert saved["price_target_fired"] is False
    assert saved["last_news_at"] is None
    assert saved["last_risk_at"] is None
    assert saved["last_alert_error"] == "transient_delivery_error"


def _install_smtp_cleanup_failure(monkeypatch, error_kind, accepted, *, reject_data=False):
    class CleanupSMTP(email_module.smtplib.SMTP):
        def __init__(self, *_args, **_kwargs):
            pass

        def starttls(self):
            return 220, b"Ready"

        def login(self, *_args):
            return 235, b"Authenticated"

        def send_message(self, msg):
            if reject_data:
                raise email_module.smtplib.SMTPDataError(550, b"PRIVATE rejected data")
            accepted.append(msg)
            return {}

        def docmd(self, command):
            assert command == "QUIT"
            if error_kind == "timeout":
                raise TimeoutError("PRIVATE SMTP timeout")
            return (500, b"PRIVATE bad QUIT") if error_kind == "quit_reply" else (221, b"Bye")

        def close(self):
            if error_kind == "close":
                raise ConnectionError("PRIVATE close failure")

    monkeypatch.setattr(email_module.smtplib, "SMTP", CleanupSMTP)


@pytest.mark.parametrize("error_kind", ["quit_reply", "timeout", "close"])
def test_accepted_email_remains_successful_after_smtp_cleanup_error(monkeypatch, caplog, error_kind):
    accepted = []
    _install_smtp_cleanup_failure(monkeypatch, error_kind, accepted)

    assert _configured_service().send_email("user@example.com", "subject", "<p>body</p>") == (True, "none", None)
    assert len(accepted) == 1
    assert "SMTP cleanup failed after delivery acceptance" in caplog.text
    assert "PRIVATE" not in caplog.text


def test_unaccepted_email_does_not_report_success(monkeypatch):
    accepted = []
    _install_smtp_cleanup_failure(monkeypatch, "none", accepted, reject_data=True)

    assert _configured_service().send_email("user@example.com", "subject", "<p>body</p>") == (
        False, "permanent", "Email delivery rejected",
    )
    assert accepted == []


@pytest.mark.parametrize("mode", ["price_change_pct", "price_target", "news", "risk"])
def test_smtp_cleanup_error_does_not_repeat_delivered_alert(monkeypatch, tmp_path, mode):
    from datetime import datetime, timedelta, timezone
    from backend.services import subscription_service as subs
    from backend.services.alert_scheduler import NewsAlertScheduler, PriceChangeScheduler, PriceSnapshot, RiskAlertScheduler

    monkeypatch.setattr(subs, "SUBSCRIPTIONS_FILE", tmp_path / "subscriptions.json")
    service = subs.SubscriptionService()
    assert service.subscribe(
        "user@example.com", "AAPL", alert_types=[mode] if mode in {"news", "risk"} else ["price_change"],
        alert_mode="price_target" if mode == "price_target" else "price_change_pct",
        price_threshold=3.0, price_target=110.0, direction="above",
    )
    accepted = []
    _install_smtp_cleanup_failure(monkeypatch, "quit_reply", accepted)
    email = _configured_service()
    quote = lambda ticker: PriceSnapshot(ticker, 120.0, -9.0)
    if mode == "news":
        articles = [{
            "title": "Earnings release", "related_tickers": ["AAPL"],
            "published_at": datetime.now(timezone.utc) - timedelta(hours=1),
        }]
        scheduler = NewsAlertScheduler(service, email, lambda _ticker: articles)
    elif mode == "risk":
        scheduler = RiskAlertScheduler(service, email, quote)
    else:
        scheduler = PriceChangeScheduler(service, email, quote)

    assert len(scheduler.run_once()) == 1
    assert scheduler.run_once() == []
    assert len(accepted) == 1
    saved = service.get_subscriptions("user@example.com")[0]
    assert saved["alert_failures"] == 0
    assert len(saved["recent_events"]) == 1
