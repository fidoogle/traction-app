"""Each team has its own Vision/Traction Organizer."""

import re


def purposes(html: str) -> set[str]:
    return set(re.findall(r"\b(alpha|bravo|charlie|xray) purpose\b", html))


def test_the_vto_page_shows_the_current_teams_vto(world, login):
    mia = login("mia")  # Alpha + Bravo
    html = mia.get("/vto").text
    assert purposes(html) == {"alpha"}
    assert "Alpha" in html.split("The V/TO for", 1)[1].split("</p>")[0]
    mia.switch_team(world["team_bravo"])
    assert purposes(mia.get("/vto").text) == {"bravo"}


def test_saving_changes_only_the_current_teams_vto(world, login):
    from app.db import SessionLocal
    from app.models import VTO

    mia = login("mia")
    mia.switch_team(world["team_bravo"])
    saved = mia.put("/vto", data={"core_focus_purpose": "bravo reworked", "core_values": "Care: always"})
    assert saved.status_code == 200
    with SessionLocal() as db:
        assert db.get(VTO, world["vto_bravo"]).core_focus_purpose == "bravo reworked"
        assert db.get(VTO, world["vto_alpha"]).core_focus_purpose == "alpha purpose"
        assert db.get(VTO, world["vto_charlie"]).core_focus_purpose == "charlie purpose"


def test_a_team_without_a_vto_gets_one_on_first_save(world, login):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Team, VTO

    admin = login("admin")
    created = admin.post("/teams", data={"name": "Fresh"})
    team_id = re.search(r"team-row-([0-9a-f-]+)", created.text).group(1)
    admin.post("/teams/current", data={"team_id": team_id})
    page = admin.get("/vto").text
    assert "Not set yet" not in page and 'name="core_focus_purpose"' in page
    assert admin.put("/vto", data={"core_focus_purpose": "fresh purpose"}).status_code == 200
    with SessionLocal() as db:
        vto = db.scalar(select(VTO).join(Team, VTO.team_id == Team.id).where(Team.name == "Fresh"))
        assert vto is not None and vto.core_focus_purpose == "fresh purpose"
        assert vto.org_id == world["org"]


def test_admins_on_all_teams_are_asked_to_pick_a_team(world, login):
    admin = login("admin")  # starts on All teams
    html = admin.get("/vto").text
    assert "Choose a team" in html and 'name="core_focus_purpose"' not in html
    assert admin.put("/vto", data={"core_focus_purpose": "x"}).status_code == 400
    for name in ("Alpha", "Bravo", "Charlie"):
        assert f"<td>{name}</td>" in html
    assert "Xray" not in html


def test_viewers_can_read_but_not_save(world, login):
    vic = login("vic")
    assert purposes(vic.get("/vto").text) == {"alpha"}
    assert vic.put("/vto", data={"core_focus_purpose": "x"}).status_code == 403


def test_a_team_whose_only_content_is_a_vto_cannot_be_deleted(world, login):
    admin = login("admin")
    created = admin.post("/teams", data={"name": "Only a VTO"})
    team_id = re.search(r"team-row-([0-9a-f-]+)", created.text).group(1)
    admin.post("/teams/current", data={"team_id": team_id})
    assert admin.put("/vto", data={"core_focus_purpose": "keep me"}).status_code == 200
    assert admin.delete(f"/teams/{team_id}").status_code == 400
    assert admin.delete(f"/api/teams/{team_id}/vto").status_code == 204
    assert admin.delete(f"/teams/{team_id}").status_code == 200


# --- People Analyzer core values come from the seat's team ------------------


def ratings_for(entry_id):
    from app.db import SessionLocal
    from app.models import PeopleAnalyzerEntry

    with SessionLocal() as db:
        return db.get(PeopleAnalyzerEntry, entry_id).core_values_ratings


def latest_entry(user_id):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import PeopleAnalyzerEntry

    with SessionLocal() as db:
        return db.scalar(
            select(PeopleAnalyzerEntry)
            .where(PeopleAnalyzerEntry.user_id == user_id, PeopleAnalyzerEntry.notes == "new")
        )


def test_people_analyzer_offers_the_current_teams_core_values(world, login):
    mia = login("mia")
    html = mia.get("/people-analyzer").text
    assert "alpha value" in html and "bravo value" not in html
    assert 'name="rate_core_values"' in html
    admin = login("admin")  # All teams: no single set of values to rate against
    page = admin.get("/people-analyzer").text
    assert "value</label>" not in page and 'name="rate_core_values"' not in page


def test_core_value_ratings_use_the_seats_team_and_only_when_offered(world, login):
    entry = {"evaluated_at": "2026-10-09", "notes": "new", "seat_id": str(world["seat_alpha"]),
             "user_id": str(world["mia"])}
    mia = login("mia")
    assert mia.post("/people-analyzer", data={**entry, "rate_core_values": "1",
                                              "core_value_names": ["alpha value", "bravo value"]}).status_code == 200
    # Only Alpha's own values are recorded, whatever else was sent.
    assert ratings_for(latest_entry(world["mia"]).id) == {"alpha value": True}

    admin = login("admin")  # All teams: the form never offered core values
    assert admin.post("/people-analyzer", data={**entry, "notes": "new", "user_id": str(world["mia"])}).status_code == 200
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import PeopleAnalyzerEntry

    with SessionLocal() as db:
        rows = db.scalars(select(PeopleAnalyzerEntry).where(PeopleAnalyzerEntry.notes == "new")).all()
        assert sorted(len(r.core_values_ratings) for r in rows) == [0, 1]
