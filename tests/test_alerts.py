"""The optional team alerts: Rocks going off track, repeated scorecard misses,
new issues, meeting recaps, quarter reminders and system notices."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app import worker
from app.core import notifications as n
from app.core.alert_emails import announce_new_issues
from app.db import SessionLocal
from app.models import Issue, Rock, RockStatus, TeamMembership, User


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
