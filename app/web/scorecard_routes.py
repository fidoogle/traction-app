"""Scorecards: 13-week, Sunday-start grids of measurables.

Admins create/delete scorecards and add/edit/delete measurables (assigning
each an owner). A measurable's owner - or an admin - types values into its
weekly cells; everyone else, viewers included, sees them read-only.
"""

import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_db
from app.core.scorecard_format import format_value, goal_met, parse_value
from app.models import (
    SCORECARD_WEEKS,
    GoalDirection,
    Measurable,
    MeasurableUnit,
    Scorecard,
    ScorecardEntry,
    User,
    UserRole,
)
from app.web.deps import get_current_user_web
from app.web.templates import templates

router = APIRouter(prefix="/scorecards")
# The page used to live at /scorecard; keep old bookmarks working.
legacy_router = APIRouter()

SUNDAY = 6  # date.weekday()


@legacy_router.get("/scorecard")
def legacy_scorecard_redirect():
    return RedirectResponse("/scorecards", status_code=307)


def _require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403)


def _default_start() -> date:
    """The Sunday that began the current week."""
    today = date.today()
    return today - timedelta(days=(today.weekday() + 1) % 7)


def _org_users(db: Session, org_id: uuid.UUID):
    return db.scalars(select(User).where(User.org_id == org_id).order_by(User.name)).all()


def _get_scorecard(db: Session, scorecard_id: uuid.UUID, org_id: uuid.UUID) -> Scorecard:
    scorecard = db.scalar(
        select(Scorecard)
        .where(Scorecard.id == scorecard_id, Scorecard.org_id == org_id)
        .options(
            selectinload(Scorecard.measurables).selectinload(Measurable.owner),
            selectinload(Scorecard.measurables).selectinload(Measurable.scorecard_entries),
        )
    )
    if scorecard is None:
        raise HTTPException(status_code=404)
    return scorecard


def _get_measurable(
    db: Session, scorecard_id: uuid.UUID, measurable_id: uuid.UUID, org_id: uuid.UUID
) -> Measurable:
    measurable = db.scalar(
        select(Measurable)
        .join(Scorecard, Measurable.scorecard_id == Scorecard.id)
        .where(
            Measurable.id == measurable_id,
            Scorecard.id == scorecard_id,
            Scorecard.org_id == org_id,
        )
        .options(selectinload(Measurable.owner), selectinload(Measurable.scorecard_entries))
    )
    if measurable is None:
        raise HTTPException(status_code=404)
    return measurable


def _can_edit_cells(current_user: User, measurable: Measurable) -> bool:
    return current_user.role == UserRole.ADMIN or (
        measurable.owner_id is not None and measurable.owner_id == current_user.id
    )


def _weeks(scorecard: Scorecard) -> list[dict]:
    today = date.today()
    weeks = []
    for n in range(1, SCORECARD_WEEKS + 1):
        start = scorecard.week_start(n)
        weeks.append(
            {"n": n, "start": start, "is_current": start <= today < start + timedelta(days=7)}
        )
    return weeks


def _cell(
    scorecard: Scorecard,
    measurable: Measurable,
    week: dict,
    entry: Optional[ScorecardEntry],
    current_user: User,
    error: bool = False,
) -> dict:
    state = ""
    text = ""
    if entry is not None:
        text = format_value(entry.actual_value, measurable.unit)
        met = goal_met(entry.actual_value, measurable.goal_value, measurable.goal_direction)
        state = "met" if met else "missed"
    return {
        "scorecard": scorecard,
        "measurable": measurable,
        "week": week,
        "text": text,
        "state": state,
        "error": error,
        "can_edit": _can_edit_cells(current_user, measurable),
    }


def _row_context(scorecard: Scorecard, measurable: Measurable, current_user: User) -> dict:
    by_week = {e.week_number: e for e in measurable.scorecard_entries}
    return {
        "current_user": current_user,
        "scorecard": scorecard,
        "measurable": measurable,
        "cells": [
            _cell(scorecard, measurable, w, by_week.get(w["n"]), current_user)
            for w in _weeks(scorecard)
        ],
    }


def _row_response(request: Request, scorecard: Scorecard, measurable: Measurable, user: User):
    return templates.TemplateResponse(
        request, "scorecard/_row.html", _row_context(scorecard, measurable, user)
    )


def _clean_name(name: str) -> str:
    name = name.strip()
    if not name or len(name) > 255:
        raise HTTPException(status_code=422)
    return name


def _parse_goal(text: str) -> float:
    try:
        return parse_value(text)
    except ValueError:
        raise HTTPException(status_code=422)


def _check_owner(db: Session, owner_id: uuid.UUID, org_id: uuid.UUID) -> None:
    owner = db.get(User, owner_id)
    if owner is None or owner.org_id != org_id:
        raise HTTPException(status_code=404)


def _scorecard_status(scorecard: Scorecard, today: date) -> str:
    if today < scorecard.start_date:
        return "Upcoming"
    if today > scorecard.end_date:
        return "Past"
    return "Current"


# --- Scorecards -------------------------------------------------------------


@router.get("")
def list_scorecards(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    scorecards = db.scalars(
        select(Scorecard)
        .where(Scorecard.org_id == current_user.org_id)
        .options(selectinload(Scorecard.measurables))
        .order_by(Scorecard.start_date.desc(), Scorecard.name)
    ).all()
    today = date.today()
    return templates.TemplateResponse(
        request,
        "scorecard/list.html",
        {
            "current_user": current_user,
            "scorecards": [
                {"scorecard": s, "status": _scorecard_status(s, today)} for s in scorecards
            ],
            "default_start": _default_start(),
        },
    )


@router.post("")
def create_scorecard(
    name: str = Form(...),
    start_date: date = Form(...),
    copy_from: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    name = _clean_name(name)
    if start_date.weekday() != SUNDAY:
        raise HTTPException(status_code=422, detail="Start date must be a Sunday")

    source = None
    if copy_from.strip():
        try:
            source_id = uuid.UUID(copy_from)
        except ValueError:
            raise HTTPException(status_code=422)
        source = _get_scorecard(db, source_id, current_user.org_id)

    scorecard = Scorecard(org_id=current_user.org_id, name=name, start_date=start_date)
    if source is not None:
        # Same rows (owners, goals, units), empty weeks.
        for m in source.measurables:
            scorecard.measurables.append(
                Measurable(
                    owner_id=m.owner_id,
                    name=m.name,
                    unit=m.unit,
                    goal_value=m.goal_value,
                    goal_direction=m.goal_direction,
                    position=m.position,
                )
            )
    db.add(scorecard)
    db.commit()
    return Response(status_code=200, headers={"HX-Redirect": f"/scorecards/{scorecard.id}"})


@router.delete("/{scorecard_id}")
def delete_scorecard(
    scorecard_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    scorecard = _get_scorecard(db, scorecard_id, current_user.org_id)
    db.delete(scorecard)
    db.commit()
    return Response(status_code=200)


@router.get("/{scorecard_id}")
def view_scorecard(
    request: Request,
    scorecard_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    scorecard = _get_scorecard(db, scorecard_id, current_user.org_id)
    return templates.TemplateResponse(
        request,
        "scorecard/detail.html",
        {
            "current_user": current_user,
            "scorecard": scorecard,
            "weeks": _weeks(scorecard),
            "rows": [_row_context(scorecard, m, current_user) for m in scorecard.measurables],
            "org_users": _org_users(db, current_user.org_id),
            "units": list(MeasurableUnit),
            "directions": list(GoalDirection),
        },
    )


# --- Measurables (admin) ----------------------------------------------------


@router.post("/{scorecard_id}/measurables")
def create_measurable(
    request: Request,
    scorecard_id: uuid.UUID,
    name: str = Form(...),
    owner_id: uuid.UUID = Form(...),
    unit: MeasurableUnit = Form(...),
    goal_value: str = Form(...),
    goal_direction: GoalDirection = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    scorecard = _get_scorecard(db, scorecard_id, current_user.org_id)
    _check_owner(db, owner_id, current_user.org_id)
    measurable = Measurable(
        name=_clean_name(name),
        owner_id=owner_id,
        unit=unit.value,
        goal_value=_parse_goal(goal_value),
        goal_direction=goal_direction.value,
        position=max((m.position for m in scorecard.measurables), default=0) + 1,
    )
    scorecard.measurables.append(measurable)
    db.commit()
    db.expire_all()
    scorecard = _get_scorecard(db, scorecard_id, current_user.org_id)
    measurable = _get_measurable(db, scorecard_id, measurable.id, current_user.org_id)
    return _row_response(request, scorecard, measurable, current_user)


@router.get("/{scorecard_id}/measurables/{measurable_id}/edit")
def edit_measurable_form(
    request: Request,
    scorecard_id: uuid.UUID,
    measurable_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    measurable = _get_measurable(db, scorecard_id, measurable_id, current_user.org_id)
    return templates.TemplateResponse(
        request,
        "scorecard/_edit_measurable.html",
        {
            "current_user": current_user,
            "scorecard_id": scorecard_id,
            "measurable": measurable,
            "org_users": _org_users(db, current_user.org_id),
            "units": list(MeasurableUnit),
            "directions": list(GoalDirection),
        },
    )


@router.put("/{scorecard_id}/measurables/{measurable_id}")
def update_measurable(
    request: Request,
    scorecard_id: uuid.UUID,
    measurable_id: uuid.UUID,
    name: str = Form(...),
    owner_id: uuid.UUID = Form(...),
    unit: MeasurableUnit = Form(...),
    goal_value: str = Form(...),
    goal_direction: GoalDirection = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    measurable = _get_measurable(db, scorecard_id, measurable_id, current_user.org_id)
    _check_owner(db, owner_id, current_user.org_id)
    measurable.name = _clean_name(name)
    measurable.owner_id = owner_id
    measurable.unit = unit.value
    measurable.goal_value = _parse_goal(goal_value)
    measurable.goal_direction = goal_direction.value
    db.commit()
    db.expire_all()
    scorecard = _get_scorecard(db, scorecard_id, current_user.org_id)
    measurable = _get_measurable(db, scorecard_id, measurable_id, current_user.org_id)
    return _row_response(request, scorecard, measurable, current_user)


@router.delete("/{scorecard_id}/measurables/{measurable_id}")
def delete_measurable(
    scorecard_id: uuid.UUID,
    measurable_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    measurable = _get_measurable(db, scorecard_id, measurable_id, current_user.org_id)
    db.delete(measurable)
    db.commit()
    return Response(status_code=200)


# --- Cells (owner or admin) -------------------------------------------------


@router.put("/{scorecard_id}/measurables/{measurable_id}/weeks/{week}")
def set_cell(
    request: Request,
    scorecard_id: uuid.UUID,
    measurable_id: uuid.UUID,
    week: int,
    value: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    if not 1 <= week <= SCORECARD_WEEKS:
        raise HTTPException(status_code=404)
    scorecard = _get_scorecard(db, scorecard_id, current_user.org_id)
    measurable = _get_measurable(db, scorecard_id, measurable_id, current_user.org_id)
    if not _can_edit_cells(current_user, measurable):
        raise HTTPException(status_code=403)

    entry = next((e for e in measurable.scorecard_entries if e.week_number == week), None)
    error = False
    if not value.strip():
        # Clearing a cell (e.g. a holiday week) removes its value.
        if entry is not None:
            db.delete(entry)
    else:
        try:
            parsed = parse_value(value)
        except ValueError:
            parsed = None
            error = True
        if parsed is not None and entry is not None:
            entry.actual_value = parsed
        elif parsed is not None:
            db.add(ScorecardEntry(measurable_id=measurable.id, week_number=week, actual_value=parsed))
    db.commit()
    db.expire_all()

    measurable = _get_measurable(db, scorecard_id, measurable_id, current_user.org_id)
    entry = next((e for e in measurable.scorecard_entries if e.week_number == week), None)
    week_ctx = next(w for w in _weeks(scorecard) if w["n"] == week)
    return templates.TemplateResponse(
        request,
        "scorecard/_cell.html",
        {"c": _cell(scorecard, measurable, week_ctx, entry, current_user, error=error)},
    )
