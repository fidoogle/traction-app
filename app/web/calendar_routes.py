"""A person's private calendar subscription feed.

The address contains a secret token (User.calendar_token) instead of needing a
login, because calendar apps fetch it on their own. Whoever has the address can
see the team names, times and locations of that person's upcoming meetings -
and nothing else. The person can switch it off or replace the address on the
"My notifications" page.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.core import ical
from app.core.meeting_emails import event_for
from app.models import Meeting, MeetingStatus, User

router = APIRouter()

# Keep recent meetings so a meeting that has just started doesn't vanish mid-day.
LOOK_BACK = timedelta(days=1)
MAX_EVENTS = 300


@router.get("/calendar/{token}.ics")
def calendar_feed(token: str, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.calendar_token == token)) if token else None
    if user is None:
        raise HTTPException(status_code=404)
    team_ids = [m.team_id for m in user.memberships]
    meetings = db.scalars(
        select(Meeting)
        .options(joinedload(Meeting.team))
        .where(
            Meeting.team_id.in_(team_ids),
            Meeting.status == MeetingStatus.SCHEDULED,
            Meeting.scheduled_start >= datetime.now(timezone.utc) - LOOK_BACK,
        )
        .order_by(Meeting.scheduled_start)
        .limit(MAX_EVENTS)
    ).unique().all()
    body = ical.build_calendar(
        [event_for(m, m.team) for m in meetings], method=ical.PUBLISH, name="Traction meetings"
    )
    return Response(
        body,
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "private, no-store"},
    )
