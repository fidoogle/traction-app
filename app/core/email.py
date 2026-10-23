"""Outgoing email over the district's own SMTP relay.

Nothing here is required: with SMTP unset (settings.email_enabled is False)
send_email does nothing and says so. Failures are returned, never raised, so a
mail problem can't break the request or job that asked for the email.

A send that fails for a reason that may pass (the server is busy, the network
blinked) is tried again a couple of times with a growing pause. A server that
cannot be reached at all is then left alone for a minute, so a long list of
emails during an outage fails quickly instead of waiting out every timeout.
"""

import logging
import smtplib
import ssl
import time
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

# Indirections so tests can run without waiting.
_sleep = time.sleep
_clock = time.monotonic
# Until this moment (by _clock) the server is treated as down: no new attempts.
_unreachable_until = 0.0

PERMANENT, TRANSIENT, UNREACHABLE = "permanent", "transient", "unreachable"


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
    Every email gets base_url in its context for building links. The plain-text
    version ends with the same "choose which emails you get" note the HTML
    footer carries."""
    context.setdefault("base_url", settings.base_url.rstrip("/"))
    text = _env.get_template(f"{template}.txt").render(**context)
    html = _env.get_template(f"{template}.html").render(**context)
    if context.get("always_on"):
        text = text.rstrip("\n") + "\n\n--\nThis is an account email, so it can't be turned off.\n"
    if context.get("preferences_url"):
        text = text.rstrip("\n") + f"\n\n--\nChoose which emails you get: {context['preferences_url']}\n"
    return text, html


def classify_failure(exc: Exception) -> str:
    """Whether trying again could help: PERMANENT (no), TRANSIENT (maybe), or
    UNREACHABLE (maybe, and the server isn't answering at all)."""
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        codes = [code for code, _msg in exc.recipients.values()]
        return TRANSIENT if codes and all(400 <= c < 500 for c in codes) else PERMANENT
    if isinstance(exc, smtplib.SMTPConnectError):
        return UNREACHABLE
    if isinstance(exc, smtplib.SMTPResponseException):
        return TRANSIENT if 400 <= exc.smtp_code < 500 else PERMANENT
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return UNREACHABLE
    if isinstance(exc, smtplib.SMTPException):
        return PERMANENT
    return UNREACHABLE  # refused, timed out, name not found, TLS trouble


def _deliver(msg: EmailMessage) -> None:
    if settings.smtp_security == "ssl":
        smtp = smtplib.SMTP_SSL(
            settings.smtp_host, settings.smtp_port,
            timeout=settings.smtp_timeout_seconds, context=ssl.create_default_context(),
        )
    else:
        smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds)
    with smtp:
        if settings.smtp_security == "starttls":
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(msg)


def send_email(
    to: str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
    attachments: Iterable[Attachment] = (),
    headers: Optional[dict] = None,
) -> SendResult:
    global _unreachable_until
    if not settings.email_enabled:
        return SendResult(False, "Email is not configured.")

    msg = EmailMessage()
    try:
        msg["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_address))
        msg["To"] = to
        msg["Subject"] = subject
        for name, value in (headers or {}).items():
            msg[name] = value
    except ValueError as exc:  # e.g. a newline smuggled into a header
        return SendResult(False, f"Invalid message: {exc}")
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=settings.smtp_from_address.rpartition("@")[2] or None)
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
    for att in attachments:
        msg.add_attachment(
            att.content, maintype=att.maintype, subtype=att.subtype,
            filename=att.filename, params=att.params or {},
        )

    if _clock() < _unreachable_until:
        return SendResult(False, "The mail server could not be reached a moment ago; not trying again yet.")

    attempts = 1 + max(0, settings.smtp_retries)
    for attempt in range(1, attempts + 1):
        try:
            _deliver(msg)
        except (OSError, smtplib.SMTPException) as exc:
            kind = classify_failure(exc)
            logger.warning("Email send failed (attempt %d of %d, %s): %s", attempt, attempts, kind, exc)
            if kind != PERMANENT and attempt < attempts:
                _sleep(settings.smtp_retry_delay_seconds * 2 ** (attempt - 1))
                continue
            if kind == UNREACHABLE:
                _unreachable_until = _clock() + settings.smtp_down_cooldown_seconds
            tried = f" (tried {attempt} times)" if attempt > 1 else ""
            return SendResult(False, f"{type(exc).__name__}: {exc}{tried}")
        _unreachable_until = 0.0
        return SendResult(True)
    return SendResult(False, "Not sent.")  # unreachable: the loop always returns
