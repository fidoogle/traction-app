"""The daily "your To-Dos are due" email."""

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.core.notifications import notify
from app.models import Todo, TodoStatus, User

DUE_WITHIN_DAYS = 2
MAX_ITEMS = 20  # the rest are summarised as "and N more"


def due_label(due: date, today: date) -> str:
    days = (due - today).days
    if days < 0:
        return "overdue by 1 day" if days == -1 else f"overdue by {-days} days"
    if days == 0:
        return "due today"
    if days == 1:
        return "due tomorrow"
    return "due " + due.strftime("%A, %B %d").replace(" 0", " ")


def send_due_todos(db: Session, today: date) -> int:
    """One email per person listing their open To-Dos that are due within two
    days or late. Safe to run repeatedly: notify() sends at most one per person
    per `today`. Returns how many emails went out."""
    if not settings.email_enabled:
        return 0
    todos = (
        db.scalars(
            select(Todo)
            .where(
                Todo.status == TodoStatus.OPEN,
                Todo.due_date.is_not(None),
                Todo.due_date <= today + timedelta(days=DUE_WITHIN_DAYS),
            )
            .options(joinedload(Todo.team))
            .order_by(Todo.due_date, Todo.title)
        )
        .unique()
        .all()
    )
    # Plain data first: notify() commits, which would expire the ORM objects.
    by_owner = defaultdict(list)
    for todo in todos:
        by_owner[todo.owner_id].append(
            {
                "title": todo.title,
                "team": todo.team.name,
                "when": due_label(todo.due_date, today),
                "overdue": todo.due_date < today,
            }
        )

    sent = 0
    link = settings.absolute_url("/todos")
    for owner_id, items in by_owner.items():
        owner = db.get(User, owner_id)
        count = len(items)
        result = notify(
            db,
            owner,
            "todo_due",
            subject_line=f"{count} To-Do{'s' if count != 1 else ''} due soon or overdue",
            template="todo_due",
            context={
                "items": items[:MAX_ITEMS],
                "more": max(0, count - MAX_ITEMS),
                "count": count,
                "link": link,
            },
            period=today.isoformat(),
        )
        sent += result.sent
    return sent
