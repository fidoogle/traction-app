import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models import Issue, IssueStatus, User, UserRole
from app.web.deps import get_current_user_web, get_team_context
from app.web.notes import clean_notes, notes_form_response
from app.web.team_context import TeamContext
from app.web.templates import templates

router = APIRouter(prefix="/issues")


def _issues_query(team_ids: list[uuid.UUID]):
    return (
        select(Issue)
        .where(Issue.team_id.in_(team_ids))
        .options(joinedload(Issue.team))
        .order_by(Issue.priority, Issue.title)
    )


@router.get("")
def list_issues(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    issues = db.scalars(_issues_query(team_ctx.scope_ids)).unique().all()
    default_team = team_ctx.default_team(current_user.team_id)
    return templates.TemplateResponse(
        request,
        "issues/list.html",
        {
            "current_user": current_user,
            "issues": issues,
            "teams": team_ctx.teams,
            "default_team_id": default_team.id if default_team else None,
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
    team_ctx: TeamContext = Depends(get_team_context),
):
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)
    team = team_ctx.get_team(team_id)

    title = title.strip()
    if not title or len(title) > 255:
        raise HTTPException(status_code=422)

    issue = Issue(team_id=team.id, title=title, priority=priority)
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
    team_ctx: TeamContext = Depends(get_team_context),
):
    issue = _get_issue(db, issue_id, team_ctx)
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


def _get_issue(db: Session, issue_id: uuid.UUID, team_ctx: TeamContext) -> Issue:
    # Any of the user's teams, not just the current one (see scorecard_routes).
    issue = db.scalar(_issues_query(team_ctx.team_ids).where(Issue.id == issue_id))
    if issue is None:
        raise HTTPException(status_code=404)
    return issue


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
    team_ctx: TeamContext = Depends(get_team_context),
):
    return _row_response(request, current_user, _get_issue(db, issue_id, team_ctx))


@router.get("/{issue_id}/edit")
def edit_issue_row(
    request: Request,
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    issue = _get_issue(db, issue_id, team_ctx)
    team_ctx.require_admin(issue.team_id)
    return templates.TemplateResponse(
        request,
        "issues/_edit_row.html",
        {
            "current_user": current_user,
            "issue": issue,
            "teams": team_ctx.admin_teams,
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
    team_ctx: TeamContext = Depends(get_team_context),
):
    issue = _get_issue(db, issue_id, team_ctx)
    team_ctx.require_admin(issue.team_id)
    team_ctx.require_admin(team_id)
    team = team_ctx.get_team(team_id)
    title = title.strip()
    if not title or len(title) > 255:
        raise HTTPException(status_code=422)

    issue.team_id = team.id
    # To-dos about this issue belong to the issue's team, so they move with it.
    for todo in issue.todos:
        todo.team_id = team.id
    issue.title = title
    issue.priority = priority
    issue.status = status
    db.commit()
    db.expire_all()
    return _row_response(request, current_user, _get_issue(db, issue_id, team_ctx))


@router.delete("/{issue_id}")
def delete_issue(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    issue = _get_issue(db, issue_id, team_ctx)
    team_ctx.require_admin(issue.team_id)
    db.delete(issue)
    db.commit()
    return Response(status_code=200)


def _require_notes_editor(current_user: User) -> None:
    # Same people who can already change an issue's status.
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)


@router.get("/{issue_id}/notes")
def get_issue_notes(
    request: Request,
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    issue = _get_issue(db, issue_id, team_ctx)
    return notes_form_response(
        request,
        subject=issue.title,
        url=f"/issues/{issue.id}/notes",
        row_id=f"issue-row-{issue.id}",
        notes=issue.notes,
        can_edit=current_user.role != UserRole.VIEWER,
    )


@router.put("/{issue_id}/notes")
def update_issue_notes(
    request: Request,
    issue_id: uuid.UUID,
    notes: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    _require_notes_editor(current_user)
    issue = _get_issue(db, issue_id, team_ctx)
    issue.notes = clean_notes(notes)
    db.commit()
    db.expire_all()
    return _row_response(request, current_user, _get_issue(db, issue_id, team_ctx))
