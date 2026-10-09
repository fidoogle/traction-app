import re
import uuid
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from sqlalchemy import select, union
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db
from app.models import (
    Issue,
    Measurable,
    Meeting,
    Rock,
    Scorecard,
    Seat,
    Team,
    TeamMembership,
    User,
    UserRole,
)
from app.web.deps import get_current_user_web, get_team_context
from app.web.team_context import ALL_TEAMS, TeamContext, remember_team
from app.web.templates import templates

router = APIRouter(prefix="/teams")

# Everything a team owns. A team with any of it (or any members) can't be
# deleted - that would silently take a whole team's history with it.
_TEAM_CONTENT = (Rock, Issue, Meeting, Seat, Scorecard)


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


def _teams_in_use(db: Session, team_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Which of these teams have members or content."""
    if not team_ids:
        return set()
    owners = [TeamMembership, *_TEAM_CONTENT]
    return set(
        db.scalars(union(*(select(m.team_id).where(m.team_id.in_(team_ids)) for m in owners)))
    )


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
            "in_use": _teams_in_use(db, [team_id]),
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
            "in_use": _teams_in_use(db, [t.id for t in teams]),
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
    remember_team(response, team_id)
    return response


@router.delete("/{team_id}")
def delete_team(
    team_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    team = _get_team(db, team_id, current_user.org_id)
    if _teams_in_use(db, [team.id]):
        raise HTTPException(
            status_code=400, detail="Only a team with no members and no content can be deleted"
        )
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
    # Seats they held on this team become vacant, and their rows on its
    # scorecards stay, unowned, for an admin to reassign. (Their rocks keep
    # them as owner - a rock must have one.)
    for seat in db.scalars(select(Seat).where(Seat.team_id == team_id, Seat.user_id == user.id)):
        seat.user_id = None
    for measurable in db.scalars(
        select(Measurable)
        .join(Scorecard, Measurable.scorecard_id == Scorecard.id)
        .where(Scorecard.team_id == team_id, Measurable.owner_id == user.id)
    ):
        measurable.owner_id = None
    db.delete(membership)
    db.commit()
    return _row_response(request, db, current_user, team_id)
