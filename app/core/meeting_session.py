"""Running a live meeting: six timed steps driven from the sidebar.

The state lives on the Meeting row (see the model) as timestamps, never as a
ticking counter, so a page reload, a second tab or a sleeping laptop can't
make the clocks drift - the browser just recomputes from the numbers here.

Steps run in order: only the furthest step reached and the ones before it
can be started. Starting a step pauses whichever one was running, so only
one clock runs at a time. Stopping the current step moves on to the next and
starts it. The final Stop freezes everything; Finish closes the session.
"""

import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Meeting, MeetingStatus

# (label, page it opens, minutes allotted)
STEPS = [
    ("Segue", "/", 5),
    ("Rocks", "/rocks", 5),
    ("Scorecard", "/scorecards", 5),
    ("Issues", "/issues", 60),
    ("To-Dos", "/todos", 10),
    ("Closing", "/meetings", 5),
]
TOTAL_SECONDS = sum(minutes for _, _, minutes in STEPS) * 60
LAST_STEP = len(STEPS) - 1


class SessionError(Exception):
    """The requested move isn't allowed right now (the route turns it into a 409)."""


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def active_meeting(db: Session, team_id: uuid.UUID) -> Optional[Meeting]:
    return db.scalar(
        select(Meeting)
        .where(Meeting.team_id == team_id, Meeting.status == MeetingStatus.IN_PROGRESS)
        .order_by(Meeting.started_at.desc().nulls_last())
    )


def start(db: Session, team_id: uuid.UUID, now: datetime) -> Meeting:
    """Begin a meeting for the team and start the first step. Reuses a meeting
    already scheduled for today, else records a new one; if one is already
    running it's left as it is."""
    meeting = active_meeting(db, team_id)
    if meeting is not None:
        return meeting
    today = date.today()
    meeting = db.scalar(
        select(Meeting).where(
            Meeting.team_id == team_id,
            Meeting.status == MeetingStatus.SCHEDULED,
            Meeting.scheduled_date == today,
        )
    )
    if meeting is None:
        meeting = Meeting(team_id=team_id, scheduled_date=today)
        db.add(meeting)
    meeting.status = MeetingStatus.IN_PROGRESS
    meeting.started_at = now
    meeting.finished_at = None
    meeting.stopped_at = None
    meeting.step_seconds = [0] * len(STEPS)
    meeting.current_step = 0
    meeting.running_step = 0
    meeting.running_since = now
    return meeting


def _bank(meeting: Meeting, now: datetime) -> None:
    """Pause whichever step is running, banking the time it ran."""
    if meeting.running_step is not None and meeting.running_since is not None:
        seconds = list(meeting.step_seconds)
        seconds[meeting.running_step] += max(0, int((now - meeting.running_since).total_seconds()))
        meeting.step_seconds = seconds
    meeting.running_step = None
    meeting.running_since = None


def _check_open(meeting: Meeting, step: int) -> None:
    if meeting.stopped_at is not None:
        raise SessionError("The meeting has been stopped.")
    if not 0 <= step <= (meeting.current_step or 0):
        raise SessionError("That step isn't available yet.")


def toggle(meeting: Meeting, step: int, now: datetime) -> bool:
    """Pause the step if it's running, otherwise (re)start it. True if it's
    now running."""
    _check_open(meeting, step)
    if meeting.running_step == step:
        _bank(meeting, now)
        return False
    _bank(meeting, now)
    meeting.running_step = step
    meeting.running_since = now
    return True


def stop_step(meeting: Meeting, step: int, now: datetime) -> Optional[int]:
    """Stop a step. When it's the furthest one reached, move on and start the
    next; returns that step's index (None if nothing was started)."""
    _check_open(meeting, step)
    _bank(meeting, now)
    if step == meeting.current_step and step < LAST_STEP:
        meeting.current_step = step + 1
        meeting.running_step = step + 1
        meeting.running_since = now
        return step + 1
    return None


def stop(meeting: Meeting, now: datetime) -> None:
    """The final Stop: freeze every counter."""
    if meeting.stopped_at is None:
        _bank(meeting, now)
        meeting.stopped_at = now


def finish(meeting: Meeting, now: datetime) -> None:
    stop(meeting, now)
    meeting.finished_at = now
    meeting.status = MeetingStatus.COMPLETED


def elapsed(meeting: Meeting, step: int, now: datetime) -> int:
    """Whole seconds a step has run, including the stretch in progress."""
    seconds = list(meeting.step_seconds or [])
    total = seconds[step] if step < len(seconds) else 0
    if meeting.running_step == step and meeting.running_since is not None:
        total += max(0, int((now - meeting.running_since).total_seconds()))
    return total


def total_elapsed(meeting: Meeting, now: datetime) -> int:
    return sum(elapsed(meeting, i, now) for i in range(len(STEPS)))


def step_url(step: int) -> str:
    return STEPS[step][1]


def view(meeting: Meeting, now: datetime) -> dict[str, Any]:
    """What the sidebar needs to draw (and tick) the session."""
    reached = meeting.current_step or 0
    frozen = meeting.stopped_at is not None
    steps = []
    for i, (label, url, minutes) in enumerate(STEPS):
        running = meeting.running_step == i
        steps.append(
            {
                "index": i,
                "label": label,
                "url": url,
                "allotted": minutes * 60,
                "base": (meeting.step_seconds or [0] * len(STEPS))[i],
                "since_ms": int(meeting.running_since.timestamp() * 1000) if running and meeting.running_since else None,
                "running": running,
                "enabled": not frozen and i <= reached,
                "current": i == reached and not frozen,
                "can_advance": not frozen and i == reached and i < LAST_STEP,
                "done": i < reached or frozen and elapsed(meeting, i, now) > 0,
            }
        )
    return {
        "meeting_id": meeting.id,
        "steps": steps,
        "stopped": frozen,
        "now_ms": int(now.timestamp() * 1000),
        "total_allotted": TOTAL_SECONDS,
        "total_elapsed": total_elapsed(meeting, now),
    }
