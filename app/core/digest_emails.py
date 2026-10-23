"""Sending the weekly summary, and deciding when this week's is due."""

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.digest import build_digest, monday_of, week_key
from app.core.notifications import notify
from app.core.org_time import local_to_utc, to_local, tz_of
from app.db import SessionLocal
from app.models import Organization, User

STEP_MINUTES = 15  # the schedule is set in quarter-hours
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def scheduled_moment(org: Organization, now: datetime) -> tuple[datetime, str]:
    """This week's send time for the organization (as a UTC moment), and the
    week's label. "This week" runs Monday to Sunday by the organization's clock,
    so a Sunday schedule is the end of the week it belongs to."""
    tz = tz_of(org.timezone)
    local_today = to_local(now, tz).date()
    day = monday_of(local_today) + timedelta(days=org.digest_weekday)
    return local_to_utc(day, org.digest_time, tz), week_key(day)


def digest_due(org: Organization, now: datetime) -> tuple[bool, str]:
    """(is it time, this week's label). Once the moment has passed it stays due
    for the rest of the week, so a worker that was down at the time still sends
    on its next tick; the per-person record stops a second send."""
    moment, label = scheduled_moment(org, now)
    return now >= moment, label


def send_digest_now(org_id: uuid.UUID) -> None:
    """The admin's "send it now": counts as this week's summary, so the scheduled
    run later finds everyone already done and sends nothing more."""
    with SessionLocal() as db:
        org = db.get(Organization, org_id)
        now = datetime.now(timezone.utc)
        _, label = scheduled_moment(org, now)
        send_digests(db, org_id, to_local(now, tz_of(org.timezone)).date(), label)


def send_digests(db: Session, org_id: uuid.UUID, today: date, label: str) -> int:
    """Emails everyone in the organization who has something in this week's
    summary. `label` is the week (e.g. 2026-W44): a person gets at most one per
    label, however many times this runs. Returns how many went out."""
    if not settings.email_enabled:
        return 0
    user_ids = list(db.scalars(select(User.id).where(User.org_id == org_id).order_by(User.name)))
    sent = 0
    for user_id in user_ids:
        user = db.get(User, user_id)
        digest = build_digest(db, user, today)
        if digest.is_empty:
            continue
        monday = monday_of(today)
        result = notify(
            db,
            user,
            "weekly_digest",
            subject_line=f"Your weekly summary, week of {monday.strftime('%b')} {monday.day}",
            template="weekly_digest",
            context={
                "digest": digest,
                "link": settings.absolute_url("/"),
                "todos_link": settings.absolute_url("/todos"),
                "rocks_link": settings.absolute_url("/rocks"),
                "scorecards_link": settings.absolute_url("/scorecards"),
            },
            period=label,
        )
        sent += result.sent
    return sent
