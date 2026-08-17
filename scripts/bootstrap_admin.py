"""Seed an initial Organization, Team, and admin User on a fresh database.

All API write routes require authentication, so there is no unauthenticated
signup endpoint to create the first account. Run this once, directly against
the database, to bootstrap access:

    python scripts/bootstrap_admin.py --org "Riverside School District" \
        --team "Leadership Team" --name "Admin User" \
        --email admin@example.com --password "change-me-now"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.security import hash_password  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Organization, Team, User, UserRole  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", required=True, help="Organization name")
    parser.add_argument("--team", required=True, help="Initial team name")
    parser.add_argument("--name", required=True, help="Admin user's full name")
    parser.add_argument("--email", required=True, help="Admin user's login email")
    parser.add_argument("--password", required=True, help="Admin user's password")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        org = Organization(name=args.org)
        db.add(org)
        db.flush()

        team = Team(org_id=org.id, name=args.team)
        db.add(team)
        db.flush()

        user = User(
            org_id=org.id,
            team_id=team.id,
            name=args.name,
            email=args.email,
            hashed_password=hash_password(args.password),
            role=UserRole.ADMIN,
        )
        db.add(user)
        db.commit()

        print(f"Created organization {org.id}, team {team.id}, admin user {user.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
