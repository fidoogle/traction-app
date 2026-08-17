import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import Team, User, UserRole
from app.web.deps import get_current_user_web
from app.web.templates import templates

router = APIRouter(prefix="/teams")


def _require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403)


@router.get("")
def list_teams(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    teams = db.scalars(
        select(Team).where(Team.org_id == current_user.org_id).order_by(Team.name)
    ).all()
    return templates.TemplateResponse(
        request, "teams/list.html", {"current_user": current_user, "teams": teams}
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
    db.refresh(team)
    return templates.TemplateResponse(
        request, "teams/_row.html", {"current_user": current_user, "team": team}
    )


@router.delete("/{team_id}")
def delete_team(
    team_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    team = db.get(Team, team_id)
    if team is None or team.org_id != current_user.org_id:
        raise HTTPException(status_code=404)
    db.delete(team)
    db.commit()
    return Response(status_code=200)
