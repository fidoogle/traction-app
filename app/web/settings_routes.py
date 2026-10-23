from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from markupsafe import escape
from sqlalchemy.orm import Session

from app.config import settings
from app.api.deps import get_db
from app.core.email import render_email, send_email
from app.core.org_time import all_timezones, is_valid_timezone
from app.models import User, UserRole
from app.web.deps import get_current_user_web
from app.web.templates import templates

router = APIRouter(prefix="/settings")


def _require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403)


@router.get("")
def settings_page(request: Request, current_user: User = Depends(get_current_user_web)):
    _require_admin(current_user)
    return templates.TemplateResponse(
        request,
        "settings/index.html",
        {
            "current_user": current_user,
            "cfg": settings,
            "org": current_user.organization,
            "timezones": all_timezones(),
        },
    )


@router.post("/timezone")
def save_timezone(
    timezone: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    timezone = timezone.strip()
    if not is_valid_timezone(timezone):
        raise HTTPException(status_code=422, detail="That is not a known time zone.")
    current_user.organization.timezone = timezone
    db.commit()
    return HTMLResponse("Saved")


@router.post("/calendar-links")
def save_calendar_links(
    # A checkbox sends its value only when ticked, so a missing value means off.
    enabled: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    current_user.organization.calendar_web_links = bool(enabled)
    db.commit()
    return HTMLResponse("Saved")


@router.post("/test-email")
def send_test_email(current_user: User = Depends(get_current_user_web)):
    """Sends a test message to the signed-in admin's own address (never to an
    address typed into the form)."""
    _require_admin(current_user)
    if not settings.email_enabled:
        return HTMLResponse('<p class="error">Email is not configured.</p>')
    text, html = render_email("test")
    result = send_email(current_user.email, "Traction test email", text, html)
    if result.ok:
        return HTMLResponse(f"<p>Test email sent to <strong>{escape(current_user.email)}</strong>.</p>")
    return HTMLResponse(f'<p class="error">Could not send: {escape(result.error)}</p>')
