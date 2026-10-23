"""The optional alert emails: things a team's admins (or anyone who opts in)
may want to hear about. Like the assignment emails, routes queue these as
background tasks after their own commit, and the person who made the change is
never emailed about it. Who actually gets one is decided by notify(): the
recipient's role and their own choice on the "My notifications" page."""

import uuid
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.core.assignment_emails import one_line
from app.core.meeting_session import STEPS
from app.core.notifications import notify
from app.core.org_time import format_short, tz_of
from app.core.scorecard_format import format_goal, format_value, goal_met
from app.db import SessionLocal
from app.models import Issue, IssueStatus, Measurable, Meeting, MeetingStatus, Rock, RockStatus, Team, TeamMembership, Todo, TodoStatus, User, UserRole


def team_admin_ids(db: Session, team_id: uuid.UUID) -> list[uuid.UUID]:
    """Everyone who administers the team: its team admins, and the organization's
    admins (who administer every team; for them these alerts are opt-in)."""
    team = db.get(Team, team_id)
    team_admins = select(TeamMembership.user_id).where(
        TeamMembership.team_id == team_id, TeamMembership.is_team_admin.is_(True)
    )
    org_admins = select(User.id).where(User.org_id == team.org_id, User.role == UserRole.ADMIN)
    ids = set(db.scalars(team_admins)) | set(db.scalars(org_admins))
    return sorted(ids, key=str)


def alert_people(
    db: Session,
    user_ids: Iterable[uuid.UUID],
    key: str,
    *,
    actor_id: Optional[uuid.UUID],
    subject_line: str,
    template: str,
    context: dict,
    subject: str,
    period: str,
) -> int:
    """notify() each person (never the actor). Returns how many emails went out."""
    sent = 0
    for user_id in user_ids:
        if user_id == actor_id:
            continue
        user = db.get(User, user_id)
        if user is None:
            continue
        result = notify(
            db, user, key, subject_line=subject_line, template=template,
            context=context, subject=subject, period=period,
        )
        sent += result.sent
    return sent


def goes_off_track(previous: Optional[RockStatus], new: RockStatus) -> bool:
    """True when a Rock has just become off track (a change into that status)."""
    return settings.email_enabled and new == RockStatus.OFF_TRACK and previous != RockStatus.OFF_TRACK


def send_rock_off_track(rock_id: uuid.UUID, actor_id: uuid.UUID, event_id: str) -> None:
    with SessionLocal() as db:
        rock = db.get(Rock, rock_id)
        if rock is None or rock.status != RockStatus.OFF_TRACK:
            return
        actor = db.get(User, actor_id)
        context = {
            "title": rock.title,
            "team": rock.team.name,
            "quarter": rock.quarter,
            "owner": rock.owner.name,
            "changed_by": actor.name if actor else "Someone",
            "link": settings.absolute_url("/rocks"),
        }
        alert_people(
            db, team_admin_ids(db, rock.team_id), "rock_off_track", actor_id=actor_id,
            subject_line=f"Rock off track: {one_line(rock.title)}", template="rock_off_track",
            context=context, subject=f"rock:{rock.id}",
            # Each time a Rock slips is its own occasion; going off track again later alerts again.
            period=event_id,
        )


MISS_STREAK = 2  # weeks in a row below goal before anyone is told


def send_scorecard_missed(measurable_id: uuid.UUID, week: int, actor_id: uuid.UUID) -> None:
    """After a result is saved: if this week and the weeks just before it all
    missed the goal, MISS_STREAK or more in a row, tell the owner and the
    team's admins. Once per measurable per week, however often the cell is edited."""
    with SessionLocal() as db:
        measurable = db.get(Measurable, measurable_id)
        if measurable is None:
            return
        by_week = {e.week_number: e.actual_value for e in measurable.scorecard_entries}
        missed = [
            n for n in range(week, 0, -1)
            if n in by_week and not goal_met(by_week[n], measurable.goal_value, measurable.goal_direction)
        ]
        # Only the unbroken run ending at this week counts.
        streak = []
        for n in range(week, 0, -1):
            if n in missed:
                streak.append(n)
            else:
                break
        if len(streak) < MISS_STREAK:
            return
        card = measurable.scorecard
        people = set(team_admin_ids(db, card.team_id))
        if measurable.owner_id:
            people.add(measurable.owner_id)
        goal = format_goal(measurable.goal_value, measurable.unit, measurable.goal_direction)
        context = {
            "measure": measurable.name,
            "team": card.team.name,
            "owner": measurable.owner.name if measurable.owner else "nobody",
            "goal": goal,
            "streak": len(streak),
            "results": [
                {
                    "week": f"Week of {card.week_start(n).strftime('%b')} {card.week_start(n).day}",
                    "actual": format_value(by_week[n], measurable.unit),
                }
                for n in reversed(streak)
            ],
            "link": settings.absolute_url("/scorecards"),
        }
        alert_people(
            db, sorted(people, key=str), "scorecard_missed", actor_id=actor_id,
            subject_line=f"Scorecard: {one_line(measurable.name)} missed goal {len(streak)} weeks in a row",
            template="scorecard_missed", context=context,
            subject=f"measurable:{measurable.id}", period=f"week-{week}",
        )


# New issues are announced in one email per team: once nothing new has been
# added for ISSUE_QUIET (so a busy meeting is one email, not twenty), or
# ISSUE_MAX_WAIT after the first, whichever comes first. Issues added more than
# ISSUE_STALE_AFTER ago (say, while email was off) are never announced.
ISSUE_QUIET = timedelta(minutes=5)
ISSUE_MAX_WAIT = timedelta(minutes=15)
ISSUE_STALE_AFTER = timedelta(hours=24)
MAX_LISTED = 10


def announce_new_issues(db: Session, now: datetime) -> int:
    """Emails each team's members (those who opted in) about issues added since
    the last announcement. Run every minute; returns how many emails went out."""
    if not settings.email_enabled:
        return 0
    pending = db.scalars(
        select(Issue).where(Issue.announced_at.is_(None)).order_by(Issue.created_at, Issue.title)
    ).all()
    # Plain data first: notify() commits, which would expire the ORM objects.
    batches: dict[uuid.UUID, list[dict]] = {}
    stale_ids = []
    for issue in pending:
        if now - issue.created_at > ISSUE_STALE_AFTER:
            stale_ids.append(issue.id)
        else:
            batches.setdefault(issue.team_id, []).append(
                {"id": issue.id, "title": issue.title, "created_at": issue.created_at}
            )
    if stale_ids:
        db.execute(update(Issue).where(Issue.id.in_(stale_ids)).values(announced_at=now))
        db.commit()

    sent = 0
    for team_id, issues in batches.items():
        newest = max(i["created_at"] for i in issues)
        oldest = min(i["created_at"] for i in issues)
        if now - newest < ISSUE_QUIET and now - oldest < ISSUE_MAX_WAIT:
            continue  # more may still be coming
        team = db.get(Team, team_id)
        count = len(issues)
        context = {
            "team": team.name,
            "count": count,
            "issues": [i["title"] for i in issues[:MAX_LISTED]],
            "more": max(0, count - MAX_LISTED),
            "link": settings.absolute_url("/issues"),
        }
        subject_line = (
            f"{team.name}: new issue: {one_line(issues[0]['title'])}"
            if count == 1
            else f"{team.name}: {count} new issues"
        )
        user_ids = list(
            db.scalars(
                select(TeamMembership.user_id)
                .join(User, User.id == TeamMembership.user_id)
                .where(TeamMembership.team_id == team_id)
                .order_by(User.name)
            )
        )
        ids = [i["id"] for i in issues]
        sent += alert_people(
            db, user_ids, "issue_added", actor_id=None, subject_line=subject_line,
            template="issue_added", context=context,
            # Named by the batch's first issue, so running this again can't send it twice.
            subject=f"issues:{team_id}", period=str(ids[0]),
        )
        db.execute(update(Issue).where(Issue.id.in_(ids)).values(announced_at=now))
        db.commit()
    return sent


def _clock(seconds: int) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"


def send_meeting_recap(meeting_id: uuid.UUID) -> None:
    """After a meeting is finished: how it went, the To-Dos made during it, and
    the issues still open, to team members who opted in. (The app does not
    record decisions, so there is no list of them.)"""
    with SessionLocal() as db:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None or meeting.status != MeetingStatus.COMPLETED or meeting.started_at is None:
            return
        team = meeting.team
        tz = tz_of(team.organization.timezone)
        seconds = list(meeting.step_seconds or [])
        steps = [
            {
                "label": label,
                "time": _clock(seconds[i]) if i < len(seconds) else "0:00",
                "over": i < len(seconds) and seconds[i] > minutes * 60,
            }
            for i, (label, _url, minutes) in enumerate(STEPS)
        ]
        ended = meeting.finished_at or meeting.started_at
        new_todos = db.scalars(
            select(Todo)
            .where(
                Todo.team_id == team.id,
                Todo.created_at >= meeting.started_at,
                Todo.created_at <= ended + timedelta(minutes=5),
                Todo.status != TodoStatus.DROPPED,
            )
            .options(joinedload(Todo.owner))
            .order_by(Todo.created_at)
        ).unique().all()
        open_issues = db.scalars(
            select(Issue)
            .where(Issue.team_id == team.id, Issue.status == IssueStatus.OPEN)
            .order_by(Issue.priority.desc(), Issue.title)
        ).all()
        context = {
            "team": team.name,
            "when": format_short(meeting.started_at, tz),
            "total": _clock(sum(seconds)),
            "steps": steps,
            "todos": [
                {
                    "title": t.title,
                    "owner": t.owner.name,
                    "due": t.due_date.strftime("%b ") + str(t.due_date.day) if t.due_date else "",
                }
                for t in new_todos[:MAX_LISTED]
            ],
            "todos_more": max(0, len(new_todos) - MAX_LISTED),
            "issues": [i.title for i in open_issues[:MAX_LISTED]],
            "issues_more": max(0, len(open_issues) - MAX_LISTED),
            "issue_count": len(open_issues),
            "link": settings.absolute_url("/meetings"),
        }
        user_ids = list(
            db.scalars(
                select(TeamMembership.user_id)
                .join(User, User.id == TeamMembership.user_id)
                .where(TeamMembership.team_id == team.id)
                .order_by(User.name)
            )
        )
        alert_people(
            db, user_ids, "meeting_summary", actor_id=None,
            subject_line=f"{one_line(team.name)} meeting recap, {format_short(meeting.started_at, tz)}",
            template="meeting_summary", context=context, subject=f"meeting:{meeting_id}", period="recap",
        )


# --- quarter reminders ---
# Rocks are labelled by calendar quarter ("2026-Q4"), so the quarters here are
# calendar quarters too. A reminder goes out the day a quarter starts, and two
# weeks before it ends; one that was missed (the worker was down) is still sent
# for up to a week afterwards, but never later.

QUARTER_END_NOTICE = timedelta(days=14)
QUARTER_CATCH_UP = timedelta(days=7)


def quarter_bounds(day: date) -> tuple[date, date]:
    """First and last day of the calendar quarter containing `day`."""
    first_month = 3 * ((day.month - 1) // 3) + 1
    first = date(day.year, first_month, 1)
    next_first = date(day.year + (first_month == 10), (first_month + 3 - 1) % 12 + 1, 1)
    return first, next_first - timedelta(days=1)


def due_quarter_events(today: date) -> list[tuple[str, str, date]]:
    """The reminders due today: (kind, quarter label, the day it belongs to)."""
    first, last = quarter_bounds(today)
    label = f"{today.year}-Q{(today.month - 1) // 3 + 1}"
    events = [("start", label, first), ("end", label, last - QUARTER_END_NOTICE)]
    return [e for e in events if e[2] <= today < e[2] + QUARTER_CATCH_UP]


def send_quarter_reminders(db: Session, org_id: uuid.UUID, today: date) -> int:
    """Tells each team's admins that the quarter is starting or ending. Safe to
    run repeatedly: each person gets each reminder once per quarter."""
    if not settings.email_enabled:
        return 0
    events = due_quarter_events(today)
    if not events:
        return 0
    sent = 0
    team_ids = list(db.scalars(select(Team.id).where(Team.org_id == org_id).order_by(Team.name)))
    for kind, quarter, _day in events:
        for team_id in team_ids:
            team = db.get(Team, team_id)
            rocks = db.scalars(select(Rock).where(Rock.team_id == team_id, Rock.quarter == quarter)).all()
            first, last = quarter_bounds(today)
            context = {
                "kind": kind,
                "team": team.name,
                "quarter": quarter,
                "ends": f"{last.strftime('%B')} {last.day}",
                "rocks_total": len(rocks),
                "rocks_done": sum(1 for r in rocks if r.status == RockStatus.DONE),
                "unfinished": sorted(r.title for r in rocks if r.status != RockStatus.DONE)[:MAX_LISTED],
                "link": settings.absolute_url("/rocks"),
            }
            subject_line = (
                f"{quarter} has begun: set Rocks for {one_line(team.name)}"
                if kind == "start"
                else f"{quarter} ends {context['ends']}: review {one_line(team.name)}'s Rocks"
            )
            sent += alert_people(
                db, team_admin_ids(db, team_id), "quarter_reminder", actor_id=None,
                subject_line=subject_line, template="quarter_reminder", context=context,
                subject=f"team:{team_id}", period=f"{quarter}-{kind}",
            )
    return sent
