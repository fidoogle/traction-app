"""Activity log: records who added, edited or deleted what.

Rather than every route remembering to write a log entry, a before_flush
hook on the session inspects what's about to be inserted/updated/deleted
and writes ActivityLog rows in the same transaction. The auth dependencies
stamp the signed-in user onto the session (set_actor); sessions with no
actor - seed/bootstrap scripts, migrations - aren't logged.
"""

import enum
import uuid
from datetime import date
from typing import Any, Optional

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.models import (
    VTO,
    ActivityLog,
    Issue,
    Measurable,
    Meeting,
    Organization,
    PeopleAnalyzerEntry,
    Rock,
    ScorecardEntry,
    Seat,
    Team,
    Todo,
    User,
)
from app.models.base import Base

ACTOR_KEY = "activity_actor"

# entity_type key -> (display name, page it lives on)
ENTITY_TYPES: dict[str, tuple[str, Optional[str]]] = {
    "rock": ("rock", "/rocks"),
    "issue": ("issue", "/issues"),
    "todo": ("to-do", "/todos"),
    "measurable": ("measurable", "/scorecard"),
    "scorecard_entry": ("scorecard entry", "/scorecard"),
    "meeting": ("meeting", "/meetings"),
    "seat": ("seat", "/seats"),
    "vto": ("VTO", "/vto"),
    "people_analyzer_entry": ("People Analyzer entry", "/people-analyzer"),
    "team": ("team", "/teams"),
    "user": ("user", "/users"),
    "organization": ("organization", None),
}

_MODEL_TYPES: dict[type, str] = {
    Rock: "rock",
    Issue: "issue",
    Todo: "todo",
    Measurable: "measurable",
    ScorecardEntry: "scorecard_entry",
    Meeting: "meeting",
    Seat: "seat",
    VTO: "vto",
    PeopleAnalyzerEntry: "people_analyzer_entry",
    Team: "team",
    User: "user",
    Organization: "organization",
}

# Bookkeeping, not something anyone "did" - a change to only these isn't logged.
_IGNORED_FIELDS = {"id", "activity_last_seen_at"}
# Logged as changed, but the value itself is never written to the log.
_SECRET_FIELDS = {"hashed_password"}

_FIELD_NAMES = {
    "owner_id": "Owner",
    "user_id": "Person",
    "team_id": "Team",
    "issue_id": "Related issue",
    "measurable_id": "Measurable",
    "seat_id": "Seat",
    "parent_seat_id": "Reports to",
    "goal_value": "Goal",
    "actual_value": "Actual",
    "hashed_password": "Password",
    "gets_it": "Gets it",
    "wants_it": "Wants it",
    "has_capacity": "Capacity",
    "core_focus_purpose": "Core focus (purpose)",
    "core_focus_niche": "Core focus (niche)",
    "ten_year_target": "10-year target",
    "three_year_picture": "3-year picture",
    "one_year_plan": "1-year plan",
}

_MAX_VALUE_LENGTH = 60


def set_actor(db: Session, user: User) -> None:
    """Attribute this session's writes to user. Called by the auth deps."""
    db.info[ACTOR_KEY] = (user.id, user.org_id, user.name)


def _field_name(key: str) -> str:
    if key in _FIELD_NAMES:
        return _FIELD_NAMES[key]
    return key.removesuffix("_id").replace("_", " ").capitalize()


def _fmt_date(d: date) -> str:
    return f"{d:%b} {d.day}, {d.year}"


def _label(db: Session, obj: Any) -> str:
    if isinstance(obj, (Rock, Issue, Todo, Seat)):
        return obj.title
    if isinstance(obj, (Team, User, Measurable, Organization)):
        return obj.name
    if isinstance(obj, Meeting):
        team = db.get(Team, obj.team_id) if obj.team_id else None
        when = _fmt_date(obj.scheduled_date) if obj.scheduled_date else ""
        return f"{team.name if team else 'Team'} meeting {when}".strip()
    if isinstance(obj, ScorecardEntry):
        measurable = db.get(Measurable, obj.measurable_id) if obj.measurable_id else None
        name = measurable.name if measurable else "Scorecard"
        return f"{name}, week ending {_fmt_date(obj.week_ending)}" if obj.week_ending else name
    if isinstance(obj, PeopleAnalyzerEntry):
        person = db.get(User, obj.user_id) if obj.user_id else None
        seat = db.get(Seat, obj.seat_id) if obj.seat_id else None
        return " / ".join(x for x in (person and person.name, seat and seat.title) if x)
    if isinstance(obj, VTO):
        return "Vision/Traction Organizer"
    return ""


def _fk_target(column) -> Optional[type]:
    for fk in column.foreign_keys:
        for mapper in Base.registry.mappers:
            if mapper.local_table is fk.column.table:
                return mapper.class_
    return None


def _fmt_value(db: Session, column, value: Any) -> Optional[str]:
    """A short display string, or None if the value isn't worth spelling out."""
    if value is None:
        return "none"
    if isinstance(value, uuid.UUID):
        target = _fk_target(column)
        related = db.get(target, value) if target else None
        return _label(db, related) if related is not None else None
    if isinstance(value, enum.Enum):
        return str(value.value).replace("_", " ").title()
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, date):
        return _fmt_date(value)
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, (int, str)):
        text = str(value)
        return text if len(text) <= _MAX_VALUE_LENGTH and "\n" not in text else None
    return None  # lists / dicts (JSONB) - just say the field changed


def _changes(db: Session, obj: Any) -> list[str]:
    state = inspect(obj)
    lines = []
    for attr in state.mapper.column_attrs:
        key = attr.key
        if key in _IGNORED_FIELDS:
            continue
        history = state.attrs[key].history
        if not history.has_changes():
            continue
        old = history.deleted[0] if history.deleted else None
        new = history.added[0] if history.added else None
        if old == new and history.deleted:
            continue
        name = _field_name(key)
        if key in _SECRET_FIELDS:
            lines.append(f"{name} changed")
        elif key == "notes":
            lines.append("Notes cleared" if not new else ("Notes added" if not old else "Notes edited"))
        else:
            column = attr.columns[0]
            new_text = _fmt_value(db, column, new)
            old_text = _fmt_value(db, column, old) if history.deleted else None
            if new_text is None:
                lines.append(f"{name} updated")
            elif old_text is None:
                lines.append(f"{name}: {new_text}")
            else:
                lines.append(f"{name}: {old_text} → {new_text}")
    return lines


def _entry(db: Session, actor, action: str, obj: Any, changes: list[str]) -> ActivityLog:
    actor_id, org_id, actor_name = actor
    return ActivityLog(
        org_id=org_id,
        actor_id=actor_id,
        actor_name=actor_name,
        action=action,
        entity_type=_MODEL_TYPES[type(obj)],
        entity_id=obj.id,
        entity_label=(_label(db, obj) or "(untitled)")[:255],
        changes=changes,
    )


def _before_flush(db: Session, flush_context, instances) -> None:
    actor = db.info.get(ACTOR_KEY)
    if actor is None:
        return
    entries = []
    for obj in db.new:
        if type(obj) in _MODEL_TYPES:
            if obj.id is None:
                # Normally assigned at INSERT time; needed now for entity_id.
                obj.id = uuid.uuid4()
            entries.append(_entry(db, actor, "created", obj, []))
    for obj in db.dirty:
        if type(obj) in _MODEL_TYPES and db.is_modified(obj, include_collections=False):
            changes = _changes(db, obj)
            if changes:
                entries.append(_entry(db, actor, "updated", obj, changes))
    for obj in db.deleted:
        if type(obj) in _MODEL_TYPES:
            entries.append(_entry(db, actor, "deleted", obj, []))
    db.add_all(entries)


def register(session_factory) -> None:
    event.listen(session_factory, "before_flush", _before_flush)
