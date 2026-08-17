import uuid
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models import PeopleAnalyzerEntry, Seat, Team, User, UserRole, VTO
from app.web.deps import get_current_user_web
from app.web.templates import templates

router = APIRouter(prefix="/people-analyzer")


def _org_entries_query(org_id: uuid.UUID):
    return (
        select(PeopleAnalyzerEntry)
        .join(User, PeopleAnalyzerEntry.user_id == User.id)
        .where(User.org_id == org_id)
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


def _list_context(db: Session, current_user: User) -> dict:
    entries = db.scalars(_org_entries_query(current_user.org_id)).unique().all()
    org_users = db.scalars(
        select(User).where(User.org_id == current_user.org_id).order_by(User.name)
    ).all()
    org_seats = db.scalars(
        select(Seat)
        .join(Team, Seat.team_id == Team.id)
        .where(Team.org_id == current_user.org_id)
        .order_by(Seat.title)
    ).all()
    return {
        "current_user": current_user,
        "entries": entries,
        "org_users": org_users,
        "org_seats": org_seats,
        "core_value_names": _org_core_value_names(db, current_user.org_id),
        "today": date.today(),
    }


@router.get("")
def list_entries(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    return templates.TemplateResponse(
        request, "people_analyzer/list.html", _list_context(db, current_user)
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
):
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)

    user = db.get(User, user_id)
    if user is None or user.org_id != current_user.org_id:
        raise HTTPException(status_code=404)

    seat = db.scalar(
        select(Seat)
        .join(Team, Seat.team_id == Team.id)
        .where(Seat.id == seat_id, Team.org_id == current_user.org_id)
    )
    if seat is None:
        raise HTTPException(status_code=404)

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
