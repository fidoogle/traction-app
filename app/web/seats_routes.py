import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models import Seat, Team, User, UserRole
from app.web.deps import get_current_user_web
from app.web.templates import templates

router = APIRouter(prefix="/seats")


def _org_seats_query(org_id: uuid.UUID):
    return (
        select(Seat)
        .join(Team, Seat.team_id == Team.id)
        .where(Team.org_id == org_id)
        .options(joinedload(Seat.team), joinedload(Seat.user))
    )


def _build_tree(seats: list[Seat]) -> dict:
    tree: dict = {}
    for seat in seats:
        tree.setdefault(seat.parent_seat_id, []).append(seat)
    for children in tree.values():
        children.sort(key=lambda s: s.title)
    return tree


def _seats_context(db: Session, current_user: User) -> dict:
    seats = db.scalars(_org_seats_query(current_user.org_id)).unique().all()
    teams = db.scalars(
        select(Team).where(Team.org_id == current_user.org_id).order_by(Team.name)
    ).all()
    org_users = db.scalars(
        select(User).where(User.org_id == current_user.org_id).order_by(User.name)
    ).all()
    tree = _build_tree(seats)
    return {
        "current_user": current_user,
        "tree": tree,
        "roots": tree.get(None, []),
        "seats": seats,
        "teams": teams,
        "org_users": org_users,
    }


@router.get("")
def list_seats(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    return templates.TemplateResponse(
        request, "seats/list.html", _seats_context(db, current_user)
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
):
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)
    team = db.get(Team, team_id)
    if team is None or team.org_id != current_user.org_id:
        raise HTTPException(status_code=404)

    resolved_parent = uuid.UUID(parent_seat_id) if parent_seat_id else None
    if resolved_parent is not None:
        parent = db.get(Seat, resolved_parent)
        if parent is None or parent.team.org_id != current_user.org_id:
            raise HTTPException(status_code=404)

    resolved_user = uuid.UUID(user_id) if user_id else None
    if resolved_user is not None:
        occupant = db.get(User, resolved_user)
        if occupant is None or occupant.org_id != current_user.org_id:
            raise HTTPException(status_code=404)

    responsibilities_list = [
        line.strip() for line in responsibilities.splitlines() if line.strip()
    ]

    seat = Seat(
        title=title,
        team_id=team_id,
        parent_seat_id=resolved_parent,
        user_id=resolved_user,
        responsibilities=responsibilities_list,
    )
    db.add(seat)
    db.commit()
    return templates.TemplateResponse(
        request, "seats/_tree.html", _seats_context(db, current_user)
    )


@router.patch("/{seat_id}/occupant")
def update_seat_occupant(
    request: Request,
    seat_id: uuid.UUID,
    user_id: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)
    seat = db.scalar(
        select(Seat)
        .join(Team, Seat.team_id == Team.id)
        .where(Seat.id == seat_id, Team.org_id == current_user.org_id)
    )
    if seat is None:
        raise HTTPException(status_code=404)

    resolved_user = uuid.UUID(user_id) if user_id else None
    if resolved_user is not None:
        occupant = db.get(User, resolved_user)
        if occupant is None or occupant.org_id != current_user.org_id:
            raise HTTPException(status_code=404)

    seat.user_id = resolved_user
    db.commit()
    return templates.TemplateResponse(
        request, "seats/_tree.html", _seats_context(db, current_user)
    )


@router.delete("/{seat_id}")
def delete_seat(
    request: Request,
    seat_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)
    seat = db.scalar(
        select(Seat)
        .join(Team, Seat.team_id == Team.id)
        .where(Seat.id == seat_id, Team.org_id == current_user.org_id)
    )
    if seat is None:
        raise HTTPException(status_code=404)
    db.delete(seat)
    db.commit()
    return templates.TemplateResponse(
        request, "seats/_tree.html", _seats_context(db, current_user)
    )
