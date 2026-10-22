"""Background worker: the emails that go out on a clock, not in reply to a click.

Run as its own container (`python -m app.worker`, see docker-compose.yml). Run
exactly one of it. Every job is safe to repeat - notify() records what it sent -
so a restart or a late start just catches up.
"""

import logging
import signal
import threading
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from app.config import settings
from app.core.due_emails import send_due_todos
from app.db import SessionLocal

logger = logging.getLogger("app.worker")

TICK_SECONDS = 60
TODO_DUE_HOUR = 7  # local time; the day's To-Do email goes out from here on


@dataclass
class WorkerState:
    """What this process has already done today, to avoid re-checking every tick."""

    todo_due_date: Optional[date] = None


def tick(state: WorkerState, now: Optional[datetime] = None) -> None:
    if not settings.email_enabled:
        return
    local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(settings.default_timezone))

    if local.hour >= TODO_DUE_HOUR and state.todo_due_date != local.date():
        try:
            with SessionLocal() as db:
                sent = send_due_todos(db, local.date())
            logger.info("To-Do due emails: %d sent", sent)
            state.todo_due_date = local.date()
        except Exception:
            logger.exception("To-Do due job failed; will retry next tick")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    logger.info(
        "Worker started (email %s, time zone %s)",
        "on" if settings.email_enabled else "off - idle",
        settings.default_timezone,
    )
    state = WorkerState()
    while not stop.is_set():
        tick(state)
        stop.wait(TICK_SECONDS)
    logger.info("Worker stopped")


if __name__ == "__main__":
    main()
