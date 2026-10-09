"""The JSON API only reaches rows in the caller's org and teams."""

import pytest

# Every generic CRUD endpoint, and which seeded items (by team) each lists.
ENDPOINTS = {
    "/api/teams/": "team",
    "/api/rocks/": "rock",
    "/api/issues/": "issue",
    "/api/meetings/": "meeting",
    "/api/seats/": "seat",
    "/api/scorecards/": "card",
    "/api/measurables/": "measurable",
    "/api/scorecard-entries/": "entry",
    "/api/people-analyzer-entries/": "review",
}


def listed_ids(browser, path) -> set[str]:
    response = browser.get(path)
    assert response.status_code == 200, response.text
    return {row["id"] for row in response.json()}


def seeded(world, kind, *teams) -> set[str]:
    return {str(world[f"{kind}_{team}"]) for team in teams}


@pytest.mark.parametrize("path,kind", ENDPOINTS.items())
def test_lists_only_include_your_teams(world, login, path, kind):
    mia = login("mia")  # Alpha + Bravo
    assert listed_ids(mia, path) == seeded(world, kind, "alpha", "bravo")
    assert listed_ids(login("max"), path) == seeded(world, kind, "charlie")
    # An admin gets their whole org - and nothing from the other one.
    assert listed_ids(login("admin"), path) == seeded(world, kind, "alpha", "bravo", "charlie")
    assert listed_ids(login("other"), path) == seeded(world, kind, "xray")


@pytest.mark.parametrize("path,kind", [(p, k) for p, k in ENDPOINTS.items() if k != "team"])
def test_other_teams_rows_cannot_be_read_changed_or_deleted(world, login, path, kind):
    mia = login("mia")
    foreign = f"{path}{world[f'{kind}_charlie']}"
    assert mia.get(foreign).status_code == 404
    assert mia.patch(foreign, json={}).status_code in (403, 404)  # 403: admin-only route
    assert mia.delete(foreign).status_code in (403, 404)
    other_org = login("other")
    own_org_row = f"{path}{world[f'{kind}_alpha']}"
    assert other_org.get(own_org_row).status_code == 404
    assert other_org.patch(own_org_row, json={}).status_code == 404
    assert other_org.delete(own_org_row).status_code == 404


def test_rows_can_be_read_on_your_own_teams(world, login):
    mia = login("mia")
    assert mia.get(f"/api/rocks/{world['rock_bravo']}").status_code == 200
    assert login("admin").get(f"/api/rocks/{world['rock_charlie']}").status_code == 200


def test_cannot_create_rows_on_a_team_you_are_not_on(world, login):
    mia = login("mia")
    issue = {"title": "Via API", "priority": 1}
    assert mia.post("/api/issues/", json={**issue, "team_id": str(world["team_charlie"])}).status_code == 404
    assert mia.post("/api/issues/", json={**issue, "team_id": str(world["team_xray"])}).status_code == 404
    assert mia.post("/api/issues/", json={**issue, "team_id": str(world["team_bravo"])}).status_code == 201


def test_cannot_point_a_row_at_someone_elses_data(world, login):
    admin = login("admin")
    # Move an issue to a team in another org.
    resp = admin.patch(f"/api/issues/{world['issue_alpha']}", json={"team_id": str(world["team_xray"])})
    assert resp.status_code == 404
    # Make a to-do about another org's issue, owned by another org's user.
    todo = {"title": "x", "owner_id": str(world["admin"])}
    assert admin.post("/api/todos/", json={**todo, "issue_id": str(world["issue_xray"])}).status_code == 404
    assert admin.post("/api/todos/", json={**todo, "owner_id": str(world["other"])}).status_code == 404
    # Add a measurable to a scorecard on a team you're not on.
    measurable = {"owner_id": str(world["mia"]), "name": "m", "unit": "number", "goal_value": 1,
                  "goal_direction": "gte", "position": 1}
    resp = login("mia").post("/api/measurables/", json={**measurable, "scorecard_id": str(world["card_charlie"])})
    assert resp.status_code in (403, 404)
    resp = admin.post("/api/measurables/", json={**measurable, "scorecard_id": str(world["card_xray"])})
    assert resp.status_code == 404


def test_users_are_limited_to_your_org(world, login):
    admin = login("admin")
    ids = listed_ids(admin, "/api/users/")
    assert ids == {str(world[k]) for k in ("admin", "mia", "max", "vic")}
    assert admin.get(f"/api/users/{world['other']}").status_code == 404
    assert login("other").get(f"/api/users/{world['mia']}").status_code == 404
    assert login("other").delete(f"/api/users/{world['mia']}").status_code == 404
    # New users must land on one of your org's teams.
    user = {"org_id": str(world["org"]), "name": "New", "email": "new@example.com",
            "password": "long-enough-pw"}
    assert admin.post("/api/users/", json={**user, "team_id": str(world["team_xray"])}).status_code == 404
    assert admin.post("/api/users/", json={**user, "team_id": str(world["team_bravo"])}).status_code == 201
    assert admin.post("/api/users/", json={**user, "email": "n2@example.com",
                                           "org_id": str(world["org2"]),
                                           "team_id": str(world["team_bravo"])}).status_code == 404


def test_organizations_are_limited_to_your_own(world, login):
    admin = login("admin")
    assert listed_ids(admin, "/api/organizations/") == {str(world["org"])}
    assert admin.get(f"/api/organizations/{world['org2']}").status_code == 404
    assert admin.patch(f"/api/organizations/{world['org2']}", json={"name": "Mine now"}).status_code == 404


def test_vto_is_limited_to_your_own_org(world, login):
    admin = login("admin")
    assert admin.get(f"/api/organizations/{world['org2']}/vto").status_code == 404
    assert admin.delete(f"/api/organizations/{world['org2']}/vto").status_code == 404
    assert admin.get(f"/api/organizations/{world['org']}/vto").status_code == 404  # none set yet
    body = {"core_focus_purpose": "p", "core_focus_niche": "n"}
    assert admin.put(f"/api/organizations/{world['org2']}/vto", json=body).status_code == 404
