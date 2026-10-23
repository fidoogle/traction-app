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
