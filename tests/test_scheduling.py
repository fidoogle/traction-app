"""Scheduling meetings, the invitation / cancellation / reminder emails with
their calendar files, the download, the subscription feed and the org settings
behind them."""

import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select, update

from app import worker
from app.core import meeting_session
from app.core import notifications as n
from app.core.meeting_emails import send_meeting_reminders
from app.core.org_time import local_to_utc
from app.db import SessionLocal
from app.models import Meeting, MeetingStatus, Organization, TeamMembership, User

CENTRAL = ZoneInfo("America/Chicago")
DAY = date.today() + timedelta(days=10)
NOW = datetime(2026, 10, 22, 15, 0, tzinfo=timezone.utc)


def sent(smtp):
    return [m for conn in smtp.instances for m in conn.sent]


def recipients(smtp):
    return sorted(m["To"] for m in sent(smtp))


def calendar_part(msg):
    parts = [p for p in msg.iter_attachments() if p.get_content_type() == "text/calendar"]
    assert len(parts) == 1
    return parts[0]


def ics(msg) -> str:
    return calendar_part(msg).get_payload(decode=True).decode("utf-8")


def form(world, **over):
    data = {
        "team_id": str(world["team_alpha"]), "day": DAY.isoformat(), "at": "15:30",
        "duration_minutes": "90", "location": "Room 4",
    }
    data.update(over)
    return data


def only_new_meeting(world):
    with SessionLocal() as db:
        return db.scalar(
            select(Meeting).where(Meeting.team_id == world["team_alpha"], Meeting.location.is_not(None))
        )


def add_meeting(db, world, start, team="alpha", **over):
    meeting = Meeting(team_id=world[f"team_{team}"], scheduled_start=start, **over)
    db.add(meeting)
    db.commit()
    return meeting.id


def make_team_admin(world, user="mia", team="bravo"):
    with SessionLocal() as db:
        db.execute(
            update(TeamMembership)
            .where(TeamMembership.user_id == world[user], TeamMembership.team_id == world[f"team_{team}"])
            .values(is_team_admin=True)
        )
        db.commit()


def set_org(world, **values):
    with SessionLocal() as db:
        db.execute(update(Organization).where(Organization.id == db.get(User, world["admin"]).org_id).values(**values))
        db.commit()


# --- scheduling ---


def test_scheduling_stores_utc_and_invites_every_team_member(world, login, smtp, configured):
    resp = login("admin").post("/meetings", data=form(world))
    assert resp.status_code == 200
    meeting = only_new_meeting(world)
    assert meeting.scheduled_start == local_to_utc(DAY, time(15, 30), CENTRAL)
    assert (meeting.duration_minutes, meeting.location, meeting.ical_sequence) == (90, "Room 4", 0)
    assert meeting.status == MeetingStatus.SCHEDULED and meeting.ical_uid

    assert recipients(smtp) == ["admin@example.com", "mia@example.com", "vic@example.com"]  # all of Alpha
    msg = sent(smtp)[0]
    assert msg["Subject"].startswith("Alpha meeting, ") and "3:30 PM" in msg["Subject"]
    body = msg.get_body(("plain",)).get_content()
    assert "3:30 PM - 5:00 PM" in body and "Room 4" in body and "scheduled" in body
    assert "calendar.google.com" not in body  # web links are off unless an admin turns them on


def test_the_invite_carries_a_calendar_request_for_that_person(world, login, smtp, configured):
    login("admin").post("/meetings", data=form(world))
    meeting = only_new_meeting(world)
    for msg in sent(smtp):
        part = calendar_part(msg)
        assert part.get_param("method") == "REQUEST"
        text = ics(msg)
        assert "METHOD:REQUEST" in text and f"UID:{meeting.ical_uid}@traction-app" in text
        assert "SEQUENCE:0" in text and "DTSTART:" in text and "LOCATION:Room 4" in text
        assert f"mailto:{msg['To']}" in text.replace("\r\n ", "")
        assert "TRIGGER:-PT15M" in text


def test_only_admins_of_the_team_can_schedule(world, login, smtp, configured):
    make_team_admin(world, "mia", "bravo")
    assert login("mia").post("/meetings", data=form(world, team_id=str(world["team_bravo"]))).status_code == 200
    assert login("mia").post("/meetings", data=form(world)).status_code == 403  # Alpha: just a member
    assert login("vic").post("/meetings", data=form(world)).status_code == 403
    assert login("max").post("/meetings", data=form(world)).status_code == 403
    assert login("admin").post("/meetings", data=form(world, team_id=str(world["team_xray"]))).status_code in (403, 404)
    assert login("other").post("/meetings", data=form(world)).status_code in (403, 404)


@pytest.mark.parametrize(
    "bad",
    [
        {"duration_minutes": "5"},
        {"duration_minutes": "481"},
        {"duration_minutes": "ninety"},
        {"location": "x" * 256},
        {"location": "Room 4\nBcc: someone"},
        {"day": "2020-01-01"},  # in the past
        {"day": "not-a-date"},
        {"at": "25:99"},
    ],
)
def test_bad_input_is_refused(world, login, smtp, configured, bad):
    assert login("admin").post("/meetings", data=form(world, **bad)).status_code == 422
    assert only_new_meeting(world) is None
    assert sent(smtp) == []


def test_scheduling_works_without_email(world, login, smtp):
    assert login("admin").post("/meetings", data=form(world)).status_code == 200
    assert only_new_meeting(world) is not None and sent(smtp) == []


def test_the_organizations_time_zone_is_used(world, login, smtp, configured):
    set_org(world, timezone="America/Los_Angeles")
    login("admin").post("/meetings", data=form(world))
    assert only_new_meeting(world).scheduled_start == local_to_utc(DAY, time(15, 30), ZoneInfo("America/Los_Angeles"))
    assert "PDT" in sent(smtp)[0].get_body(("plain",)).get_content() or "PST" in sent(smtp)[0].get_body(("plain",)).get_content()


# --- editing and cancelling ---


def test_changing_a_meeting_bumps_the_sequence_and_sends_an_update(world, login, smtp, configured):
    admin = login("admin")
    admin.post("/meetings", data=form(world))
    meeting = only_new_meeting(world)
    smtp.instances.clear()

    new_day = DAY + timedelta(days=1)
    resp = admin.put(f"/meetings/{meeting.id}", data=form(world, day=new_day.isoformat(), at="10:00"))
    assert resp.status_code == 200
    changed = only_new_meeting(world)
    assert changed.ical_sequence == 1 and changed.ical_uid == meeting.ical_uid
    assert changed.scheduled_start == local_to_utc(new_day, time(10, 0), CENTRAL)

    assert len(sent(smtp)) == 3
    msg = sent(smtp)[0]
    assert msg["Subject"].startswith("Updated: Alpha meeting")
    text = ics(msg)
    assert f"UID:{meeting.ical_uid}@traction-app" in text and "SEQUENCE:1" in text
    assert "changed" in msg.get_body(("plain",)).get_content()


def test_saving_without_changes_does_nothing(world, login, smtp, configured):
    admin = login("admin")
    admin.post("/meetings", data=form(world))
    meeting = only_new_meeting(world)
    smtp.instances.clear()
    assert admin.put(f"/meetings/{meeting.id}", data=form(world)).status_code == 200
    assert only_new_meeting(world).ical_sequence == 0 and sent(smtp) == []


def test_each_change_is_a_new_version_but_the_same_version_is_never_sent_twice(world, login, smtp, configured):
    admin = login("admin")
    admin.post("/meetings", data=form(world))
    meeting = only_new_meeting(world)
    admin.put(f"/meetings/{meeting.id}", data=form(world, location="Room 5"))
    admin.put(f"/meetings/{meeting.id}", data=form(world, location="Room 6"))
    assert only_new_meeting(world).ical_sequence == 2
    assert len(sent(smtp)) == 9  # 3 people x versions 0, 1 and 2


def test_cancelling_sends_a_calendar_cancellation(world, login, smtp, configured):
    admin = login("admin")
    admin.post("/meetings", data=form(world))
    meeting = only_new_meeting(world)
    smtp.instances.clear()

    assert admin.post(f"/meetings/{meeting.id}/cancel").status_code == 200
    cancelled = only_new_meeting(world)
    assert cancelled.status == MeetingStatus.CANCELED and cancelled.ical_sequence == 1
    assert len(sent(smtp)) == 3
    for msg in sent(smtp):
        assert msg["Subject"].startswith("Cancelled: Alpha meeting")
        assert calendar_part(msg).get_param("method") == "CANCEL"
        text = ics(msg)
        assert f"UID:{meeting.ical_uid}@traction-app" in text and "SEQUENCE:1" in text
        assert "STATUS:CANCELLED" in text and "METHOD:CANCEL" in text


def test_only_a_scheduled_meeting_can_be_changed_or_cancelled(world, login, smtp, configured):
    admin = login("admin")
    admin.post("/meetings", data=form(world))
    meeting = only_new_meeting(world)
    admin.post(f"/meetings/{meeting.id}/cancel")
    assert admin.post(f"/meetings/{meeting.id}/cancel").status_code == 409
    assert admin.get(f"/meetings/{meeting.id}/edit").status_code == 409
    assert admin.put(f"/meetings/{meeting.id}", data=form(world, location="Elsewhere")).status_code == 409
    with SessionLocal() as db:
        running = add_meeting(db, world, NOW, status=MeetingStatus.IN_PROGRESS)
    assert admin.post(f"/meetings/{running}/cancel").status_code == 409


def test_editing_and_cancelling_are_for_that_teams_admins(world, login, smtp, configured):
    login("admin").post("/meetings", data=form(world))
    meeting = only_new_meeting(world)
    for who in ("mia", "vic", "max"):
        browser = login(who)
        assert browser.get(f"/meetings/{meeting.id}/edit").status_code in (403, 404)
        assert browser.put(f"/meetings/{meeting.id}", data=form(world, location="Hijack")).status_code in (403, 404)
        assert browser.post(f"/meetings/{meeting.id}/cancel").status_code in (403, 404)
    assert only_new_meeting(world).ical_sequence == 0


def test_the_edit_form_shows_local_time(world, login):
    login("admin").post("/meetings", data=form(world))
    meeting = only_new_meeting(world)
    page = login("admin").get(f"/meetings/{meeting.id}/edit").text
    assert f'value="{DAY.isoformat()}"' in page and 'value="15:30"' in page


# --- reminders ---


def test_reminders_go_out_a_day_ahead_once(world, smtp, configured):
    with SessionLocal() as db:
        add_meeting(db, world, NOW + timedelta(hours=23), location="Room 4")
        assert send_meeting_reminders(db, NOW) == 3
        assert send_meeting_reminders(db, NOW + timedelta(minutes=1)) == 0
    assert recipients(smtp) == ["admin@example.com", "mia@example.com", "vic@example.com"]
    msg = sent(smtp)[0]
    assert msg["Subject"].startswith("Reminder: Alpha meeting tomorrow")
    assert "tomorrow" in msg.get_body(("plain",)).get_content()
    assert not list(msg.iter_attachments())


def test_only_meetings_in_the_window_get_a_day_ahead_reminder(world, smtp, configured):
    with SessionLocal() as db:
        add_meeting(db, world, NOW + timedelta(hours=25))  # too far off
        add_meeting(db, world, NOW + timedelta(hours=21))  # invited with less than a day's notice
        add_meeting(db, world, NOW - timedelta(hours=1))   # already over
        assert send_meeting_reminders(db, NOW) == 0
    assert sent(smtp) == []


def test_the_hour_ahead_reminder_is_opt_in(world, smtp, configured):
    with SessionLocal() as db:
        add_meeting(db, world, NOW + timedelta(minutes=50))
        assert send_meeting_reminders(db, NOW) == 0
        n.set_preference(db, db.get(User, world["mia"]), "meeting_reminder_1h", True)
        assert send_meeting_reminders(db, NOW) == 1
        assert send_meeting_reminders(db, NOW + timedelta(minutes=5)) == 0
    assert recipients(smtp) == ["mia@example.com"]
    assert "in about an hour" in sent(smtp)[0]["Subject"]


def test_people_can_turn_the_day_ahead_reminder_off(world, smtp, configured):
    with SessionLocal() as db:
        n.set_preference(db, db.get(User, world["vic"]), "meeting_reminder", False)
        add_meeting(db, world, NOW + timedelta(hours=23))
        assert send_meeting_reminders(db, NOW) == 2
    assert "vic@example.com" not in recipients(smtp)


def test_a_rescheduled_meeting_reminds_again_and_a_cancelled_one_does_not(world, smtp, configured):
    with SessionLocal() as db:
        meeting_id = add_meeting(db, world, NOW + timedelta(hours=23))
        assert send_meeting_reminders(db, NOW) == 3
        meeting = db.get(Meeting, meeting_id)
        meeting.scheduled_start = NOW + timedelta(hours=22, minutes=30)
        meeting.ical_sequence = 1
        db.commit()
        assert send_meeting_reminders(db, NOW) == 3  # the new version is a new occasion
        meeting.status = MeetingStatus.CANCELED
        meeting.ical_sequence = 2
        db.commit()
        assert send_meeting_reminders(db, NOW) == 0
    assert len(sent(smtp)) == 6


def test_reminders_do_nothing_when_email_is_off(world, smtp):
    with SessionLocal() as db:
        add_meeting(db, world, NOW + timedelta(hours=23))
        assert send_meeting_reminders(db, NOW) == 0
    assert sent(smtp) == []


def test_the_worker_sends_reminders_on_its_tick(world, smtp, configured):
    with SessionLocal() as db:
        add_meeting(db, world, NOW + timedelta(hours=23))
    worker.tick(worker.WorkerState(), NOW)
    assert len(sent(smtp)) == 3


# --- the calendar file download ---


def test_a_team_member_can_download_the_meeting(world, login):
    login("admin").post("/meetings", data=form(world))
    meeting = only_new_meeting(world)
    resp = login("vic").get(f"/meetings/{meeting.id}/calendar.ics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/calendar")
    assert "attachment" in resp.headers["content-disposition"]
    text = resp.text
    assert "METHOD:PUBLISH" in text and f"UID:{meeting.ical_uid}@traction-app" in text
    assert "SUMMARY:Alpha meeting" in text and "ATTENDEE" not in text


def test_someone_off_the_team_cannot_download_it(world, login):
    login("admin").post("/meetings", data=form(world))
    meeting = only_new_meeting(world)
    assert login("max").get(f"/meetings/{meeting.id}/calendar.ics").status_code == 404
    assert login("other").get(f"/meetings/{meeting.id}/calendar.ics").status_code == 404


def test_a_cancelled_meeting_downloads_as_a_cancellation(world, login):
    admin = login("admin")
    admin.post("/meetings", data=form(world))
    meeting = only_new_meeting(world)
    admin.post(f"/meetings/{meeting.id}/cancel")
    text = admin.get(f"/meetings/{meeting.id}/calendar.ics").text
    assert "METHOD:CANCEL" in text and "STATUS:CANCELLED" in text and "SEQUENCE:1" in text


def test_the_download_link_shows_only_for_scheduled_meetings(world, login):
    admin = login("admin")
    admin.post("/meetings", data=form(world))
    meeting = only_new_meeting(world)
    assert f"/meetings/{meeting.id}/calendar.ics" in login("vic").get("/meetings").text
    admin.post(f"/meetings/{meeting.id}/cancel")
    assert f"/meetings/{meeting.id}/calendar.ics" not in admin.get("/meetings").text


# --- web links ---


def test_web_calendar_links_appear_only_when_an_admin_turns_them_on(world, login, smtp, configured):
    set_org(world, calendar_web_links=True)
    login("admin").post("/meetings", data=form(world))
    msg = sent(smtp)[0]
    for part in ("plain", "html"):
        body = msg.get_body((part,)).get_content()
        assert "https://calendar.google.com/calendar/render" in body
        assert "https://outlook.office.com/calendar/0/deeplink/compose" in body


# --- starting a meeting finds the scheduled one ---


def test_starting_picks_the_scheduled_meeting_nearest_now_by_the_organizations_clock(world):
    set_org(world, timezone="America/Los_Angeles")  # 2026-10-23 05:00Z is Oct 22, 10 PM there
    now = datetime(2026, 10, 23, 5, 0, tzinfo=timezone.utc)
    with SessionLocal() as db:
        tonight = add_meeting(db, world, datetime(2026, 10, 23, 1, 0, tzinfo=timezone.utc))      # Oct 22, 6 PM
        late = add_meeting(db, world, datetime(2026, 10, 23, 6, 30, tzinfo=timezone.utc))       # Oct 22, 11:30 PM
        tomorrow = add_meeting(db, world, datetime(2026, 10, 23, 8, 0, tzinfo=timezone.utc))     # Oct 23, 1 AM
        picked = meeting_session.start(db, world["team_alpha"], now)
        db.commit()
        assert picked.id == late  # same local day, nearest to now
        assert db.get(Meeting, tonight).status == MeetingStatus.SCHEDULED
        assert db.get(Meeting, tomorrow).status == MeetingStatus.SCHEDULED


def test_starting_with_nothing_scheduled_records_a_new_meeting(world):
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(Meeting).where(Meeting.team_id == world["team_alpha"]))
        started = meeting_session.start(db, world["team_alpha"], NOW)
        db.commit()
        assert started.status == MeetingStatus.IN_PROGRESS and started.scheduled_start == NOW
        assert started.duration_minutes == 90
        assert db.scalar(select(func.count()).select_from(Meeting).where(Meeting.team_id == world["team_alpha"])) == before + 1


def test_a_cancelled_meeting_is_not_picked_up_by_start(world):
    with SessionLocal() as db:
        add_meeting(db, world, NOW, status=MeetingStatus.CANCELED)
        started = meeting_session.start(db, world["team_alpha"], NOW)
        assert started.status == MeetingStatus.IN_PROGRESS
        db.commit()
        assert db.scalar(select(func.count()).select_from(Meeting).where(
            Meeting.team_id == world["team_alpha"], Meeting.status == MeetingStatus.CANCELED)) == 1


# --- pages ---


def test_the_meetings_page_offers_scheduling_to_admins_only(world, login):
    assert "Schedule a meeting" in login("admin").get("/meetings").text
    assert "Schedule a meeting" not in login("mia").get("/meetings").text
    make_team_admin(world, "mia", "bravo")
    page = login("mia").get("/meetings").text
    assert "Schedule a meeting" in page and "Bravo" in page


def test_the_meetings_page_and_dashboard_show_local_times(world, login):
    login("admin").post("/meetings", data=form(world))
    page = login("vic").get("/meetings").text
    assert "3:30 PM" in page and "90 min" in page and "Room 4" in page and "Scheduled" in page
    assert "3:30 PM" in login("vic").get("/").text


# --- org settings ---


def test_an_admin_can_change_the_time_zone_and_web_link_settings(world, login):
    admin = login("admin")
    assert admin.post("/settings/timezone", data={"timezone": "America/Denver"}).status_code == 200
    assert admin.post("/settings/calendar-links", data={"enabled": "1"}).status_code == 200
    with SessionLocal() as db:
        org = db.get(Organization, db.get(User, world["admin"]).org_id)
        assert (org.timezone, org.calendar_web_links) == ("America/Denver", True)
    assert admin.post("/settings/calendar-links", data={}).status_code == 200
    with SessionLocal() as db:
        assert db.get(Organization, db.get(User, world["admin"]).org_id).calendar_web_links is False


def test_a_bad_time_zone_is_refused(world, login):
    assert login("admin").post("/settings/timezone", data={"timezone": "Mars/Olympus"}).status_code == 422
    with SessionLocal() as db:
        assert db.get(Organization, db.get(User, world["admin"]).org_id).timezone == "America/Chicago"


def test_only_admins_change_organization_settings(world, login):
    for who in ("mia", "vic"):
        assert login(who).post("/settings/timezone", data={"timezone": "America/Denver"}).status_code == 403
        assert login(who).post("/settings/calendar-links", data={"enabled": "1"}).status_code == 403


def test_settings_changes_stay_inside_the_admins_organization(world, login):
    login("other").post("/settings/timezone", data={"timezone": "America/Denver"})
    with SessionLocal() as db:
        assert db.get(Organization, db.get(User, world["admin"]).org_id).timezone == "America/Chicago"
        assert db.get(Organization, db.get(User, world["other"]).org_id).timezone == "America/Denver"


# --- the subscription feed ---

FEED = re.compile(r"/calendar/([A-Za-z0-9_-]+)\.ics")


def feed_token(browser):
    match = FEED.search(browser.get("/notifications").text)
    return match.group(1) if match else None


def test_a_feed_has_to_be_switched_on(world, login):
    mia = login("mia")
    assert feed_token(mia) is None
    assert "Subscribe" in mia.get("/notifications").text
    assert mia.post("/notifications/calendar-feed").status_code == 200
    assert feed_token(mia)


def test_the_feed_needs_no_login_and_lists_only_that_persons_teams(world, login):
    admin = login("admin")
    for team in ("alpha", "bravo", "charlie"):
        admin.post("/meetings", data=form(world, team_id=str(world[f"team_{team}"]), location=f"{team} room"))
    cancelled = login("admin").post("/meetings", data=form(world, location="cancelled room"))
    assert cancelled.status_code == 200
    with SessionLocal() as db:
        gone = db.scalar(select(Meeting.id).where(Meeting.location == "cancelled room"))
    admin.post(f"/meetings/{gone}/cancel")

    mia, max_ = login("mia"), login("max")
    mia.post("/notifications/calendar-feed")
    max_.post("/notifications/calendar-feed")
    from fastapi.testclient import TestClient

    from app.main import app

    anonymous = TestClient(app, follow_redirects=False)
    mia_feed = anonymous.get(f"/calendar/{feed_token(mia)}.ics")
    assert mia_feed.status_code == 200 and mia_feed.headers["content-type"].startswith("text/calendar")
    assert "METHOD:PUBLISH" in mia_feed.text
    assert "alpha room" in mia_feed.text and "bravo room" in mia_feed.text  # Mia is on Alpha and Bravo
    assert "charlie room" not in mia_feed.text and "cancelled room" not in mia_feed.text
    max_feed = anonymous.get(f"/calendar/{feed_token(max_)}.ics").text
    assert "charlie room" in max_feed and "alpha room" not in max_feed


def test_a_wrong_or_missing_feed_address_finds_nothing(world, login):
    from fastapi.testclient import TestClient

    from app.main import app

    anonymous = TestClient(app, follow_redirects=False)
    assert anonymous.get("/calendar/not-a-real-token.ics").status_code == 404
    assert anonymous.get("/calendar/.ics").status_code == 404


def test_making_a_new_feed_address_kills_the_old_one_and_switching_off_kills_both(world, login):
    from fastapi.testclient import TestClient

    from app.main import app

    mia = login("mia")
    mia.post("/notifications/calendar-feed")
    first = feed_token(mia)
    mia.post("/notifications/calendar-feed")
    second = feed_token(mia)
    assert first != second
    anonymous = TestClient(app, follow_redirects=False)
    assert anonymous.get(f"/calendar/{first}.ics").status_code == 404
    assert anonymous.get(f"/calendar/{second}.ics").status_code == 200
    assert mia.delete("/notifications/calendar-feed").status_code == 200
    assert feed_token(mia) is None
    assert anonymous.get(f"/calendar/{second}.ics").status_code == 404


def test_feed_addresses_are_private_to_each_person(world, login):
    mia, vic = login("mia"), login("vic")
    mia.post("/notifications/calendar-feed")
    assert feed_token(vic) is None
    vic.post("/notifications/calendar-feed")
    assert feed_token(vic) != feed_token(mia)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(User).where(User.calendar_token.is_not(None))) == 2
