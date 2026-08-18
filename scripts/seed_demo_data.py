"""Seed a rich, entirely fictional demo dataset for local development and
UI work.

Not for production use - this creates a fake school district (Cedar Valley
USD) with multiple teams, users across all three roles, an accountability
chart (including a deliberately vacant seat), a VTO, rocks, several weeks
of scorecard history, issues/to-dos, meetings, and People Analyzer entries,
so there's something real to look at while building the UI.

Usage:
    python scripts/seed_demo_data.py [--reset]

--reset truncates all app tables first. Destructive - only ever run this
against a local/dev database, never a database with real district data.
"""
import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Issue,
    IssueStatus,
    Measurable,
    Meeting,
    MeetingStatus,
    Organization,
    PeopleAnalyzerEntry,
    Rock,
    RockStatus,
    ScorecardEntry,
    Seat,
    Team,
    Todo,
    TodoStatus,
    User,
    UserRole,
    VTO,
)

DEMO_TABLES = [
    "people_analyzer_entries",
    "vtos",
    "seats",
    "todos",
    "issues",
    "scorecard_entries",
    "measurables",
    "rocks",
    "meetings",
    "users",
    "teams",
    "organizations",
]

DEMO_PASSWORD = "demo1234"


def reset(db) -> None:
    db.execute(text(f"TRUNCATE {', '.join(DEMO_TABLES)} CASCADE"))
    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset", action="store_true", help="Truncate all app tables first (destructive)"
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.reset:
            reset(db)

        org = Organization(name="Cedar Valley Unified School District")
        db.add(org)
        db.flush()

        leadership = Team(org_id=org.id, name="Leadership Team", meeting_day="Monday")
        curriculum = Team(org_id=org.id, name="Curriculum & Instruction", meeting_day="Tuesday")
        ops = Team(org_id=org.id, name="Operations & Facilities", meeting_day="Wednesday")
        db.add_all([leadership, curriculum, ops])
        db.flush()

        def make_user(name: str, email: str, team: Team, role: UserRole) -> User:
            user = User(
                org_id=org.id,
                team_id=team.id,
                name=name,
                email=email,
                role=role,
                hashed_password=hash_password(DEMO_PASSWORD),
            )
            db.add(user)
            db.flush()
            return user

        superintendent = make_user(
            "Dana Admin", "admin@school.example", leadership, UserRole.ADMIN
        )
        cfo = make_user(
            "Marcus Member", "member1@school.example", leadership, UserRole.MEMBER
        )
        curriculum_dir = make_user(
            "Priya Member", "member2@school.example", curriculum, UserRole.MEMBER
        )
        ops_dir = make_user(
            "Sam Member", "member3@school.example", ops, UserRole.MEMBER
        )
        board_liaison = make_user(
            "Ellis Viewer", "viewer@school.example", leadership, UserRole.VIEWER
        )

        # --- Accountability chart ---
        integrator_seat = Seat(
            team_id=leadership.id,
            user_id=superintendent.id,
            title="Integrator",
            responsibilities=[
                "Own the annual plan",
                "Run the Leadership Team L10",
                "Resolve cross-department issues",
            ],
        )
        db.add(integrator_seat)
        db.flush()

        finance_seat = Seat(
            team_id=leadership.id,
            user_id=cfo.id,
            parent_seat_id=integrator_seat.id,
            title="Finance Leader",
            responsibilities=["Own the budget", "Monthly financial reporting"],
        )
        curriculum_seat = Seat(
            team_id=curriculum.id,
            user_id=curriculum_dir.id,
            parent_seat_id=integrator_seat.id,
            title="Curriculum Leader",
            responsibilities=["Own instructional quality", "Lead curriculum adoption"],
        )
        ops_seat = Seat(
            team_id=ops.id,
            user_id=ops_dir.id,
            parent_seat_id=integrator_seat.id,
            title="Operations Leader",
            responsibilities=["Own facilities & transportation", "Vendor management"],
        )
        db.add_all([finance_seat, curriculum_seat, ops_seat])
        db.flush()

        # Deliberately vacant - demonstrates the "open seat" state.
        vacant_seat = Seat(
            team_id=ops.id,
            parent_seat_id=ops_seat.id,
            title="Facilities Manager",
            responsibilities=["Day-to-day facilities upkeep"],
        )
        db.add(vacant_seat)

        # --- VTO ---
        vto = VTO(
            org_id=org.id,
            core_values=[
                {
                    "name": "Students First",
                    "description": "Every decision starts with what is best for kids",
                },
                {"name": "Integrity", "description": "We do what we say we'll do"},
                {
                    "name": "Ownership",
                    "description": "We take responsibility for outcomes, not just effort",
                },
            ],
            core_focus_purpose="Prepare every student for a life of their choosing",
            core_focus_niche="K-12 public education in Cedar Valley",
            ten_year_target={
                "description": "Every school in the top decile statewide for student growth",
                "target_date": "2036-06-30",
            },
            three_year_picture={
                "target_date": "2029-06-30",
                "looks_like": [
                    "Graduation rate above 95%",
                    "Every school fully staffed",
                    "Balanced budget with 3 months reserve",
                ],
            },
            one_year_plan={
                "target_date": "2027-06-30",
                "goals": [
                    "Launch new K-5 literacy curriculum",
                    "Close the achievement gap by 5 points",
                    "Complete HVAC upgrades at 3 sites",
                ],
            },
        )
        db.add(vto)

        # --- Rocks (current quarter) ---
        quarter = "2026-Q3"
        db.add_all(
            [
                Rock(
                    team_id=leadership.id,
                    owner_id=superintendent.id,
                    title="Finalize FY27 budget",
                    quarter=quarter,
                    status=RockStatus.ON_TRACK,
                ),
                Rock(
                    team_id=leadership.id,
                    owner_id=cfo.id,
                    title="Complete annual audit",
                    quarter=quarter,
                    status=RockStatus.OFF_TRACK,
                ),
                Rock(
                    team_id=curriculum.id,
                    owner_id=curriculum_dir.id,
                    title="Pilot new literacy curriculum in 3 schools",
                    quarter=quarter,
                    status=RockStatus.ON_TRACK,
                ),
                Rock(
                    team_id=ops.id,
                    owner_id=ops_dir.id,
                    title="Complete HVAC upgrade at Lincoln Elementary",
                    quarter=quarter,
                    status=RockStatus.DONE,
                ),
            ]
        )

        # --- Measurables + weekly scorecard history ---
        measurables = [
            Measurable(team_id=leadership.id, name="Weekly cash on hand ($M)", goal_value=5.0),
            Measurable(
                team_id=curriculum.id, name="Chronic absenteeism rate (%)", goal_value=8.0
            ),
            Measurable(team_id=ops.id, name="Open maintenance tickets", goal_value=15.0),
        ]
        db.add_all(measurables)
        db.flush()

        random.seed(42)
        today = date.today()
        this_friday = today - timedelta(days=today.weekday()) + timedelta(days=4)
        for measurable in measurables:
            for weeks_ago in range(12, 0, -1):
                week_ending = this_friday - timedelta(weeks=weeks_ago)
                drift = random.uniform(-0.15, 0.15) * measurable.goal_value
                db.add(
                    ScorecardEntry(
                        measurable_id=measurable.id,
                        week_ending=week_ending,
                        actual_value=round(measurable.goal_value + drift, 1),
                    )
                )

        # --- Issues + to-dos ---
        issue1 = Issue(
            team_id=leadership.id,
            title="Substitute teacher shortage",
            status=IssueStatus.OPEN,
            priority=1,
        )
        issue2 = Issue(
            team_id=ops.id,
            title="Aging bus fleet needs a replacement plan",
            status=IssueStatus.OPEN,
            priority=2,
        )
        issue3 = Issue(
            team_id=curriculum.id,
            title="Vendor delayed curriculum materials",
            status=IssueStatus.RESOLVED,
            priority=3,
        )
        db.add_all([issue1, issue2, issue3])
        db.flush()

        db.add_all(
            [
                Todo(
                    owner_id=superintendent.id,
                    issue_id=issue1.id,
                    title="Draft substitute pay increase proposal",
                    due_date=today + timedelta(days=7),
                    status=TodoStatus.OPEN,
                ),
                Todo(
                    owner_id=ops_dir.id,
                    issue_id=issue2.id,
                    title="Get quotes for 3 replacement buses",
                    due_date=today + timedelta(days=14),
                    status=TodoStatus.OPEN,
                ),
                Todo(
                    owner_id=curriculum_dir.id,
                    issue_id=issue3.id,
                    title="Confirm delivery date with vendor",
                    due_date=today - timedelta(days=2),
                    status=TodoStatus.DONE,
                ),
            ]
        )

        # --- Meetings ---
        db.add_all(
            [
                Meeting(
                    team_id=leadership.id,
                    scheduled_date=today - timedelta(days=7),
                    status=MeetingStatus.COMPLETED,
                ),
                Meeting(
                    team_id=leadership.id,
                    scheduled_date=today + timedelta(days=7),
                    status=MeetingStatus.SCHEDULED,
                ),
            ]
        )

        # --- People Analyzer ---
        db.add_all(
            [
                PeopleAnalyzerEntry(
                    user_id=cfo.id,
                    seat_id=finance_seat.id,
                    evaluated_at=today - timedelta(days=30),
                    gets_it=True,
                    wants_it=True,
                    has_capacity=True,
                    core_values_ratings={
                        "Students First": True,
                        "Integrity": True,
                        "Ownership": True,
                    },
                ),
                PeopleAnalyzerEntry(
                    user_id=curriculum_dir.id,
                    seat_id=curriculum_seat.id,
                    evaluated_at=today - timedelta(days=30),
                    gets_it=True,
                    wants_it=True,
                    has_capacity=False,
                    core_values_ratings={
                        "Students First": True,
                        "Integrity": True,
                        "Ownership": False,
                    },
                    notes="Stretched thin during the curriculum pilot",
                ),
            ]
        )

        db.commit()

        print(f"Demo data seeded for {org.name} ({org.id})")
        print(f"Teams: {leadership.name}, {curriculum.name}, {ops.name}")
        print(f"\nLog in as any of these (password: {DEMO_PASSWORD}):")
        for user in [superintendent, cfo, curriculum_dir, ops_dir, board_liaison]:
            print(f"  {user.email}  [{user.role.value}]")
    finally:
        db.close()


if __name__ == "__main__":
    main()
