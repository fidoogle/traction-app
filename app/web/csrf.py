import hmac
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import settings

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
EXEMPT_PREFIXES = ("/api", "/static", "/health")
# login/logout are plain (non-htmx) forms - a native browser submit never
# carries a custom header, so these two validate a hidden `csrf_token`
# field in their own route handler instead (via FastAPI's normal Form()
# parsing). The middleware can't also read the body to check a form field
# here without breaking that downstream parse - Starlette's request body
# can only safely be consumed once.
FORM_FIELD_VALIDATED_PATHS = {"/login", "/logout"}


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_tokens_match(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and hmac.compare_digest(a, b)


class CSRFMiddleware(BaseHTTPMiddleware):
    """Double-submit-cookie CSRF protection for the server-rendered web UI.

    The JSON API (/api/*) is exempt: CSRF is specifically about a victim's
    browser being tricked into firing an unwanted *cookie-authenticated*
    request, and a bearer-header client can't be forged cross-site the
    same way. The web UI's cookie session is what's exposed, so that's
    what this guards.

    The CSRF cookie is deliberately NOT HttpOnly (unlike the session
    cookie) - the point of the pattern is that only same-origin JS can
    read it and echo it back as a header, which a cross-site attacker's
    forged form can't do (see the htmx:configRequest listener in
    base.html). This middleware only ever inspects headers/cookies, never
    the request body, so it can't interfere with downstream Form() parsing.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path.startswith(EXEMPT_PREFIXES):
            return await call_next(request)

        incoming_token = request.cookies.get(CSRF_COOKIE_NAME)
        request.state.csrf_token = incoming_token or generate_csrf_token()

        needs_header_check = (
            request.method not in SAFE_METHODS
            and request.url.path not in FORM_FIELD_VALIDATED_PATHS
        )
        if needs_header_check:
            submitted_token = request.headers.get(CSRF_HEADER_NAME)
            if not csrf_tokens_match(incoming_token, submitted_token):
                return JSONResponse({"detail": "CSRF token missing or invalid"}, status_code=403)

        response = await call_next(request)

        if incoming_token is None:
            response.set_cookie(
                key=CSRF_COOKIE_NAME,
                value=request.state.csrf_token,
                httponly=False,
                samesite="lax",
                secure=settings.cookie_secure,
                path="/",
            )
        return response
