"""Which emails exist, who may get them, and the one function that sends them.

The CATALOG below is the single list of notification types; everything else
(the "My notifications" page, notify(), later the scheduler jobs) reads it.

Nobody configures defaults. Each type says which kinds of people may receive it
(`audience`) and which of those get it switched on from the start
(`default_on`). People are described by "hats": their role (viewer / member /
admin) plus team_admin if they administer a team. A person's own toggles are
stored only where they differ from the default, so changing a default here
reaches everyone who hasn't chosen for themselves.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import delete, exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.email import Attachment, render_email, send_email
from app.models import NotificationLog, NotificationPreference, TeamMembership, User

logger = logging.getLogger("app.notifications")

VIEWER, MEMBER, TEAM_ADMIN, ADMIN = "viewer", "member", "team_admin", "admin"
EVERYONE = frozenset({VIEWER, MEMBER, TEAM_ADMIN, ADMIN})
# Viewers can't own anything, so they get no emails about owning things.
OWNERS = frozenset({MEMBER, TEAM_ADMIN, ADMIN})
NOBODY: frozenset = frozenset()

# A claim on a notice that never finished (the process died mid-send) is
# treated as abandoned after this long, and may be retried.
PENDING_STALE_AFTER = timedelta(minutes=10)


@dataclass(frozen=True)
class NotificationType:
    key: str
    label: str
    description: str
    group: str
    audience: frozenset
    default_on: frozenset
    always: bool = False  # cannot be turned off


CATALOG: list[NotificationType] = [
    NotificationType(
        "account_welcome", "Account created",
        "The link to set your password when an account is made for you.",
        "Your account", EVERYONE, EVERYONE, always=True,
    ),
    NotificationType(
        "password_reset", "Password reset",
        "The link you ask for when you forget your password.",
        "Your account", EVERYONE, EVERYONE, always=True,
    ),
    NotificationType(
        "todo_assigned", "A To-Do is assigned to you", "When someone gives you a To-Do.",
        "Assignments", OWNERS, OWNERS,
    ),
    NotificationType(
        "rock_assigned", "A Rock is assigned to you",
        "When someone makes you the owner of a Rock, new or existing.",
        "Assignments", OWNERS, OWNERS,
    ),
    NotificationType(
        "todo_due", "To-Dos due soon or overdue",
        "One email a day listing your To-Dos that are due within two days or late.",
        "Assignments", OWNERS, OWNERS,
    ),
    NotificationType(
        "meeting_invite", "Meeting scheduled or changed",
        "An invitation you can add to your calendar.",
        "Meetings", EVERYONE, EVERYONE,
    ),
    NotificationType(
        "meeting_cancelled", "Meeting cancelled", "When a scheduled meeting is called off.",
        "Meetings", EVERYONE, EVERYONE,
    ),
    NotificationType(
        "meeting_reminder", "Meeting reminder, the day before",
        "A reminder 24 hours before your team's meeting.",
        "Meetings", EVERYONE, EVERYONE,
    ),
    NotificationType(
        "meeting_reminder_1h", "Meeting reminder, one hour before",
        "A second reminder an hour before. Your calendar can also alert you on its own.",
        "Meetings", EVERYONE, NOBODY,
    ),
    NotificationType(
        "weekly_digest", "Weekly summary",
        "Your open To-Dos, Rocks that need attention and off-track scorecard items.",
        "Summaries", EVERYONE, EVERYONE,
    ),
    NotificationType(
        "meeting_summary", "Meeting recap",
        "After a meeting finishes: new To-Dos and the issues still open.",
        "Summaries", EVERYONE, NOBODY,
    ),
    NotificationType(
        "issue_added", "New issue on your team's list",
        "Each time someone adds an issue (grouped if several are added together).",
        "Summaries", EVERYONE, NOBODY,
    ),
    NotificationType(
        "rock_off_track", "A Rock goes off track",
        "When a Rock on a team you administer is marked off track.",
        "Team alerts", frozenset({TEAM_ADMIN, ADMIN}), frozenset({TEAM_ADMIN}),
    ),
    NotificationType(
        "scorecard_missed", "A scorecard goal is missed repeatedly",
        "When a measurable misses its goal two weeks in a row.",
        "Team alerts", OWNERS, NOBODY,
    ),
    NotificationType(
        "quarter_reminder", "Quarterly Rock-setting reminder",
        "At the start and end of each quarter.",
        "Team alerts", frozenset({TEAM_ADMIN, ADMIN}), frozenset({TEAM_ADMIN}),
    ),
    NotificationType(
        "admin_system", "System notices",
        "New users, role changes, and email delivery problems.",
        "Administration", frozenset({ADMIN}), NOBODY,
    ),
]
BY_KEY = {t.key: t for t in CATALOG}


def hats(db: Session, user: User) -> frozenset:
    found = {user.role.value}
    if user.role.value == MEMBER and db.scalar(
        select(
            exists().where(
                TeamMembership.user_id == user.id, TeamMembership.is_team_admin.is_(True)
            )
        )
    ):
        found.add(TEAM_ADMIN)
    return frozenset(found)


def eligible(nt: NotificationType, user_hats: Iterable[str]) -> bool:
    return bool(nt.audience & set(user_hats))


def default_for(nt: NotificationType, user_hats: Iterable[str]) -> bool:
    return nt.always or bool(nt.default_on & set(user_hats))


def types_for(db: Session, user: User) -> list[tuple[NotificationType, bool]]:
    """The types this person may receive, in catalog order, each with whether
    it is on for them (their own choice, else the default)."""
    user_hats = hats(db, user)
    chosen = {
        p.key: p.enabled
        for p in db.scalars(select(NotificationPreference).where(NotificationPreference.user_id == user.id))
    }
    return [
        (nt, True if nt.always else chosen.get(nt.key, default_for(nt, user_hats)))
        for nt in CATALOG
        if eligible(nt, user_hats)
    ]


def is_enabled(db: Session, user: User, key: str) -> bool:
    nt = BY_KEY[key]
    user_hats = hats(db, user)
    if not eligible(nt, user_hats):
        return False
    if nt.always:
        return True
    pref = db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user.id, NotificationPreference.key == key
        )
    )
    return pref.enabled if pref is not None else default_for(nt, user_hats)


def set_preference(db: Session, user: User, key: str, enabled: bool) -> None:
    """Records the person's choice; a choice equal to the default is not kept.
    Raises ValueError for a type they can't receive or can't turn off. Commits."""
    nt = BY_KEY.get(key)
    user_hats = hats(db, user)
    if nt is None or nt.always or not eligible(nt, user_hats):
        raise ValueError(key)
    existing = db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user.id, NotificationPreference.key == key
        )
    )
    if enabled == default_for(nt, user_hats):
        if existing is not None:
            db.delete(existing)
    elif existing is not None:
        existing.enabled = enabled
    else:
        db.add(NotificationPreference(user_id=user.id, key=key, enabled=enabled))
    db.commit()


@dataclass
class NotifyResult:
    status: str  # "sent", "failed" or "skipped"
    detail: str = ""

    @property
    def sent(self) -> bool:
        return self.status == "sent"


def prune_log(db: Session) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.notification_log_retention_days)
    count = db.execute(delete(NotificationLog).where(NotificationLog.created_at < cutoff)).rowcount
    db.commit()
    return count


_last_prune = 0.0


def _prune_now_and_then(db: Session) -> None:
    global _last_prune
    if time.monotonic() - _last_prune > 3600:
        _last_prune = time.monotonic()
        prune_log(db)


def notify(
    db: Session,
    user: User,
    key: str,
    *,
    subject_line: str,
    template: str,
    context: Optional[dict] = None,
    subject: str = "",
    period: str = "",
    attachments: Iterable[Attachment] = (),
) -> NotifyResult:
    """Emails one person about one thing, at most once.

    Skips (without error) when email isn't set up, the person's role can't get
    this type, or they turned it off. `subject` and `period` identify the
    occasion - e.g. subject="todo:<id>", or period="2026-W43" - and the same
    (person, type, subject, period) is never sent twice. A send that failed may
    be tried again by calling notify() again.

    This commits, so call it after the change it reports has been committed,
    never in the middle of a transaction.
    """
    nt = BY_KEY[key]
    if not settings.email_enabled:
        return NotifyResult("skipped", "email is not configured")
    user_hats = hats(db, user)
    if not eligible(nt, user_hats):
        return NotifyResult("skipped", "not available for this role")
    if not nt.always and not is_enabled(db, user, key):
        return NotifyResult("skipped", "turned off by the recipient")

    user_id, to, name = user.id, user.email, user.name
    row = db.scalar(
        select(NotificationLog).where(
            NotificationLog.user_id == user_id,
            NotificationLog.key == key,
            NotificationLog.subject == subject,
            NotificationLog.period == period,
        )
    )
    now = datetime.now(timezone.utc)
    if row is not None:
        in_flight = row.status == "pending" and now - row.created_at < PENDING_STALE_AFTER
        if row.status == "sent" or in_flight:
            return NotifyResult("skipped", "already sent")
        row.status, row.error = "pending", None  # retry a failed or abandoned one
    else:
        row = NotificationLog(user_id=user_id, key=key, subject=subject, period=period, status="pending")
        db.add(row)
    try:
        db.commit()
    except IntegrityError:  # someone else claimed it between our check and insert
        db.rollback()
        return NotifyResult("skipped", "already sent")

    try:
        text, html = render_email(
            template,
            name=name,
            preferences_url=settings.absolute_url("/notifications"),
            **(context or {}),
        )
        result = send_email(to, subject_line, text, html, attachments)
    except Exception as exc:  # a broken template must not leave the claim pending
        logger.exception("Rendering %s email failed", key)
        db.rollback()
        row = db.get(NotificationLog, row.id)
        row.status, row.error = "failed", f"{type(exc).__name__}: {exc}"[:500]
        db.commit()
        return NotifyResult("failed", row.error)

    row = db.get(NotificationLog, row.id)
    row.status = "sent" if result.ok else "failed"
    row.error = None if result.ok else result.error[:500]
    db.commit()
    _prune_now_and_then(db)
    return NotifyResult(row.status, row.error or "")
