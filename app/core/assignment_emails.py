"""Emails sent when someone is made the owner of a To-Do or Rock.

Routes queue these as background tasks after their own commit, so each one
opens its own session. The person who made the change is never emailed about
it, and the recipient's role and choices are applied by notify().
"""

from typing import Optional
import uuid

from app.config import settings
from app.core.notifications import notify
from app.db import SessionLocal
from app.models import Rock, Todo, User


def one_line(text: str) -> str:
    """Collapses whitespace so user text is safe in an email subject."""
    return " ".join(text.split())


def send_todo_assigned(todo_id: uuid.UUID, actor_id: uuid.UUID, event_id: str) -> None:
    with SessionLocal() as db:
        todo = db.get(Todo, todo_id)
        actor = db.get(User, actor_id)
        if todo is None or todo.owner_id == actor_id:
            return
        notify(
            db,
            todo.owner,
            "todo_assigned",
            subject_line=f"New To-Do: {one_line(todo.title)}",
            template="todo_assigned",
            context={
                "title": todo.title,
                "team": todo.team.name,
                "due": todo.due_date.strftime("%A, %B %d").replace(" 0", " ") if todo.due_date else "",
                "assigned_by": actor.name if actor else "Someone",
                "link": settings.absolute_url("/todos"),
            },
            subject=f"todo:{todo.id}",
            # One per assignment: handing it to the same person again later is a new event.
            period=event_id,
        )


def send_rock_assigned(rock_id: uuid.UUID, actor_id: uuid.UUID, event_id: str) -> None:
    with SessionLocal() as db:
        rock = db.get(Rock, rock_id)
        actor = db.get(User, actor_id)
        if rock is None or rock.owner_id == actor_id:
            return
        notify(
            db,
            rock.owner,
            "rock_assigned",
            subject_line=f"New Rock: {one_line(rock.title)}",
            template="rock_assigned",
            context={
                "title": rock.title,
                "team": rock.team.name,
                "quarter": rock.quarter,
                "assigned_by": actor.name if actor else "Someone",
                "link": settings.absolute_url("/rocks"),
            },
            subject=f"rock:{rock.id}",
            period=event_id,
        )


def new_event_id() -> str:
    return uuid.uuid4().hex


def should_notify(previous_owner: Optional[uuid.UUID], new_owner: uuid.UUID) -> bool:
    """For edits: only when the owner actually changed (None = a new item)."""
    return settings.email_enabled and previous_owner != new_owner
