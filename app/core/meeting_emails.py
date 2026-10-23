"""Meeting invitations, cancellations and reminders (and the iCalendar events
behind them). Invites and cancellations are queued by the routes after their
commit; reminders are sent by the worker."""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core import ical
from app.core.assignment_emails import one_line
from app.core.email import Attachment
from app.core.notifications import notify
from app.core.org_time import format_short, format_when, tz_of
from app.db import SessionLocal
from app.models import Meeting, MeetingStatus, Team, TeamMembership, User

# (notification type, how far ahead it goes out, earliest it still goes out, wording)
# A meeting made with less notice than the window gets no reminder: its invitation is the notice.
REMINDERS = [
    ("meeting_reminder", timedelta(hours=24), timedelta(hours=22), "tomorrow"),
    ("meeting_reminder_1h", timedelta(hours=1), timedelta(minutes=30), "in about an hour"),
]


def event_for(meeting: Meeting, team: Team) -> ical.Event:
    link = settings.absolute_url("/meetings") if settings.base_url else ""
    return ical.Event(
        uid=f"{meeting.ical_uid}@traction-app",
        sequence=meeting.ical_sequence,
        start=meeting.scheduled_start,
        duration_minutes=meeting.duration_minutes,
        summary=f"{team.name} meeting",
        description=f"Team meeting. Open Traction: {link}" if link else "Team meeting.",
        location=meeting.location or "",
        url=link,
        cancelled=meeting.status == MeetingStatus.CANCELED,
    )


def calendar_file(meeting: Meeting, team: Team, method: str, attendee: Optional[User] = None) -> bytes:
    return ical.build_calendar(
        [event_for(meeting, team)],
        method=method,
        organizer=(settings.smtp_from_name or "Traction", settings.smtp_from_address) if settings.smtp_from_address else None,
        attendee=(attendee.name, attendee.email) if attendee else None,
    )


def member_ids(db: Session, team_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(TeamMembership.user_id)
            .join(User, User.id == TeamMembership.user_id)
            .where(TeamMembership.team_id == team_id)
            .order_by(User.name)
        )
    )


def _details(meeting: Meeting, team: Team, tz) -> dict:
    return {
        "team": team.name,
        "when": format_when(meeting.scheduled_start, meeting.duration_minutes, tz),
        "location": meeting.location or "",
        "link": settings.absolute_url("/meetings"),
    }


def send_meeting_invites(meeting_id: uuid.UUID, sequence: int) -> None:
    """Invites everyone on the team (or tells them of a change, when sequence > 0)."""
    with SessionLocal() as db:
        meeting = db.get(Meeting, meeting_id)
        # Only the latest version goes out; an older queued one is stale.
        if meeting is None or meeting.status != MeetingStatus.SCHEDULED or meeting.ical_sequence != sequence:
            return
        team = meeting.team
        org = team.organization
        tz = tz_of(org.timezone)
        details = _details(meeting, team, tz)
        event = event_for(meeting, team)
        details["updated"] = sequence > 0
        if org.calendar_web_links:
            details["google_url"], details["outlook_url"] = ical.google_link(event), ical.outlook_link(event)
        subject = f"{'Updated: ' if sequence else ''}{one_line(team.name)} meeting, {format_short(meeting.scheduled_start, tz)}"
        for user_id in member_ids(db, team.id):
            user = db.get(User, user_id)
            meeting = db.get(Meeting, meeting_id)
            attachment = Attachment(
                "meeting.ics", calendar_file(meeting, meeting.team, ical.REQUEST, user), "text", "calendar",
                {"method": ical.REQUEST, "charset": "UTF-8"},
            )
            notify(
                db, user, "meeting_invite", subject_line=subject, template="meeting_invite",
                context=details, subject=f"meeting:{meeting_id}", period=str(sequence),
                attachments=[attachment],
            )


def send_meeting_cancelled(meeting_id: uuid.UUID, sequence: int) -> None:
    with SessionLocal() as db:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None or meeting.status != MeetingStatus.CANCELED or meeting.ical_sequence != sequence:
            return
        team = meeting.team
        tz = tz_of(team.organization.timezone)
        details = _details(meeting, team, tz)
        subject = f"Cancelled: {one_line(team.name)} meeting, {format_short(meeting.scheduled_start, tz)}"
        for user_id in member_ids(db, team.id):
            user = db.get(User, user_id)
            meeting = db.get(Meeting, meeting_id)
            attachment = Attachment(
                "meeting.ics", calendar_file(meeting, meeting.team, ical.CANCEL, user), "text", "calendar",
                {"method": ical.CANCEL, "charset": "UTF-8"},
            )
            notify(
                db, user, "meeting_cancelled", subject_line=subject, template="meeting_cancelled",
                context=details, subject=f"meeting:{meeting_id}", period=str(sequence),
                attachments=[attachment],
            )


def send_meeting_reminders(db: Session, now: datetime) -> int:
    """Reminders for meetings coming up. Safe to run every minute: each person
    gets each reminder once per meeting version (rescheduling reminds again)."""
    if not settings.email_enabled:
        return 0
    sent = 0
    for key, ahead, earliest, lead in REMINDERS:
        meetings = db.scalars(
            select(Meeting).where(
                Meeting.status == MeetingStatus.SCHEDULED,
                Meeting.scheduled_start > now + earliest,
                Meeting.scheduled_start <= now + ahead,
            )
        ).all()
        # Plain data first: notify() commits, which would expire the ORM objects.
        jobs = []
        for meeting in meetings:
            team = meeting.team
            tz = tz_of(team.organization.timezone)
            jobs.append(
                (
                    meeting.id, meeting.ical_sequence, member_ids(db, team.id),
                    {**_details(meeting, team, tz), "lead": lead},
                    f"Reminder: {one_line(team.name)} meeting {lead}, {format_short(meeting.scheduled_start, tz)}",
                )
            )
        for meeting_id, sequence, user_ids, details, subject in jobs:
            for user_id in user_ids:
                result = notify(
                    db, db.get(User, user_id), key, subject_line=subject, template="meeting_reminder",
                    context=details, subject=f"meeting:{meeting_id}", period=str(sequence),
                )
                sent += result.sent
    return sent
