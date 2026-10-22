"""One-time links for setting a password: issue, look up, redeem.

The raw token only ever exists in the emailed link; the database keeps its
SHA-256 (the token is 256 bits of randomness, so a fast hash is enough).
Looking a token up does not use it up - mail scanners often open links - only
redeeming it with a new password does.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import PasswordToken, User

WELCOME = "welcome"
RESET = "reset"
LIFETIME = {WELCOME: timedelta(hours=48), RESET: timedelta(hours=1)}
MIN_PASSWORD_LENGTH = 8


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def issue_token(db: Session, user: User, purpose: str) -> str:
    """A fresh link for the user; any earlier unused link stops working.
    Flushes but does not commit - the caller commits."""
    db.execute(
        delete(PasswordToken).where(PasswordToken.user_id == user.id, PasswordToken.used_at.is_(None))
    )
    raw = secrets.token_urlsafe(32)
    db.add(
        PasswordToken(
            user_id=user.id,
            token_hash=_hash(raw),
            purpose=purpose,
            expires_at=_now() + LIFETIME[purpose],
        )
    )
    db.flush()
    return raw


def find_valid(db: Session, raw: str) -> Optional[PasswordToken]:
    """The token row if the link is real, unused and unexpired, else None."""
    if not raw:
        return None
    token = db.scalar(select(PasswordToken).where(PasswordToken.token_hash == _hash(raw)))
    if token is None or token.used_at is not None or token.expires_at <= _now():
        return None
    return token


def redeem(db: Session, token: PasswordToken, new_password: str) -> None:
    """Sets the password and uses the link (and any other open links) up.
    Does not commit."""
    token.user.hashed_password = hash_password(new_password)
    token.used_at = _now()
    db.execute(
        delete(PasswordToken).where(
            PasswordToken.user_id == token.user_id,
            PasswordToken.used_at.is_(None),
            PasswordToken.id != token.id,
        )
    )
