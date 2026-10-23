"""To-Do / Rock assignment emails, the daily due-date email and the worker's clock."""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app import worker
from app.core import notifications as n
from app.core.assignment_emails import one_line
from app.core.due_emails import MAX_ITEMS, due_label, send_due_todos
from app.db import SessionLocal
from app.models import NotificationLog, TeamMembership, Todo, TodoStatus, User

TODAY = date(2026, 10, 22)


def sent(smtp):
    return [m for conn in smtp.instances for m in conn.sent]


def text(msg) -> str:
    return msg.get_body(("plain",)).get_content()


def to_list(smtp):
    return [m["To"] for m in sent(smtp)]


@pytest.fixture()
def max_on_alpha(world):
    """Max also joins Alpha, so a To-Do/Rock there can be handed to him."""
    with SessionLocal() as db:
        db.add(TeamMembership(user_id=world["max"], team_id=world["team_alpha"]))
        db.commit()


def todo_form(world, owner="mia", **over):
    form = {"title": "Order the buses", "team_id": str(world["team_alpha"]), "owner_id": str(world[owner])}
    form.update(over)
    return form


def rock_form(world, owner="mia", **over):
    form = {
        "title": "Raise reading scores", "team_id": str(world["team_alpha"]),
        "owner_id": str(world[owner]), "quarter": "2026-Q4",
    }
    form.update(over)
    return form


def add_todo(db, owner_id, team_id, title, due, status=TodoStatus.OPEN):
    db.add(Todo(owner_id=owner_id, team_id=team_id, title=title, due_date=due, status=status))


# --- assignment emails ---


def test_assigning_a_todo_emails_the_new_owner(world, login, smtp, configured):
    assert login("admin").post("/todos", data=todo_form(world, due_date="2026-11-03")).status_code == 200
    (msg,) = sent(smtp)
    assert msg["To"] == "mia@example.com" and msg["Subject"] == "New To-Do: Order the buses"
    body = text(msg)
    assert "Ada Admin" in body and "Order the buses" in body and "Alpha" in body
    assert "Due Tuesday, November 3" in body
    assert "https://traction.district.test/todos" in body


def test_assigning_to_yourself_sends_nothing(world, login, smtp, configured):
    assert login("mia").post("/todos", data=todo_form(world)).status_code == 200
    assert sent(smtp) == []


def test_nothing_is_sent_when_email_is_off(world, login, smtp):
    login("admin").post("/todos", data=todo_form(world))
    login("admin").post("/rocks", data=rock_form(world))
    assert sent(smtp) == []
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(NotificationLog)) == 0


def test_the_owners_choice_and_role_are_respected(world, login, smtp, configured):
    with SessionLocal() as db:
        n.set_preference(db, db.get(User, world["mia"]), "todo_assigned", False)
    admin = login("admin")
    admin.post("/todos", data=todo_form(world))
    admin.post("/todos", data=todo_form(world, owner="vic"))  # a viewer owns nothing by email
    assert sent(smtp) == []


def test_reassigning_a_todo_emails_only_the_new_owner(world, login, smtp, configured, max_on_alpha):
    admin = login("admin")
    admin.post("/todos", data=todo_form(world))
    with SessionLocal() as db:
        todo_id = db.scalar(select(Todo.id).where(Todo.title == "Order the buses"))
    edit = {**todo_form(world, owner="max"), "status": "open"}
    assert admin.put(f"/todos/{todo_id}", data=edit).status_code == 200
    assert to_list(smtp) == ["mia@example.com", "max@example.com"]

    # Editing something else leaves the owner alone, so nobody is emailed again.
    assert admin.put(f"/todos/{todo_id}", data={**edit, "title": "Order more buses"}).status_code == 200
    assert len(sent(smtp)) == 2

    # Handing it back is a new assignment and does email again.
    assert admin.put(f"/todos/{todo_id}", data={**edit, "owner_id": str(world["mia"])}).status_code == 200
    assert to_list(smtp) == ["mia@example.com", "max@example.com", "mia@example.com"]


def test_assigning_a_rock_emails_the_owner(world, login, smtp, configured, max_on_alpha):
    admin = login("admin")
    assert admin.post("/rocks", data=rock_form(world)).status_code == 200
    (msg,) = sent(smtp)
    assert msg["To"] == "mia@example.com" and msg["Subject"] == "New Rock: Raise reading scores"
    assert "2026-Q4" in text(msg) and "Ada Admin" in text(msg)

    with SessionLocal() as db:
        from app.models import Rock

        rock_id = db.scalar(select(Rock.id).where(Rock.title == "Raise reading scores"))
    edit = {**rock_form(world, owner="max"), "status": "on_track"}
    assert admin.put(f"/rocks/{rock_id}", data=edit).status_code == 200
    assert to_list(smtp) == ["mia@example.com", "max@example.com"]
    assert admin.put(f"/rocks/{rock_id}", data={**edit, "title": "Renamed"}).status_code == 200
    assert len(sent(smtp)) == 2


def test_subject_lines_are_one_line():
    assert one_line("  Two\r\nlines\tand   gaps ") == "Two lines and gaps"


# --- the daily due-date email ---


def test_due_email_lists_what_is_due_soon_or_late(world, smtp, configured):
    with SessionLocal() as db:
        alpha, mia = world["team_alpha"], world["mia"]
        add_todo(db, mia, alpha, "Late one", TODAY - timedelta(days=3))
        add_todo(db, mia, alpha, "Today one", TODAY)
        add_todo(db, mia, alpha, "In two days", TODAY + timedelta(days=2))
        add_todo(db, mia, alpha, "In three days", TODAY + timedelta(days=3))
        add_todo(db, mia, alpha, "Already done", TODAY, TodoStatus.DONE)
        add_todo(db, mia, alpha, "Dropped", TODAY, TodoStatus.DROPPED)
        add_todo(db, mia, alpha, "No date", None)
        add_todo(db, world["max"], world["team_charlie"], "Max tomorrow", TODAY + timedelta(days=1))
        db.commit()
        assert send_due_todos(db, TODAY) == 2

    by_to = {m["To"]: m for m in sent(smtp)}
    mia_mail = by_to["mia@example.com"]
    assert mia_mail["Subject"] == "3 To-Dos due soon or overdue"
    body = text(mia_mail)
    assert "overdue by 3 days" in body and "due today" in body and "Late one" in body
    assert "In two days" in body
    for left_out in ("In three days", "Already done", "Dropped", "No date"):
        assert left_out not in body
    assert body.index("Late one") < body.index("Today one") < body.index("In two days")
    assert by_to["max@example.com"]["Subject"] == "1 To-Do due soon or overdue"
    assert "due tomorrow" in text(by_to["max@example.com"])


def test_due_email_goes_out_once_a_day(world, smtp, configured):
    with SessionLocal() as db:
        add_todo(db, world["mia"], world["team_alpha"], "Late one", TODAY - timedelta(days=1))
        db.commit()
        assert send_due_todos(db, TODAY) == 1
        assert send_due_todos(db, TODAY) == 0
        assert send_due_todos(db, TODAY + timedelta(days=1)) == 1  # still late tomorrow: a new day
    assert len(sent(smtp)) == 2


def test_due_email_respects_choices_and_empty_lists(world, smtp, configured):
    with SessionLocal() as db:
        assert send_due_todos(db, TODAY) == 0  # nothing due: no email at all
        add_todo(db, world["mia"], world["team_alpha"], "Late one", TODAY - timedelta(days=1))
        db.commit()
        n.set_preference(db, db.get(User, world["mia"]), "todo_due", False)
        assert send_due_todos(db, TODAY) == 0
    assert sent(smtp) == []


def test_due_email_does_nothing_when_email_is_off(world, smtp):
    with SessionLocal() as db:
        add_todo(db, world["mia"], world["team_alpha"], "Late one", TODAY - timedelta(days=1))
        db.commit()
        assert send_due_todos(db, TODAY) == 0
    assert sent(smtp) == []


def test_a_long_list_is_cut_off_with_a_count(world, smtp, configured):
    with SessionLocal() as db:
        for i in range(MAX_ITEMS + 2):
            add_todo(db, world["mia"], world["team_alpha"], f"Task {i:02d}", TODAY)
        db.commit()
        send_due_todos(db, TODAY)
    (msg,) = sent(smtp)
    assert msg["Subject"] == f"{MAX_ITEMS + 2} To-Dos due soon or overdue"
    assert "...and 2 more." in text(msg) and f"Task {MAX_ITEMS:02d}" not in text(msg)


def test_due_labels():
    assert due_label(TODAY - timedelta(days=1), TODAY) == "overdue by 1 day"
    assert due_label(TODAY, TODAY) == "due today"
    assert due_label(TODAY + timedelta(days=1), TODAY) == "due tomorrow"
    assert due_label(date(2026, 10, 24), TODAY) == "due Saturday, October 24"


# --- the worker's clock (US Central: UTC-5 until early November, then UTC-6) ---


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


@pytest.fixture()
def late_todo(world):
    with SessionLocal() as db:
        add_todo(db, world["mia"], world["team_alpha"], "Late one", date(2026, 10, 1))
        add_todo(db, world["mia"], world["team_alpha"], "Late in Nov", date(2026, 11, 1))
        db.commit()


def test_the_worker_waits_until_7am_local_then_sends_once(world, smtp, configured, late_todo, no_digest):
    state = worker.WorkerState()
    worker.tick(state, utc(2026, 10, 22, 11, 59))  # 6:59 CDT
    assert sent(smtp) == [] and not state.todo_due_dates
    worker.tick(state, utc(2026, 10, 22, 12, 0))  # 7:00 CDT
    assert len(sent(smtp)) == 1 and set(state.todo_due_dates.values()) == {date(2026, 10, 22)}
    worker.tick(state, utc(2026, 10, 22, 12, 1))
    worker.tick(state, utc(2026, 10, 22, 23, 0))
    assert len(sent(smtp)) == 1


def test_the_worker_follows_daylight_saving(world, smtp, configured, late_todo, no_digest):
    state = worker.WorkerState()
    worker.tick(state, utc(2026, 11, 10, 12, 0))  # 6:00 CST: not yet
    assert sent(smtp) == []
    worker.tick(state, utc(2026, 11, 10, 13, 0))  # 7:00 CST
    assert len(sent(smtp)) == 1


def test_a_restarted_worker_does_not_resend(world, smtp, configured, late_todo, no_digest):
    worker.tick(worker.WorkerState(), utc(2026, 10, 22, 15, 0))
    worker.tick(worker.WorkerState(), utc(2026, 10, 22, 16, 0))  # a fresh process, same day
    assert len(sent(smtp)) == 1


def test_the_worker_idles_when_email_is_off(world, smtp, late_todo):
    state = worker.WorkerState()
    worker.tick(state, utc(2026, 10, 22, 15, 0))
    assert sent(smtp) == [] and not state.todo_due_dates


def test_a_failed_job_is_retried_on_the_next_tick(world, smtp, configured, monkeypatch):
    calls = []

    def boom(db, today, org_id=None):
        calls.append(today)
        raise RuntimeError("database hiccup")

    monkeypatch.setattr(worker, "send_due_todos", boom)
    state = worker.WorkerState()
    worker.tick(state, utc(2026, 10, 22, 15, 0))
    worker.tick(state, utc(2026, 10, 22, 15, 1))
    assert len(calls) == 4 and not state.todo_due_dates  # two organizations x two ticks
