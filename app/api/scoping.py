"""Row-level scoping for the JSON API.

The web UI scopes every query by the signed-in user's teams (see
app/web/team_context.py); this does the same for the generic CRUD routes, so
the API can't read or write across organizations or into teams the caller
isn't on. Same rule as the UI (app/core/team_access.py): admins reach every
team in their org, everyone else only the teams they belong to.

`visible()` says which rows of a model a user may see. `check_refs()` makes
sure the ids in a create/update payload (team_id, owner_id, ...) point at
rows the user could see too - otherwise you could attach your data to
someone else's team.
"""

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from app.core.team_access import accessible_teams
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
    Todo,
    User,
)
from app.models.base import Base

# Models that carry their own team_id.
_TEAM_OWNED = (Rock, Issue, Meeting, Seat, Scorecard)

# Payload field -> the model it points at.
REF_FIELDS: dict[str, type[Base]] = {
    "org_id": Organization,
    "team_id": Team,
    "scorecard_id": Scorecard,
    "measurable_id": Measurable,
    "seat_id": Seat,
    "parent_seat_id": Seat,
    "issue_id": Issue,
    "owner_id": User,
    "user_id": User,
}


def team_ids_for(db: Session, user: User) -> list[uuid.UUID]:
    return [t.id for t in accessible_teams(db, user)]


def visible(model: type[Base], user: User, team_ids: list[uuid.UUID]) -> ColumnElement[bool]:
    """WHERE clause for the rows of `model` this user may see."""
    if model is Organization:
        return Organization.id == user.org_id
    if model is Team:
        return Team.id.in_(team_ids)
    if model is User:
        return User.org_id == user.org_id
    if model in _TEAM_OWNED:
        return model.team_id.in_(team_ids)

    scorecards = select(Scorecard.id).where(Scorecard.team_id.in_(team_ids))
    if model is Measurable:
        return Measurable.scorecard_id.in_(scorecards)
    if model is ScorecardEntry:
        measurables = select(Measurable.id).where(Measurable.scorecard_id.in_(scorecards))
        return ScorecardEntry.measurable_id.in_(measurables)
    if model is PeopleAnalyzerEntry:
        seats = select(Seat.id).where(Seat.team_id.in_(team_ids))
        return PeopleAnalyzerEntry.seat_id.in_(seats)
    if model is Todo:
        # To-dos aren't team-owned yet: scoped to the org via their owner.
        return Todo.owner_id.in_(select(User.id).where(User.org_id == user.org_id))
    # Fail closed: a model added to the API without a rule here is a bug.
    raise NotImplementedError(f"No API scoping rule for {model.__name__}")


def check_refs(db: Session, user: User, team_ids: list[uuid.UUID], values: dict[str, Any]) -> None:
    """404 if any id in a create/update payload points outside the user's reach."""
    for field, ref_model in REF_FIELDS.items():
        value = values.get(field)
        if value is None:
            continue
        found = db.scalar(
            select(ref_model.id).where(
                ref_model.id == value, visible(ref_model, user, team_ids)
            )
        )
        if found is None:
            raise HTTPException(status_code=404, detail=f"{ref_model.__name__} not found")
