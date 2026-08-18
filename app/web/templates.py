import os
from pathlib import Path

from fastapi.templating import Jinja2Templates

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def static_version(filename: str) -> str:
    # Cache-busting query param for static assets. Browsers otherwise cache
    # /static/style.css and /static/htmx.min.js aggressively (no build step
    # generates hashed filenames here), so a deploy that changes CSS/JS
    # without changing the URL can silently keep serving stale assets to
    # already-visited browsers. Using mtime means the value only changes
    # when the file actually does, so normal caching still applies between
    # deploys.
    try:
        return str(int(os.path.getmtime(STATIC_DIR / filename)))
    except OSError:
        return "0"


templates.env.globals["static_version"] = static_version
