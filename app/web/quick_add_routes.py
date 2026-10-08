"""Global "quick add" modal (topbar +): log an Issue or To-Do from any page."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import Issue, Team, User, UserRole
from app.web.deps import get_current_user_web
from app.web.templates import templates

router = APIRouter(prefix="/quick-add")


@router.get("")
def quick_add_form(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)
    org_id = current_user.org_id
    return templates.TemplateResponse(
        request,
        "_quick_add.html",
        {
            "current_user": current_user,
            "teams": db.scalars(
                select(Team).where(Team.org_id == org_id).order_by(Team.name)
            ).all(),
            "org_users": db.scalars(
                select(User).where(User.org_id == org_id).order_by(User.name)
            ).all(),
            "org_issues": db.scalars(
                select(Issue)
                .join(Team, Issue.team_id == Team.id)
                .where(Team.org_id == org_id)
                .order_by(Issue.title)
            ).all(),
        },
    )
