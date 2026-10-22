"""Outgoing email: a no-op when unconfigured, correct messages when configured,
and failures reported rather than raised. smtplib is replaced by a fake."""

import smtplib
from email.utils import parseaddr

import pytest

from app.config import settings
from app.core import email as mailer


class FakeSMTP:
    instances: list = []
    fail_connect = False

    def __init__(self, host, port, timeout=None, context=None):
        if FakeSMTP.fail_connect:
            raise ConnectionRefusedError("relay down")
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.started_tls = False
        self.logged_in = None
        self.sent = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.started_tls = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, msg):
        self.sent.append(msg)


@pytest.fixture()
def smtp(monkeypatch):
    FakeSMTP.instances, FakeSMTP.fail_connect = [], False
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    return FakeSMTP


@pytest.fixture()
def configured(monkeypatch):
    for name, value in {
        "smtp_host": "mail.district.test",
        "smtp_port": 587,
        "smtp_security": "starttls",
        "smtp_username": "",
        "smtp_password": "",
        "smtp_from_address": "traction@district.test",
        "smtp_from_name": "Traction",
        "base_url": "https://traction.district.test/",
    }.items():
        monkeypatch.setattr(settings, name, value)


def test_disabled_by_default_sends_nothing(smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")
    assert not settings.email_enabled
    result = mailer.send_email("a@b.test", "Hi", "body")
    assert not result.ok
    assert smtp.instances == []


def test_enabled_needs_host_from_address_and_base_url(monkeypatch, configured):
    assert settings.email_enabled
    for name in ("smtp_host", "smtp_from_address", "base_url"):
        monkeypatch.setattr(settings, name, "")
        assert not settings.email_enabled
        monkeypatch.undo()


def test_sends_text_and_html_with_starttls(smtp, configured):
    text, html = mailer.render_email("test")
    result = mailer.send_email("ada@example.com", "Hello", text, html)
    assert result.ok
    (conn,) = smtp.instances
    assert (conn.host, conn.port, conn.started_tls) == ("mail.district.test", 587, True)
    (msg,) = conn.sent
    assert msg["To"] == "ada@example.com"
    assert parseaddr(msg["From"]) == ("Traction", "traction@district.test")
    assert msg["Subject"] == "Hello"
    assert msg["Message-ID"] and msg["Date"]
    assert msg.get_body(("plain",)).get_content().startswith("Test email")
    assert "https://traction.district.test" in msg.get_body(("html",)).get_content()


def test_login_only_when_username_set(smtp, configured, monkeypatch):
    mailer.send_email("a@b.test", "s", "b")
    assert smtp.instances[-1].logged_in is None
    monkeypatch.setattr(settings, "smtp_username", "svc")
    monkeypatch.setattr(settings, "smtp_password", "pw")
    mailer.send_email("a@b.test", "s", "b")
    assert smtp.instances[-1].logged_in == ("svc", "pw")


def test_security_modes(smtp, configured, monkeypatch):
    monkeypatch.setattr(settings, "smtp_security", "none")
    mailer.send_email("a@b.test", "s", "b")
    assert smtp.instances[-1].started_tls is False
    monkeypatch.setattr(settings, "smtp_security", "ssl")
    mailer.send_email("a@b.test", "s", "b")
    assert smtp.instances[-1].started_tls is False  # implicit TLS, no STARTTLS


def test_attachment_keeps_content_type_params(smtp, configured):
    att = mailer.Attachment(
        "invite.ics", b"BEGIN:VCALENDAR", "text", "calendar", {"method": "REQUEST"}
    )
    assert mailer.send_email("a@b.test", "s", "b", attachments=[att]).ok
    (msg,) = smtp.instances[-1].sent
    part = [p for p in msg.iter_attachments()][0]
    assert part.get_content_type() == "text/calendar"
    assert part.get_param("method") == "REQUEST"


def test_connection_failure_is_returned_not_raised(smtp, configured):
    smtp.fail_connect = True
    result = mailer.send_email("a@b.test", "s", "b")
    assert not result.ok and "relay down" in result.error


def test_header_injection_is_rejected(smtp, configured):
    result = mailer.send_email("a@b.test", "Hi\r\nBcc: evil@x.test", "b")
    assert not result.ok
    assert smtp.instances == []


def test_html_template_escapes_context(configured):
    from app.core.email import _env

    out = _env.from_string("{% extends 'base.html' %}{% block body %}{{ x }}{% endblock %}").render(
        x="<script>"
    )
    assert "<script>" not in out and "&lt;script&gt;" in out


# --- Settings page / test-email action (needs the test database) ---


def test_settings_page_admin_only(world, login):
    assert login("admin").get("/settings").status_code == 200
    assert login("mia").get("/settings").status_code == 403
    assert login("vic").post("/settings/test-email").status_code == 403


def test_settings_page_when_not_configured(world, login, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")
    page = login("admin").get("/settings").text
    assert "not configured" in page
    reply = login("admin").post("/settings/test-email").text
    assert "not configured" in reply


def test_test_email_goes_to_the_admins_own_address(world, login, smtp, configured):
    reply = login("admin").post("/settings/test-email", data={"to": "someone@else.test"})
    assert "admin@example.com" in reply.text
    (msg,) = smtp.instances[-1].sent
    assert msg["To"] == "admin@example.com"


def test_test_email_reports_failure(world, login, smtp, configured):
    smtp.fail_connect = True
    assert "Could not send" in login("admin").post("/settings/test-email").text
