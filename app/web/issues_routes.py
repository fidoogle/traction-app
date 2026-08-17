import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models import Issue, IssueStatus, Team, User, UserRole
from app.web.deps import get_current_user_web
from app.web.templates import templates

router = APIRouter(prefix="/issues")


def _org_issues_query(org_id: uuid.UUID):
    return (
        select(Issue)
        .join(Team, Issue.team_id == Team.id)
        .where(Team.org_id == org_id)
        .options(joinedload(Issue.team))
        .order_by(Issue.priority, Issue.title)
    )


@router.get("")
def list_issues(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    issues = db.scalars(_org_issues_query(current_user.org_id)).unique().all()
    teams = db.scalars(
        select(Team).where(Team.org_id == current_user.org_id).order_by(Team.name)
    ).all()
    return templates.TemplateResponse(
        request,
        "issues/list.html",
        {
            "current_user": current_user,
            "issues": issues,
            "teams": teams,
            "IssueStatus": IssueStatus,
        },
    )


@router.post("")
def create_issue(
    request: Request,
    team_id: uuid.UUID = Form(...),
    title: str = Form(...),
    priority: int = Form(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)
    team = db.get(Team, team_id)
    if team is None or team.org_id != current_user.org_id:
        raise HTTPException(status_code=404)

    issue = Issue(team_id=team_id, title=title, priority=priority)
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return templates.TemplateResponse(
        request,
        "issues/_row.html",
        {"current_user": current_user, "issue": issue, "IssueStatus": IssueStatus},
    )


@router.patch("/{issue_id}/status")
def update_issue_status(
    request: Request,
    issue_id: uuid.UUID,
    status: IssueStatus = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    issue = db.scalar(
        select(Issue)
        .join(Team, Issue.team_id == Team.id)
        .where(Issue.id == issue_id, Team.org_id == current_user.org_id)
        .options(joinedload(Issue.team))
    )
    if issue is None:
        raise HTTPException(status_code=404)
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)

    issue.status = status
    db.commit()
    db.refresh(issue)
    return templates.TemplateResponse(
        request,
        "issues/_row.html",
        {"current_user": current_user, "issue": issue, "IssueStatus": IssueStatus},
    )
