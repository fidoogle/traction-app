"""The optional alert emails: things a team's admins (or anyone who opts in)
may want to hear about. Like the assignment emails, routes queue these as
background tasks after their own commit, and the person who made the change is
never emailed about it. Who actually gets one is decided by notify(): the
recipient's role and their own choice on the "My notifications" page."""

import uuid
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.assignment_emails import one_line
from app.core.notifications import notify
from app.db import SessionLocal
from app.models import Rock, RockStatus, Team, TeamMembership, User, UserRole


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
