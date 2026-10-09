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
