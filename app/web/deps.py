import uuid
from typing import Optional

import jwt
from fastapi import Cookie, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.activity import set_actor
from app.core.security import ACCESS_TOKEN_COOKIE_NAME, decode_access_token
from app.core import meeting_session
from app.models.user import User
from app.web.team_context import TEAM_COOKIE_NAME, TeamContext, build_team_context


class RedirectToLogin(Exception):
    """Raised by get_current_user_web when there's no valid session.

    Handled at the app level (see app.main) by sending the browser to
    /login - either a real redirect for normal navigation, or an
    HX-Redirect for requests htmx made mid-page.
    """


def _meeting_session_view(db: Session, user: User, team_ctx) -> Optional[dict]:
    """The live meeting the sidebar should show: only admins of the team run
    one, and only on a single team (not under "All teams")."""
    if not team_ctx.can_admin_current:
        return None
    meeting = meeting_session.active_meeting(db, team_ctx.current.id)
    return meeting_session.view(meeting, meeting_session.now_utc()) if meeting else None


def get_current_user_web(
    request: Request,
    cookie_token: Optional[str] = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> User:
    """The signed-in user. Also works out their current team (see team_context)
    and leaves it on request.state.team_ctx, where base.html's switcher and
    get_team_context read it."""
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
    set_actor(db, user)
    request.state.team_ctx = build_team_context(db, user, request.cookies.get(TEAM_COOKIE_NAME))
    request.state.meeting_session = _meeting_session_view(db, user, request.state.team_ctx)
    return user


def get_optional_user_web(
    request: Request,
    cookie_token: Optional[str] = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Like get_current_user_web, but None instead of a redirect to /login.

    For background polls (e.g. the Activity badge), where an expired session
    shouldn't yank an idle tab over to the login page.
    """
    try:
        return get_current_user_web(request, cookie_token, db)
    except RedirectToLogin:
        return None


def get_team_context(
    request: Request, current_user: User = Depends(get_current_user_web)
) -> TeamContext:
    """The signed-in user's current team and the teams they can switch to."""
    return request.state.team_ctx
