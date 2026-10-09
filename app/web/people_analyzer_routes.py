import uuid
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models import PeopleAnalyzerEntry, Seat, User, UserRole, VTO
from app.web.deps import get_current_user_web, get_team_context
from app.web.team_context import TeamContext, require_member, team_people
from app.web.templates import templates

router = APIRouter(prefix="/people-analyzer")


def _entries_query(team_ids: list[uuid.UUID]):
    # An evaluation belongs to the team of the seat it rates.
    return (
        select(PeopleAnalyzerEntry)
        .join(Seat, PeopleAnalyzerEntry.seat_id == Seat.id)
        .where(Seat.team_id.in_(team_ids))
        .options(joinedload(PeopleAnalyzerEntry.user), joinedload(PeopleAnalyzerEntry.seat))
        .order_by(PeopleAnalyzerEntry.evaluated_at.desc())
    )


def _org_core_value_names(db: Session, org_id: uuid.UUID) -> list[str]:
    vto = db.scalar(select(VTO).where(VTO.org_id == org_id))
    if vto is None:
        return []
    return [
        cv.get("name") for cv in (vto.core_values or []) if isinstance(cv, dict) and cv.get("name")
    ]


def _list_context(db: Session, current_user: User, team_ctx: TeamContext) -> dict:
    entries = db.scalars(_entries_query(team_ctx.scope_ids)).unique().all()
    # The form rates seats on the teams being shown (the person list narrows
    # to the picked seat's team in the browser).
    seats = db.scalars(
        select(Seat).where(Seat.team_id.in_(team_ctx.scope_ids)).order_by(Seat.title)
    ).all()
    return {
        "current_user": current_user,
        "entries": entries,
        "people": team_people(db, team_ctx),
        "org_seats": seats,
        "core_value_names": _org_core_value_names(db, current_user.org_id),
        "today": date.today(),
    }


@router.get("")
def list_entries(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    return templates.TemplateResponse(
        request, "people_analyzer/list.html", _list_context(db, current_user, team_ctx)
    )


@router.post("")
def create_entry(
    request: Request,
    user_id: uuid.UUID = Form(...),
    seat_id: uuid.UUID = Form(...),
    evaluated_at: date = Form(...),
    gets_it: bool = Form(default=False),
    wants_it: bool = Form(default=False),
    has_capacity: bool = Form(default=False),
    core_value_names: list[str] = Form(default=[]),
    notes: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)

    seat = db.scalar(
        select(Seat).where(Seat.id == seat_id, Seat.team_id.in_(team_ctx.team_ids))
    )
    if seat is None:
        raise HTTPException(status_code=404)
    # You evaluate someone who is on the seat's team.
    require_member(seat.team, user_id)

    org_core_values = _org_core_value_names(db, current_user.org_id)
    ratings = {name: (name in core_value_names) for name in org_core_values}

    entry = PeopleAnalyzerEntry(
        user_id=user_id,
        seat_id=seat_id,
        evaluated_at=evaluated_at,
        gets_it=gets_it,
        wants_it=wants_it,
        has_capacity=has_capacity,
        core_values_ratings=ratings,
        notes=notes.strip() or None,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return templates.TemplateResponse(
        request, "people_analyzer/_row.html", {"current_user": current_user, "entry": entry}
    )
