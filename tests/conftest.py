"""Shared fixtures. The route/API tests run against a throwaway Postgres
database (created and dropped per test session) on the server named by
TEST_DATABASE_URL - by default the docker-compose `db` service on localhost.
Without a reachable server they're skipped locally, and fail under CI.
"""

import os
import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

SERVER_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://traction:traction@localhost:5432/postgres"
)
TEST_DB_NAME = f"traction_test_{os.getpid()}"

# Must be set before anything imports app.config / app.db.
os.environ["DATABASE_URL"] = make_url(SERVER_URL).set(database=TEST_DB_NAME).render_as_string(
    hide_password=False
)

from app.core.security import hash_password  # noqa: E402

PASSWORD = "pw-for-tests"
_PASSWORD_HASH = hash_password(PASSWORD)  # bcrypt is slow; hash once


@pytest.fixture(scope="session")
def engine():
    server = create_engine(SERVER_URL, isolation_level="AUTOCOMMIT")
    try:
        with server.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    except OperationalError:
        if os.environ.get("CI"):
            raise
        pytest.skip("no Postgres reachable for DB tests (set TEST_DATABASE_URL)")

    from app.db import engine as app_engine
    from app.models import Base

    Base.metadata.create_all(app_engine)
    yield app_engine
    app_engine.dispose()
    with server.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}" WITH (FORCE)'))
    server.dispose()


@dataclass
class World:
    """Two orgs. Org 1 has teams Alpha / Bravo / Charlie and people placed so
    each access rule has someone on each side of it:

      admin  - admin, home Alpha (admins reach every team)
      mia    - member of Alpha and Bravo
      max    - member of Charlie only
      vic    - viewer on Alpha
      other  - admin of the second org, with its own team and content
    """

    ids: dict

    def __getitem__(self, key):
        return self.ids[key]


@pytest.fixture()
def world(engine) -> World:
    from app.db import SessionLocal
    from app.models import (
        Issue,
        Measurable,
        Meeting,
        Organization,
        PeopleAnalyzerEntry,
        Rock,
        Scorecard,
        ScorecardEntry,
        Seat,
        Team,
        TeamMembership,
        Todo,
        User,
        UserRole,
        VTO,
    )
    from datetime import date

    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE activity_log, people_analyzer_entries, vtos, seats, todos, issues, "
                "scorecard_entries, measurables, scorecards, rocks, meetings, team_memberships, "
                "users, teams, organizations CASCADE"
            )
        )

    db = SessionLocal()
    ids: dict = {}
    try:
        org = Organization(name="District One")
        org2 = Organization(name="District Two")
        db.add_all([org, org2])
        db.flush()
        ids["org"], ids["org2"] = org.id, org2.id

        teams = {}
        for key, name in (("alpha", "Alpha"), ("bravo", "Bravo"), ("charlie", "Charlie")):
            teams[key] = Team(org_id=org.id, name=name)
        teams["xray"] = Team(org_id=org2.id, name="Xray")
        db.add_all(teams.values())
        db.flush()
        for key, team in teams.items():
            ids[f"team_{key}"] = team.id

        def person(key, name, role, org_, home, *on):
            user = User(
                org_id=org_.id,
                team_id=teams[home].id,
                name=name,
                email=f"{key}@example.com",
                role=role,
                hashed_password=_PASSWORD_HASH,
                memberships=[TeamMembership(team_id=teams[t].id) for t in (home, *on)],
            )
            db.add(user)
            db.flush()
            ids[key] = user.id
            return user

        people = {
            "admin": person("admin", "Ada Admin", UserRole.ADMIN, org, "alpha"),
            "mia": person("mia", "Mia Member", UserRole.MEMBER, org, "alpha", "bravo"),
            "max": person("max", "Max Member", UserRole.MEMBER, org, "charlie"),
            "vic": person("vic", "Vic Viewer", UserRole.VIEWER, org, "alpha"),
            "other": person("other", "Olly Other", UserRole.ADMIN, org2, "xray"),
        }

        # The same set of content on every team (owned by someone on it).
        owners = {"alpha": "mia", "bravo": "mia", "charlie": "max", "xray": "other"}
        for key, team in teams.items():
            owner = people[owners[key]]
            rock = Rock(team_id=team.id, owner_id=owner.id, title=f"{key} rock", quarter="2026-Q4")
            issue = Issue(team_id=team.id, title=f"{key} issue", priority=1)
            meeting = Meeting(team_id=team.id, scheduled_date=date(2099, 1, 1))
            seat = Seat(team_id=team.id, user_id=owner.id, title=f"{key} seat")
            card = Scorecard(
                org_id=team.org_id, team_id=team.id, name=f"{key} card", start_date=date(2026, 10, 5)
            )
            db.add_all([rock, issue, meeting, seat, card])
            db.flush()
            measurable = Measurable(
                scorecard_id=card.id, owner_id=owner.id, name=f"{key} m", unit="number",
                goal_value=1, goal_direction="gte", position=1,
            )
            db.add(measurable)
            db.flush()
            entry = ScorecardEntry(measurable_id=measurable.id, week_number=1, actual_value=2)
            review = PeopleAnalyzerEntry(
                user_id=owner.id, seat_id=seat.id, evaluated_at=date(2026, 10, 1),
                gets_it=True, wants_it=True, has_capacity=True, core_values_ratings={},
            )
            todo = Todo(team_id=team.id, owner_id=owner.id, issue_id=issue.id, title=f"{key} todo")
            vto = VTO(
                org_id=team.org_id, team_id=team.id, core_focus_purpose=f"{key} purpose",
                core_values=[{"name": f"{key} value", "description": ""}],
            )
            db.add_all([entry, review, todo, vto])
            db.flush()
            for kind, obj in (
                ("rock", rock), ("issue", issue), ("meeting", meeting), ("seat", seat),
                ("card", card), ("measurable", measurable), ("entry", entry),
                ("review", review), ("todo", todo), ("vto", vto),
            ):
                ids[f"{kind}_{key}"] = obj.id
        db.commit()
    finally:
        db.close()
    return World(ids)


class Browser:
    """A signed-in (or anonymous) client that behaves like the htmx UI: it
    keeps cookies, and sends the CSRF header on every request."""

    def __init__(self):
        from fastapi.testclient import TestClient

        from app.main import app

        self.client = TestClient(app, follow_redirects=False)

    def login(self, email: str) -> "Browser":
        page = self.client.get("/login")
        assert page.status_code == 200
        token = self.client.cookies.get("csrf_token")
        resp = self.client.post(
            "/login", data={"email": email, "password": PASSWORD, "csrf_token": token}
        )
        assert resp.status_code == 303, resp.text
        return self

    def request(self, method: str, path: str, **kwargs):
        headers = kwargs.pop("headers", {})
        headers.setdefault("X-CSRF-Token", self.client.cookies.get("csrf_token") or "")
        headers.setdefault("HX-Request", "true")
        return self.client.request(method, path, headers=headers, **kwargs)

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, **kw):
        return self.request("POST", path, **kw)

    def put(self, path, **kw):
        return self.request("PUT", path, **kw)

    def patch(self, path, **kw):
        return self.request("PATCH", path, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)

    def switch_team(self, team_id) -> None:
        resp = self.post("/teams/current", data={"team_id": str(team_id)})
        assert resp.status_code == 204, resp.text


@pytest.fixture()
def login(world):
    """login("mia") -> a Browser signed in as that person from the world."""

    def _login(key: str) -> Browser:
        return Browser().login(f"{key}@example.com")

    return _login


def titles(html: str, kind: str) -> set[str]:
    """Which seeded items ('alpha rock', ...) a rendered page mentions."""
    import re

    return set(re.findall(rf"\b(alpha|bravo|charlie|xray) {kind}\b", html))


def new_id() -> uuid.UUID:
    return uuid.uuid4()
