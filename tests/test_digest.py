"""The weekly summary email: what each role gets, the once-a-week rule, the
admin's schedule, and the worker."""

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select, update

from app import worker
from app.core import notifications as n
from app.core.digest import build_digest, current_quarter, week_key
from app.core.digest_emails import digest_due, scheduled_moment, send_digest_now, send_digests
from app.db import SessionLocal
from app.models import (
    Measurable,
    NotificationLog,
    Organization,
    Rock,
    RockStatus,
    ScorecardEntry,
    TeamMembership,
    Todo,
    TodoStatus,
    User,
)

TODAY = date(2026, 10, 22)  # a Thursday, in 2026-Q4; the seeded scorecards started 2026-10-05, so this is week 3


def sent(smtp):
    return [m for conn in smtp.instances for m in conn.sent]


def recipients(smtp):
    return sorted(m["To"] for m in sent(smtp))


def text(msg) -> str:
    return msg.get_body(("plain",)).get_content()


def digest_for(world, who, today=TODAY):
    with SessionLocal() as db:
        return build_digest(db, db.get(User, world[who]), today)


def make_team_admin(world, user="mia", team="bravo"):
    with SessionLocal() as db:
        db.execute(
            update(TeamMembership)
            .where(TeamMembership.user_id == world[user], TeamMembership.team_id == world[f"team_{team}"])
            .values(is_team_admin=True)
        )
        db.commit()


def set_rock(world, team="alpha", **values):
    with SessionLocal() as db:
        db.execute(update(Rock).where(Rock.id == world[f"rock_{team}"]).values(**values))
        db.commit()


def set_result(world, team, week, actual):
    """Record a result for the team's seeded measurable (goal: at least 1)."""
    with SessionLocal() as db:
        existing = db.scalar(
            select(ScorecardEntry).where(
                ScorecardEntry.measurable_id == world[f"measurable_{team}"], ScorecardEntry.week_number == week
            )
        )
        if existing:
            existing.actual_value = actual
        else:
            db.add(ScorecardEntry(measurable_id=world[f"measurable_{team}"], week_number=week, actual_value=actual))
        db.commit()


def set_org(world, **values):
    with SessionLocal() as db:
        db.execute(update(Organization).where(Organization.id == db.get(User, world["admin"]).org_id).values(**values))
        db.commit()


# --- what each role gets ---


def test_a_member_gets_what_they_own_and_no_team_totals(world):
    digest = digest_for(world, "mia")
    assert sorted(t["team"] for t in digest.todos) == ["Alpha", "Bravo"]  # her To-Do on each team
    assert all(t["when"] == "no due date" for t in digest.todos)
    assert digest.rocks == [] and digest.off_goal == [] and digest.teams == []
    assert not digest.is_empty


def test_a_viewer_gets_a_read_only_summary_of_their_team(world):
    digest = digest_for(world, "vic")
    assert digest.todos == [] and digest.rocks == [] and digest.off_goal == []
    (alpha,) = digest.teams
    assert (alpha.name, alpha.rocks_total, alpha.open_todos, alpha.open_issues) == ("Alpha", 1, 1, 1)
    assert alpha.rocks_off_track == [] and alpha.overdue_todos == 0


def test_a_team_admin_gets_what_they_own_plus_totals_for_the_teams_they_administer(world):
    make_team_admin(world, "mia", "bravo")
    digest = digest_for(world, "mia")
    assert len(digest.todos) == 2
    assert [t.name for t in digest.teams] == ["Bravo"]  # not Alpha, where she is only a member


def test_an_admin_gets_what_they_own_and_nothing_else(world):
    digest = digest_for(world, "admin")  # owns nothing in the seeded content
    assert digest.is_empty and digest.teams == []


def test_someone_on_no_team_gets_nothing(world):
    with SessionLocal() as db:
        db.execute(TeamMembership.__table__.delete().where(TeamMembership.user_id == world["max"]))
        db.commit()
    assert digest_for(world, "max").is_empty


def test_rocks_off_track_this_quarter_only(world):
    set_rock(world, "alpha", status=RockStatus.OFF_TRACK)
    set_rock(world, "bravo", status=RockStatus.OFF_TRACK, quarter="2026-Q3")  # last quarter: ignored
    mia = digest_for(world, "mia")
    assert mia.rocks == [{"title": "alpha rock", "team": "Alpha"}]
    vic = digest_for(world, "vic")
    assert vic.teams[0].rocks_off_track == ["alpha rock"] and vic.teams[0].rocks_total == 1
    assert current_quarter(date(2026, 1, 1)) == "2026-Q1" and current_quarter(date(2026, 12, 31)) == "2026-Q4"


def test_done_rocks_are_counted_but_not_flagged(world):
    set_rock(world, "alpha", status=RockStatus.DONE)
    team = digest_for(world, "vic").teams[0]
    assert (team.rocks_total, team.rocks_done, team.rocks_off_track) == (1, 1, [])
    assert digest_for(world, "mia").rocks == []


def test_only_open_todos_count_and_overdue_ones_are_marked(world):
    with SessionLocal() as db:
        alpha, mia = world["team_alpha"], world["mia"]
        db.add_all(
            [
                Todo(team_id=alpha, owner_id=mia, title="Late", due_date=TODAY - timedelta(days=2)),
                Todo(team_id=alpha, owner_id=mia, title="Soon", due_date=TODAY + timedelta(days=1)),
                Todo(team_id=alpha, owner_id=mia, title="Finished", status=TodoStatus.DONE),
                Todo(team_id=alpha, owner_id=mia, title="Dropped", status=TodoStatus.DROPPED),
            ]
        )
        db.commit()
    todos = digest_for(world, "mia").todos
    titles = [t["title"] for t in todos]
    assert titles[:2] == ["Late", "Soon"]  # dated ones first, soonest first
    assert "Finished" not in titles and "Dropped" not in titles
    assert todos[0]["overdue"] and todos[0]["when"] == "overdue by 2 days" and not todos[1]["overdue"]
    alpha_summary = digest_for(world, "vic").teams[0]
    assert alpha_summary.open_todos == 3 and alpha_summary.overdue_todos == 1


def test_a_long_to_do_list_is_cut_off_with_a_count(world):
    with SessionLocal() as db:
        db.add_all([Todo(team_id=world["team_alpha"], owner_id=world["mia"], title=f"T{i:02d}") for i in range(15)])
        db.commit()
    digest = digest_for(world, "mia")
    assert len(digest.todos) == 10 and digest.todos_more == 7  # 17 open in all


def test_scorecard_numbers_below_goal_use_the_latest_recent_result(world):
    set_result(world, "alpha", 3, 0)  # this week: below the goal of 1
    mia = digest_for(world, "mia")
    assert mia.off_goal == [{"name": "alpha m", "actual": "0", "goal": "≥ 1"}]
    team = digest_for(world, "vic").teams[0]
    assert (team.measured, team.off_goal) == (1, ["alpha m"])

    set_result(world, "alpha", 3, 5)  # now met
    assert digest_for(world, "mia").off_goal == []
    assert digest_for(world, "vic").teams[0].off_goal == []
    assert digest_for(world, "vic").teams[0].measured == 1


def test_last_weeks_result_counts_but_an_old_one_does_not(world):
    set_result(world, "alpha", 2, 0)  # last week
    assert len(digest_for(world, "mia").off_goal) == 1
    with SessionLocal() as db:
        db.execute(ScorecardEntry.__table__.delete())
        db.commit()
    set_result(world, "alpha", 1, 0)  # three weeks ago: stale, ignored
    assert digest_for(world, "mia").off_goal == [] and digest_for(world, "vic").teams[0].measured == 0


def test_scorecards_outside_their_dates_are_ignored(world):
    set_result(world, "alpha", 3, 0)
    assert digest_for(world, "mia", date(2027, 6, 1)).off_goal == []  # long after the 13 weeks
    assert digest_for(world, "mia", date(2026, 9, 1)).off_goal == []  # before it starts


def test_a_measurable_nobody_owns_still_shows_in_the_team_summary(world):
    set_result(world, "alpha", 3, 0)
    with SessionLocal() as db:
        db.execute(update(Measurable).where(Measurable.id == world["measurable_alpha"]).values(owner_id=None))
        db.commit()
    assert digest_for(world, "mia").off_goal == []
    assert digest_for(world, "vic").teams[0].off_goal == ["alpha m"]


def test_week_labels_follow_iso_weeks():
    assert week_key(date(2026, 10, 26)) == "2026-W44"
    assert week_key(date(2026, 11, 1)) == "2026-W44"  # Sunday ends the same week
    assert week_key(date(2027, 1, 1)) == "2026-W53"  # the year boundary belongs to the old year's week


# --- sending ---


def test_everyone_with_something_to_say_gets_one(world, smtp, configured):
    with SessionLocal() as db:
        assert send_digests(db, db.get(User, world["admin"]).org_id, TODAY, "2026-W43") == 3
    assert recipients(smtp) == ["max@example.com", "mia@example.com", "vic@example.com"]  # not the admin: nothing to report
    mia = next(m for m in sent(smtp) if m["To"] == "mia@example.com")
    assert mia["Subject"] == "Your weekly summary, week of Oct 19"
    body = text(mia)
    assert "YOUR OPEN TO-DOS" in body and "alpha todo" in body and "bravo todo" in body
    vic = text(next(m for m in sent(smtp) if m["To"] == "vic@example.com"))
    assert "ALPHA" in vic and "Rocks this quarter: 1" in vic and "YOUR OPEN TO-DOS" not in vic
    assert "https://traction.district.test" in mia.get_body(("html",)).get_content()


def test_a_week_is_sent_only_once_however_often_it_runs(world, smtp, configured):
    with SessionLocal() as db:
        org = db.get(User, world["admin"]).org_id
        assert send_digests(db, org, TODAY, "2026-W43") == 3
        assert send_digests(db, org, TODAY, "2026-W43") == 0
        assert send_digests(db, org, TODAY + timedelta(days=1), "2026-W43") == 0
        assert send_digests(db, org, TODAY + timedelta(days=7), "2026-W44") == 3
    assert len(sent(smtp)) == 6


def test_people_can_opt_out_and_other_organizations_are_left_alone(world, smtp, configured):
    with SessionLocal() as db:
        n.set_preference(db, db.get(User, world["vic"]), "weekly_digest", False)
        org = db.get(User, world["admin"]).org_id
        send_digests(db, org, TODAY, "2026-W43")
    assert recipients(smtp) == ["max@example.com", "mia@example.com"]  # not vic (opted out), not the other district


def test_nothing_is_sent_when_there_is_nothing_to_report(world, smtp, configured):
    with SessionLocal() as db:
        db.execute(Todo.__table__.update().values(status=TodoStatus.DONE))
        db.execute(Rock.__table__.update().values(quarter="2025-Q1"))
        db.execute(ScorecardEntry.__table__.delete())
        db.execute(update(Measurable).values(owner_id=None))
        from app.models import Issue, IssueStatus

        db.execute(Issue.__table__.update().values(status=IssueStatus.RESOLVED))
        db.commit()
        assert send_digests(db, db.get(User, world["admin"]).org_id, TODAY, "2026-W43") == 0
    assert sent(smtp) == []


def test_nothing_is_sent_when_email_is_off(world, smtp):
    with SessionLocal() as db:
        assert send_digests(db, db.get(User, world["admin"]).org_id, TODAY, "2026-W43") == 0
    assert sent(smtp) == []


def test_user_text_cannot_inject_markup_into_the_html(world, smtp, configured):
    with SessionLocal() as db:
        db.add(Todo(team_id=world["team_alpha"], owner_id=world["mia"], title="<script>alert(1)</script>"))
        db.commit()
        send_digests(db, db.get(User, world["admin"]).org_id, TODAY, "2026-W43")
    html = next(m for m in sent(smtp) if m["To"] == "mia@example.com").get_body(("html",)).get_content()
    assert "<script>" not in html and "&lt;script&gt;" in html


# --- when it is due ---

CENTRAL_MONDAY_7AM = {"digest_weekday": 0, "digest_time": time(7, 0)}


def org_with(world, **values):
    if values:
        set_org(world, **values)
    with SessionLocal() as db:
        return db.get(Organization, db.get(User, world["admin"]).org_id)


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_default_schedule_is_monday_at_7_by_the_organizations_clock(world):
    org = org_with(world)
    assert (org.digest_weekday, org.digest_time) == (0, time(7, 0))
    assert digest_due(org, utc(2026, 10, 26, 11, 59)) == (False, "2026-W44")  # 6:59 CDT
    assert digest_due(org, utc(2026, 10, 26, 12, 0)) == (True, "2026-W44")    # 7:00 CDT
    assert digest_due(org, utc(2026, 10, 28, 3, 0)) == (True, "2026-W44")     # still this week's, on Tuesday evening
    # Sunday evening is still the previous week (W43), whose Monday moment has long passed.
    assert digest_due(org, utc(2026, 10, 25, 20, 0)) == (True, "2026-W43")
    # A new week starts at local midnight Monday: 11:00Z is still Sunday night in Chicago (CDT).
    assert digest_due(org, utc(2026, 10, 26, 4, 59)) == (True, "2026-W43")
    assert digest_due(org, utc(2026, 10, 26, 5, 0)) == (False, "2026-W44")


def test_a_time_zone_change_moves_the_moment(world):
    org = org_with(world, timezone="America/Los_Angeles")
    assert digest_due(org, utc(2026, 10, 26, 13, 59))[0] is False  # 6:59 PDT
    assert digest_due(org, utc(2026, 10, 26, 14, 0))[0] is True


def test_daylight_saving_week_boundaries(world):
    org = org_with(world)
    moment, label = scheduled_moment(org, utc(2026, 11, 2, 20, 0))  # the Monday after clocks fell back
    assert (moment, label) == (utc(2026, 11, 2, 13, 0), "2026-W45")  # 7:00 CST is 13:00Z, not 12:00Z
    moment, _ = scheduled_moment(org, utc(2026, 3, 9, 20, 0))  # the Monday after they sprang forward
    assert moment == utc(2026, 3, 9, 12, 0)  # 7:00 CDT


def test_a_sunday_schedule_belongs_to_the_end_of_its_week(world):
    org = org_with(world, digest_weekday=6, digest_time=time(18, 0))
    assert digest_due(org, utc(2026, 10, 26, 15, 0)) == (False, "2026-W44")  # Monday: the week has only begun
    assert digest_due(org, utc(2026, 11, 1, 23, 59)) == (False, "2026-W44")  # Sunday 5:59 PM CST... not yet 6:00 PM
    assert digest_due(org, utc(2026, 11, 2, 0, 0)) == (True, "2026-W44")     # Sunday 6:00 PM CST


def test_a_changed_schedule_is_honoured(world):
    org = org_with(world, digest_weekday=2, digest_time=time(9, 30))
    assert digest_due(org, utc(2026, 10, 26, 15, 0))[0] is False  # Monday: not yet
    assert digest_due(org, utc(2026, 10, 28, 14, 29))[0] is False
    assert digest_due(org, utc(2026, 10, 28, 14, 30))[0] is True  # Wednesday 9:30 CDT


# --- the worker ---


def test_the_worker_sends_once_the_moment_has_passed_and_not_again(world, smtp, configured):
    state = worker.WorkerState()
    worker.tick(state, utc(2026, 10, 26, 11, 59))
    assert sent(smtp) == []
    worker.tick(state, utc(2026, 10, 26, 12, 0))
    first = len(sent(smtp))
    assert first >= 3 and state.digest_weeks  # at least mia, max and vic
    worker.tick(state, utc(2026, 10, 26, 12, 1))
    worker.tick(state, utc(2026, 10, 27, 12, 0))
    assert len(sent(smtp)) == first


def test_a_worker_that_was_down_still_sends_that_week_and_a_restart_does_not_repeat_it(world, smtp, configured):
    worker.tick(worker.WorkerState(), utc(2026, 10, 28, 18, 0))  # Wednesday: well after Monday 7:00
    first = len(sent(smtp))
    assert first >= 3
    worker.tick(worker.WorkerState(), utc(2026, 10, 28, 19, 0))  # a fresh process
    assert len(sent(smtp)) == first


def test_the_next_week_sends_again(world, smtp, configured):
    state = worker.WorkerState()
    worker.tick(state, utc(2026, 10, 26, 12, 0))
    first = len(sent(smtp))
    worker.tick(state, utc(2026, 11, 2, 13, 0))
    assert len(sent(smtp)) > first


def test_moving_the_schedule_later_after_it_was_sent_does_not_send_twice(world, smtp, configured):
    state = worker.WorkerState()
    worker.tick(state, utc(2026, 10, 26, 12, 0))
    first = len(sent(smtp))
    set_org(world, digest_weekday=4, digest_time=time(8, 0))  # now Friday
    worker.tick(state, utc(2026, 10, 30, 14, 0))
    assert len(sent(smtp)) == first
    worker.tick(worker.WorkerState(), utc(2026, 10, 30, 14, 0))  # even from a fresh process
    assert len(sent(smtp)) == first


def test_moving_the_schedule_earlier_than_now_sends_on_the_next_tick(world, smtp, configured):
    state = worker.WorkerState()
    set_org(world, digest_weekday=4, digest_time=time(8, 0))  # Friday
    worker.tick(state, utc(2026, 10, 26, 15, 0))  # Monday: not yet
    assert not {"mia@example.com", "max@example.com", "vic@example.com"} & set(recipients(smtp))
    set_org(world, digest_weekday=0, digest_time=time(7, 0))  # admin moves it to Monday morning
    worker.tick(state, utc(2026, 10, 26, 15, 1))
    assert {"mia@example.com", "max@example.com", "vic@example.com"} <= set(recipients(smtp))


def test_one_organizations_clock_does_not_hold_up_another(world, smtp, configured):
    with SessionLocal() as db:
        other_org = db.get(User, world["other"]).org_id
        db.execute(update(Organization).where(Organization.id == other_org).values(timezone="Pacific/Auckland"))
        db.commit()
    state = worker.WorkerState()
    state.digest_weeks[world["org"]] = "2026-W43"  # Chicago's last week is done
    worker.tick(state, utc(2026, 10, 25, 19, 0))  # Monday 8:00 AM in Auckland, still Sunday afternoon in Chicago
    assert set(recipients(smtp)) == {"other@example.com"}
    assert state.digest_weeks[world["org2"]] == "2026-W44" and state.digest_weeks[world["org"]] == "2026-W43"


# --- the admin's settings ---


def test_an_admin_can_set_the_day_and_time(world, login):
    admin = login("admin")
    assert admin.post("/settings/digest", data={"weekday": "4", "at": "16:45"}).status_code == 200
    with SessionLocal() as db:
        org = db.get(Organization, db.get(User, world["admin"]).org_id)
        assert (org.digest_weekday, org.digest_time) == (4, time(16, 45))
    page = admin.get("/settings").text
    assert 'value="16:45"' in page and "Friday" in page


def test_the_settings_page_shows_the_default(world, login):
    page = login("admin").get("/settings").text
    assert "Weekly summary email" in page and 'value="07:00"' in page


def test_bad_schedules_are_refused(world, login):
    admin = login("admin")
    for bad in ({"weekday": "7", "at": "07:00"}, {"weekday": "-1", "at": "07:00"}, {"weekday": "0", "at": "07:10"},
                {"weekday": "x", "at": "07:00"}, {"weekday": "0", "at": "7pm"}):
        assert admin.post("/settings/digest", data=bad).status_code == 422, bad
    with SessionLocal() as db:
        org = db.get(Organization, db.get(User, world["admin"]).org_id)
        assert (org.digest_weekday, org.digest_time) == (0, time(7, 0))


def test_only_admins_set_the_schedule_or_send_it_now(world, login):
    for who in ("mia", "vic"):
        assert login(who).post("/settings/digest", data={"weekday": "2", "at": "08:00"}).status_code == 403
        assert login(who).post("/settings/digest/send-now").status_code == 403


def test_the_schedule_belongs_to_each_organization(world, login):
    login("other").post("/settings/digest", data={"weekday": "3", "at": "10:00"})
    with SessionLocal() as db:
        assert db.get(Organization, db.get(User, world["admin"]).org_id).digest_weekday == 0
        assert db.get(Organization, db.get(User, world["other"]).org_id).digest_weekday == 3


def test_send_now_counts_as_this_weeks_summary(world, login, smtp, configured):
    resp = login("admin").post("/settings/digest/send-now")
    assert resp.status_code == 200 and "Sending" in resp.text
    first = len(sent(smtp))
    assert first >= 3
    send_digest_now(db_org(world))  # pressing it again, or the schedule arriving, sends nothing more
    assert len(sent(smtp)) == first
    with SessionLocal() as db:
        labels = set(db.scalars(select(NotificationLog.period).where(NotificationLog.key == "weekly_digest")))
    assert len(labels) == 1


def db_org(world):
    with SessionLocal() as db:
        return db.get(User, world["admin"]).org_id


def test_send_now_when_email_is_off(world, login, smtp):
    resp = login("admin").post("/settings/digest/send-now")
    assert "not configured" in resp.text and sent(smtp) == []
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(NotificationLog)) == 0
