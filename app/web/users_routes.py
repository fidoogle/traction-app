import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db
from app.core.security import hash_password
from app.models import Team, TeamMembership, User, UserRole
from app.web.deps import get_current_user_web
from app.web.templates import templates

router = APIRouter(prefix="/users")


def _require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403)


@router.get("")
def list_users(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    users = db.scalars(
        select(User)
        .where(User.org_id == current_user.org_id)
        .options(selectinload(User.teams))
        .order_by(User.name)
    ).all()
    teams = db.scalars(
        select(Team).where(Team.org_id == current_user.org_id).order_by(Team.name)
    ).all()
    return templates.TemplateResponse(
        request,
        "users/list.html",
        {
            "current_user": current_user,
            "users": users,
            "teams": teams,
            "UserRole": UserRole,
        },
    )


@router.post("")
def create_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    team_ids: list[uuid.UUID] = Form(...),
    role: UserRole = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    team_ids = list(dict.fromkeys(team_ids))
    teams = db.scalars(
        select(Team).where(Team.id.in_(team_ids), Team.org_id == current_user.org_id)
    ).all()
    if not team_ids or len(teams) != len(team_ids):
        raise HTTPException(status_code=404)
    if len(password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

    user = User(
        org_id=current_user.org_id,
        # Home team: the first one ticked (the form lists teams by name).
        team_id=team_ids[0],
        name=name,
        email=email,
        role=role,
        hashed_password=hash_password(password),
        memberships=[TeamMembership(team_id=team_id) for team_id in team_ids],
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return templates.TemplateResponse(
        request,
        "users/_row.html",
        {"current_user": current_user, "user": user, "UserRole": UserRole},
    )


@router.patch("/{user_id}/role")
def update_user_role(
    request: Request,
    user_id: uuid.UUID,
    role: UserRole = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    user = db.scalar(
        select(User)
        .where(User.id == user_id, User.org_id == current_user.org_id)
        .options(selectinload(User.teams))
    )
    if user is None:
        raise HTTPException(status_code=404)

    user.role = role
    db.commit()
    db.refresh(user)
    return templates.TemplateResponse(
        request,
        "users/_row.html",
        {"current_user": current_user, "user": user, "UserRole": UserRole},
    )


@router.delete("/{user_id}")
def delete_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    user = db.get(User, user_id)
    if user is None or user.org_id != current_user.org_id:
        raise HTTPException(status_code=404)
    db.delete(user)
    db.commit()
    return Response(status_code=200)
