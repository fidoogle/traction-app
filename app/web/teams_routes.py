import re
import uuid
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db
from app.config import settings
from app.models import Team, TeamMembership, User, UserRole
from app.web.deps import get_current_user_web, get_team_context
from app.web.team_context import ALL_TEAMS, TEAM_COOKIE_NAME, TeamContext
from app.web.templates import templates

router = APIRouter(prefix="/teams")

TEAM_COOKIE_MAX_AGE = 365 * 24 * 60 * 60


def _require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403)


def _get_team(db: Session, team_id: uuid.UUID, org_id: uuid.UUID) -> Team:
    team = db.scalar(
        select(Team)
        .where(Team.id == team_id, Team.org_id == org_id)
        .options(selectinload(Team.members).selectinload(User.teams))
    )
    if team is None:
        raise HTTPException(status_code=404)
    return team


def _org_users(db: Session, org_id: uuid.UUID):
    return db.scalars(select(User).where(User.org_id == org_id).order_by(User.name)).all()


def _row_response(request: Request, db: Session, current_user: User, team_id: uuid.UUID):
    db.expire_all()
    return templates.TemplateResponse(
        request,
        "teams/_row.html",
        {
            "current_user": current_user,
            "team": _get_team(db, team_id, current_user.org_id),
            "org_users": _org_users(db, current_user.org_id),
        },
    )


@router.get("")
def list_teams(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    teams = db.scalars(
        select(Team)
        .where(Team.org_id == current_user.org_id)
        .options(selectinload(Team.members).selectinload(User.teams))
        .order_by(Team.name)
    ).all()
    return templates.TemplateResponse(
        request,
        "teams/list.html",
        {
            "current_user": current_user,
            "teams": teams,
            "org_users": _org_users(db, current_user.org_id),
        },
    )


@router.post("")
def create_team(
    request: Request,
    name: str = Form(...),
    meeting_day: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    team = Team(org_id=current_user.org_id, name=name, meeting_day=meeting_day or None)
    db.add(team)
    db.commit()
    return _row_response(request, db, current_user, team.id)


def _section_url(request: Request) -> str:
    """The list page of whatever section the user was on, e.g. /scorecards.

    After switching teams, a detail page (one scorecard, say) may belong to
    the old team, so land on its section's list instead. Only a plain path
    segment is kept, so the header can't steer the redirect anywhere else.
    """
    path = urlsplit(request.headers.get("HX-Current-URL", "")).path
    section = path.strip("/").split("/")[0]
    return f"/{section}" if re.fullmatch(r"[a-z0-9-]+", section) else "/"


@router.post("/current")
def switch_team(
    request: Request,
    team_id: str = Form(...),
    team_ctx: TeamContext = Depends(get_team_context),
):
    allowed = {str(t.id) for t in team_ctx.teams}
    if team_ctx.can_view_all:
        allowed.add(ALL_TEAMS)
    if team_id not in allowed:
        raise HTTPException(status_code=404)
    response = Response(status_code=204, headers={"HX-Redirect": _section_url(request)})
    response.set_cookie(
        key=TEAM_COOKIE_NAME,
        value=team_id,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=TEAM_COOKIE_MAX_AGE,
        path="/",
    )
    return response


@router.delete("/{team_id}")
def delete_team(
    team_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    team = _get_team(db, team_id, current_user.org_id)
    if team.members:
        # Members' home team would dangle; move them off the team first.
        raise HTTPException(status_code=400, detail="Remove the team's members first")
    db.delete(team)
    db.commit()
    return Response(status_code=200)


# --- Members (admin) --------------------------------------------------------


@router.post("/{team_id}/members")
def add_member(
    request: Request,
    team_id: uuid.UUID,
    user_id: uuid.UUID = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    team = _get_team(db, team_id, current_user.org_id)
    user = db.get(User, user_id)
    if user is None or user.org_id != current_user.org_id:
        raise HTTPException(status_code=404)
    if user not in team.members:
        db.add(TeamMembership(user_id=user.id, team_id=team.id))
        db.commit()
    return _row_response(request, db, current_user, team_id)


@router.delete("/{team_id}/members/{user_id}")
def remove_member(
    request: Request,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    _get_team(db, team_id, current_user.org_id)
    user = db.scalar(
        select(User)
        .where(User.id == user_id, User.org_id == current_user.org_id)
        .options(selectinload(User.memberships).selectinload(TeamMembership.team))
    )
    membership = next((m for m in user.memberships if m.team_id == team_id), None) if user else None
    if membership is None:
        raise HTTPException(status_code=404)
    others = sorted(
        (m for m in user.memberships if m.team_id != team_id), key=lambda m: m.team.name
    )
    if not others:
        raise HTTPException(status_code=400, detail="Everyone must belong to at least one team")
    if user.team_id == team_id:
        user.team_id = others[0].team_id
    db.delete(membership)
    db.commit()
    return _row_response(request, db, current_user, team_id)
