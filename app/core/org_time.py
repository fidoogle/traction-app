"""Time zones. An organization has one time zone (default US Central); meeting
times are typed and shown in it, stored in UTC, and sent to calendars in UTC so
every calendar app converts them for its own user."""

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from app.config import settings


def tz_of(name: Optional[str]) -> ZoneInfo:
    """The named zone, falling back to the site default if it is blank or unknown."""
    for candidate in (name, settings.default_timezone, "UTC"):
        try:
            if candidate:
                return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            continue
    return ZoneInfo("UTC")


def is_valid_timezone(name: str) -> bool:
    return name in available_timezones()


def all_timezones() -> list[str]:
    return sorted(available_timezones())


def to_local(moment: datetime, tz: ZoneInfo) -> datetime:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(tz)


def local_to_utc(day: date, at: time, tz: ZoneInfo) -> datetime:
    """The UTC moment when the wall clock in `tz` reads `day` `at`. A time that
    doesn't exist (clocks springing forward) moves an hour on; an ambiguous one
    (clocks falling back) takes the first of its two occurrences."""
    naive = datetime.combine(day, at)
    return naive.replace(tzinfo=tz, fold=0).astimezone(timezone.utc)


def _clock(moment: datetime) -> str:
    return moment.strftime("%I:%M %p").lstrip("0")


def format_when(start: datetime, duration_minutes: int, tz: ZoneInfo) -> str:
    """'Tuesday, October 27, 2026, 3:30 - 5:00 PM CDT'."""
    first = to_local(start, tz)
    last = first + timedelta(minutes=duration_minutes)
    day = first.strftime("%A, %B %d, %Y").replace(" 0", " ")
    return f"{day}, {_clock(first)} - {_clock(last)} {first.strftime('%Z')}"


def format_short(start: datetime, tz: ZoneInfo) -> str:
    """'Tue, Oct 27, 3:30 PM'."""
    first = to_local(start, tz)
    return f"{first.strftime('%a, %b')} {first.day}, {first.year}, {_clock(first)}"
