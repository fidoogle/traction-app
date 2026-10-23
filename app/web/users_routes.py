import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db
from app.config import settings
from app.core.account_emails import send_welcome_email
from app.core.alert_emails import send_role_changed_notice, send_user_added_notice
from app.core.assignment_emails import new_event_id
from app.core.password_tokens import MIN_PASSWORD_LENGTH, WELCOME, issue_token
from app.core.security import hash_password
from app.models import Team, TeamMembership, User, UserRole
from app.web.deps import get_current_user_web, get_team_context
from app.web.team_context import TeamContext
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
        .options(selectinload(User.memberships).selectinload(TeamMembership.team))
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
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    email: str = Form(...),
    team_ids: list[uuid.UUID] = Form(...),
    role: UserRole = Form(...),
    # Optional when email is set up: leave it blank and the person sets their
    # own through the emailed link.
    password: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    if current_user.role != UserRole.ADMIN:
        # A team admin adds people to their own team, as members or viewers.
        admin_team_id = next(iter(team_ctx.admin_team_ids), None)
        if admin_team_id is None or role == UserRole.ADMIN:
            raise HTTPException(status_code=403)
        team_ids = [admin_team_id]
    team_ids = list(dict.fromkeys(team_ids))
    teams = db.scalars(
        select(Team).where(Team.id.in_(team_ids), Team.org_id == current_user.org_id)
    ).all()
    if not team_ids or len(teams) != len(team_ids):
        raise HTTPException(status_code=404)
    if password:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise HTTPException(
                status_code=422, detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
            )
        hashed_password = hash_password(password)
    elif settings.email_enabled:
        hashed_password = None
    else:
        raise HTTPException(
            status_code=422, detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
        )

    user = User(
        org_id=current_user.org_id,
        # Home team: the first one ticked (the form lists teams by name).
        team_id=team_ids[0],
        name=name,
        email=email,
        role=role,
        hashed_password=hashed_password,
        memberships=[TeamMembership(team_id=team_id) for team_id in team_ids],
    )
    db.add(user)
    if settings.email_enabled:
        db.flush()
        welcome_token = issue_token(db, user, WELCOME)
    db.commit()
    if settings.email_enabled:
        background_tasks.add_task(
            send_welcome_email, user.email, user.name, welcome_token, current_user.name
        )
        background_tasks.add_task(send_user_added_notice, user.id, current_user.id, new_event_id())
    db.refresh(user)
    return templates.TemplateResponse(
        request,
        "users/_row.html",
        {"current_user": current_user, "user": user, "UserRole": UserRole},
    )


@router.patch("/{user_id}/role")
def update_user_role(
    request: Request,
    background_tasks: BackgroundTasks,
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

    previous_role = user.role
    user.role = role
    if user.role != UserRole.MEMBER:
        # Team admin is a member-only role; it doesn't survive becoming
        # something else (or coming back later as a member).
        for membership in user.memberships:
            membership.is_team_admin = False
    db.commit()
    if settings.email_enabled and previous_role != role:
        background_tasks.add_task(
            send_role_changed_notice, user_id, previous_role.value, current_user.id, new_event_id()
        )
    db.refresh(user)
    return templates.TemplateResponse(
        request,
        "users/_row.html",
        {"current_user": current_user, "user": user, "UserRole": UserRole},
    )


@router.post("/{user_id}/resend-welcome")
def resend_welcome(
    user_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    """Emails the person a fresh set-password link (the old one stops working)."""
    _require_admin(current_user)
    user = db.get(User, user_id)
    if user is None or user.org_id != current_user.org_id:
        raise HTTPException(status_code=404)
    if not settings.email_enabled:
        return HTMLResponse('<span class="error">Email is not configured.</span>')
    token = issue_token(db, user, WELCOME)
    db.commit()
    background_tasks.add_task(send_welcome_email, user.email, user.name, token, current_user.name)
    return HTMLResponse("<span>Sent.</span>")


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
