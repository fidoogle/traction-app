import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models import Rock, RockStatus, Team, User, UserRole
from app.web.deps import get_current_user_web
from app.web.templates import templates

router = APIRouter(prefix="/rocks")


def _org_rocks_query(org_id: uuid.UUID):
    return (
        select(Rock)
        .join(Team, Rock.team_id == Team.id)
        .where(Team.org_id == org_id)
        .options(joinedload(Rock.owner), joinedload(Rock.team))
        .order_by(Rock.quarter.desc(), Rock.title)
    )


@router.get("")
def list_rocks(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    rocks = db.scalars(_org_rocks_query(current_user.org_id)).unique().all()
    return templates.TemplateResponse(
        request,
        "rocks/list.html",
        {"current_user": current_user, "rocks": rocks, "RockStatus": RockStatus},
    )


@router.patch("/{rock_id}/status")
def update_rock_status(
    request: Request,
    rock_id: uuid.UUID,
    status: RockStatus = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    rock = db.scalar(
        select(Rock)
        .join(Team, Rock.team_id == Team.id)
        .where(Rock.id == rock_id, Team.org_id == current_user.org_id)
        .options(joinedload(Rock.owner), joinedload(Rock.team))
    )
    if rock is None:
        raise HTTPException(status_code=404)
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)

    rock.status = status
    db.commit()
    db.refresh(rock)
    return templates.TemplateResponse(
        request,
        "rocks/_row.html",
        {"current_user": current_user, "rock": rock, "RockStatus": RockStatus},
    )
