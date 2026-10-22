from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from markupsafe import escape

from app.config import settings
from app.core.email import render_email, send_email
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
        request, "settings/index.html", {"current_user": current_user, "cfg": settings}
    )


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
