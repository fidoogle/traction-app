"""Welcome and password-reset links: the token rules, and the pages and emails
built on them. Uses the fake SMTP server from fixtures_email.py."""

import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core import password_tokens as tokens
from app.core.security import verify_password
from app.db import SessionLocal
from app.main import app
from app.models import PasswordToken, User
from app.web.password_routes import forgot_email_limiter, forgot_ip_limiter

LINK = re.compile(r"https://traction\.district\.test/set-password/(\S+)")


@pytest.fixture(autouse=True)
def _fresh_limiters():
    forgot_ip_limiter.clear()
    forgot_email_limiter.clear()


def sent(smtp):
    return [m for conn in smtp.instances for m in conn.sent]


def link_token(msg) -> str:
    return LINK.search(msg.get_body(("plain",)).get_content()).group(1)


def anon() -> TestClient:
    """A signed-out browser that already holds a CSRF cookie."""
    client = TestClient(app, follow_redirects=False)
    assert client.get("/login").status_code == 200
    return client


def csrf(client) -> str:
    return client.cookies.get("csrf_token")


def forgot(client, email):
    return client.post("/forgot-password", data={"email": email, "csrf_token": csrf(client)})


def set_password(client, token, password="brand-new-pw", confirm=None):
    return client.post(
        "/set-password",
        data={
            "token": token,
            "password": password,
            "confirm": password if confirm is None else confirm,
            "csrf_token": csrf(client),
        },
    )


def can_log_in(email, password) -> bool:
    client = anon()
    resp = client.post(
        "/login", data={"email": email, "password": password, "csrf_token": csrf(client)}
    )
    return resp.status_code == 303


def new_user_form(world, **overrides):
    form = {
        "name": "Nia Newhire",
        "email": "nia@example.com",
        "team_ids": str(world["team_alpha"]),
        "role": "member",
    }
    form.update(overrides)
    return form


# --- the token rules ---


def test_token_is_stored_hashed_and_found_by_the_raw_value(world):
    with SessionLocal() as db:
        user = db.get(User, world["mia"])
        raw = tokens.issue_token(db, user, tokens.RESET)
        db.commit()
        row = db.scalar(select(PasswordToken))
        assert raw not in (row.token_hash, row.purpose)
        assert tokens.find_valid(db, raw).id == row.id
        assert tokens.find_valid(db, raw + "x") is None
        assert tokens.find_valid(db, "") is None


def test_lifetimes_differ_for_welcome_and_reset(world):
    with SessionLocal() as db:
        user = db.get(User, world["mia"])
        tokens.issue_token(db, user, tokens.WELCOME)
        welcome = db.scalar(select(PasswordToken))
        assert welcome.expires_at - datetime.now(timezone.utc) > timedelta(hours=47)
        tokens.issue_token(db, user, tokens.RESET)
        reset = db.scalar(select(PasswordToken))
        assert reset.expires_at - datetime.now(timezone.utc) < timedelta(hours=2)


def test_expired_token_is_not_valid(world):
    with SessionLocal() as db:
        user = db.get(User, world["mia"])
        raw = tokens.issue_token(db, user, tokens.RESET)
        db.scalar(select(PasswordToken)).expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
        assert tokens.find_valid(db, raw) is None


def test_a_new_token_replaces_the_old_one(world):
    with SessionLocal() as db:
        user = db.get(User, world["mia"])
        first = tokens.issue_token(db, user, tokens.RESET)
        second = tokens.issue_token(db, user, tokens.RESET)
        db.commit()
        assert tokens.find_valid(db, first) is None
        assert tokens.find_valid(db, second) is not None


def test_redeeming_sets_the_password_and_uses_the_token_up(world):
    with SessionLocal() as db:
        user = db.get(User, world["mia"])
        raw = tokens.issue_token(db, user, tokens.RESET)
        db.commit()
        tokens.redeem(db, tokens.find_valid(db, raw), "a-fresh-password")
        db.commit()
        assert verify_password("a-fresh-password", db.get(User, world["mia"]).hashed_password)
        assert tokens.find_valid(db, raw) is None


# --- forgot password ---


def test_forgot_password_emails_a_working_link(world, smtp, configured):
    client = anon()
    resp = forgot(client, "mia@example.com")
    assert resp.status_code == 200 and "we have sent it a link" in resp.text
    (msg,) = sent(smtp)
    assert msg["To"] == "mia@example.com"
    assert set_password(client, link_token(msg)).status_code == 303
    assert can_log_in("mia@example.com", "brand-new-pw")


def test_forgot_password_is_case_insensitive(world, smtp, configured):
    forgot(anon(), "  MIA@Example.com ")
    assert len(sent(smtp)) == 1


def test_forgot_password_answers_the_same_for_unknown_addresses(world, smtp, configured):
    known = forgot(anon(), "mia@example.com")
    unknown = forgot(anon(), "nobody@example.com")
    assert (known.status_code, unknown.status_code) == (200, 200)
    strip = lambda html: re.sub(r'name="csrf_token" value="[^"]*"', "", html)  # noqa: E731
    assert strip(known.text) == strip(unknown.text)
    assert [m["To"] for m in sent(smtp)] == ["mia@example.com"]


def test_forgot_password_sends_nothing_when_email_is_off(world, smtp):
    page = anon().get("/forgot-password").text
    assert "not set up to send email" in page
    assert forgot(anon(), "mia@example.com").status_code == 200
    assert sent(smtp) == []


def test_forgot_password_is_throttled_per_address_and_per_client(world, smtp, configured):
    client = anon()
    for _ in range(5):
        forgot(client, "mia@example.com")
    assert len(sent(smtp)) == 3  # the 4th and 5th are quietly dropped, same page
    codes = [forgot(client, f"x{i}@example.com").status_code for i in range(8)]
    assert codes[:4] == [200] * 4 and codes[-1] == 429


def test_forgot_password_form_needs_the_csrf_token(world, configured):
    client = anon()
    resp = client.post("/forgot-password", data={"email": "mia@example.com", "csrf_token": "wrong"})
    assert resp.status_code == 403


# --- the set-password page ---


def test_opening_the_link_does_not_use_it_up(world, smtp, configured):
    forgot(anon(), "mia@example.com")
    token = link_token(sent(smtp)[0])
    client = anon()
    assert client.get(f"/set-password/{token}").status_code == 200
    assert client.get(f"/set-password/{token}").status_code == 200  # e.g. a mail scanner opened it first
    assert set_password(client, token).status_code == 303


def test_a_link_works_only_once(world, smtp, configured):
    forgot(anon(), "mia@example.com")
    token = link_token(sent(smtp)[0])
    client = anon()
    assert set_password(client, token).status_code == 303
    assert set_password(client, token, "another-password").status_code == 400
    assert client.get(f"/set-password/{token}").status_code == 400
    assert not can_log_in("mia@example.com", "another-password")


def test_bad_password_input_keeps_the_link_alive(world, smtp, configured):
    forgot(anon(), "mia@example.com")
    token = link_token(sent(smtp)[0])
    client = anon()
    assert set_password(client, token, "short").status_code == 400
    assert set_password(client, token, "long-enough-pw", confirm="different-pw").status_code == 400
    assert set_password(client, token, "long-enough-pw").status_code == 303


def test_expired_and_made_up_links_are_refused(world, smtp, configured):
    forgot(anon(), "mia@example.com")
    token = link_token(sent(smtp)[0])
    with SessionLocal() as db:
        db.scalar(select(PasswordToken)).expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    client = anon()
    assert client.get(f"/set-password/{token}").status_code == 400
    assert set_password(client, token).status_code == 400
    assert client.get("/set-password/not-a-real-token").status_code == 400
    assert not can_log_in("mia@example.com", "brand-new-pw")


def test_set_password_form_needs_the_csrf_token(world, smtp, configured):
    forgot(anon(), "mia@example.com")
    token = link_token(sent(smtp)[0])
    client = anon()
    resp = client.post(
        "/set-password",
        data={"token": token, "password": "brand-new-pw", "confirm": "brand-new-pw", "csrf_token": "x"},
    )
    assert resp.status_code == 403


def test_login_page_offers_forgot_password_only_when_email_is_on(world, smtp):
    assert "/forgot-password" not in anon().get("/login").text


def test_login_page_links_to_forgot_password(world, smtp, configured):
    assert "/forgot-password" in anon().get("/login").text


def test_login_page_shows_only_known_notices(world):
    client = anon()
    assert "Your password is set" in client.get("/login?notice=password-set").text
    assert "evil" not in client.get("/login?notice=evil").text


# --- welcome emails when an admin adds someone ---


def test_new_user_without_a_password_gets_a_welcome_link(world, login, smtp, configured):
    admin = login("admin")
    assert admin.post("/users", data=new_user_form(world)).status_code == 200
    (msg,) = sent(smtp)
    assert msg["To"] == "nia@example.com"
    body = msg.get_body(("plain",)).get_content()
    assert "Ada Admin" in body and "Nia Newhire" in body
    with SessionLocal() as db:
        assert db.scalar(select(User).where(User.email == "nia@example.com")).hashed_password is None
    assert not can_log_in("nia@example.com", "")
    assert set_password(anon(), link_token(msg)).status_code == 303
    assert can_log_in("nia@example.com", "brand-new-pw")


def test_a_temporary_password_still_works_and_the_email_is_sent_anyway(world, login, smtp, configured):
    resp = login("admin").post("/users", data=new_user_form(world, password="temp-pass-1"))
    assert resp.status_code == 200
    assert len(sent(smtp)) == 1
    assert "temp-pass-1" not in sent(smtp)[0].as_string()
    assert can_log_in("nia@example.com", "temp-pass-1")


def test_without_email_a_password_is_still_required(world, login, smtp):
    admin = login("admin")
    assert admin.post("/users", data=new_user_form(world)).status_code == 422
    assert admin.post("/users", data=new_user_form(world, password="short")).status_code == 422
    assert admin.post("/users", data=new_user_form(world, password="temp-pass-1")).status_code == 200
    assert sent(smtp) == []
    assert can_log_in("nia@example.com", "temp-pass-1")


def test_users_form_says_when_the_password_is_optional(world, login, smtp, configured):
    assert "Temporary password (optional)" in login("admin").get("/users").text


def test_a_team_admin_can_add_someone_and_they_get_the_email(world, login, smtp, configured):
    from sqlalchemy import update

    from app.models import TeamMembership

    with SessionLocal() as db:
        db.execute(
            update(TeamMembership)
            .where(TeamMembership.user_id == world["mia"], TeamMembership.team_id == world["team_bravo"])
            .values(is_team_admin=True)
        )
        db.commit()
    resp = login("mia").post("/users", data=new_user_form(world, team_ids=str(world["team_bravo"])))
    assert resp.status_code == 200
    assert [m["To"] for m in sent(smtp)] == ["nia@example.com"]


def test_resend_welcome_email_is_admin_only_and_replaces_the_old_link(world, login, smtp, configured):
    admin = login("admin")
    admin.post("/users", data=new_user_form(world))
    first = link_token(sent(smtp)[0])
    with SessionLocal() as db:
        nia = db.scalar(select(User).where(User.email == "nia@example.com")).id

    assert login("mia").post(f"/users/{nia}/resend-welcome").status_code == 403
    assert admin.post(f"/users/{nia}/resend-welcome").status_code == 200
    assert len(sent(smtp)) == 2
    second = link_token(sent(smtp)[1])

    client = anon()
    assert client.get(f"/set-password/{first}").status_code == 400
    assert client.get(f"/set-password/{second}").status_code == 200


def test_resend_welcome_stays_inside_the_org(world, login, smtp, configured):
    assert login("admin").post(f"/users/{world['other']}/resend-welcome").status_code == 404
    assert sent(smtp) == []


def test_resend_welcome_when_email_is_off(world, login, smtp):
    resp = login("admin").post(f"/users/{world['mia']}/resend-welcome")
    assert "not configured" in resp.text
    assert sent(smtp) == []


def test_deleting_a_user_removes_their_links(world, login, smtp, configured):
    admin = login("admin")
    admin.post("/users", data=new_user_form(world))
    with SessionLocal() as db:
        nia = db.scalar(select(User).where(User.email == "nia@example.com")).id
        assert db.scalar(select(func.count()).select_from(PasswordToken)) == 1
    assert admin.delete(f"/users/{nia}").status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(PasswordToken)) == 0
