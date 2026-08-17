import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models import Issue, Team, Todo, TodoStatus, User, UserRole
from app.web.deps import get_current_user_web
from app.web.templates import templates

router = APIRouter(prefix="/todos")


def _org_todos_query(org_id: uuid.UUID):
    return (
        select(Todo)
        .join(User, Todo.owner_id == User.id)
        .where(User.org_id == org_id)
        .options(joinedload(Todo.owner), joinedload(Todo.issue))
        .order_by(Todo.due_date.is_(None), Todo.due_date, Todo.title)
    )


@router.get("")
def list_todos(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    todos = db.scalars(_org_todos_query(current_user.org_id)).unique().all()
    org_users = db.scalars(
        select(User).where(User.org_id == current_user.org_id).order_by(User.name)
    ).all()
    org_issues = db.scalars(
        select(Issue)
        .join(Team, Issue.team_id == Team.id)
        .where(Team.org_id == current_user.org_id)
        .order_by(Issue.title)
    ).all()
    return templates.TemplateResponse(
        request,
        "todos/list.html",
        {
            "current_user": current_user,
            "todos": todos,
            "org_users": org_users,
            "org_issues": org_issues,
            "TodoStatus": TodoStatus,
        },
    )


@router.post("")
def create_todo(
    request: Request,
    title: str = Form(...),
    owner_id: uuid.UUID = Form(...),
    issue_id: Optional[str] = Form(default=None),
    due_date: Optional[date] = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)
    owner = db.get(User, owner_id)
    if owner is None or owner.org_id != current_user.org_id:
        raise HTTPException(status_code=404)

    resolved_issue_id = uuid.UUID(issue_id) if issue_id else None
    if resolved_issue_id is not None:
        issue = db.get(Issue, resolved_issue_id)
        if issue is None or issue.team.org_id != current_user.org_id:
            raise HTTPException(status_code=404)

    todo = Todo(
        title=title, owner_id=owner_id, issue_id=resolved_issue_id, due_date=due_date
    )
    db.add(todo)
    db.commit()
    db.refresh(todo)
    return templates.TemplateResponse(
        request,
        "todos/_row.html",
        {"current_user": current_user, "todo": todo, "TodoStatus": TodoStatus},
    )


@router.patch("/{todo_id}/status")
def update_todo_status(
    request: Request,
    todo_id: uuid.UUID,
    status: TodoStatus = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    todo = db.scalar(
        select(Todo)
        .join(User, Todo.owner_id == User.id)
        .where(Todo.id == todo_id, User.org_id == current_user.org_id)
        .options(joinedload(Todo.owner), joinedload(Todo.issue))
    )
    if todo is None:
        raise HTTPException(status_code=404)
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)

    todo.status = status
    db.commit()
    db.refresh(todo)
    return templates.TemplateResponse(
        request,
        "todos/_row.html",
        {"current_user": current_user, "todo": todo, "TodoStatus": TodoStatus},
    )
