import uuid
from collections.abc import Generator
from typing import Optional

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import ACCESS_TOKEN_COOKIE_NAME, decode_access_token
from app.db import SessionLocal
from app.models.enums import UserRole
from app.models.user import User

# auto_error=False: a missing header isn't fatal here, since the session
# cookie is an equally valid way in (see get_bearer_or_cookie_token below).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_bearer_or_cookie_token(
    header_token: Optional[str] = Depends(oauth2_scheme),
    cookie_token: Optional[str] = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE_NAME),
) -> Optional[str]:
    # API clients send Authorization: Bearer <token>; the browser/htmx UI
    # relies on the HttpOnly session cookie set by POST /auth/login instead.
    return header_token or cookie_token


def get_current_user(
    token: Optional[str] = Depends(get_bearer_or_cookie_token),
    db: Session = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise credentials_error
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_error
    except jwt.InvalidTokenError:
        raise credentials_error

    user = db.get(User, uuid.UUID(user_id))
    if user is None:
        raise credentials_error
    return user


def require_roles(*roles: UserRole):
    allowed = set(roles)

    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions"
            )
        return current_user

    return dependency
