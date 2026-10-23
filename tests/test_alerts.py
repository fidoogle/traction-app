"""The optional team alerts: Rocks going off track, repeated scorecard misses,
new issues, meeting recaps, quarter reminders and system notices."""

from sqlalchemy import update

from app.core import notifications as n
from app.db import SessionLocal
from app.models import Rock, RockStatus, TeamMembership, User


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
