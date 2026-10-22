"""Shared fixtures for the email tests: smtplib replaced by a fake, and
settings pointed at an imaginary relay. Loaded via pytest_plugins in conftest.py."""

import smtplib

import pytest

from app.config import settings


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
