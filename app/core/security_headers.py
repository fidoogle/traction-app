from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """A few low-risk, always-safe response headers.

    Deliberately not setting a Content-Security-Policy here: the templates
    rely on inline htmx `hx-on::` attributes and an inline script (see
    app/web/csrf.py), so a CSP tight enough to matter would need those
    moved out to external JS first - left as a follow-up rather than
    shipping a CSP that either does nothing or breaks the UI.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
