"""Every email renders cleanly, loads nothing from outside, reads fine as plain
text, and leaves out the things that must never be emailed."""

import re
from pathlib import Path

import pytest
from sqlalchemy import update

from app import worker
from app.core import notifications as n
from app.core.alert_emails import announce_new_issues, send_quarter_reminders
from app.core.digest_emails import send_digests
from app.core.due_emails import send_due_todos
from app.core.email import render_email
from app.core.email_samples import SAMPLES, context_for
from app.db import SessionLocal
from app.models import Issue, PeopleAnalyzerEntry, Rock, RockStatus, Todo, User

TEMPLATES = Path(__file__).resolve().parent.parent / "app" / "templates" / "email"
APP = Path(__file__).resolve().parent.parent / "app"


def test_every_email_template_has_sample_data():
    on_disk = {p.stem for p in TEMPLATES.glob("*.txt")}
    assert on_disk == {p.stem for p in TEMPLATES.glob("*.html") if p.stem != "base"}  # a text and an HTML version each
    assert on_disk == set(SAMPLES), "add sample data for the new email in app/core/email_samples.py"


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_renders_cleanly_in_both_versions(name):
    context = context_for(name)
    text, html = render_email(name, **context)
    assert text.strip() and html.strip()
    for version in (text, html):
        assert "{{" not in version and "{%" not in version
        assert "Undefined" not in version and "None" not in version
    if name != "test":  # the admin's "send a test email" has no greeting
        assert context["name"] in text and context["name"] in html


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_loads_nothing_from_outside(name):
    """Mail programs fetch images, styles and scripts as soon as a message opens;
    these emails use none, so opening one tells nobody anything."""
    _, html = render_email(name, **context_for(name))
    for forbidden in ("<img", "<script", "<link", "<style", "<iframe", "src=", "@import", "url(", "background="):
        assert forbidden not in html.lower(), forbidden
    assert html.lstrip().lower().startswith("<!doctype html>")


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_links_in_html_are_https_or_the_apps_own(name):
    _, html = render_email(name, **context_for(name))
    for url in re.findall(r'href="([^"]+)"', html):
        assert url.startswith("https://"), url


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_plain_text_stands_on_its_own(name):
    """Anyone reading only the text part still gets every link the HTML offers."""
    context = context_for(name)
    text, html = render_email(name, **context)
    for url in re.findall(r'href="([^"]+)"', html):
        plain = url.replace("&amp;", "&")
        assert plain in text, f"{plain} is only in the HTML"
    assert max(len(line) for line in text.splitlines() if "http" not in line) <= 200  # mail programs wrap paragraphs themselves


def test_the_footer_note_matches_the_kind_of_email():
    text, html = render_email("todo_due", **context_for("todo_due"))
    assert "Choose which emails you get" in text and "Choose which emails you get" in html
    for account in ("welcome", "password_reset"):
        text, html = render_email(account, **context_for(account))
        assert "can't be turned off" in text and "can't be turned off" in html
        assert "Choose which emails you get" not in text


# --- what must never be in an email ---

# Things that are personnel-sensitive or whole-text fields. The emails carry titles,
# names and numbers; none of these.
FORBIDDEN_IN_EMAIL_CODE = [
    r"PeopleAnalyzer", r"people_analyzer", r"gets_it", r"wants_it", r"has_capacity", r"core_values",
    r"\bSeat\b", r"\bVTO\b", r"\.notes\b", r"hashed_password", r"calendar_token",
]
EMAIL_CODE = [
    "core/account_emails.py", "core/alert_emails.py", "core/assignment_emails.py", "core/digest.py",
    "core/digest_emails.py", "core/due_emails.py", "core/meeting_emails.py", "core/notifications.py",
]


@pytest.mark.parametrize("module", EMAIL_CODE)
def test_email_code_never_reads_sensitive_fields(module):
    source = (APP / module).read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.strip().startswith("#"))
    for pattern in FORBIDDEN_IN_EMAIL_CODE:
        assert not re.search(pattern, code), f"{module} mentions {pattern}"


def test_sensitive_content_does_not_leak_into_any_email(world, smtp, configured, no_digest):
    """Fill every sensitive field with a marker, run every sender, and look for the marker."""
    marker = "SENSITIVE-MARKER"
    with SessionLocal() as db:
        db.execute(update(Rock).values(notes=marker, status=RockStatus.OFF_TRACK))
        db.execute(update(Issue).values(notes=marker, announced_at=None))
        db.execute(update(Todo).values(notes=marker))
        db.execute(update(PeopleAnalyzerEntry).values(core_values_ratings={marker: True}))
        for who in ("mia", "max", "vic", "admin"):
            for nt in n.CATALOG:
                if n.eligible(nt, n.hats(db, db.get(User, world[who]))) and not nt.always:
                    n.set_preference(db, db.get(User, world[who]), nt.key, True)
        from datetime import date, datetime, timedelta, timezone

        org = db.get(User, world["admin"]).org_id
        today = date(2026, 10, 22)
        send_digests(db, org, today, "2026-W43")
        send_due_todos(db, today, org)
        send_quarter_reminders(db, org, date(2026, 12, 18))
        announce_new_issues(db, datetime.now(timezone.utc) + timedelta(hours=1))
    from app.core.assignment_emails import send_rock_assigned, send_todo_assigned
    from app.core.alert_emails import send_rock_off_track

    send_rock_off_track(world["rock_alpha"], world["admin"], "e1")
    send_rock_assigned(world["rock_alpha"], world["admin"], "e2")
    send_todo_assigned(world["todo_alpha"], world["admin"], "e3")

    messages = [m for conn in smtp.instances for m in conn.sent]
    assert len(messages) >= 8   # the senders really did run
    everything = "\n".join(m.as_string() for m in messages)
    for body in (m.get_body(("plain",)).get_content() for m in messages):
        everything += body
    for secret in (marker, "alpha seat", "alpha purpose", "alpha value", "hashed_password"):
        assert secret not in everything, secret


def test_the_worker_module_is_not_a_back_door(world, smtp, configured, no_digest):
    """A tick on an empty-handed day sends nothing surprising."""
    worker.tick(worker.WorkerState(), __import__("datetime").datetime(2026, 11, 20, 3, 0, tzinfo=__import__("datetime").timezone.utc))
    assert [m for conn in smtp.instances for m in conn.sent] == []
