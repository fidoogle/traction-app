import uuid
from typing import Optional

import jwt
from fastapi import Cookie, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.security import ACCESS_TOKEN_COOKIE_NAME, decode_access_token
from app.models.user import User


class RedirectToLogin(Exception):
    """Raised by get_current_user_web when there's no valid session.

    Handled at the app level (see app.main) by sending the browser to
    /login - either a real redirect for normal navigation, or an
    HX-Redirect for requests htmx made mid-page.
    """


def get_current_user_web(
    cookie_token: Optional[str] = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> User:
    if cookie_token is None:
        raise RedirectToLogin()
    try:
        payload = decode_access_token(cookie_token)
        user_id = payload.get("sub")
        if user_id is None:
            raise RedirectToLogin()
        user = db.get(User, uuid.UUID(user_id))
    except jwt.InvalidTokenError:
        raise RedirectToLogin()
    if user is None:
        raise RedirectToLogin()
    return user
