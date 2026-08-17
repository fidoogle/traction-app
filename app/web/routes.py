from fastapi import APIRouter

from app.web.auth_routes import router as auth_routes
from app.web.dashboard_routes import router as dashboard_routes
from app.web.rocks_routes import router as rocks_routes

web_router = APIRouter()
web_router.include_router(auth_routes)
web_router.include_router(dashboard_routes)
web_router.include_router(rocks_routes)
