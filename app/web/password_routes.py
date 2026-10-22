"""Forgot-password and set-password (the link in welcome / reset emails)."""

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import settings
from app.core.account_emails import send_reset_email
from app.core.password_tokens import (
    MIN_PASSWORD_LENGTH,
    RESET,
    find_valid,
    issue_token,
    redeem,
)
from app.core.rate_limit import FailureRateLimiter
from app.models import User
from app.web.auth_routes import _client_key, _validate_csrf_form_field
from app.web.templates import templates

router = APIRouter()

# Every request counts (not just failures): the page answers the same whether
# or not the address has an account, so the limits can't depend on that either.
forgot_ip_limiter = FailureRateLimiter(max_failures=10, window_seconds=900)
# Keeps one person's inbox from being flooded by repeated requests for them.
forgot_email_limiter = FailureRateLimiter(max_failures=3, window_seconds=3600)


@router.get("/forgot-password")
def forgot_password_form(request: Request):
    return templates.TemplateResponse(request, "auth/forgot_password.html", {})


@router.post("/forgot-password")
def forgot_password_submit(
    request: Request,
    background_tasks: BackgroundTasks,
    email: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _validate_csrf_form_field(request, csrf_token)

    ip = _client_key(request)
    if forgot_ip_limiter.is_blocked(ip):
        return templates.TemplateResponse(
            request,
            "auth/forgot_password.html",
            {"error": "Too many requests. Please wait a few minutes and try again."},
            status_code=429,
        )
    forgot_ip_limiter.record_failure(ip)

    if settings.email_enabled:
        key = email.strip().lower()
        throttled = forgot_email_limiter.is_blocked(key)
        forgot_email_limiter.record_failure(key)
        if not throttled:
            user = db.scalars(select(User).where(func.lower(User.email) == key)).first()
            if user is not None:
                token = issue_token(db, user, RESET)
                db.commit()
                background_tasks.add_task(send_reset_email, user.email, user.name, token)

    # Same answer whatever happened, so this can't be used to find out who has an account.
    return templates.TemplateResponse(request, "auth/forgot_password.html", {"sent": True})


def _set_password_page(request: Request, token: str, db: Session, **extra):
    row = find_valid(db, token)
    if row is None:
        return templates.TemplateResponse(
            request, "auth/set_password.html", {"invalid": True}, status_code=400
        )
    return templates.TemplateResponse(
        request,
        "auth/set_password.html",
        {"token": token, "account_email": row.user.email, "welcome": row.purpose != RESET, **extra},
        status_code=400 if extra.get("error") else 200,
    )


@router.get("/set-password/{token}")
def set_password_form(request: Request, token: str, db: Session = Depends(get_db)):
    # Only looks at the link; it is used up when the form is submitted.
    return _set_password_page(request, token, db)


@router.post("/set-password")
def set_password_submit(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    confirm: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _validate_csrf_form_field(request, csrf_token)

    row = find_valid(db, token)
    if row is None:
        return _set_password_page(request, token, db)
    if len(password) < MIN_PASSWORD_LENGTH:
        return _set_password_page(
            request, token, db, error=f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        )
    if password != confirm:
        return _set_password_page(request, token, db, error="The two passwords don't match.")

    redeem(db, row, password)
    db.commit()
    return RedirectResponse(url="/login?notice=password-set", status_code=303)
