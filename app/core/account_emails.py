"""The emails about getting into an account. Called from background tasks so
a slow mail relay never holds up the page, and so a request for someone else's
address takes the same time whether or not it sends anything."""

from app.config import settings
from app.core.email import SendResult, render_email, send_email
from app.core.password_tokens import LIFETIME, RESET, WELCOME


def _hours(purpose: str) -> int:
    return int(LIFETIME[purpose].total_seconds() // 3600)


def send_welcome_email(to: str, name: str, token: str, invited_by: str) -> SendResult:
    link = settings.absolute_url(f"/set-password/{token}")
    text, html = render_email(
        "welcome", name=name, link=link, invited_by=invited_by, email=to, hours=_hours(WELCOME),
        always_on=True,
    )
    return send_email(to, "Your Traction account", text, html)


def send_reset_email(to: str, name: str, token: str) -> SendResult:
    link = settings.absolute_url(f"/set-password/{token}")
    text, html = render_email("password_reset", name=name, link=link, hours=_hours(RESET), always_on=True)
    return send_email(to, "Reset your Traction password", text, html)
