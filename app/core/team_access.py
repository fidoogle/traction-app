"""Which teams a user may work in, and what that lets them see.

The one rule, shared by the web UI (app/web/team_context.py) and the JSON
API (app/api/scoping.py): admins can work in every team in their org;
everyone else only in the teams they're a member of.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Team, TeamMembership, User, UserRole


def accessible_teams(db: Session, user: User) -> list[Team]:
    """Teams the user may work in, by name."""
    if user.role == UserRole.ADMIN:
        query = select(Team).where(Team.org_id == user.org_id)
    else:
        query = (
            select(Team)
            .join(TeamMembership, TeamMembership.team_id == Team.id)
            .where(TeamMembership.user_id == user.id, Team.org_id == user.org_id)
        )
    return list(db.scalars(query.order_by(Team.name)))
