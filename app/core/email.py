"""Outgoing email over the district's own SMTP relay.

Nothing here is required: with SMTP unset (settings.email_enabled is False)
send_email does nothing and says so. Failures are returned, never raised, so a
mail problem can't break the request or job that asked for the email.
"""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from pathlib import Path
from typing import Iterable, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.config import settings

logger = logging.getLogger("app.email")

_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).resolve().parent.parent / "templates" / "email")),
    autoescape=select_autoescape(["html"]),
)


@dataclass
class Attachment:
    filename: str
    content: bytes
    maintype: str = "application"
    subtype: str = "octet-stream"
    # Extra Content-Type parameters, e.g. {"method": "REQUEST"} for calendar invites.
    params: Optional[dict] = None


@dataclass
class SendResult:
    ok: bool
    error: str = ""


def render_email(template: str, **context) -> tuple[str, str]:
    """(text body, html body) from templates/email/<template>.txt and .html.
    Every email gets base_url in its context for building links."""
    context.setdefault("base_url", settings.base_url.rstrip("/"))
    text = _env.get_template(f"{template}.txt").render(**context)
    html = _env.get_template(f"{template}.html").render(**context)
    return text, html


def send_email(
    to: str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
    attachments: Iterable[Attachment] = (),
) -> SendResult:
    if not settings.email_enabled:
        return SendResult(False, "Email is not configured.")

    msg = EmailMessage()
    try:
        msg["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_address))
        msg["To"] = to
        msg["Subject"] = subject
    except ValueError as exc:  # e.g. a newline smuggled into a header
        return SendResult(False, f"Invalid message: {exc}")
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=settings.smtp_from_address.rpartition("@")[2] or None)
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    for att in attachments:
        params = att.params or {}
        msg.add_attachment(
            att.content, maintype=att.maintype, subtype=att.subtype,
            filename=att.filename, params=params,
        )

    try:
        if settings.smtp_security == "ssl":
            smtp = smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port,
                timeout=settings.smtp_timeout_seconds, context=ssl.create_default_context(),
            )
        else:
            smtp = smtplib.SMTP(
                settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds
            )
        with smtp:
            if settings.smtp_security == "starttls":
                smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(msg)
    except (OSError, smtplib.SMTPException) as exc:
        logger.warning("Email send failed: %s", exc)
        return SendResult(False, f"{type(exc).__name__}: {exc}")
    return SendResult(True)
