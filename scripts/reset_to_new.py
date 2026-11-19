"""Wipe the database back to a brand-new install and create the first admins.

Deletes EVERY row in every app table (organizations, teams, users, rocks,
scorecards, meetings, activity, ...), then creates one organization, one team
and the admin accounts you name. The schema (and alembic_version) is kept.

Destructive and irreversible - it asks you to type the word RESET unless you
pass --yes.

    python -m scripts.reset_to_new --org "My Organization" --team "Leadership Team" \
        --admin "Fidel Guajardo:fidelg3@gmail.com" --admin "Mike:mike@yourswbc.com" \
        --password demo1234

In Docker:  docker compose exec app python -m scripts.reset_to_new ...
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.core.password_tokens import MIN_PASSWORD_LENGTH  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Organization, Team, TeamMembership, User, UserRole  # noqa: E402


def wipe(db) -> list[str]:
    tables = [
        r[0]
        for r in db.execute(
            text("select tablename from pg_tables where schemaname='public' and tablename <> 'alembic_version'")
        )
    ]
    db.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " CASCADE"))
    return tables


def create_admins(db, org_name: str, team_name: str, admins: list[tuple[str, str]], password: str) -> None:
    org = Organization(name=org_name)
    db.add(org)
    db.flush()
    team = Team(org_id=org.id, name=team_name)
    db.add(team)
    db.flush()
    hashed = hash_password(password)
    for name, email in admins:
        db.add(
            User(
                org_id=org.id,
                team_id=team.id,
                name=name,
                email=email,
                hashed_password=hashed,
                role=UserRole.ADMIN,
                memberships=[TeamMembership(team_id=team.id)],
            )
        )


def parse_admin(value: str) -> tuple[str, str]:
    name, sep, email = value.rpartition(":")
    if not sep or "@" not in email or not name.strip():
        raise argparse.ArgumentTypeError('use "Full Name:email@example.com"')
    return name.strip(), email.strip().lower()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--org", required=True)
    parser.add_argument("--team", required=True)
    parser.add_argument("--admin", required=True, action="append", type=parse_admin, help='"Name:email"; repeatable')
    parser.add_argument("--password", required=True, help="Starting password for every admin created")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    args = parser.parse_args()

    if len(args.password) < MIN_PASSWORD_LENGTH:
        parser.error(f"--password must be at least {MIN_PASSWORD_LENGTH} characters")

    if not args.yes:
        if input("This deletes ALL data in the database. Type RESET to continue: ").strip() != "RESET":
            sys.exit("Aborted.")

    db = SessionLocal()
    try:
        tables = wipe(db)
        create_admins(db, args.org, args.team, args.admin, args.password)
        db.commit()
    finally:
        db.close()
    print(f"Cleared {len(tables)} tables. Created organization '{args.org}', team '{args.team}' and admins:")
    for name, email in args.admin:
        print(f"  {name} <{email}>")


if __name__ == "__main__":
    main()
