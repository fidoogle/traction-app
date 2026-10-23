"""The optional team alerts: Rocks going off track, repeated scorecard misses,
new issues, meeting recaps, quarter reminders and system notices."""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app import worker
from app.core import meeting_session
from app.core import notifications as n
from app.core.alert_emails import announce_new_issues, due_quarter_events, quarter_bounds, send_quarter_reminders
from app.db import SessionLocal
from app.models import Issue, Rock, RockStatus, TeamMembership, Todo, TodoStatus, User


def sent(smtp):
    return [m for conn in smtp.instances for m in conn.sent]


def recipients(smtp):
    return sorted(m["To"] for m in sent(smtp))


def text(msg) -> str:
    return msg.get_body(("plain",)).get_content()


def make_team_admin(world, user="mia", team="alpha"):
    with SessionLocal() as db:
        db.execute(
            update(TeamMembership)
            .where(TeamMembership.user_id == world[user], TeamMembership.team_id == world[f"team_{team}"])
            .values(is_team_admin=True)
        )
        db.commit()


def opt_in(world, who, key, on=True):
    with SessionLocal() as db:
        n.set_preference(db, db.get(User, world[who]), key, on)


# --- a Rock goes off track ---


def set_status(browser, world, status, team="alpha"):
    return browser.patch(f"/rocks/{world[f'rock_{team}']}/status", data={"status": status})


def test_team_admins_hear_when_a_rock_goes_off_track(world, login, smtp, configured):
    make_team_admin(world, "mia", "alpha")
    assert set_status(login("admin"), world, "off_track").status_code == 200
    (msg,) = sent(smtp)
    assert msg["To"] == "mia@example.com" and msg["Subject"] == "Rock off track: alpha rock"
    body = text(msg)
    assert "Ada Admin" in body and "alpha rock" in body and "Alpha" in body and "Owner: Mia Member" in body
    assert "https://traction.district.test/rocks" in body


def test_the_person_who_made_the_change_is_not_emailed(world, login, smtp, configured):
    make_team_admin(world, "mia", "alpha")
    assert set_status(login("mia"), world, "off_track").status_code == 200
    assert sent(smtp) == []


def test_ordinary_members_viewers_and_other_teams_admins_are_not_emailed(world, login, smtp, configured):
    make_team_admin(world, "mia", "bravo")  # Mia administers Bravo, not Alpha
    set_status(login("admin"), world, "off_track")
    assert sent(smtp) == []  # the owner (a plain member) and the viewer hear nothing either


def test_org_admins_can_opt_in_to_hear_about_every_team(world, login, smtp, configured):
    make_team_admin(world, "mia", "alpha")
    opt_in(world, "admin", "rock_off_track")
    set_status(login("mia"), world, "off_track")  # a team admin changes it; the org admin opted in
    assert recipients(smtp) == ["admin@example.com"]


def test_people_can_turn_it_off(world, login, smtp, configured):
    make_team_admin(world, "mia", "alpha")
    opt_in(world, "mia", "rock_off_track", False)
    set_status(login("admin"), world, "off_track")
    assert sent(smtp) == []


def test_only_going_off_track_counts(world, login, smtp, configured):
    make_team_admin(world, "mia", "alpha")
    admin = login("admin")
    set_status(admin, world, "done")
    set_status(admin, world, "on_track")
    assert sent(smtp) == []
    set_status(admin, world, "off_track")
    assert len(sent(smtp)) == 1
    set_status(admin, world, "off_track")  # already off track
    assert len(sent(smtp)) == 1
    set_status(admin, world, "on_track")
    set_status(admin, world, "off_track")  # slips again: a new alert
    assert len(sent(smtp)) == 2


def test_editing_a_rock_that_goes_off_track_alerts_too(world, login, smtp, configured):
    make_team_admin(world, "mia", "alpha")
    form = {
        "team_id": str(world["team_alpha"]), "owner_id": str(world["mia"]),
        "title": "alpha rock", "quarter": "2026-Q4", "status": "off_track",
    }
    admin = login("admin")
    assert admin.put(f"/rocks/{world['rock_alpha']}", data=form).status_code == 200
    assert recipients(smtp) == ["mia@example.com"]
    assert admin.put(f"/rocks/{world['rock_alpha']}", data={**form, "title": "Renamed"}).status_code == 200
    assert len(sent(smtp)) == 1  # still off track: nothing new


def test_a_new_rock_that_starts_off_track_alerts(world, login, smtp, configured):
    make_team_admin(world, "mia", "alpha")
    form = {
        "team_id": str(world["team_alpha"]), "owner_id": str(world["mia"]), "title": "Shaky start",
        "quarter": "2026-Q4", "status": "off_track",
    }
    assert login("admin").post("/rocks", data=form).status_code == 200
    # Mia is also the new Rock's owner, so she gets that email as well as the alert.
    subjects = sorted(m["Subject"] for m in sent(smtp))
    assert subjects == ["New Rock: Shaky start", "Rock off track: Shaky start"]


def test_no_alert_when_email_is_off(world, login, smtp):
    make_team_admin(world, "mia", "alpha")
    set_status(login("admin"), world, "off_track")
    assert sent(smtp) == []
    with SessionLocal() as db:
        assert db.get(Rock, world["rock_alpha"]).status == RockStatus.OFF_TRACK


# --- a scorecard number keeps missing its goal ---
# Alpha's seeded number has a goal of "at least 1", and week 1 already holds a result of 2.


def put_result(browser, world, week, value, team="alpha"):
    return browser.put(
        f"/scorecards/{world[f'card_{team}']}/measurables/{world[f'measurable_{team}']}/weeks/{week}",
        data={"value": value},
    )


def test_two_misses_in_a_row_tell_the_owner_and_opted_in_admins(world, login, smtp, configured):
    opt_in(world, "mia", "scorecard_missed")      # the owner
    opt_in(world, "admin", "scorecard_missed")    # an org admin, opted in
    admin = login("admin")
    put_result(admin, world, 1, "0")              # replaces the seeded 2: a first miss
    assert sent(smtp) == []
    assert put_result(admin, world, 2, "0").status_code == 200   # second in a row
    assert recipients(smtp) == ["mia@example.com"]  # the admin made the change, so is not told
    msg = sent(smtp)[0]
    assert msg["Subject"] == "Scorecard: alpha m missed goal 2 weeks in a row"
    body = text(msg)
    assert "alpha m on Alpha" in body and "goal (\u2265 1)" in body.replace("goal (≥ 1)", "goal (\u2265 1)")
    assert "Week of Oct 5: 0" in body and "Week of Oct 12: 0" in body and "Owner: Mia Member" in body


def test_the_owner_entering_their_own_numbers_tells_the_opted_in_admin(world, login, smtp, configured):
    opt_in(world, "mia", "scorecard_missed")
    opt_in(world, "admin", "scorecard_missed")
    mia = login("mia")
    put_result(mia, world, 1, "0")
    put_result(mia, world, 2, "0")
    assert recipients(smtp) == ["admin@example.com"]  # not Mia: she just typed it


def test_it_is_off_unless_someone_opts_in(world, login, smtp, configured):
    admin = login("admin")
    put_result(admin, world, 1, "0")
    put_result(admin, world, 2, "0")
    assert sent(smtp) == []


def test_a_met_goal_or_a_gap_breaks_the_run(world, login, smtp, configured):
    opt_in(world, "mia", "scorecard_missed")
    admin = login("admin")
    put_result(admin, world, 1, "0")
    put_result(admin, world, 2, "5")   # met: the run is broken
    put_result(admin, world, 3, "0")
    assert sent(smtp) == []
    put_result(admin, world, 5, "0")   # week 4 is blank: not "in a row"
    assert sent(smtp) == []


def test_a_longer_run_says_so_and_each_week_is_told_once(world, login, smtp, configured):
    opt_in(world, "mia", "scorecard_missed")
    admin = login("admin")
    for week in (1, 2, 3):
        put_result(admin, world, week, "0")
    put_result(admin, world, 3, "0.5")   # edited again, still the same week: not a second email
    assert [m["Subject"] for m in sent(smtp)] == [
        "Scorecard: alpha m missed goal 2 weeks in a row",
        "Scorecard: alpha m missed goal 3 weeks in a row",
    ]


def test_clearing_a_cell_or_a_bad_value_alerts_nobody(world, login, smtp, configured):
    opt_in(world, "mia", "scorecard_missed")
    admin = login("admin")
    put_result(admin, world, 1, "0")
    put_result(admin, world, 2, "")
    put_result(admin, world, 2, "not a number")
    assert sent(smtp) == []


def test_no_scorecard_email_when_email_is_off(world, login, smtp):
    opt_in(world, "mia", "scorecard_missed")
    admin = login("admin")
    put_result(admin, world, 1, "0")
    put_result(admin, world, 2, "0")
    assert sent(smtp) == []


# --- new issues, grouped ---

NOW = datetime(2026, 10, 22, 15, 0, tzinfo=timezone.utc)


def settle_existing_issues(db):
    """The seeded issues were 'added' when the test world was built; mark them announced."""
    db.execute(update(Issue).values(announced_at=NOW))
    db.commit()


def add_issue(db, world, title, minutes_ago, team="alpha"):
    issue = Issue(team_id=world[f"team_{team}"], title=title, created_at=NOW - timedelta(minutes=minutes_ago))
    db.add(issue)
    db.commit()
    return issue.id


def test_a_new_issue_is_announced_after_a_quiet_spell(world, smtp, configured):
    opt_in(world, "mia", "issue_added")
    with SessionLocal() as db:
        settle_existing_issues(db)
        add_issue(db, world, "Bus route 12 is late", minutes_ago=4)
        assert announce_new_issues(db, NOW) == 0                       # only 4 minutes: more may be coming
        assert announce_new_issues(db, NOW + timedelta(minutes=1)) == 1  # 5 minutes of quiet
        assert announce_new_issues(db, NOW + timedelta(minutes=2)) == 0  # not announced twice
    (msg,) = sent(smtp)
    assert msg["To"] == "mia@example.com" and msg["Subject"] == "Alpha: new issue: Bus route 12 is late"
    assert "A new issue was added to the Alpha list" in text(msg)
    assert "https://traction.district.test/issues" in text(msg)


def test_issues_added_together_are_one_email(world, smtp, configured):
    opt_in(world, "mia", "issue_added")
    opt_in(world, "vic", "issue_added")
    with SessionLocal() as db:
        settle_existing_issues(db)
        for i, minutes in enumerate((9, 8, 6)):
            add_issue(db, world, f"Issue {i}", minutes_ago=minutes)
        assert announce_new_issues(db, NOW) == 2   # one email each for Mia and Vic, not six
    assert recipients(smtp) == ["mia@example.com", "vic@example.com"]
    msg = sent(smtp)[0]
    assert msg["Subject"] == "Alpha: 3 new issues"
    assert all(f"Issue {i}" in text(msg) for i in range(3))


def test_a_steady_stream_is_not_held_back_forever(world, smtp, configured):
    opt_in(world, "mia", "issue_added")
    with SessionLocal() as db:
        settle_existing_issues(db)
        add_issue(db, world, "First", minutes_ago=16)
        add_issue(db, world, "Latest", minutes_ago=1)   # still arriving, but the first has waited 16 minutes
        assert announce_new_issues(db, NOW) == 1
    assert "2 new issues" in sent(smtp)[0]["Subject"]


def test_a_long_list_is_cut_off_with_a_count(world, smtp, configured):
    opt_in(world, "mia", "issue_added")
    with SessionLocal() as db:
        settle_existing_issues(db)
        for i in range(13):
            add_issue(db, world, f"Item {i:02d}", minutes_ago=10)
        announce_new_issues(db, NOW)
    body = text(sent(smtp)[0])
    assert "...and 3 more." in body and "Item 09" in body and "Item 10" not in body


def test_each_team_gets_its_own_email(world, smtp, configured):
    opt_in(world, "mia", "issue_added")  # Mia is on Alpha and Bravo
    with SessionLocal() as db:
        settle_existing_issues(db)
        add_issue(db, world, "Alpha thing", minutes_ago=10, team="alpha")
        add_issue(db, world, "Bravo thing", minutes_ago=10, team="bravo")
        announce_new_issues(db, NOW)
    subjects = sorted(m["Subject"] for m in sent(smtp))
    assert subjects == ["Alpha: new issue: Alpha thing", "Bravo: new issue: Bravo thing"]


def test_people_who_have_not_opted_in_hear_nothing_and_it_is_not_saved_up(world, smtp, configured):
    with SessionLocal() as db:
        settle_existing_issues(db)
        add_issue(db, world, "Quiet one", minutes_ago=10)
        assert announce_new_issues(db, NOW) == 0
    opt_in(world, "mia", "issue_added")   # opting in later does not bring back the old announcement
    with SessionLocal() as db:
        assert announce_new_issues(db, NOW + timedelta(minutes=30)) == 0
    assert sent(smtp) == []


def test_issues_from_long_ago_are_never_announced(world, smtp, configured):
    opt_in(world, "mia", "issue_added")
    with SessionLocal() as db:
        settle_existing_issues(db)
        old = add_issue(db, world, "Added last week", minutes_ago=60 * 24 * 7)
        assert announce_new_issues(db, NOW) == 0
        assert db.get(Issue, old).announced_at is not None
    assert sent(smtp) == []


def test_nothing_happens_and_nothing_is_marked_when_email_is_off(world, smtp):
    with SessionLocal() as db:
        settle_existing_issues(db)
        issue = add_issue(db, world, "Waiting", minutes_ago=10)
        assert announce_new_issues(db, NOW) == 0
        assert db.get(Issue, issue).announced_at is None


def test_an_issue_added_in_the_app_is_announced_later(world, login, smtp, configured):
    opt_in(world, "mia", "issue_added")
    with SessionLocal() as db:
        settle_existing_issues(db)
    resp = login("admin").post("/issues", data={"team_id": str(world["team_alpha"]), "title": "Heater broken", "priority": "1"})
    assert resp.status_code == 200
    with SessionLocal() as db:
        issue = db.scalar(select(Issue).where(Issue.title == "Heater broken"))
        assert issue.created_at is not None and issue.announced_at is None
        assert announce_new_issues(db, datetime.now(timezone.utc)) == 0
        assert announce_new_issues(db, datetime.now(timezone.utc) + timedelta(minutes=6)) == 1
    assert sent(smtp)[0]["Subject"] == "Alpha: new issue: Heater broken"


def test_the_worker_announces_issues_on_its_tick(world, smtp, configured, no_digest):
    opt_in(world, "mia", "issue_added")
    with SessionLocal() as db:
        settle_existing_issues(db)
        add_issue(db, world, "From the worker", minutes_ago=10)
    worker.tick(worker.WorkerState(), NOW)
    assert recipients(smtp) == ["mia@example.com"]


# --- the meeting recap ---

T0 = datetime(2026, 10, 12, 15, 0, 0, tzinfo=timezone.utc)  # when the test meeting starts


@pytest.fixture()
def clock(monkeypatch):
    state = {"now": T0}
    monkeypatch.setattr(meeting_session, "now_utc", lambda: state["now"])

    def advance(seconds):
        state["now"] += timedelta(seconds=seconds)

    return advance


def run_meeting(world, login, clock, seconds=310):
    admin = login("admin")
    admin.switch_team(world["team_alpha"])
    admin.post("/meetings/session/start")
    clock(seconds)
    admin.post("/meetings/session/stop")
    return admin


def add_todo(db, world, title, created_at, owner="mia", status=TodoStatus.OPEN, due=None):
    db.add(Todo(team_id=world["team_alpha"], owner_id=world[owner], title=title, created_at=created_at,
                status=status, due_date=due))


def test_finishing_a_meeting_sends_a_recap_to_opted_in_team_members(world, login, smtp, configured, clock):
    opt_in(world, "mia", "meeting_summary")
    opt_in(world, "max", "meeting_summary")   # Max is on Charlie, not Alpha
    with SessionLocal() as db:
        add_todo(db, world, "Before the meeting", T0 - timedelta(hours=1))
        add_todo(db, world, "Order buses", T0 + timedelta(minutes=2), owner="vic")
        add_todo(db, world, "Call the vendor", T0 + timedelta(minutes=4))
        add_todo(db, world, "Dropped idea", T0 + timedelta(minutes=3), status=TodoStatus.DROPPED)
        add_todo(db, world, "Next week's thing", T0 + timedelta(days=3))
        db.commit()
    admin = run_meeting(world, login, clock)
    assert sent(smtp) == []                       # stopping is not finishing
    assert admin.post("/meetings/session/finish").status_code == 200

    (msg,) = sent(smtp)
    assert msg["To"] == "mia@example.com"
    assert msg["Subject"].startswith("Alpha meeting recap, ")
    body = text(msg)
    assert "It ran 5:10 in all" in body and "Segue: 5:10 (over its time)" in body
    assert "Order buses (Vic Viewer)" in body and "Call the vendor (Mia Member)" in body
    for left_out in ("Before the meeting", "Dropped idea", "Next week's thing"):
        assert left_out not in body
    assert "ISSUES STILL OPEN (1)" in body and "alpha issue" in body
    assert "https://traction.district.test/meetings" in body


def test_a_recap_with_nothing_new_says_so(world, login, smtp, configured, clock):
    opt_in(world, "vic", "meeting_summary")
    with SessionLocal() as db:
        db.execute(update(Issue).values(status="resolved"))
        db.commit()
    run_meeting(world, login, clock).post("/meetings/session/finish")
    body = text(sent(smtp)[0])
    assert "No new To-Dos were added during the meeting." in body and "No issues are left open." in body


def test_no_recap_unless_opted_in_or_when_email_is_off(world, login, smtp, configured, clock):
    run_meeting(world, login, clock).post("/meetings/session/finish")
    assert sent(smtp) == []


def test_no_recap_when_email_is_off(world, login, smtp, clock):
    opt_in(world, "mia", "meeting_summary")
    run_meeting(world, login, clock).post("/meetings/session/finish")
    assert sent(smtp) == []


# --- quarter reminders ---


def test_quarter_bounds():
    assert quarter_bounds(date(2026, 2, 14)) == (date(2026, 1, 1), date(2026, 3, 31))
    assert quarter_bounds(date(2026, 4, 1)) == (date(2026, 4, 1), date(2026, 6, 30))
    assert quarter_bounds(date(2026, 9, 30)) == (date(2026, 7, 1), date(2026, 9, 30))
    assert quarter_bounds(date(2026, 12, 31)) == (date(2026, 10, 1), date(2026, 12, 31))


def test_reminders_are_due_at_the_start_and_two_weeks_before_the_end():
    assert due_quarter_events(date(2026, 10, 1)) == [("start", "2026-Q4", date(2026, 10, 1))]
    assert due_quarter_events(date(2026, 10, 7)) == [("start", "2026-Q4", date(2026, 10, 1))]  # a week's grace
    assert due_quarter_events(date(2026, 10, 8)) == []
    assert due_quarter_events(date(2026, 12, 16)) == []
    assert due_quarter_events(date(2026, 12, 17)) == [("end", "2026-Q4", date(2026, 12, 17))]
    assert due_quarter_events(date(2026, 12, 23)) == [("end", "2026-Q4", date(2026, 12, 17))]
    assert due_quarter_events(date(2026, 12, 24)) == []
    assert due_quarter_events(date(2027, 1, 2)) == [("start", "2027-Q1", date(2027, 1, 1))]
    assert due_quarter_events(date(2026, 3, 17)) == [("end", "2026-Q1", date(2026, 3, 17))]


def org_of(world):
    with SessionLocal() as db:
        return db.get(User, world["admin"]).org_id


def test_team_admins_hear_when_a_quarter_begins(world, smtp, configured):
    make_team_admin(world, "mia", "alpha")
    with SessionLocal() as db:
        assert send_quarter_reminders(db, org_of(world), date(2026, 10, 2)) == 1
    (msg,) = sent(smtp)
    assert msg["To"] == "mia@example.com"
    assert msg["Subject"] == "2026-Q4 has begun: set Rocks for Alpha"
    assert "1 Rock is set so far" in text(msg)  # the seeded 2026-Q4 rock


def test_team_admins_hear_two_weeks_before_the_quarter_ends(world, smtp, configured):
    make_team_admin(world, "mia", "alpha")
    with SessionLocal() as db:
        assert send_quarter_reminders(db, org_of(world), date(2026, 12, 18)) == 1
    msg = sent(smtp)[0]
    assert msg["Subject"] == "2026-Q4 ends December 31: review Alpha's Rocks"
    body = text(msg)
    assert "0 of 1 Rock done so far" in body and "alpha rock" in body


def test_each_reminder_is_sent_once_per_quarter(world, smtp, configured):
    make_team_admin(world, "mia", "alpha")
    with SessionLocal() as db:
        org = org_of(world)
        assert send_quarter_reminders(db, org, date(2026, 10, 1)) == 1
        assert send_quarter_reminders(db, org, date(2026, 10, 1)) == 0
        assert send_quarter_reminders(db, org, date(2026, 10, 4)) == 0
        assert send_quarter_reminders(db, org, date(2026, 12, 17)) == 1   # the end-of-quarter one
        assert send_quarter_reminders(db, org, date(2027, 1, 1)) == 1     # and the next quarter's start
        assert send_quarter_reminders(db, org, date(2026, 11, 15)) == 0   # nothing due mid-quarter


def test_only_the_teams_own_admins_hear_and_org_admins_must_opt_in(world, smtp, configured):
    make_team_admin(world, "mia", "bravo")
    with SessionLocal() as db:
        send_quarter_reminders(db, org_of(world), date(2026, 10, 1))
    assert [m["Subject"] for m in sent(smtp)] == ["2026-Q4 has begun: set Rocks for Bravo"]  # not Alpha or Charlie
    smtp.instances.clear()
    opt_in(world, "admin", "quarter_reminder")
    with SessionLocal() as db:
        send_quarter_reminders(db, org_of(world), date(2027, 1, 1))
    admin_subjects = [m["Subject"] for m in sent(smtp) if m["To"] == "admin@example.com"]
    assert len(admin_subjects) == 3   # an opted-in org admin hears for each of the district's three teams


def test_people_can_turn_quarter_reminders_off(world, smtp, configured):
    make_team_admin(world, "mia", "alpha")
    opt_in(world, "mia", "quarter_reminder", False)
    with SessionLocal() as db:
        assert send_quarter_reminders(db, org_of(world), date(2026, 10, 1)) == 0
    assert sent(smtp) == []


def test_quarter_reminders_do_nothing_when_email_is_off(world, smtp):
    make_team_admin(world, "mia", "alpha")
    with SessionLocal() as db:
        assert send_quarter_reminders(db, org_of(world), date(2026, 10, 1)) == 0
    assert sent(smtp) == []


def test_the_worker_sends_them_from_7am_local_on_the_day(world, smtp, configured, no_digest):
    make_team_admin(world, "mia", "alpha")
    state = worker.WorkerState()
    worker.tick(state, datetime(2026, 10, 1, 11, 59, tzinfo=timezone.utc))  # 6:59 CDT
    assert sent(smtp) == []
    worker.tick(state, datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc))   # 7:00 CDT
    assert recipients(smtp) == ["mia@example.com"]
    worker.tick(state, datetime(2026, 10, 1, 18, 0, tzinfo=timezone.utc))
    worker.tick(worker.WorkerState(), datetime(2026, 10, 1, 20, 0, tzinfo=timezone.utc))  # even after a restart
    assert len(sent(smtp)) == 1
