"""What goes in a person's weekly summary email.

By role (the system decides; nobody configures it):
  viewer      a read-only summary of each team they are on (they own nothing)
  member      what they own: open To-Dos, Rocks that are off track, measurables off goal
  team admin  the same, plus the summary of each team they administer
  admin       what they own (an admin is not mailed the summary of every team)

Everything is looked at as of `today` on the organization's calendar. Returns
an empty digest when there is nothing to say, and then no email is sent.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.due_emails import due_label
from app.core.notifications import ADMIN, MEMBER, TEAM_ADMIN, VIEWER, hats
from app.core.scorecard_format import format_goal, format_value, goal_met
from app.models import (
    Issue,
    IssueStatus,
    Measurable,
    Rock,
    RockStatus,
    Scorecard,
    Team,
    TeamMembership,
    Todo,
    TodoStatus,
    User,
)
from app.models.scorecard import SCORECARD_WEEKS

MAX_ITEMS = 10  # per list; the rest are summarised as "and N more"


def current_quarter(today: date) -> str:
    """The quarter label rocks use, e.g. 2026-Q4."""
    return f"{today.year}-Q{(today.month - 1) // 3 + 1}"


@dataclass
class TeamSummary:
    name: str
    rocks_total: int = 0
    rocks_done: int = 0
    rocks_off_track: list[str] = field(default_factory=list)
    open_todos: int = 0
    overdue_todos: int = 0
    open_issues: int = 0
    measured: int = 0  # measurables with a recent result
    off_goal: list[str] = field(default_factory=list)

    @property
    def has_content(self) -> bool:
        return bool(self.rocks_total or self.open_todos or self.open_issues or self.measured)


@dataclass
class Digest:
    todos: list[dict] = field(default_factory=list)
    todos_more: int = 0
    rocks: list[dict] = field(default_factory=list)
    off_goal: list[dict] = field(default_factory=list)
    teams: list[TeamSummary] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.todos or self.rocks or self.off_goal or any(t.has_content for t in self.teams))


def _latest_results(db: Session, team_ids: list, today: date) -> list[dict]:
    """The most recent result (this week or last) for every measurable on a
    team's current scorecard, with whether it met its goal."""
    scorecards = db.scalars(
        select(Scorecard)
        .where(Scorecard.team_id.in_(team_ids))
        .options(joinedload(Scorecard.measurables).joinedload(Measurable.scorecard_entries))
    ).unique().all()
    results = []
    for card in scorecards:
        if not card.start_date <= today <= card.end_date:
            continue
        week = min(SCORECARD_WEEKS, (today - card.start_date).days // 7 + 1)
        for m in card.measurables:
            recent = [e for e in m.scorecard_entries if week - 1 <= e.week_number <= week]
            if not recent:
                continue
            entry = max(recent, key=lambda e: e.week_number)
            results.append(
                {
                    "team_id": card.team_id,
                    "owner_id": m.owner_id,
                    "name": m.name,
                    "met": goal_met(entry.actual_value, m.goal_value, m.goal_direction),
                    "actual": format_value(entry.actual_value, m.unit),
                    "goal": format_goal(m.goal_value, m.unit, m.goal_direction),
                }
            )
    return results


def _team_summary(db: Session, team: Team, quarter: str, today: date, results: list[dict]) -> TeamSummary:
    summary = TeamSummary(name=team.name)
    rocks = db.scalars(select(Rock).where(Rock.team_id == team.id, Rock.quarter == quarter)).all()
    summary.rocks_total = len(rocks)
    summary.rocks_done = sum(1 for r in rocks if r.status == RockStatus.DONE)
    summary.rocks_off_track = sorted(r.title for r in rocks if r.status == RockStatus.OFF_TRACK)
    todos = db.execute(
        select(func.count(), func.count().filter(Todo.due_date < today))
        .where(Todo.team_id == team.id, Todo.status == TodoStatus.OPEN)
    ).one()
    summary.open_todos, summary.overdue_todos = todos[0], todos[1]
    summary.open_issues = db.scalar(
        select(func.count()).select_from(Issue).where(Issue.team_id == team.id, Issue.status == IssueStatus.OPEN)
    )
    mine = [r for r in results if r["team_id"] == team.id]
    summary.measured = len(mine)
    summary.off_goal = sorted(r["name"] for r in mine if not r["met"])
    return summary


def build_digest(db: Session, user: User, today: date) -> Digest:
    digest = Digest()
    user_hats = hats(db, user)
    team_ids = list(db.scalars(select(TeamMembership.team_id).where(TeamMembership.user_id == user.id)))
    if not team_ids:
        return digest
    quarter = current_quarter(today)
    results = _latest_results(db, team_ids, today)

    owns_things = bool(user_hats & {MEMBER, TEAM_ADMIN, ADMIN})
    if owns_things:
        todos = db.scalars(
            select(Todo)
            .where(Todo.owner_id == user.id, Todo.status == TodoStatus.OPEN)
            .options(joinedload(Todo.team))
            .order_by(Todo.due_date.is_(None), Todo.due_date, Todo.title)
        ).unique().all()
        digest.todos = [
            {
                "title": t.title,
                "team": t.team.name,
                "when": due_label(t.due_date, today) if t.due_date else "no due date",
                "overdue": bool(t.due_date and t.due_date < today),
            }
            for t in todos[:MAX_ITEMS]
        ]
        digest.todos_more = max(0, len(todos) - MAX_ITEMS)

        rocks = db.scalars(
            select(Rock)
            .where(Rock.owner_id == user.id, Rock.quarter == quarter, Rock.status == RockStatus.OFF_TRACK)
            .options(joinedload(Rock.team))
            .order_by(Rock.title)
        ).unique().all()
        digest.rocks = [{"title": r.title, "team": r.team.name} for r in rocks]

        digest.off_goal = [
            {"name": r["name"], "actual": r["actual"], "goal": r["goal"]}
            for r in results
            if r["owner_id"] == user.id and not r["met"]
        ]

    # Team totals: viewers see their own teams, team admins the ones they administer.
    summary_team_ids: Optional[list] = None
    if VIEWER in user_hats:
        summary_team_ids = team_ids
    elif TEAM_ADMIN in user_hats:
        summary_team_ids = list(
            db.scalars(
                select(TeamMembership.team_id).where(
                    TeamMembership.user_id == user.id, TeamMembership.is_team_admin.is_(True)
                )
            )
        )
    if summary_team_ids:
        teams = db.scalars(select(Team).where(Team.id.in_(summary_team_ids)).order_by(Team.name)).all()
        digest.teams = [t for t in (_team_summary(db, team, quarter, today, results) for team in teams) if t.has_content]
    return digest


def week_key(day: date) -> str:
    """ISO week label for a date, e.g. 2026-W44 (weeks run Monday to Sunday)."""
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())
