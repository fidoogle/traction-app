import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
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

    title = title.strip()
    if not title or len(title) > 255:
        raise HTTPException(status_code=422)

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


def _require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403)


def _get_org_issue(db: Session, issue_id: uuid.UUID, org_id: uuid.UUID) -> Issue:
    issue = db.scalar(_org_issues_query(org_id).where(Issue.id == issue_id))
    if issue is None:
        raise HTTPException(status_code=404)
    return issue


def _org_teams(db: Session, org_id: uuid.UUID):
    return db.scalars(select(Team).where(Team.org_id == org_id).order_by(Team.name)).all()


def _row_response(request: Request, current_user: User, issue: Issue):
    return templates.TemplateResponse(
        request,
        "issues/_row.html",
        {"current_user": current_user, "issue": issue, "IssueStatus": IssueStatus},
    )


@router.get("/{issue_id}")
def get_issue_row(
    request: Request,
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    return _row_response(request, current_user, _get_org_issue(db, issue_id, current_user.org_id))


@router.get("/{issue_id}/edit")
def edit_issue_row(
    request: Request,
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    issue = _get_org_issue(db, issue_id, current_user.org_id)
    return templates.TemplateResponse(
        request,
        "issues/_edit_row.html",
        {
            "current_user": current_user,
            "issue": issue,
            "teams": _org_teams(db, current_user.org_id),
            "IssueStatus": IssueStatus,
        },
    )


@router.put("/{issue_id}")
def update_issue(
    request: Request,
    issue_id: uuid.UUID,
    team_id: uuid.UUID = Form(...),
    title: str = Form(...),
    priority: int = Form(...),
    status: IssueStatus = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    issue = _get_org_issue(db, issue_id, current_user.org_id)
    team = db.get(Team, team_id)
    if team is None or team.org_id != current_user.org_id:
        raise HTTPException(status_code=404)
    title = title.strip()
    if not title or len(title) > 255:
        raise HTTPException(status_code=422)

    issue.team_id = team_id
    issue.title = title
    issue.priority = priority
    issue.status = status
    db.commit()
    db.expire_all()
    return _row_response(request, current_user, _get_org_issue(db, issue_id, current_user.org_id))


@router.delete("/{issue_id}")
def delete_issue(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    issue = _get_org_issue(db, issue_id, current_user.org_id)
    db.delete(issue)
    db.commit()
    return Response(status_code=200)
