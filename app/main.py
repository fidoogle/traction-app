import logging

from fastapi import FastAPI

from app.api.routes import api_router
from app.config import DEFAULT_SECRET_KEY, settings

logger = logging.getLogger("app")

if settings.secret_key == DEFAULT_SECRET_KEY:
    logger.warning("Using default SECRET_KEY - set SECRET_KEY in the environment before deploying.")

app = FastAPI(title="Traction/EOS API")

app.include_router(api_router)


@app.get("/health")
def health():
    return {"status": "ok"}
