"""A team admin has admin rights on their one team and a member's on the rest.

Mia is a member of Alpha and Bravo; here she is made team admin of Bravo.
"""

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import TeamMembership


@pytest.fixture()
def mia_admin_of_bravo(world, login):
    with SessionLocal() as db:
        m = db.scalar(
            select(TeamMembership).where(
                TeamMembership.user_id == world["mia"],
                TeamMembership.team_id == world["team_bravo"],
            )
        )
        m.is_team_admin = True
        db.commit()
    return login("mia")


def _rock_form(world, team, owner="mia"):
    return {
        "team_id": str(world[f"team_{team}"]),
        "owner_id": str(world[owner]),
        "title": "New rock",
        "quarter": "2026-Q4",
    }


def test_team_admin_manages_rocks_on_their_team_only(world, mia_admin_of_bravo):
    mia = mia_admin_of_bravo
    assert mia.post("/rocks", data=_rock_form(world, "bravo")).status_code == 200
    assert mia.post("/rocks", data=_rock_form(world, "alpha")).status_code == 403
    assert mia.get(f"/rocks/{world['rock_bravo']}/edit").status_code == 200
    assert mia.get(f"/rocks/{world['rock_alpha']}/edit").status_code == 403
    assert mia.patch(f"/rocks/{world['rock_bravo']}/status", data={"status": "done"}).status_code == 200
    assert mia.patch(f"/rocks/{world['rock_alpha']}/status", data={"status": "done"}).status_code == 403
    assert mia.delete(f"/rocks/{world['rock_alpha']}").status_code == 403
    assert mia.delete(f"/rocks/{world['rock_bravo']}").status_code == 200


def test_team_admin_cannot_move_a_rock_to_a_team_they_dont_admin(world, mia_admin_of_bravo):
    resp = mia_admin_of_bravo.put(
        f"/rocks/{world['rock_bravo']}",
        data={**_rock_form(world, "alpha"), "status": "on_track"},
    )
    assert resp.status_code == 403


def test_team_admin_rock_buttons_only_on_their_team(world, mia_admin_of_bravo):
    mia = mia_admin_of_bravo
    mia.switch_team(world["team_alpha"])
    html = mia.get("/rocks").text
    assert "alpha rock" in html  # listed...
    assert f"/rocks/{world['rock_alpha']}/edit" not in html  # ...but no admin controls
    assert "add-rock-modal" in html  # the + is there: she can add on Bravo
    mia.switch_team(world["team_bravo"])
    assert f"/rocks/{world['rock_bravo']}/edit" in mia.get("/rocks").text


def test_team_admin_issues_and_todos(world, mia_admin_of_bravo):
    mia = mia_admin_of_bravo
    assert mia.get(f"/issues/{world['issue_bravo']}/edit").status_code == 200
    assert mia.get(f"/issues/{world['issue_alpha']}/edit").status_code == 403
    assert mia.delete(f"/issues/{world['issue_alpha']}").status_code == 403
    assert mia.get(f"/todos/{world['todo_bravo']}/edit").status_code == 200
    assert mia.get(f"/todos/{world['todo_alpha']}/edit").status_code == 403
    assert mia.delete(f"/todos/{world['todo_alpha']}").status_code == 403
    assert mia.delete(f"/todos/{world['todo_bravo']}").status_code == 200


def test_team_admin_scorecards(world, mia_admin_of_bravo):
    mia = mia_admin_of_bravo
    card = {"name": "Q1", "start_date": "2026-10-05"}
    assert mia.post("/scorecards", data={**card, "team_id": str(world["team_bravo"])}).status_code == 200
    assert mia.post("/scorecards", data={**card, "team_id": str(world["team_alpha"])}).status_code == 403
    assert mia.get(f"/scorecards/{world['card_bravo']}/measurables/{world['measurable_bravo']}/edit").status_code == 200
    assert mia.get(f"/scorecards/{world['card_alpha']}/measurables/{world['measurable_alpha']}/edit").status_code == 403
    assert mia.delete(f"/scorecards/{world['card_alpha']}").status_code == 403
    assert mia.delete(f"/scorecards/{world['card_bravo']}").status_code == 200


def test_team_admin_can_fill_a_cell_they_do_not_own(world, login, mia_admin_of_bravo):
    from app.models import Measurable

    with SessionLocal() as db:  # Bravo's row loses its owner
        db.get(Measurable, world["measurable_bravo"]).owner_id = None
        db.commit()
    url = f"/scorecards/{world['card_bravo']}/measurables/{world['measurable_bravo']}/weeks/2"
    assert mia_admin_of_bravo.put(url, data={"value": "5"}).status_code == 200
    # A plain member who isn't the owner can't.
    assert login("max").put(url, data={"value": "5"}).status_code == 404


def test_plain_member_still_has_no_admin_rights(world, login):
    mia = login("mia")
    assert mia.get(f"/rocks/{world['rock_bravo']}/edit").status_code == 403
    assert mia.delete(f"/issues/{world['issue_bravo']}").status_code == 403


def test_team_admin_runs_meetings_for_their_team_only(world, mia_admin_of_bravo):
    mia = mia_admin_of_bravo
    mia.switch_team(world["team_alpha"])
    assert 'class="nav-play"' not in mia.get("/").text
    assert mia.post("/meetings/session/start").status_code == 403

    mia.switch_team(world["team_bravo"])
    assert 'class="nav-play"' in mia.get("/").text
    assert mia.post("/meetings/session/start").status_code == 200
    assert "meeting-panel" in mia.get("/").text
    assert mia.post("/meetings/session/steps/0/stop").status_code == 200
    assert mia.post("/meetings/session/stop").status_code == 200
    assert mia.post("/meetings/session/finish").status_code == 200


def test_team_admin_deletes_only_their_teams_meetings(world, mia_admin_of_bravo):
    mia = mia_admin_of_bravo
    assert mia.delete(f"/meetings/{world['meeting_alpha']}").status_code == 403
    assert mia.delete(f"/meetings/{world['meeting_bravo']}").status_code == 200


def test_plain_member_cannot_start_a_meeting(world, login):
    mia = login("mia")
    mia.switch_team(world["team_bravo"])
    assert mia.post("/meetings/session/start").status_code == 403


# --- Teams page: roster and the team-admin toggle -----------------------------


def _is_team_admin(user, team):
    with SessionLocal() as db:
        return db.scalar(
            select(TeamMembership.is_team_admin).where(
                TeamMembership.user_id == user, TeamMembership.team_id == team
            )
        )


def test_admin_can_make_and_unmake_a_team_admin(world, login):
    admin = login("admin")
    url = f"/teams/{world['team_bravo']}/members/{world['mia']}/admin"
    assert admin.patch(url, data={"is_team_admin": "true"}).status_code == 200
    assert _is_team_admin(world["mia"], world["team_bravo"])
    assert admin.patch(url, data={"is_team_admin": "false"}).status_code == 200
    assert not _is_team_admin(world["mia"], world["team_bravo"])


def test_team_admin_flag_rules(world, login):
    admin = login("admin")
    flag = {"is_team_admin": "true"}
    on = lambda team, who: f"/teams/{world['team_' + team]}/members/{world[who]}/admin"  # noqa: E731
    assert admin.patch(on("alpha", "mia"), data=flag).status_code == 200
    # Only one team each.
    assert admin.patch(on("bravo", "mia"), data=flag).status_code == 409
    # Only members, and only of teams they're on.
    assert admin.patch(on("alpha", "vic"), data=flag).status_code == 400
    assert admin.patch(on("alpha", "admin"), data=flag).status_code == 400
    assert admin.patch(on("bravo", "max"), data=flag).status_code == 404
    # Only an admin can hand it out - not a team admin, not a member.
    assert login("mia").patch(on("alpha", "mia"), data={"is_team_admin": "false"}).status_code == 403
    assert login("max").patch(on("charlie", "max"), data=flag).status_code == 403


def test_team_admin_manages_their_roster(world, mia_admin_of_bravo):
    mia = mia_admin_of_bravo
    members = f"/teams/{world['team_bravo']}/members"
    assert mia.post(members, data={"user_id": str(world["max"])}).status_code == 200
    assert mia.delete(f"{members}/{world['max']}").status_code == 200
    # Not another team's roster.
    assert mia.post(f"/teams/{world['team_alpha']}/members", data={"user_id": str(world["max"])}).status_code == 403
    assert mia.delete(f"/teams/{world['team_alpha']}/members/{world['vic']}").status_code == 403
    # Can't create or delete teams.
    assert mia.post("/teams", data={"name": "New"}).status_code == 403
    assert mia.delete(f"/teams/{world['team_bravo']}").status_code == 403


def test_team_admin_cannot_remove_themselves_a_peer_or_an_admin(world, login, mia_admin_of_bravo):
    mia = mia_admin_of_bravo
    admin = login("admin")
    members = f"/teams/{world['team_bravo']}/members"
    assert admin.post(members, data={"user_id": str(world["admin"])}).status_code == 200
    assert admin.post(members, data={"user_id": str(world["max"])}).status_code == 200
    assert admin.patch(f"{members}/{world['max']}/admin", data={"is_team_admin": "true"}).status_code == 200
    assert mia.delete(f"{members}/{world['mia']}").status_code == 403
    assert mia.delete(f"{members}/{world['max']}").status_code == 403
    assert mia.delete(f"{members}/{world['admin']}").status_code == 403
    # The admin can remove a team admin; the flag goes with the membership.
    assert admin.delete(f"{members}/{world['max']}").status_code == 200
    assert not _is_team_admin(world["max"], world["team_bravo"])


def test_teams_page_shows_roster_controls_only_where_allowed(world, mia_admin_of_bravo):
    html = mia_admin_of_bravo.get("/teams").text
    assert f'hx-post="/teams/{world["team_bravo"]}/members"' in html
    assert f'hx-post="/teams/{world["team_alpha"]}/members"' not in html
    assert "make admin" not in html  # only an admin hands out the role


# --- Users page ----------------------------------------------------------------


def _new_user(world, **over):
    return {
        "name": "New Person", "email": "new@example.com", "password": "longenough",
        "role": "member", "team_ids": str(world["team_charlie"]), **over,
    }


def test_team_admin_creates_users_on_their_own_team_only(world, mia_admin_of_bravo):
    from app.models import User

    mia = mia_admin_of_bravo
    # The team they ask for is ignored: it's always the team they administer.
    assert mia.post("/users", data=_new_user(world)).status_code == 200
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "new@example.com"))
        assert [t.id for t in user.teams] == [world["team_bravo"]]
        assert user.team_id == world["team_bravo"]
    assert mia.post("/users", data=_new_user(world, email="v@example.com", role="viewer")).status_code == 200
    assert mia.post("/users", data=_new_user(world, email="a@example.com", role="admin")).status_code == 403


def test_team_admin_cannot_change_roles_or_delete_users(world, mia_admin_of_bravo):
    mia = mia_admin_of_bravo
    assert mia.patch(f"/users/{world['max']}/role", data={"role": "admin"}).status_code == 403
    assert mia.delete(f"/users/{world['max']}").status_code == 403


def test_plain_member_cannot_create_users(world, login):
    assert login("mia").post("/users", data=_new_user(world)).status_code == 403


def test_users_page_form_for_a_team_admin(world, login, mia_admin_of_bravo):
    html = mia_admin_of_bravo.get("/users").text
    assert 'hx-post="/users"' in html
    assert 'name="team_ids" value="%s"' % world["team_bravo"] in html
    assert '<option value="admin"' not in html
    assert 'hx-post="/users"' not in login("max").get("/users").text


def test_changing_the_role_clears_team_admin(world, login, mia_admin_of_bravo):
    admin = login("admin")
    assert "(team admin)" in admin.get("/users").text
    assert admin.patch(f"/users/{world['mia']}/role", data={"role": "viewer"}).status_code == 200
    assert not _is_team_admin(world["mia"], world["team_bravo"])
    assert admin.patch(f"/users/{world['mia']}/role", data={"role": "member"}).status_code == 200
    assert not _is_team_admin(world["mia"], world["team_bravo"])
