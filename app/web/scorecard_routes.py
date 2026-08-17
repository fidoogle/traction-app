import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_db
from app.models import Measurable, ScorecardEntry, Team, User, UserRole
from app.web.deps import get_current_user_web
from app.web.templates import templates

router = APIRouter(prefix="/scorecard")

HISTORY_WEEKS = 12
CHART_WIDTH = 280
CHART_HEIGHT = 60
CHART_PAD = 8


def _this_weeks_friday() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday()) + timedelta(days=4)


def _build_sparkline(entries: list[ScorecardEntry], goal_value: float) -> dict:
    if not entries:
        return {"points": "", "goal_y": None, "width": CHART_WIDTH, "height": CHART_HEIGHT}

    values = [e.actual_value for e in entries] + [goal_value]
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    n = len(entries)
    step = (CHART_WIDTH - 2 * CHART_PAD) / (n - 1) if n > 1 else 0

    def y_for(value: float) -> float:
        return CHART_HEIGHT - CHART_PAD - ((value - lo) / span) * (CHART_HEIGHT - 2 * CHART_PAD)

    points = " ".join(
        f"{CHART_PAD + i * step:.1f},{y_for(e.actual_value):.1f}" for i, e in enumerate(entries)
    )
    return {
        "points": points,
        "goal_y": round(y_for(goal_value), 1),
        "width": CHART_WIDTH,
        "height": CHART_HEIGHT,
    }


def _measurable_card_context(db: Session, measurable: Measurable, current_user: User) -> dict:
    entries = list(
        reversed(
            db.scalars(
                select(ScorecardEntry)
                .where(ScorecardEntry.measurable_id == measurable.id)
                .order_by(ScorecardEntry.week_ending.desc())
                .limit(HISTORY_WEEKS)
            ).all()
        )
    )
    latest = entries[-1] if entries else None
    return {
        "current_user": current_user,
        "measurable": measurable,
        "chart": _build_sparkline(entries, measurable.goal_value),
        "latest_value": latest.actual_value if latest else None,
        "latest_week": latest.week_ending if latest else None,
        "default_week_ending": _this_weeks_friday(),
    }


def _org_measurables_query(org_id: uuid.UUID):
    return (
        select(Measurable)
        .join(Team, Measurable.team_id == Team.id)
        .where(Team.org_id == org_id)
        .options(joinedload(Measurable.team))
        .order_by(Measurable.name)
    )


@router.get("")
def list_scorecard(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    measurables = db.scalars(_org_measurables_query(current_user.org_id)).unique().all()
    teams = db.scalars(
        select(Team).where(Team.org_id == current_user.org_id).order_by(Team.name)
    ).all()
    cards = [_measurable_card_context(db, m, current_user) for m in measurables]
    return templates.TemplateResponse(
        request,
        "scorecard/list.html",
        {"current_user": current_user, "cards": cards, "teams": teams},
    )


@router.post("")
def create_measurable(
    request: Request,
    name: str = Form(...),
    team_id: uuid.UUID = Form(...),
    goal_value: float = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)
    team = db.get(Team, team_id)
    if team is None or team.org_id != current_user.org_id:
        raise HTTPException(status_code=404)

    measurable = Measurable(team_id=team_id, name=name, goal_value=goal_value)
    db.add(measurable)
    db.commit()
    db.refresh(measurable)
    measurable.team = team
    return templates.TemplateResponse(
        request,
        "scorecard/_card.html",
        _measurable_card_context(db, measurable, current_user),
    )


@router.post("/{measurable_id}/entries")
def log_scorecard_entry(
    request: Request,
    measurable_id: uuid.UUID,
    week_ending: date = Form(...),
    actual_value: float = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(status_code=403)
    measurable = db.scalar(
        select(Measurable)
        .join(Team, Measurable.team_id == Team.id)
        .where(Measurable.id == measurable_id, Team.org_id == current_user.org_id)
        .options(joinedload(Measurable.team))
    )
    if measurable is None:
        raise HTTPException(status_code=404)

    existing = db.scalar(
        select(ScorecardEntry).where(
            ScorecardEntry.measurable_id == measurable_id,
            ScorecardEntry.week_ending == week_ending,
        )
    )
    if existing is not None:
        existing.actual_value = actual_value
    else:
        db.add(
            ScorecardEntry(
                measurable_id=measurable_id, week_ending=week_ending, actual_value=actual_value
            )
        )
    db.commit()

    return templates.TemplateResponse(
        request,
        "scorecard/_card.html",
        _measurable_card_context(db, measurable, current_user),
    )
