from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import settings
from app.core.rate_limit import login_rate_limiter
from app.core.security import ACCESS_TOKEN_COOKIE_NAME, create_access_token, verify_password
from app.models.user import User
from app.web.csrf import CSRF_COOKIE_NAME, csrf_tokens_match
from app.web.templates import templates

router = APIRouter()


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _validate_csrf_form_field(request: Request, csrf_token: str) -> None:
    # login/logout are plain forms without the htmx header, so they're
    # validated here instead of by CSRFMiddleware - see app/web/csrf.py.
    if not csrf_tokens_match(request.cookies.get(CSRF_COOKIE_NAME), csrf_token):
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")


@router.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _validate_csrf_form_field(request, csrf_token)

    client_key = _client_key(request)
    if login_rate_limiter.is_blocked(client_key):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Too many failed login attempts. Please wait a few minutes and try again."},
            status_code=429,
        )

    user = db.scalar(select(User).where(User.email == email))
    if (
        user is None
        or user.hashed_password is None
        or not verify_password(password, user.hashed_password)
    ):
        login_rate_limiter.record_failure(client_key)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Incorrect email or password"},
            status_code=401,
        )

    login_rate_limiter.reset(client_key)
    token = create_access_token(subject=str(user.id))
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )
    return response


@router.post("/logout")
def logout(request: Request, csrf_token: str = Form(...)):
    _validate_csrf_form_field(request, csrf_token)
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(ACCESS_TOKEN_COOKIE_NAME, path="/")
    return response
