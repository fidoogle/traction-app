"""The signed-in person's own email choices ("My notifications")."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.notifications import set_preference, types_for
from app.models import User
from app.web.deps import get_current_user_web
from app.web.templates import templates

router = APIRouter(prefix="/notifications")


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
        {"current_user": current_user, "groups": groups},
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
