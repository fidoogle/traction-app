"""Safeguards around sending: retries, the outage cool-down, the hourly cap per
person, and the unsubscribe header and footers."""

import smtplib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.core import email as mailer
from app.core import notifications as n
from app.core.account_emails import send_reset_email, send_welcome_email
from app.db import SessionLocal
from app.models import NotificationLog, User


def sent(smtp):
    return [m for conn in smtp.instances for m in conn.sent]


def text(msg) -> str:
    return msg.get_body(("plain",)).get_content()


@pytest.fixture()
def pauses(monkeypatch):
    """Records the pauses between tries instead of waiting."""
    recorded = []
    monkeypatch.setattr(mailer, "_sleep", recorded.append)
    monkeypatch.setattr(settings, "smtp_retry_delay_seconds", 1.5)
    return recorded


def busy():
    return smtplib.SMTPResponseException(451, b"Try again later")


def refused():
    return smtplib.SMTPRecipientsRefused({"a@b.test": (550, b"No such user")})


# --- retries ---


def test_a_passing_hiccup_is_retried_with_growing_pauses(smtp, configured, pauses):
    smtp.errors = [busy(), busy()]
    assert mailer.send_email("a@b.test", "Hi", "body").ok
    assert pauses == [1.5, 3.0]
    assert len(sent(smtp)) == 1


def test_giving_up_after_the_last_try_says_how_many(smtp, configured, pauses):
    smtp.errors = [busy(), busy(), busy()]
    result = mailer.send_email("a@b.test", "Hi", "body")
    assert not result.ok and "451" in result.error and "tried 3 times" in result.error
    assert pauses == [1.5, 3.0] and sent(smtp) == []


@pytest.mark.parametrize(
    "error",
    [refused(), smtplib.SMTPAuthenticationError(535, b"Bad credentials"), smtplib.SMTPSenderRefused(553, b"No", "x@y.test")],
)
def test_a_permanent_refusal_is_not_retried(smtp, configured, pauses, error):
    smtp.errors = [error]
    result = mailer.send_email("a@b.test", "Hi", "body")
    assert not result.ok and "tried" not in result.error
    assert pauses == []


def test_a_temporary_refusal_of_every_recipient_is_retried(smtp, configured, pauses):
    smtp.errors = [smtplib.SMTPRecipientsRefused({"a@b.test": (452, b"Mailbox full")})]
    assert mailer.send_email("a@b.test", "Hi", "body").ok
    assert pauses == [1.5]


def test_retries_can_be_switched_off(smtp, configured, pauses, monkeypatch):
    monkeypatch.setattr(settings, "smtp_retries", 0)
    smtp.errors = [busy()]
    assert not mailer.send_email("a@b.test", "Hi", "body").ok
    assert pauses == []


def test_failures_are_classified():
    assert mailer.classify_failure(busy()) == mailer.TRANSIENT
    assert mailer.classify_failure(smtplib.SMTPResponseException(550, b"No")) == mailer.PERMANENT
    assert mailer.classify_failure(refused()) == mailer.PERMANENT
    assert mailer.classify_failure(smtplib.SMTPServerDisconnected("gone")) == mailer.UNREACHABLE
    assert mailer.classify_failure(smtplib.SMTPConnectError(421, b"Busy")) == mailer.UNREACHABLE
    assert mailer.classify_failure(ConnectionRefusedError("no")) == mailer.UNREACHABLE
    assert mailer.classify_failure(TimeoutError("slow")) == mailer.UNREACHABLE
    assert mailer.classify_failure(smtplib.SMTPException("odd")) == mailer.PERMANENT


# --- the outage cool-down ---


def test_an_unreachable_server_is_left_alone_for_a_minute(smtp, configured, pauses, monkeypatch):
    now = {"t": 1000.0}
    monkeypatch.setattr(mailer, "_clock", lambda: now["t"])
    smtp.errors = [ConnectionRefusedError("down")] * 3
    first = mailer.send_email("a@b.test", "Hi", "body")
    assert not first.ok and "tried 3 times" in first.error

    smtp.errors = []  # the server is back, but we are not looking yet
    quick = mailer.send_email("a@b.test", "Hi", "body")
    assert not quick.ok and "not trying again yet" in quick.error
    assert pauses == [1.5, 3.0]  # and no more waiting
    assert smtp.instances == []

    now["t"] += settings.smtp_down_cooldown_seconds + 1
    assert mailer.send_email("a@b.test", "Hi", "body").ok


def test_a_long_list_during_an_outage_fails_fast(smtp, configured, pauses):
    smtp.errors = [ConnectionRefusedError("down")] * 3
    results = [mailer.send_email(f"u{i}@b.test", "Hi", "body") for i in range(50)]
    assert not any(r.ok for r in results)
    assert pauses == [1.5, 3.0]  # only the first email waited


def test_a_busy_server_does_not_trigger_the_cool_down(smtp, configured, pauses):
    smtp.errors = [busy(), busy(), busy()]
    assert not mailer.send_email("a@b.test", "Hi", "body").ok
    assert mailer.send_email("b@b.test", "Hi", "body").ok  # tried straight away


def test_extra_headers_go_out(smtp, configured):
    mailer.send_email("a@b.test", "Hi", "body", headers={"List-Unsubscribe": "<https://x.test/n>"})
    assert sent(smtp)[0]["List-Unsubscribe"] == "<https://x.test/n>"


# --- the hourly cap per person ---


def send(db, user_id, key="todo_assigned", **kw):
    kw.setdefault("subject_line", "Hello")
    kw.setdefault("template", "test")
    return n.notify(db, db.get(User, user_id), key, **kw)


def test_a_person_gets_at_most_so_many_emails_an_hour(world, smtp, configured, monkeypatch):
    monkeypatch.setattr(settings, "email_max_per_user_per_hour", 3)
    with SessionLocal() as db:
        results = [send(db, world["max"], subject=f"todo:{i}") for i in range(5)]
        assert [r.status for r in results] == ["sent", "sent", "sent", "skipped", "skipped"]
        assert "too many" in results[3].detail
        assert db.scalar(select(func.count()).select_from(NotificationLog)) == 3  # the dropped ones are not claimed
        assert send(db, world["mia"], subject="todo:x").sent  # someone else is unaffected
    assert len(sent(smtp)) == 4


def test_only_the_last_hour_counts(world, smtp, configured, monkeypatch):
    monkeypatch.setattr(settings, "email_max_per_user_per_hour", 2)
    with SessionLocal() as db:
        long_ago = datetime.now(timezone.utc) - timedelta(hours=2)
        for i in range(5):
            db.add(NotificationLog(user_id=world["max"], key="todo_assigned", subject=f"old{i}", status="sent", created_at=long_ago))
        db.commit()
        assert send(db, world["max"], subject="todo:new").sent


def test_failed_sends_do_not_use_up_the_cap(world, smtp, configured, monkeypatch):
    monkeypatch.setattr(settings, "email_max_per_user_per_hour", 2)
    smtp.fail_connect = True
    with SessionLocal() as db:
        for i in range(3):
            mailer._unreachable_until = 0.0
            assert send(db, world["max"], subject=f"todo:{i}").status == "failed"
        smtp.fail_connect = False
        mailer._unreachable_until = 0.0
        assert send(db, world["max"], subject="todo:ok").sent


def test_account_emails_are_never_capped(world, smtp, configured, monkeypatch):
    monkeypatch.setattr(settings, "email_max_per_user_per_hour", 1)
    with SessionLocal() as db:
        assert send(db, world["max"], key="weekly_digest", subject="a").sent
        assert send(db, world["max"], key="weekly_digest", subject="b").status == "skipped"
        assert send(db, world["max"], key="account_welcome", subject="c").sent
        assert send(db, world["max"], key="password_reset", subject="d").sent


# --- unsubscribe ---


def test_optional_emails_carry_an_unsubscribe_header_and_footer(world, smtp, configured):
    with SessionLocal() as db:
        assert send(db, world["max"], "todo_assigned").sent
    msg = sent(smtp)[0]
    assert msg["List-Unsubscribe"] == "<https://traction.district.test/notifications>"
    assert text(msg).rstrip().endswith("Choose which emails you get: https://traction.district.test/notifications")
    html = msg.get_body(("html",)).get_content()
    assert "Choose which emails you get" in html and "can't be turned off" not in html


def test_account_emails_say_they_cannot_be_turned_off(world, smtp, configured):
    with SessionLocal() as db:
        assert send(db, world["max"], "account_welcome").sent
    msg = sent(smtp)[0]
    assert "List-Unsubscribe" not in msg
    assert "can't be turned off" in text(msg) and "can't be turned off" in msg.get_body(("html",)).get_content()


def test_the_welcome_and_reset_emails_are_marked_as_account_emails(smtp, configured):
    assert send_welcome_email("a@b.test", "Ann", "tok", "Ada").ok
    assert send_reset_email("a@b.test", "Ann", "tok").ok
    for msg in sent(smtp):
        assert "can't be turned off" in text(msg) and "List-Unsubscribe" not in msg
        assert "can't be turned off" in msg.get_body(("html",)).get_content()
