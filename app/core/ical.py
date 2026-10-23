"""iCalendar (.ics) files for meetings, written by hand (RFC 5545) so there is
no extra library to vet. Times are always UTC ("...Z"); the calendar app shows
them in the viewer's own zone.

METHOD says what the file is for:
  REQUEST  an invitation or an update (same UID, higher SEQUENCE) - emailed
  CANCEL   a cancellation (same UID, higher SEQUENCE) - emailed
  PUBLISH  just an event to add, with no invitation workflow - downloads and feeds
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional
from urllib.parse import urlencode

PRODID = "-//Traction//Traction App//EN"
REQUEST, CANCEL, PUBLISH = "REQUEST", "CANCEL", "PUBLISH"
ALARM_MINUTES_BEFORE = 15


@dataclass
class Event:
    uid: str
    sequence: int
    start: datetime
    duration_minutes: int
    summary: str
    description: str = ""
    location: str = ""
    url: str = ""
    cancelled: bool = False

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=self.duration_minutes)


def escape_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def fold(line: str) -> str:
    """Lines may be at most 75 octets; longer ones continue on the next line
    after CRLF + one space. Never splits a multi-byte character."""
    if len(line.encode("utf-8")) <= 75:
        return line
    parts, current, size = [], "", 0
    limit = 75
    for ch in line:
        width = len(ch.encode("utf-8"))
        if size + width > limit:
            parts.append(current)
            current, size, limit = "", 0, 74  # continuation lines lose a byte to the leading space
        current += ch
        size += width
    parts.append(current)
    return "\r\n ".join(parts)


def utc_stamp(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _event_lines(
    event: Event,
    *,
    stamp: datetime,
    organizer: Optional[tuple[str, str]],
    attendee: Optional[tuple[str, str]],
    alarm: bool,
) -> list[str]:
    lines = [
        "BEGIN:VEVENT",
        f"UID:{event.uid}",
        f"SEQUENCE:{event.sequence}",
        f"DTSTAMP:{utc_stamp(stamp)}",
        f"DTSTART:{utc_stamp(event.start)}",
        f"DTEND:{utc_stamp(event.end)}",
        f"SUMMARY:{escape_text(event.summary)}",
    ]
    if event.description:
        lines.append(f"DESCRIPTION:{escape_text(event.description)}")
    if event.location:
        lines.append(f"LOCATION:{escape_text(event.location)}")
    if event.url:
        lines.append(f"URL:{event.url}")
    if organizer:
        name, address = organizer
        lines.append(f"ORGANIZER;CN={_param(name)}:mailto:{address}")
    if attendee:
        name, address = attendee
        lines.append(
            f"ATTENDEE;CN={_param(name)};ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=FALSE:mailto:{address}"
        )
    lines.append(f"STATUS:{'CANCELLED' if event.cancelled else 'CONFIRMED'}")
    lines.append("TRANSP:OPAQUE")
    if alarm and not event.cancelled:
        lines += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{escape_text(event.summary)}",
            f"TRIGGER:-PT{ALARM_MINUTES_BEFORE}M",
            "END:VALARM",
        ]
    lines.append("END:VEVENT")
    return lines


def _param(value: str) -> str:
    """A parameter value: quoted, with characters that would break it removed."""
    return '"' + value.replace('"', "'").replace("\r", " ").replace("\n", " ") + '"'


def build_calendar(
    events: Iterable[Event],
    *,
    method: str,
    stamp: Optional[datetime] = None,
    organizer: Optional[tuple[str, str]] = None,
    attendee: Optional[tuple[str, str]] = None,
    alarm: bool = True,
    name: str = "",
) -> bytes:
    """A complete .ics file (CRLF line endings, UTF-8)."""
    stamp = stamp or datetime.now(timezone.utc)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", f"METHOD:{method}"]
    if name:
        lines += [f"X-WR-CALNAME:{escape_text(name)}"]
    for event in events:
        lines += _event_lines(event, stamp=stamp, organizer=organizer, attendee=attendee, alarm=alarm)
    lines.append("END:VCALENDAR")
    return ("\r\n".join(fold(line) for line in lines) + "\r\n").encode("utf-8")


def google_link(event: Event) -> str:
    """'Add to Google Calendar' link. Nothing is sent anywhere until it is clicked."""
    params = {
        "action": "TEMPLATE",
        "text": event.summary,
        "dates": f"{utc_stamp(event.start)}/{utc_stamp(event.end)}",
        "details": event.description,
        "location": event.location,
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(
        {k: v for k, v in params.items() if v}
    )


def outlook_link(event: Event) -> str:
    """'Add to Outlook (web)' link."""
    params = {
        "path": "/calendar/action/compose",
        "rru": "addevent",
        "subject": event.summary,
        "startdt": event.start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "enddt": event.end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "body": event.description,
        "location": event.location,
    }
    return "https://outlook.office.com/calendar/0/deeplink/compose?" + urlencode(
        {k: v for k, v in params.items() if v}
    )
