import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models import Issue, Todo, TodoStatus, User, UserRole
from app.web.deps import get_current_user_web, get_team_context
from app.web.notes import clean_notes, notes_form_response
from app.web.team_context import TeamContext
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


def _require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403)


def _get_org_todo(db: Session, todo_id: uuid.UUID, org_id: uuid.UUID) -> Todo:
    todo = db.scalar(_org_todos_query(org_id).where(Todo.id == todo_id))
    if todo is None:
        raise HTTPException(status_code=404)
    return todo


def _org_users(db: Session, org_id: uuid.UUID):
    return db.scalars(select(User).where(User.org_id == org_id).order_by(User.name)).all()


def _team_issues(db: Session, team_ctx: TeamContext):
    return db.scalars(
        select(Issue).where(Issue.team_id.in_(team_ctx.team_ids)).order_by(Issue.title)
    ).all()


def _resolve_issue_id(
    db: Session, issue_id: Optional[str], team_ctx: TeamContext
) -> Optional[uuid.UUID]:
    if not issue_id:
        return None
    resolved = uuid.UUID(issue_id)
    issue = db.get(Issue, resolved)
    if issue is None or issue.team_id not in team_ctx.team_ids:
        raise HTTPException(status_code=404)
    return resolved


def _row_response(request: Request, current_user: User, todo: Todo):
    return templates.TemplateResponse(
        request,
        "todos/_row.html",
        {"current_user": current_user, "todo": todo, "TodoStatus": TodoStatus},
    )


@router.get("")
def list_todos(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    todos = db.scalars(_org_todos_query(current_user.org_id)).unique().all()
    return templates.TemplateResponse(
        request,
        "todos/list.html",
        {
            "current_user": current_user,
            "todos": todos,
            "org_users": _org_users(db, current_user.org_id),
            "org_issues": _team_issues(db, team_ctx),
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
    team_ctx: TeamContext = Depends(get_team_context),
):
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)
    owner = db.get(User, owner_id)
    if owner is None or owner.org_id != current_user.org_id:
        raise HTTPException(status_code=404)
    title = title.strip()
    if not title or len(title) > 255:
        raise HTTPException(status_code=422)
    resolved_issue_id = _resolve_issue_id(db, issue_id, team_ctx)

    todo = Todo(
        title=title, owner_id=owner_id, issue_id=resolved_issue_id, due_date=due_date
    )
    db.add(todo)
    db.commit()
    return _row_response(request, current_user, _get_org_todo(db, todo.id, current_user.org_id))


@router.patch("/{todo_id}/status")
def update_todo_status(
    request: Request,
    todo_id: uuid.UUID,
    status: TodoStatus = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    todo = _get_org_todo(db, todo_id, current_user.org_id)
    if not _can_edit_todo(current_user, todo):
        raise HTTPException(status_code=403)

    todo.status = status
    db.commit()
    db.refresh(todo)
    return _row_response(request, current_user, todo)


@router.get("/{todo_id}")
def get_todo_row(
    request: Request,
    todo_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    return _row_response(request, current_user, _get_org_todo(db, todo_id, current_user.org_id))


@router.get("/{todo_id}/edit")
def edit_todo_row(
    request: Request,
    todo_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    _require_admin(current_user)
    todo = _get_org_todo(db, todo_id, current_user.org_id)
    return templates.TemplateResponse(
        request,
        "todos/_edit_row.html",
        {
            "current_user": current_user,
            "todo": todo,
            "org_users": _org_users(db, current_user.org_id),
            "org_issues": _team_issues(db, team_ctx),
            "TodoStatus": TodoStatus,
        },
    )


@router.put("/{todo_id}")
def update_todo(
    request: Request,
    todo_id: uuid.UUID,
    title: str = Form(...),
    owner_id: uuid.UUID = Form(...),
    issue_id: Optional[str] = Form(default=None),
    due_date: Optional[date] = Form(default=None),
    status: TodoStatus = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    _require_admin(current_user)
    todo = _get_org_todo(db, todo_id, current_user.org_id)
    title = title.strip()
    if not title or len(title) > 255:
        raise HTTPException(status_code=422)
    owner = db.get(User, owner_id)
    if owner is None or owner.org_id != current_user.org_id:
        raise HTTPException(status_code=404)
    resolved_issue_id = _resolve_issue_id(db, issue_id, team_ctx)

    todo.title = title
    todo.owner_id = owner_id
    todo.issue_id = resolved_issue_id
    todo.due_date = due_date
    todo.status = status
    db.commit()
    db.expire_all()
    return _row_response(request, current_user, _get_org_todo(db, todo_id, current_user.org_id))


@router.delete("/{todo_id}")
def delete_todo(
    todo_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    todo = _get_org_todo(db, todo_id, current_user.org_id)
    db.delete(todo)
    db.commit()
    return Response(status_code=200)


def _can_edit_todo(current_user: User, todo: Todo) -> bool:
    # Admins: any to-do. Members: only their own (same rule as status).
    return current_user.role == UserRole.ADMIN or (
        current_user.role == UserRole.MEMBER and todo.owner_id == current_user.id
    )


@router.get("/{todo_id}/notes")
def get_todo_notes(
    request: Request,
    todo_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    todo = _get_org_todo(db, todo_id, current_user.org_id)
    return notes_form_response(
        request,
        subject=todo.title,
        url=f"/todos/{todo.id}/notes",
        row_id=f"todo-row-{todo.id}",
        notes=todo.notes,
        can_edit=_can_edit_todo(current_user, todo),
    )


@router.put("/{todo_id}/notes")
def update_todo_notes(
    request: Request,
    todo_id: uuid.UUID,
    notes: str = Form(default=""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    todo = _get_org_todo(db, todo_id, current_user.org_id)
    if not _can_edit_todo(current_user, todo):
        raise HTTPException(status_code=403)
    todo.notes = clean_notes(notes)
    db.commit()
    db.expire_all()
    return _row_response(request, current_user, _get_org_todo(db, todo_id, current_user.org_id))
