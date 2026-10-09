import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models import Seat, User, UserRole
from app.web.deps import get_current_user_web, get_team_context
from app.web.team_context import TeamContext, require_member, team_people
from app.web.templates import templates

router = APIRouter(prefix="/seats")


def _seats_query(team_ids: list[uuid.UUID]):
    return (
        select(Seat)
        .where(Seat.team_id.in_(team_ids))
        .options(joinedload(Seat.team), joinedload(Seat.user))
    )


def _get_seat(db: Session, seat_id: uuid.UUID, team_ctx: TeamContext) -> Seat:
    # Any of the user's teams, not just the current one (see scorecard_routes).
    seat = db.scalar(_seats_query(team_ctx.team_ids).where(Seat.id == seat_id))
    if seat is None:
        raise HTTPException(status_code=404)
    return seat


def _build_tree(seats: list[Seat]) -> dict:
    """Seats grouped under their parent. A seat whose parent isn't in `seats`
    (a seat on another team, or one that's been filtered out) is treated as
    top level, so nothing disappears from the chart."""
    shown = {seat.id for seat in seats}
    tree: dict = {}
    for seat in seats:
        parent = seat.parent_seat_id if seat.parent_seat_id in shown else None
        tree.setdefault(parent, []).append(seat)
    for children in tree.values():
        children.sort(key=lambda s: s.title)
    return tree


def _seats_context(db: Session, current_user: User, team_ctx: TeamContext) -> dict:
    # Every seat the user can work with feeds the add-seat form's "Reports to"
    # list (narrowed by team in the browser); only the current team's are drawn.
    all_seats = db.scalars(_seats_query(team_ctx.team_ids)).unique().all()
    scope = set(team_ctx.scope_ids)
    seats = [s for s in all_seats if s.team_id in scope]
    tree = _build_tree(seats)

    members = {t.id: list(t.members) for t in team_ctx.teams}
    occupant_choices = {}
    for seat in seats:
        people = {u.id: u for u in members.get(seat.team_id, [])}
        if seat.user is not None:
            people.setdefault(seat.user.id, seat.user)
        occupant_choices[seat.id] = sorted(people.values(), key=lambda u: u.name)

    default_team = team_ctx.default_team(current_user.team_id)
    return {
        "current_user": current_user,
        "tree": tree,
        "roots": tree.get(None, []),
        "seats": seats,
        "parent_choices": sorted(all_seats, key=lambda s: s.title),
        "occupant_choices": occupant_choices,
        "teams": team_ctx.teams,
        "default_team_id": default_team.id if default_team else None,
        "people": team_people(db, team_ctx),
    }


@router.get("")
def list_seats(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    return templates.TemplateResponse(
        request, "seats/list.html", _seats_context(db, current_user, team_ctx)
    )


@router.post("")
def create_seat(
    request: Request,
    title: str = Form(...),
    team_id: uuid.UUID = Form(...),
    parent_seat_id: Optional[str] = Form(default=None),
    user_id: Optional[str] = Form(default=None),
    responsibilities: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)
    team = team_ctx.get_team(team_id)

    # A seat reports to another seat on its own team.
    resolved_parent = uuid.UUID(parent_seat_id) if parent_seat_id else None
    if resolved_parent is not None:
        parent = db.get(Seat, resolved_parent)
        if parent is None or parent.team_id != team.id:
            raise HTTPException(status_code=404)

    resolved_user = uuid.UUID(user_id) if user_id else None
    if resolved_user is not None:
        require_member(team, resolved_user)

    responsibilities_list = [
        line.strip() for line in responsibilities.splitlines() if line.strip()
    ]

    seat = Seat(
        title=title,
        team_id=team.id,
        parent_seat_id=resolved_parent,
        user_id=resolved_user,
        responsibilities=responsibilities_list,
    )
    db.add(seat)
    db.commit()
    return templates.TemplateResponse(
        request, "seats/_tree.html", _seats_context(db, current_user, team_ctx)
    )


@router.patch("/{seat_id}/occupant")
def update_seat_occupant(
    request: Request,
    seat_id: uuid.UUID,
    user_id: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)
    seat = _get_seat(db, seat_id, team_ctx)

    resolved_user = uuid.UUID(user_id) if user_id else None
    if resolved_user is not None:
        require_member(seat.team, resolved_user, keep=seat.user_id)

    seat.user_id = resolved_user
    db.commit()
    db.expire_all()
    return templates.TemplateResponse(
        request, "seats/_tree.html", _seats_context(db, current_user, team_ctx)
    )


@router.delete("/{seat_id}")
def delete_seat(
    request: Request,
    seat_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)
    seat = _get_seat(db, seat_id, team_ctx)
    db.delete(seat)
    db.commit()
    db.expire_all()
    return templates.TemplateResponse(
        request, "seats/_tree.html", _seats_context(db, current_user, team_ctx)
    )
