"""The "current team" a signed-in user is working in.

People can belong to several teams; the topbar switcher picks which one the
pages show. The choice is remembered in a cookie, but the cookie is only a
preference - it's re-checked against the user's teams on every request, so
pointing it at someone else's team just falls back to a team you're on.

Admins can see every team in the org (member or not) and can also pick
"All teams". Everyone else only ever sees teams they're a member of.
"""

import uuid
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import Response

from app.config import settings
from app.models import Team, User, UserRole

TEAM_COOKIE_NAME = "current_team"
TEAM_COOKIE_MAX_AGE = 365 * 24 * 60 * 60
ALL_TEAMS = "all"


@dataclass
class TeamContext:
    # Every team this user may work in, by name.
    teams: list[Team] = field(default_factory=list)
    # None means "All teams" for an admin - or, for anyone else, that they
    # aren't on any team yet.
    current: Optional[Team] = None
    can_view_all: bool = False

    @property
    def scope_ids(self) -> list[uuid.UUID]:
        """Team ids a page should show: just the current team, or all of them."""
        if self.current is not None:
            return [self.current.id]
        return [t.id for t in self.teams]

    @property
    def team_ids(self) -> list[uuid.UUID]:
        """Every team this user may work in, whatever the current team is.

        For looking up one record by id (a link, an htmx edit from a tab
        opened before switching): anything on any of your teams is fine.
        """
        return [t.id for t in self.teams]

    def follow(self, team_id: uuid.UUID) -> bool:
        """Make team_id current, e.g. on opening another team's scorecard.

        Returns True if that changed the current team (so the caller should
        remember_team() on its response). "All teams" is left alone - it
        already covers every team.
        """
        if self.current is None or self.current.id == team_id:
            return False
        team = next((t for t in self.teams if t.id == team_id), None)
        if team is None:
            return False
        self.current = team
        return True


def resolve_current_team(
    teams: list[Team],
    can_view_all: bool,
    home_team_id: Optional[uuid.UUID],
    requested: Optional[str],
) -> Optional[Team]:
    """Pick the current team from the cookie's value, ignoring anything not allowed.

    Without a usable choice: admins start on All teams, everyone else on
    their home team (or their first team, if the home team is gone).
    """
    by_id = {str(t.id): t for t in teams}
    if requested == ALL_TEAMS and can_view_all:
        return None
    if requested in by_id:
        return by_id[requested]
    if can_view_all:
        return None
    if home_team_id is not None and str(home_team_id) in by_id:
        return by_id[str(home_team_id)]
    return teams[0] if teams else None


def remember_team(response: Response, value: str) -> None:
    """Save the current team choice (a team id, or ALL_TEAMS) on the browser."""
    response.set_cookie(
        key=TEAM_COOKIE_NAME,
        value=value,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=TEAM_COOKIE_MAX_AGE,
        path="/",
    )


def build_team_context(db: Session, user: User, requested: Optional[str]) -> TeamContext:
    can_view_all = user.role == UserRole.ADMIN
    if can_view_all:
        teams = list(
            db.scalars(select(Team).where(Team.org_id == user.org_id).order_by(Team.name))
        )
    else:
        teams = list(user.teams)
    return TeamContext(
        teams=teams,
        current=resolve_current_team(teams, can_view_all, user.team_id, requested),
        can_view_all=can_view_all,
    )
