"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.api.routes import health, tasks
from app.core.config import get_settings
from app.db.session import init_db


def create_app() -> FastAPI:
    settings = get_settings()
    init_db()

    app = FastAPI(title=settings.app_name, debug=settings.debug)

    app.include_router(health.router)
    app.include_router(tasks.router, prefix="/api/v1")

    return app


app = create_app()
