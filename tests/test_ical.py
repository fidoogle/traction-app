"""Calendar files and time-zone handling. No database needed."""

from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from app.core import ical
from app.core.org_time import format_short, format_when, local_to_utc, to_local, tz_of

CENTRAL = ZoneInfo("America/Chicago")
STAMP = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)


def event(**over):
    fields = dict(
        uid="abc-123@traction-app", sequence=0,
        start=datetime(2026, 10, 27, 20, 30, tzinfo=timezone.utc),
        duration_minutes=90, summary="Alpha meeting",
    )
    fields.update(over)
    return ical.Event(**fields)


def unfold(data: bytes) -> list[str]:
    """Undo line folding and split into content lines (a throwaway parser)."""
    text = data.decode("utf-8")
    assert text.endswith("\r\n") and "\n" not in text.replace("\r\n", "")
    return text.replace("\r\n ", "").split("\r\n")[:-1]


def unescape(value: str) -> str:
    out, i = [], 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            out.append({"n": "\n"}.get(value[i + 1], value[i + 1]))
            i += 2
        else:
            out.append(value[i])
            i += 1
    return "".join(out)


def prop(lines, name):
    for line in lines:
        if line.split(":", 1)[0].split(";")[0] == name:
            return line.split(":", 1)[1]
    return None


# --- the file ---


def test_a_known_event_comes_out_exactly():
    data = ical.build_calendar(
        [event(location="Room 4", description="Weekly team meeting")],
        method=ical.REQUEST, stamp=STAMP, organizer=("Traction", "traction@district.test"),
        attendee=("Mia Member", "mia@example.com"),
    )
    # (the long ATTENDEE line is folded onto continuation lines; unfold before comparing)
    assert data.decode().replace("\r\n ", "") == (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Traction//Traction App//EN\r\nCALSCALE:GREGORIAN\r\n"
        "METHOD:REQUEST\r\nBEGIN:VEVENT\r\nUID:abc-123@traction-app\r\nSEQUENCE:0\r\n"
        "DTSTAMP:20261001T120000Z\r\nDTSTART:20261027T203000Z\r\nDTEND:20261027T220000Z\r\n"
        "SUMMARY:Alpha meeting\r\nDESCRIPTION:Weekly team meeting\r\nLOCATION:Room 4\r\n"
        'ORGANIZER;CN="Traction":mailto:traction@district.test\r\n'
        'ATTENDEE;CN="Mia Member";ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=FALSE:mailto:mia@example.com\r\n'
        "STATUS:CONFIRMED\r\nTRANSP:OPAQUE\r\nBEGIN:VALARM\r\nACTION:DISPLAY\r\nDESCRIPTION:Alpha meeting\r\n"
        "TRIGGER:-PT15M\r\nEND:VALARM\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    )


def test_times_are_utc_whatever_the_input_zone():
    local = datetime(2026, 10, 27, 15, 30, tzinfo=CENTRAL)  # 3:30 PM CDT
    lines = unfold(ical.build_calendar([event(start=local)], method=ical.PUBLISH, stamp=STAMP))
    assert prop(lines, "DTSTART") == "20261027T203000Z"
    assert prop(lines, "DTEND") == "20261027T220000Z"


def test_a_cancellation_reuses_the_uid_with_a_higher_sequence_and_no_alarm():
    original = unfold(ical.build_calendar([event(sequence=0)], method=ical.REQUEST, stamp=STAMP))
    cancel = unfold(ical.build_calendar([event(sequence=1, cancelled=True)], method=ical.CANCEL, stamp=STAMP))
    assert prop(original, "UID") == prop(cancel, "UID")
    assert (prop(original, "SEQUENCE"), prop(cancel, "SEQUENCE")) == ("0", "1")
    assert prop(cancel, "METHOD") == "CANCEL" and prop(cancel, "STATUS") == "CANCELLED"
    assert "BEGIN:VALARM" in original and "BEGIN:VALARM" not in cancel


def test_every_file_has_the_15_minute_alert():
    lines = unfold(ical.build_calendar([event()], method=ical.PUBLISH, stamp=STAMP))
    assert prop(lines, "TRIGGER") == "-PT15M"


def test_text_with_commas_semicolons_newlines_and_unicode_round_trips():
    nasty = "Room 4, East; \"Wing\"\nBring: Rock list \\ agenda - Peña — \U0001F600"
    lines = unfold(ical.build_calendar([event(summary=nasty, location=nasty)], method=ical.PUBLISH, stamp=STAMP))
    assert unescape(prop(lines, "SUMMARY")) == nasty
    assert unescape(prop(lines, "LOCATION")) == nasty
    assert "\n" not in prop(lines, "SUMMARY")


def test_long_lines_are_folded_within_75_bytes_and_never_split_a_character():
    long_text = ("Reading scores, éèê — " * 30).strip()
    data = ical.build_calendar([event(description=long_text)], method=ical.PUBLISH, stamp=STAMP)
    physical = data.decode("utf-8").split("\r\n")[:-1]
    assert all(len(line.encode("utf-8")) <= 75 for line in physical)
    assert any(line.startswith(" ") for line in physical)
    assert unescape(prop(unfold(data), "DESCRIPTION")) == long_text


def test_fold_leaves_short_lines_alone():
    assert ical.fold("SUMMARY:Short") == "SUMMARY:Short"


def test_names_cannot_break_out_of_a_parameter():
    lines = unfold(
        ical.build_calendar(
            [event()], method=ical.REQUEST, stamp=STAMP, attendee=('Ev"il\r\nATTENDEE:x', "a@b.test")
        )
    )
    assert sum(1 for line in lines if line.startswith("ATTENDEE")) == 1


def test_a_feed_can_hold_many_events():
    lines = unfold(
        ical.build_calendar(
            [event(uid=f"u{i}@x", start=event().start + timedelta(days=i)) for i in range(3)],
            method=ical.PUBLISH, stamp=STAMP, name="Traction meetings",
        )
    )
    assert lines.count("BEGIN:VEVENT") == 3 and prop(lines, "X-WR-CALNAME") == "Traction meetings"


def test_web_links_carry_the_event():
    e = event(location="Room 4", description="Team meeting")
    google = urlparse(ical.google_link(e))
    assert google.netloc == "calendar.google.com"
    q = parse_qs(google.query)
    assert q["text"] == ["Alpha meeting"] and q["dates"] == ["20261027T203000Z/20261027T220000Z"]
    assert q["location"] == ["Room 4"]
    outlook = urlparse(ical.outlook_link(e))
    assert outlook.netloc == "outlook.office.com"
    q = parse_qs(outlook.query)
    assert q["startdt"] == ["2026-10-27T20:30:00Z"] and q["enddt"] == ["2026-10-27T22:00:00Z"]


# --- time zones ---


def test_local_times_convert_with_daylight_saving():
    assert local_to_utc(date(2026, 10, 27), time(15, 30), CENTRAL) == datetime(2026, 10, 27, 20, 30, tzinfo=timezone.utc)
    assert local_to_utc(date(2026, 11, 10), time(15, 30), CENTRAL) == datetime(2026, 11, 10, 21, 30, tzinfo=timezone.utc)


def test_a_time_that_does_not_exist_moves_forward_and_an_ambiguous_one_takes_the_first():
    # 2:30 AM on 2026-03-08 never happens in Chicago (02:00 jumps to 03:00).
    assert local_to_utc(date(2026, 3, 8), time(2, 30), CENTRAL) == datetime(2026, 3, 8, 8, 30, tzinfo=timezone.utc)
    # 1:30 AM on 2026-11-01 happens twice; the first is still daylight time.
    assert local_to_utc(date(2026, 11, 1), time(1, 30), CENTRAL) == datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc)


def test_display_formats():
    start = datetime(2026, 10, 27, 20, 30, tzinfo=timezone.utc)
    assert format_when(start, 90, CENTRAL) == "Tuesday, October 27, 2026, 3:30 PM - 5:00 PM CDT"
    assert format_short(start, CENTRAL) == "Tue, Oct 27, 2026, 3:30 PM"
    assert to_local(start, CENTRAL).hour == 15
    winter = datetime(2026, 12, 8, 15, 30, tzinfo=timezone.utc)
    assert format_when(winter, 60, CENTRAL).endswith("9:30 AM - 10:30 AM CST")


def test_unknown_zone_names_fall_back_to_the_site_default():
    assert tz_of("America/Los_Angeles").key == "America/Los_Angeles"
    assert tz_of("Not/AZone").key == "America/Chicago"
    assert tz_of("").key == "America/Chicago"
    assert tz_of(None).key == "America/Chicago"
