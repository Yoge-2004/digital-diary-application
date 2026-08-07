from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import sessionmaker

from app.core.config import BASE_DIR, Settings, settings
from app.db.session import Base, create_engine_from_url, patch_missing_columns
from app import models  # noqa: F401
from app.routers.api import router as api_router
from app.routers.web import router as web_router

logger = logging.getLogger(__name__)

_GENERIC_ERROR_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Something went wrong</title></head>
<body style="font-family: sans-serif; text-align: center; padding: 4rem 1rem;">
  <h1>Something went wrong</h1>
  <p>We hit an unexpected error. Please try again, and if it keeps happening, let us know.</p>
  <p><a href="/">Go back home</a></p>
</body>
</html>"""


def create_app(app_settings: Settings | None = None) -> FastAPI:
    app_settings = app_settings or settings
    engine = create_engine_from_url(app_settings.database_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    Base.metadata.create_all(bind=engine)
    patch_missing_columns(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(
        title=app_settings.app_name,
        description=(
            "REST API + server-rendered web app for a personal digital diary: "
            "entries with mood/tags/location, favourites/pins/archive/bookmarks, "
            "sharing (by user or public link), and file attachments.\n\n"
            "Browser-facing pages live outside `/api` and use cookie sessions "
            "with CSRF-protected forms; everything under `/api` is a stateless "
            "JSON API secured with JWT access/refresh token cookies."
        ),
        version="1.0.0",
        openapi_tags=[
            {"name": "Authentication", "description": "Register, log in/out, refresh tokens."},
            {"name": "Users", "description": "The signed-in user's own profile."},
            {"name": "Diaries", "description": "Create, read, update, delete, and organize diary entries."},
            {"name": "Sharing", "description": "Share an entry with a specific user or via a public link."},
            {"name": "Tags", "description": "Tags used to organize diary entries."},
            {"name": "Attachments", "description": "Files attached to a diary entry."},
            {"name": "Statistics", "description": "Aggregate counts and streaks for the dashboard."},
        ],
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.engine = engine
    app.state.db_sessionmaker = session_factory
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
    app.include_router(web_router, include_in_schema=False)
    app.include_router(api_router)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Full detail goes to the server log only — never to the browser.
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        if request.url.path.startswith("/api"):
            return JSONResponse(status_code=500, content={"detail": "Something went wrong. Please try again."})
        return HTMLResponse(status_code=500, content=_GENERIC_ERROR_HTML)

    return app


app = create_app()
