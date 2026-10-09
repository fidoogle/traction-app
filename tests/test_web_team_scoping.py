"""The web UI only shows, and only lets you change, what's on your teams."""

import pytest

from conftest import titles

# page -> (what its items are called in the seed data, where the list starts)
LISTS = {
    "/rocks": ("rock", 'id="rocks-table-body"'),
    "/issues": ("issue", 'id="issues-table-body"'),
    "/seats": ("seat", 'id="seat-tree-container"'),
    "/scorecards": ("card", 'id="scorecards-table-body"'),
    "/todos": ("todo", 'id="todos-table-body"'),
    "/people-analyzer": ("seat", 'id="pae-table-body"'),
}


def shown(browser, path) -> set[str]:
    kind, marker = LISTS[path]
    html = browser.get(path).text
    assert marker in html, f"{path} has no list"
    return titles(html.split(marker, 1)[1], kind)


@pytest.mark.parametrize("path", LISTS)
def test_member_sees_only_the_current_team(world, login, path):
    mia = login("mia")
    assert shown(mia, path) == {"alpha"}  # her home team
    mia.switch_team(world["team_bravo"])
    assert shown(mia, path) == {"bravo"}


@pytest.mark.parametrize("path", LISTS)
def test_a_forged_team_cookie_changes_nothing(world, login, path):
    mia = login("mia")
    mia.client.cookies.set("current_team", str(world["team_charlie"]))
    assert shown(mia, path) == {"alpha"}
    mia.client.cookies.set("current_team", "all")
    assert shown(mia, path) == {"alpha"}


@pytest.mark.parametrize("path", LISTS)
def test_viewer_sees_only_their_team(world, login, path):
    assert shown(login("vic"), path) == {"alpha"}


@pytest.mark.parametrize("path", LISTS)
def test_admin_sees_every_team_in_their_org_and_no_others(world, login, path):
    admin = login("admin")
    assert shown(admin, path) == {"alpha", "bravo", "charlie"}
    admin.switch_team(world["team_charlie"])
    assert shown(admin, path) == {"charlie"}


def test_meetings_follow_the_current_team(world, login):
    def teams_listed(browser):
        body = browser.get("/meetings").text.split('id="meetings-table-body"', 1)[1]
        return {name for name in ("Alpha", "Bravo", "Charlie", "Xray") if f"<td>{name}</td>" in body}

    mia = login("mia")
    assert teams_listed(mia) == {"Alpha"}
    mia.switch_team(world["team_bravo"])
    assert teams_listed(mia) == {"Bravo"}
    assert teams_listed(login("admin")) == {"Alpha", "Bravo", "Charlie"}


# --- Reaching a single item by id ------------------------------------------

# What a member may do to an item, as (method, path, form data). Every one of
# these must be a 404 for items on a team you're not on.
MEMBER_ACTIONS = [
    ("GET", "/rocks/{rock}", {}),
    ("GET", "/rocks/{rock}/notes", {}),
    ("PATCH", "/issues/{issue}/status", {"status": "resolved"}),
    ("GET", "/issues/{issue}/notes", {}),
    ("PUT", "/issues/{issue}/notes", {"notes": "hello"}),
    ("PATCH", "/seats/{seat}/occupant", {"user_id": ""}),
    ("DELETE", "/seats/{seat}", {}),
    ("GET", "/scorecards/{card}", {}),
    ("PUT", "/scorecards/{card}/measurables/{measurable}/weeks/1", {"value": "9"}),
    ("GET", "/todos/{todo}", {}),
    ("PATCH", "/todos/{todo}/status", {"status": "done"}),
    ("GET", "/todos/{todo}/notes", {}),
    ("PUT", "/todos/{todo}/notes", {"notes": "hello"}),
]
# What an admin may additionally do.
ADMIN_ACTIONS = MEMBER_ACTIONS + [
    ("GET", "/rocks/{rock}/edit", {}),
    ("PATCH", "/rocks/{rock}/status", {"status": "done"}),
    ("DELETE", "/rocks/{rock}", {}),
    ("GET", "/issues/{issue}/edit", {}),
    ("DELETE", "/issues/{issue}", {}),
    ("DELETE", "/meetings/{meeting}", {}),
    ("DELETE", "/scorecards/{card}", {}),
    ("GET", "/scorecards/{card}/measurables/{measurable}/edit", {}),
    ("DELETE", "/scorecards/{card}/measurables/{measurable}", {}),
    ("GET", "/todos/{todo}/edit", {}),
    ("DELETE", "/todos/{todo}", {}),
]


def item_paths(world, team, template):
    return template.format(
        rock=world[f"rock_{team}"],
        issue=world[f"issue_{team}"],
        meeting=world[f"meeting_{team}"],
        seat=world[f"seat_{team}"],
        card=world[f"card_{team}"],
        measurable=world[f"measurable_{team}"],
        todo=world[f"todo_{team}"],
    )


@pytest.mark.parametrize("method,template,data", MEMBER_ACTIONS)
def test_member_gets_404_for_a_team_they_are_not_on(world, login, method, template, data):
    mia = login("mia")  # Alpha + Bravo
    response = mia.request(method, item_paths(world, "charlie", template), data=data)
    assert response.status_code == 404


@pytest.mark.parametrize("method,template,data", ADMIN_ACTIONS)
def test_admin_of_another_org_gets_404_for_everything(world, login, method, template, data):
    other = login("other")
    response = other.request(method, item_paths(world, "alpha", template), data=data)
    assert response.status_code == 404


def test_member_can_reach_items_on_any_of_their_teams_not_just_the_current_one(world, login):
    mia = login("mia")  # current team: Alpha
    resp = mia.patch(f"/issues/{world['issue_bravo']}/status", data={"status": "resolved"})
    assert resp.status_code == 200


def test_opening_another_teams_scorecard_switches_to_that_team(world, login):
    mia = login("mia")
    resp = mia.get(f"/scorecards/{world['card_bravo']}")
    assert resp.status_code == 200
    assert str(world["team_bravo"]) in resp.headers["set-cookie"]
    assert shown(mia, "/rocks") == {"bravo"}


def test_viewer_cannot_change_things(world, login):
    vic = login("vic")
    assert vic.patch(f"/issues/{world['issue_alpha']}/status", data={"status": "resolved"}).status_code == 403
    assert vic.post("/issues", data={"team_id": str(world["team_alpha"]), "title": "x"}).status_code == 403


# --- Creating things --------------------------------------------------------


def test_member_can_log_issues_and_meetings_only_for_their_teams(world, login):
    mia = login("mia")
    issue = {"title": "New one", "priority": 1}
    assert mia.post("/issues", data={**issue, "team_id": str(world["team_bravo"])}).status_code == 200
    assert mia.post("/issues", data={**issue, "team_id": str(world["team_charlie"])}).status_code == 404
    assert mia.post("/issues", data={**issue, "team_id": str(world["team_xray"])}).status_code == 404
    meeting = {"scheduled_date": "2026-12-01"}
    assert mia.post("/meetings", data={**meeting, "team_id": str(world["team_bravo"])}).status_code == 200
    assert mia.post("/meetings", data={**meeting, "team_id": str(world["team_charlie"])}).status_code == 404


def test_rock_owner_must_be_on_the_rocks_team(world, login):
    admin = login("admin")
    rock = {"title": "New rock", "quarter": "2026-Q4"}
    on_charlie = {**rock, "team_id": str(world["team_charlie"])}
    assert admin.post("/rocks", data={**on_charlie, "owner_id": str(world["max"])}).status_code == 200
    assert admin.post("/rocks", data={**on_charlie, "owner_id": str(world["mia"])}).status_code == 404
    assert login("mia").post("/rocks", data={**on_charlie, "owner_id": str(world["max"])}).status_code == 403


def test_moving_a_rock_needs_an_owner_on_the_new_team(world, login):
    admin = login("admin")
    base = {"title": "Moved", "quarter": "2026-Q4", "status": "on_track"}
    move = {**base, "team_id": str(world["team_charlie"])}
    url = f"/rocks/{world['rock_alpha']}"  # owned by Mia, who isn't on Charlie
    assert admin.put(url, data={**move, "owner_id": str(world["mia"])}).status_code == 404
    assert admin.put(url, data={**move, "owner_id": str(world["max"])}).status_code == 200


def test_seats_report_to_seats_on_their_own_team_and_are_held_by_team_members(world, login):
    mia = login("mia")
    seat = {"title": "New seat", "team_id": str(world["team_alpha"])}
    assert mia.post("/seats", data={**seat, "parent_seat_id": str(world["seat_bravo"])}).status_code == 404
    assert mia.post("/seats", data={**seat, "user_id": str(world["max"])}).status_code == 404
    assert mia.post("/seats", data={**seat, "parent_seat_id": str(world["seat_alpha"]),
                                    "user_id": str(world["mia"])}).status_code == 200
    assert mia.post("/seats", data={**seat, "team_id": str(world["team_charlie"])}).status_code == 404


def test_people_analyzer_rates_team_members_on_seats_you_can_reach(world, login, ):
    entry = {"evaluated_at": "2026-10-09", "gets_it": "true"}
    seat_c = str(world["seat_charlie"])
    assert login("mia").post("/people-analyzer", data={**entry, "seat_id": seat_c,
                                                       "user_id": str(world["max"])}).status_code == 404
    admin = login("admin")
    assert admin.post("/people-analyzer", data={**entry, "seat_id": seat_c,
                                                "user_id": str(world["mia"])}).status_code == 404
    assert admin.post("/people-analyzer", data={**entry, "seat_id": seat_c,
                                                "user_id": str(world["max"])}).status_code == 200


def test_cannot_switch_to_a_team_you_are_not_on(world, login):
    mia = login("mia")
    assert mia.post("/teams/current", data={"team_id": str(world["team_charlie"])}).status_code == 404
    assert mia.post("/teams/current", data={"team_id": "all"}).status_code == 404
    assert login("admin").post("/teams/current", data={"team_id": "all"}).status_code == 204
    assert login("admin").post("/teams/current", data={"team_id": str(world["team_xray"])}).status_code == 404


def test_quick_add_only_offers_your_teams_and_their_issues(world, login):
    html = login("mia").get("/quick-add").text
    assert titles(html, "issue") == {"alpha", "bravo"}
    assert "Charlie" not in html


def test_todos_belong_to_a_team_with_member_owners_and_issues_from_that_team(world, login):
    mia = login("mia")
    base = {"title": "Do it", "owner_id": str(world["mia"])}
    bravo = {**base, "team_id": str(world["team_bravo"])}
    assert mia.post("/todos", data={**bravo, "issue_id": str(world["issue_bravo"])}).status_code == 200
    assert mia.post("/todos", data=bravo).status_code == 200  # no issue is fine
    # An issue on a team she isn't on, and one on her other team, are both refused.
    assert mia.post("/todos", data={**bravo, "issue_id": str(world["issue_charlie"])}).status_code == 404
    assert mia.post("/todos", data={**bravo, "issue_id": str(world["issue_alpha"])}).status_code == 404
    assert mia.post("/todos", data={**base, "team_id": str(world["team_charlie"])}).status_code == 404
    assert mia.post("/todos", data={**bravo, "owner_id": str(world["max"])}).status_code == 404  # not on Bravo


def test_moving_a_todo_needs_an_owner_and_issue_from_the_new_team(world, login):
    admin = login("admin")
    url = f"/todos/{world['todo_alpha']}"  # owned by Mia, about Alpha's issue
    move = {"title": "Moved", "status": "open", "team_id": str(world["team_bravo"]),
            "owner_id": str(world["mia"])}
    assert admin.put(url, data={**move, "issue_id": str(world["issue_alpha"])}).status_code == 404
    assert admin.put(url, data={**move, "owner_id": str(world["max"])}).status_code == 404
    assert admin.put(url, data=move).status_code == 200


def test_moving_an_issue_moves_its_todos_with_it(world, login):
    from app.db import SessionLocal
    from app.models import Todo

    form = {"title": "Same issue", "priority": 1, "status": "open", "team_id": str(world["team_bravo"])}
    assert login("admin").put(f"/issues/{world['issue_alpha']}", data=form).status_code == 200
    with SessionLocal() as db:
        assert db.get(Todo, world["todo_alpha"]).team_id == world["team_bravo"]


# --- Org chart and team membership -----------------------------------------


def test_a_seat_reporting_to_another_teams_seat_still_shows(world, login, engine):
    from app.db import SessionLocal
    from app.models import Seat

    with SessionLocal() as db:
        db.get(Seat, world["seat_alpha"]).parent_seat_id = world["seat_bravo"]
        db.commit()
    admin = login("admin")
    admin.switch_team(world["team_alpha"])
    assert shown(admin, "/seats") == {"alpha"}  # as a top-level seat, not lost


def test_removing_someone_from_a_team_vacates_their_seat_there(world, login):
    from app.db import SessionLocal
    from app.models import Seat, User

    admin = login("admin")
    resp = admin.delete(f"/teams/{world['team_alpha']}/members/{world['mia']}")
    assert resp.status_code == 200
    with SessionLocal() as db:
        assert db.get(Seat, world["seat_alpha"]).user_id is None
        assert db.get(Seat, world["seat_bravo"]).user_id == world["mia"]  # other team untouched
        assert db.get(User, world["mia"]).team_id == world["team_bravo"]  # home team moved
    # Her rock on Alpha is still hers, and editable without reassigning it.
    rock = {"title": "Renamed", "quarter": "2026-Q4", "status": "on_track",
            "team_id": str(world["team_alpha"]), "owner_id": str(world["mia"])}
    assert admin.put(f"/rocks/{world['rock_alpha']}", data=rock).status_code == 200


def test_a_team_with_members_or_content_cannot_be_deleted(world, login):
    admin = login("admin")
    assert admin.delete(f"/teams/{world['team_alpha']}").status_code == 400
    created = admin.post("/teams", data={"name": "Empty"})
    assert created.status_code == 200
    import re

    team_id = re.search(r'team-row-([0-9a-f-]+)', created.text).group(1)
    assert admin.delete(f"/teams/{team_id}").status_code == 200
