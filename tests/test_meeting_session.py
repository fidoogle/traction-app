"""Running a live meeting from the sidebar (admin only)."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core import meeting_session
from app.db import SessionLocal
from app.models import Meeting, MeetingStatus

T0 = datetime(2026, 10, 12, 15, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def clock(monkeypatch):
    state = {"now": T0}
    monkeypatch.setattr(meeting_session, "now_utc", lambda: state["now"])

    def advance(seconds):
        state["now"] += timedelta(seconds=seconds)

    return advance


@pytest.fixture()
def admin(world, login):
    browser = login("admin")
    browser.switch_team(world["team_alpha"])
    return browser


def navigate_to(response):
    header = response.headers.get("HX-Trigger")
    return json.loads(header)["meetingNavigate"] if header else None


def meeting_of(team_id):
    with SessionLocal() as db:
        meeting = db.scalar(
            select(Meeting).where(Meeting.team_id == team_id, Meeting.started_at.is_not(None))
        )
        db.expunge_all()
        return meeting


def test_meetings_comes_right_after_dashboard_with_a_play_button_for_admins(admin):
    html = admin.get("/").text
    order = [html.index(f'href="{path}"') for path in ("/", "/meetings", "/activity", "/rocks")]
    assert order == sorted(order)
    assert 'class="nav-play"' in html


def test_only_admins_get_the_play_button_and_can_start(world, login, admin):
    for who in ("mia", "vic"):
        other = login(who)
        assert 'class="nav-play"' not in other.get("/").text
        assert other.post("/meetings/session/start").status_code == 403


def test_all_teams_has_no_play_button_and_cannot_start(world, login):
    admin = login("admin")  # starts on All teams
    assert 'class="nav-play"' not in admin.get("/").text
    assert admin.post("/meetings/session/start").status_code == 400


def test_starting_collapses_the_menu_and_starts_segue(admin, clock):
    resp = admin.post("/meetings/session/start")
    assert resp.status_code == 200 and navigate_to(resp) == "/"
    for label in ("Segue", "Rocks", "Scorecard", "Issues", "To-Dos", "Closing", "Stop", "Finish"):
        assert f">{label}" in resp.text or f"<span>{label}</span>" in resp.text
    # The other pages are folded away (closed by default), not gone.
    details = resp.text.index('<details class="nav-more">')
    assert details < resp.text.index('href="/users"')
    assert 'href="/users"' not in resp.text[:details]
    assert 'class="nav-play"' not in resp.text
    # The sidebar on any later page load keeps showing it.
    page = admin.get("/rocks").text
    assert "meeting-panel" in page
    assert page.index('<details class="nav-more">') < page.index('href="/users"')


def test_steps_run_in_order(admin, clock):
    admin.post("/meetings/session/start")
    assert admin.post("/meetings/session/steps/1/toggle").status_code == 409
    assert admin.post("/meetings/session/steps/9/toggle").status_code == 409
    clock(100)
    resp = admin.post("/meetings/session/steps/0/stop")  # done: Rocks starts
    assert navigate_to(resp) == "/rocks"
    assert admin.post("/meetings/session/steps/2/toggle").status_code == 409
    # Going back to the earlier step is fine, and pauses the one that was running.
    clock(30)
    back = admin.post("/meetings/session/steps/0/toggle")
    assert back.status_code == 200 and navigate_to(back) == "/"


def test_pause_resume_and_overtime_are_recorded(world, admin, clock):
    admin.post("/meetings/session/start")
    clock(310)  # Segue: 5:10, over its 5 minutes
    paused = admin.post("/meetings/session/steps/0/toggle")
    assert navigate_to(paused) is None
    clock(600)  # paused time doesn't count
    admin.post("/meetings/session/steps/0/stop")  # advance to Rocks
    clock(120)
    admin.post("/meetings/session/stop")
    clock(900)  # frozen
    assert admin.post("/meetings/session/steps/1/toggle").status_code == 409
    admin.post("/meetings/session/finish")

    meeting = meeting_of(world["team_alpha"])
    assert meeting.status == MeetingStatus.COMPLETED
    assert meeting.step_seconds == [310, 120, 0, 0, 0, 0]
    assert meeting.finished_at is not None and meeting.stopped_at is not None


def test_finish_restores_the_menu_and_the_times_show_on_the_meetings_page(admin, clock):
    admin.post("/meetings/session/start")
    clock(310)
    admin.post("/meetings/session/stop")
    done = admin.post("/meetings/session/finish")
    assert 'href="/users"' in done.text and "nav-more" not in done.text
    assert "meeting-panel" not in done.text
    assert 'class="nav-play"' in done.text
    page = admin.get("/meetings").text
    assert "Segue 5:10" in page and 'class="over"' in page


def test_starting_reuses_the_meeting_scheduled_for_today(world, admin, clock):
    with SessionLocal() as db:
        db.add(Meeting(team_id=world["team_alpha"], scheduled_date=datetime.now().date()))
        db.commit()
    admin.post("/meetings/session/start")
    with SessionLocal() as db:
        meetings = db.scalars(select(Meeting).where(Meeting.team_id == world["team_alpha"])).all()
    started = [m for m in meetings if m.status == MeetingStatus.IN_PROGRESS]
    assert len(started) == 1
    assert len([m for m in meetings if m.scheduled_date == datetime.now().date()]) == 1


def test_the_session_follows_the_team_and_non_admins_never_see_it(world, login, admin, clock):
    admin.post("/meetings/session/start")
    admin.switch_team(world["team_bravo"])
    assert "meeting-panel" not in admin.get("/").text
    admin.switch_team(world["team_alpha"])
    assert "meeting-panel" in admin.get("/").text
    assert "meeting-panel" not in login("mia").get("/").text


def test_timer_bookkeeping_is_not_logged_as_activity(world, admin, clock):
    from app.models import ActivityLog

    admin.post("/meetings/session/start")
    clock(60)
    admin.post("/meetings/session/steps/0/stop")
    admin.post("/meetings/session/stop")
    admin.post("/meetings/session/finish")
    with SessionLocal() as db:
        lines = [
            line
            for entry in db.scalars(select(ActivityLog).where(ActivityLog.entity_type == "meeting"))
            for line in entry.changes
        ]
    assert not any("step" in line.lower() or "running" in line.lower() for line in lines)


def test_stop_can_be_undone_until_finish(world, admin, clock):
    admin.post("/meetings/session/start")
    clock(60)
    admin.post("/meetings/session/steps/0/stop")  # Rocks running
    clock(100)
    stopped = admin.post("/meetings/session/stop")
    assert "<span>Resume</span>" in stopped.text
    clock(500)  # frozen
    assert admin.post("/meetings/session/steps/1/toggle").status_code == 409
    assert admin.post("/meetings/session/stop").status_code == 200  # harmless repeat

    resumed = admin.post("/meetings/session/resume")
    assert navigate_to(resumed) == "/rocks"
    assert "<span>Stop</span>" in resumed.text
    clock(40)
    admin.post("/meetings/session/stop")
    admin.post("/meetings/session/finish")
    meeting = meeting_of(world["team_alpha"])
    assert meeting.step_seconds == [60, 140, 0, 0, 0, 0]
    assert admin.post("/meetings/session/resume").status_code == 409  # nothing running now


def test_resume_while_paused_leaves_the_step_paused(world, admin, clock):
    admin.post("/meetings/session/start")
    clock(30)
    admin.post("/meetings/session/steps/0/toggle")  # pause Segue
    admin.post("/meetings/session/stop")
    clock(100)
    resumed = admin.post("/meetings/session/resume")
    assert navigate_to(resumed) is None
    clock(100)
    admin.post("/meetings/session/stop")
    admin.post("/meetings/session/finish")
    assert meeting_of(world["team_alpha"]).step_seconds[0] == 30


def test_finish_needs_a_stop_first(world, admin, clock):
    started = admin.post("/meetings/session/start")
    assert 'class="meeting-finish"' in started.text
    finish_button = started.text.split('class="meeting-finish"')[1].split(">")[0]
    assert "disabled" in finish_button
    clock(60)
    assert admin.post("/meetings/session/finish").status_code == 409
    stopped = admin.post("/meetings/session/stop")
    assert "disabled" not in stopped.text.split('class="meeting-finish"')[1].split(">")[0]
    assert admin.post("/meetings/session/finish").status_code == 200
    assert meeting_of(world["team_alpha"]).status == MeetingStatus.COMPLETED


def test_admins_can_delete_a_past_meeting_but_not_a_running_one(world, login, admin, clock):
    page = admin.get("/meetings").text
    assert "Status" not in page and "status-select" not in page
    assert f"/meetings/{world['meeting_alpha']}" in page  # the Delete button

    assert login("mia").delete(f"/meetings/{world['meeting_alpha']}").status_code == 403
    assert login("vic").delete(f"/meetings/{world['meeting_alpha']}").status_code == 403
    assert "hx-delete" not in login("mia").get("/meetings").text

    admin.post("/meetings/session/start")
    running = meeting_of(world["team_alpha"])
    assert admin.delete(f"/meetings/{running.id}").status_code == 409

    assert admin.delete(f"/meetings/{world['meeting_alpha']}").status_code == 200
    with SessionLocal() as db:
        assert db.get(Meeting, world["meeting_alpha"]) is None
        assert db.get(Meeting, running.id) is not None


def test_meetings_page_has_a_plus_that_starts_a_meeting(world, login, admin, clock):
    page = admin.get("/meetings").text
    assert "Schedule a meeting" not in page
    header = page.split('class="page-header"')[1].split("</div>")[0]
    assert 'hx-post="/meetings/session/start"' in header and "disabled" not in header
    assert "/meetings/session/start" not in login("mia").get("/meetings").text

    admin.post("/meetings/session/start")
    running = admin.get("/meetings").text.split('class="page-header"')[1].split("</div>")[0]
    assert "disabled" in running and "A meeting is running" in running


def test_plus_asks_all_teams_admins_to_pick_a_team(world, login):
    header = login("admin").get("/meetings").text.split('class="page-header"')[1].split("</div>")[0]
    assert "disabled" in header and "Pick a team first" in header
