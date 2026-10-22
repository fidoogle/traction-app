"""The notification catalog, people's preferences, notify()'s send-once log,
and the "My notifications" page."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, update

from app.config import settings
from app.core import notifications as n
from app.db import SessionLocal
from app.models import (
    NotificationLog,
    NotificationPreference,
    TeamMembership,
    User,
)


def sent(smtp):
    return [m for conn in smtp.instances for m in conn.sent]


def keys_for(db, user_id):
    return {nt.key: on for nt, on in n.types_for(db, db.get(User, user_id))}


def make_team_admin(world, user="mia", team="bravo"):
    with SessionLocal() as db:
        db.execute(
            update(TeamMembership)
            .where(TeamMembership.user_id == world[user], TeamMembership.team_id == world[f"team_{team}"])
            .values(is_team_admin=True)
        )
        db.commit()


def send(db, user_id, key="todo_assigned", **kw):
    kw.setdefault("subject_line", "Hello")
    kw.setdefault("template", "test")
    return n.notify(db, db.get(User, user_id), key, **kw)


# --- the catalog (no database) ---


def test_catalog_is_consistent():
    keys = [t.key for t in n.CATALOG]
    assert len(keys) == len(set(keys))
    for nt in n.CATALOG:
        assert nt.default_on <= nt.audience, nt.key
        assert nt.audience, nt.key
        assert nt.label and nt.description and nt.group
        assert len(nt.key) <= 50
    assert {t.key for t in n.CATALOG if t.always} == {"account_welcome", "password_reset"}


def test_defaults_follow_the_hats():
    todo = n.BY_KEY["todo_assigned"]
    assert n.default_for(todo, {n.MEMBER}) and not n.eligible(todo, {n.VIEWER})
    digest = n.BY_KEY["weekly_digest"]
    assert all(n.default_for(digest, {hat}) for hat in n.EVERYONE)
    off_track = n.BY_KEY["rock_off_track"]
    assert n.default_for(off_track, {n.MEMBER, n.TEAM_ADMIN})
    assert not n.default_for(off_track, {n.ADMIN})  # eligible, but not switched on
    assert n.eligible(off_track, {n.ADMIN}) and not n.eligible(off_track, {n.MEMBER})
    assert not n.default_for(n.BY_KEY["issue_added"], {n.MEMBER})


# --- who gets what (needs the test database) ---


def test_hats(world):
    with SessionLocal() as db:
        assert n.hats(db, db.get(User, world["vic"])) == {"viewer"}
        assert n.hats(db, db.get(User, world["admin"])) == {"admin"}
        assert n.hats(db, db.get(User, world["mia"])) == {"member"}
    make_team_admin(world)
    with SessionLocal() as db:
        assert n.hats(db, db.get(User, world["mia"])) == {"member", "team_admin"}


def test_each_role_gets_its_own_list_and_defaults(world):
    make_team_admin(world, "mia", "bravo")
    with SessionLocal() as db:
        vic, max_, mia, admin = (keys_for(db, world[k]) for k in ("vic", "max", "mia", "admin"))
    assert "todo_assigned" not in vic and vic["weekly_digest"] and vic["meeting_invite"]
    assert max_["todo_assigned"] and max_["weekly_digest"] and not max_["issue_added"]
    assert "rock_off_track" not in max_ and "admin_system" not in max_
    assert mia["rock_off_track"] is True and mia["quarter_reminder"] is True
    assert admin["admin_system"] is False and admin["rock_off_track"] is False
    assert admin["account_welcome"] and vic["password_reset"]


def test_own_choice_overrides_the_default_and_matching_the_default_is_not_stored(world):
    with SessionLocal() as db:
        user = db.get(User, world["max"])
        n.set_preference(db, user, "todo_assigned", False)
        assert keys_for(db, world["max"])["todo_assigned"] is False
        assert not n.is_enabled(db, user, "todo_assigned")
        assert db.scalar(select(func.count()).select_from(NotificationPreference)) == 1

        n.set_preference(db, user, "issue_added", True)
        assert n.is_enabled(db, user, "issue_added")

        n.set_preference(db, user, "todo_assigned", True)  # back to the default
        n.set_preference(db, user, "issue_added", False)
        assert db.scalar(select(func.count()).select_from(NotificationPreference)) == 0


def test_other_peoples_choices_are_separate(world):
    with SessionLocal() as db:
        n.set_preference(db, db.get(User, world["max"]), "weekly_digest", False)
        assert keys_for(db, world["mia"])["weekly_digest"] is True


@pytest.mark.parametrize(
    "who, key",
    [("vic", "todo_assigned"), ("max", "rock_off_track"), ("mia", "account_welcome"), ("mia", "nope")],
)
def test_cannot_set_what_you_cannot_receive_or_turn_off(world, who, key):
    with SessionLocal() as db, pytest.raises(ValueError):
        n.set_preference(db, db.get(User, world[who]), key, False)


# --- notify() ---


def test_notify_does_nothing_when_email_is_off(world, smtp):
    with SessionLocal() as db:
        result = send(db, world["max"])
        assert (result.status, db.scalar(select(func.count()).select_from(NotificationLog))) == ("skipped", 0)
    assert sent(smtp) == []


def test_notify_sends_once_and_records_it(world, smtp, configured):
    with SessionLocal() as db:
        assert send(db, world["max"]).sent
        again = send(db, world["max"])
        assert again.status == "skipped" and "already" in again.detail
        row = db.scalar(select(NotificationLog))
        assert (row.key, row.status, row.error) == ("todo_assigned", "sent", None)
    (msg,) = sent(smtp)
    assert msg["To"] == "max@example.com" and msg["Subject"] == "Hello"
    body = msg.get_body(("html",)).get_content()
    assert "https://traction.district.test/notifications" in body  # the "choose which emails" link


def test_a_different_subject_or_period_is_a_new_occasion(world, smtp, configured):
    with SessionLocal() as db:
        assert send(db, world["max"], subject="todo:1").sent
        assert send(db, world["max"], subject="todo:2").sent
        assert send(db, world["max"], subject="todo:1", period="v2").sent
        assert send(db, world["max"], subject="todo:1").status == "skipped"
        assert send(db, world["mia"], subject="todo:1").sent  # a different person
    assert len(sent(smtp)) == 4


def test_notify_respects_role_and_the_recipients_choice(world, smtp, configured):
    with SessionLocal() as db:
        assert send(db, world["vic"], "todo_assigned").detail == "not available for this role"
        n.set_preference(db, db.get(User, world["max"]), "todo_assigned", False)
        assert send(db, world["max"], "todo_assigned").detail == "turned off by the recipient"
        assert send(db, world["max"], "issue_added").status == "skipped"  # off by default
        n.set_preference(db, db.get(User, world["max"]), "issue_added", True)
        assert send(db, world["max"], "issue_added").sent
        assert send(db, world["vic"], "account_welcome").sent  # always sent
    assert len(sent(smtp)) == 2


def test_a_failed_send_is_recorded_and_can_be_retried(world, smtp, configured):
    smtp.fail_connect = True
    with SessionLocal() as db:
        result = send(db, world["max"])
        assert result.status == "failed" and "relay down" in result.detail
        assert db.scalar(select(NotificationLog)).status == "failed"
        smtp.fail_connect = False
        assert send(db, world["max"]).sent
        assert db.scalar(select(func.count()).select_from(NotificationLog)) == 1
        assert db.scalar(select(NotificationLog)).status == "sent"
        assert db.scalar(select(NotificationLog)).error is None


def test_a_missing_template_fails_cleanly(world, smtp, configured):
    with SessionLocal() as db:
        result = send(db, world["max"], template="no_such_template")
        assert result.status == "failed"
        assert db.scalar(select(NotificationLog)).status == "failed"
    assert sent(smtp) == []


def test_an_inflight_claim_blocks_but_an_abandoned_one_is_retried(world, smtp, configured):
    with SessionLocal() as db:
        db.add(NotificationLog(user_id=world["max"], key="todo_assigned", status="pending"))
        db.commit()
        assert send(db, world["max"]).status == "skipped"
        db.scalar(select(NotificationLog)).created_at = datetime.now(timezone.utc) - timedelta(minutes=11)
        db.commit()
        assert send(db, world["max"]).sent
    assert len(sent(smtp)) == 1


def test_old_log_rows_are_pruned(world, monkeypatch):
    monkeypatch.setattr(settings, "notification_log_retention_days", 30)
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        db.add_all(
            [
                NotificationLog(user_id=world["max"], key="a", status="sent", created_at=now - timedelta(days=31)),
                NotificationLog(user_id=world["max"], key="b", status="sent", created_at=now - timedelta(days=29)),
            ]
        )
        db.commit()
        assert n.prune_log(db) == 1
        assert db.scalar(select(NotificationLog.key)) == "b"


def test_deleting_a_user_removes_their_preferences_and_log(world, login, smtp, configured):
    admin = login("admin")
    form = {
        "name": "Temp Person", "email": "temp@example.com", "password": "longenough",
        "role": "member", "team_ids": str(world["team_charlie"]),
    }
    assert admin.post("/users", data=form).status_code == 200
    with SessionLocal() as db:
        temp = db.scalar(select(User).where(User.email == "temp@example.com")).id
        n.set_preference(db, db.get(User, temp), "todo_assigned", False)
        send(db, temp, "weekly_digest")
        assert db.scalar(select(func.count()).select_from(NotificationLog)) == 1
    assert admin.delete(f"/users/{temp}").status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(NotificationPreference)) == 0
        assert db.scalar(select(func.count()).select_from(NotificationLog)) == 0


# --- the page ---


def test_page_lists_what_applies_to_the_role(world, login):
    vic = login("vic").get("/notifications").text
    assert "Weekly summary" in vic and "Meeting scheduled or changed" in vic
    assert "A To-Do is assigned to you" not in vic and "System notices" not in vic
    admin = login("admin").get("/notifications").text
    assert "System notices" in admin and "A To-Do is assigned to you" in admin
    assert "Always sent" in admin


def test_page_reflects_saved_choices(world, login):
    max_ = login("max")
    assert max_.post("/notifications/todo_assigned", data={}).status_code == 200
    page = max_.get("/notifications").text
    row = page[page.index("/notifications/todo_assigned") - 200 : page.index("/notifications/todo_assigned")]
    assert "checked" not in row
    assert max_.post("/notifications/issue_added", data={"enabled": "1"}).status_code == 200
    page = max_.get("/notifications").text
    row = page[page.index("/notifications/issue_added") - 200 : page.index("/notifications/issue_added")]
    assert "checked" in row


def test_page_cannot_change_what_you_cannot_receive(world, login):
    assert login("vic").post("/notifications/todo_assigned", data={"enabled": "1"}).status_code == 404
    assert login("max").post("/notifications/rock_off_track", data={}).status_code == 404
    assert login("max").post("/notifications/account_welcome", data={}).status_code == 404
    assert login("max").post("/notifications/nonsense", data={}).status_code == 404


def test_page_has_no_email_warning_when_email_is_on(world, login, configured):
    assert "isn't set up to send email" not in login("max").get("/notifications").text


def test_page_says_when_email_is_not_set_up(world, login):
    assert "isn't set up to send email" in login("max").get("/notifications").text


def test_page_needs_a_login(world):
    from fastapi.testclient import TestClient

    from app.main import app

    assert TestClient(app, follow_redirects=False).get("/notifications").status_code == 303
