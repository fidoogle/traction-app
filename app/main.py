import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.routes import api_router
from app.config import DEFAULT_SECRET_KEY, settings
from app.core.security_headers import SecurityHeadersMiddleware
from app.web.csrf import CSRFMiddleware
from app.web.deps import RedirectToLogin
from app.web.routes import web_router

logger = logging.getLogger("app")

if settings.secret_key == DEFAULT_SECRET_KEY:
    logger.warning("Using default SECRET_KEY - set SECRET_KEY in the environment before deploying.")

app = FastAPI(title="Traction/EOS App")

app.add_middleware(CSRFMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# JSON API lives under /api so the bare paths (/, /login, /rocks, ...) are
# free for the server-rendered web UI.
app.include_router(api_router, prefix="/api")
app.include_router(web_router)


@app.exception_handler(RedirectToLogin)
def redirect_to_login(request: Request, exc: RedirectToLogin):
    if request.headers.get("HX-Request") == "true":
        # htmx follows normal redirects itself, which would swap the login
        # page into whatever fragment was being targeted. HX-Redirect tells
        # it to do a full-page browser redirect instead.
        return Response(status_code=200, headers={"HX-Redirect": "/login"})
    return RedirectResponse(url="/login", status_code=303)


@app.get("/health")
def health():
    return {"status": "ok"}
