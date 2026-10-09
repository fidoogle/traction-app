from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import ColumnElement, delete, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import settings
from app.core.activity import ENTITY_TYPES
from app.models import ActivityLog, User
from app.web.deps import get_current_user_web, get_optional_user_web, get_team_context
from app.web.team_context import TeamContext
from app.web.templates import templates

router = APIRouter(prefix="/activity")

PAGE_SIZE = 50


def _cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=settings.activity_retention_days)


def _visible(user: User, team_ctx: TeamContext) -> ColumnElement[bool]:
    """Which entries this user may see: those about the current team (or all
    their teams, under an admin's "All teams"). Entries with no team - user and
    organization changes - are for admins on "All teams" only."""
    in_scope = ActivityLog.team_id.in_(team_ctx.scope_ids)
    if team_ctx.can_view_all and team_ctx.current is None:
        return or_(in_scope, ActivityLog.team_id.is_(None))
    return in_scope


def _page(
    db: Session, user: User, team_ctx: TeamContext, before: Optional[int]
) -> tuple[list[ActivityLog], bool]:
    query = (
        select(ActivityLog)
        .where(
            ActivityLog.org_id == user.org_id,
            ActivityLog.created_at >= _cutoff(),
            _visible(user, team_ctx),
        )
        .order_by(ActivityLog.id.desc())
        .limit(PAGE_SIZE + 1)
    )
    if before is not None:
        query = query.where(ActivityLog.id < before)
    entries = list(db.scalars(query))
    return entries[:PAGE_SIZE], len(entries) > PAGE_SIZE


def _entries_context(current_user: User, entries, has_more: bool, last_seen: datetime) -> dict:
    return {
        "current_user": current_user,
        "entries": entries,
        "has_more": has_more,
        "last_seen": last_seen,
        "entity_types": ENTITY_TYPES,
    }


@router.get("")
def activity_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    db.execute(
        delete(ActivityLog).where(
            ActivityLog.org_id == current_user.org_id, ActivityLog.created_at < _cutoff()
        )
    )
    entries, has_more = _page(db, current_user, team_ctx, None)
    # Highlight what's new since the last visit, then mark it all as seen.
    last_seen = current_user.activity_last_seen_at
    current_user.activity_last_seen_at = datetime.now(timezone.utc)
    db.commit()
    context = _entries_context(current_user, entries, has_more, last_seen)
    context["retention_days"] = settings.activity_retention_days
    return templates.TemplateResponse(request, "activity/list.html", context)


@router.get("/entries")
def older_entries(
    request: Request,
    before: int,
    last_seen: datetime,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
    team_ctx: TeamContext = Depends(get_team_context),
):
    entries, has_more = _page(db, current_user, team_ctx, before)
    return templates.TemplateResponse(
        request,
        "activity/_entries.html",
        _entries_context(current_user, entries, has_more, last_seen),
    )


@router.get("/badge")
def unread_badge(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user_web),
):
    if current_user is None:
        # Signed out: an inert badge, which also stops the polling.
        return HTMLResponse('<span class="nav-badge"></span>')
    unread = db.scalar(
        select(func.count())
        .select_from(ActivityLog)
        .where(
            ActivityLog.org_id == current_user.org_id,
            _visible(current_user, request.state.team_ctx),
            ActivityLog.created_at > current_user.activity_last_seen_at,
            ActivityLog.created_at >= _cutoff(),
            # Your own changes aren't news to you.
            ActivityLog.actor_id.is_distinct_from(current_user.id),
        )
    )
    return templates.TemplateResponse(request, "activity/_badge.html", {"unread": unread})
