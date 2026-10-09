"""Global "quick add" modal (topbar +): log an Issue or To-Do from any page."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import Issue, User, UserRole
from app.web.deps import get_current_user_web, get_team_context
from app.web.team_context import TeamContext
from app.web.templates import templates

router = APIRouter(prefix="/quick-add")


@router.get("")
def quick_add_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)
    org_id = current_user.org_id
    default_team = team_ctx.default_team(current_user.team_id)
    return templates.TemplateResponse(
        request,
        "_quick_add.html",
        {
            "current_user": current_user,
            "teams": team_ctx.teams,
            "default_team_id": default_team.id if default_team else None,
            "org_users": db.scalars(
                select(User).where(User.org_id == org_id).order_by(User.name)
            ).all(),
            "org_issues": db.scalars(
                select(Issue)
                .where(Issue.team_id.in_(team_ctx.team_ids))
                .order_by(Issue.title)
            ).all(),
        },
    )
