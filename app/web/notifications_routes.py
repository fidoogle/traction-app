"""The signed-in person's own email choices ("My notifications")."""

import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import settings
from app.core.notifications import set_preference, types_for
from app.models import User
from app.web.deps import get_current_user_web
from app.web.templates import templates

router = APIRouter(prefix="/notifications")


def _feed_url(request: Request, user: User) -> str | None:
    if not user.calendar_token:
        return None
    base = settings.base_url.rstrip("/") or str(request.base_url).rstrip("/")
    return f"{base}/calendar/{user.calendar_token}.ics"


def _feed_card(request: Request, user: User):
    return templates.TemplateResponse(
        request, "notifications/_calendar_feed.html", {"feed_url": _feed_url(request, user)}
    )


@router.post("/calendar-feed")
def make_calendar_feed(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    """Turns the subscription feed on, or replaces its address (the old one stops working)."""
    current_user.calendar_token = secrets.token_urlsafe(32)
    db.commit()
    return _feed_card(request, current_user)


@router.delete("/calendar-feed")
def remove_calendar_feed(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    current_user.calendar_token = None
    db.commit()
    return _feed_card(request, current_user)


@router.get("")
def my_notifications(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    groups: dict[str, list] = {}
    for nt, enabled in types_for(db, current_user):
        groups.setdefault(nt.group, []).append((nt, enabled))
    return templates.TemplateResponse(
        request,
        "notifications/index.html",
        {"current_user": current_user, "groups": groups, "feed_url": _feed_url(request, current_user)},
    )


@router.post("/{key}")
def save_notification(
    key: str,
    # A checkbox sends its value only when ticked, so a missing value means off.
    enabled: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    try:
        set_preference(db, current_user, key, bool(enabled))
    except ValueError:
        raise HTTPException(status_code=404)
    return HTMLResponse("Saved")
