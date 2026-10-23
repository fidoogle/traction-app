from datetime import datetime, time, timedelta, timezone as dt_timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from markupsafe import escape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.api.deps import get_db
from app.core.digest_emails import STEP_MINUTES, WEEKDAYS, send_digest_now
from app.core.email import render_email, send_email
from app.core.notifications import BY_KEY
from app.core.org_time import all_timezones, format_short, is_valid_timezone, tz_of
from app.models import NotificationLog, User, UserRole
from app.web.deps import get_current_user_web
from app.web.templates import templates

router = APIRouter(prefix="/settings")


def _require_admin(current_user: User) -> None:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403)


RECENT_FAILURES = 20


def _email_health(db: Session, user: User) -> dict:
    """The last day's counts and the most recent failed emails, for the Settings page."""
    since = datetime.now(dt_timezone.utc) - timedelta(hours=24)
    in_org = User.org_id == user.org_id
    counts = dict(
        db.execute(
            select(NotificationLog.status, func.count())
            .join(User, User.id == NotificationLog.user_id)
            .where(in_org, NotificationLog.created_at >= since, NotificationLog.status.in_(["sent", "failed"]))
            .group_by(NotificationLog.status)
        ).all()
    )
    rows = db.execute(
        select(NotificationLog.key, NotificationLog.error, NotificationLog.created_at, User.name, User.email)
        .join(User, User.id == NotificationLog.user_id)
        .where(in_org, NotificationLog.status == "failed")
        .order_by(NotificationLog.created_at.desc())
        .limit(RECENT_FAILURES)
    ).all()
    tz = tz_of(user.organization.timezone)
    return {
        "sent_24h": counts.get("sent", 0),
        "failed_24h": counts.get("failed", 0),
        "failures": [
            {
                "when": format_short(r.created_at, tz),
                "who": f"{r.name} ({r.email})",
                "kind": BY_KEY[r.key].label if r.key in BY_KEY else r.key,
                "error": r.error or "",
            }
            for r in rows
        ],
    }


@router.get("")
def settings_page(
    request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user_web)
):
    _require_admin(current_user)
    return templates.TemplateResponse(
        request,
        "settings/index.html",
        {
            "current_user": current_user,
            "cfg": settings,
            "org": current_user.organization,
            "timezones": all_timezones(),
            "weekdays": WEEKDAYS,
            "health": _email_health(db, current_user),
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


@router.post("/digest")
def save_digest_schedule(
    weekday: int = Form(...),
    at: time = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    if not 0 <= weekday <= 6:
        raise HTTPException(status_code=422, detail="Pick a day of the week.")
    if at.minute % STEP_MINUTES or at.second:
        raise HTTPException(status_code=422, detail=f"Pick a time on a {STEP_MINUTES}-minute step.")
    org = current_user.organization
    org.digest_weekday, org.digest_time = weekday, at.replace(microsecond=0)
    db.commit()
    return HTMLResponse("Saved. It applies from the next summary.")


@router.post("/digest/send-now")
def send_digest_now_route(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user_web),
):
    _require_admin(current_user)
    if not settings.email_enabled:
        return HTMLResponse('<span class="error">Email is not configured.</span>')
    background_tasks.add_task(send_digest_now, current_user.org_id)
    return HTMLResponse("Sending. Anyone who already got this week's summary will not get another.")


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
