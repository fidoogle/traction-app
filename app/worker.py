"""Background worker: the emails that go out on a clock, not in reply to a click.

Run as its own container (`python -m app.worker`, see docker-compose.yml). Run
exactly one of it. Every job is safe to repeat - notify() records what it sent -
so a restart or a late start just catches up.
"""

import logging
import signal
import threading
import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select

from app.config import settings
from app.core.digest_emails import digest_due, send_digests
from app.core.due_emails import send_due_todos
from app.core.meeting_emails import send_meeting_reminders
from app.core.org_time import to_local, tz_of
from app.db import SessionLocal
from app.models import Organization

logger = logging.getLogger("app.worker")

TICK_SECONDS = 60
TODO_DUE_HOUR = 7  # local time; the day's To-Do email goes out from here on


@dataclass
class WorkerState:
    """What this process has already done today, to avoid re-checking every tick."""

    todo_due_dates: dict[uuid.UUID, date] = field(default_factory=dict)  # per organization
    digest_weeks: dict[uuid.UUID, str] = field(default_factory=dict)  # week label last sent, per organization


def tick(state: WorkerState, now: Optional[datetime] = None) -> None:
    if not settings.email_enabled:
        return
    now = now or datetime.now(timezone.utc)

    with SessionLocal() as db:
        orgs = [
            SimpleNamespace(
                id=o.id, timezone=o.timezone, digest_weekday=o.digest_weekday, digest_time=o.digest_time
            )
            for o in db.scalars(select(Organization))
        ]

    # Each organization has its own clock, so "7:00" is 7:00 where they are.
    for org in orgs:
        org_id = org.id
        local = now.astimezone(tz_of(org.timezone))
        if local.hour >= TODO_DUE_HOUR and state.todo_due_dates.get(org_id) != local.date():
            try:
                with SessionLocal() as db:
                    sent = send_due_todos(db, local.date(), org_id)
                logger.info("To-Do due emails for one organization: %d sent", sent)
                state.todo_due_dates[org_id] = local.date()
            except Exception:
                logger.exception("To-Do due job failed; will retry next tick")

        # The weekly summary: once this week's moment (set by the admin) has passed,
        # until it has gone out. The per-person record stops a second send.
        due, label = digest_due(org, now)
        if due and state.digest_weeks.get(org_id) != label:
            try:
                with SessionLocal() as db:
                    sent = send_digests(db, org_id, to_local(now, tz_of(org.timezone)).date(), label)
                logger.info("Weekly summaries %s: %d sent", label, sent)
                state.digest_weeks[org_id] = label
            except Exception:
                logger.exception("Weekly summary job failed; will retry next tick")

    try:
        with SessionLocal() as db:
            sent = send_meeting_reminders(db, now)
        if sent:
            logger.info("Meeting reminders: %d sent", sent)
    except Exception:
        logger.exception("Meeting reminder job failed; will retry next tick")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    logger.info("Worker started (email %s)", "on" if settings.email_enabled else "off - idle")
    state = WorkerState()
    while not stop.is_set():
        tick(state)
        stop.wait(TICK_SECONDS)
    logger.info("Worker stopped")


if __name__ == "__main__":
    main()
