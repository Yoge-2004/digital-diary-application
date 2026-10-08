from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import BASE_DIR, Settings, settings
from app.core.scheduler import run_reminder_scheduler
from app.db.session import Base, create_engine_from_url, patch_missing_columns
from app import models  # noqa: F401
from app.routers.api import router as api_router
from app.routers.web import router as web_router
from app.routers.oauth import router as oauth_router

logger = logging.getLogger(__name__)

def _error_page(title: str, heading: str, message: str) -> str:
    """Self-contained error page. It has a viewport tag (without one phones lay a page out
    at 980px and shrink it, which is how the raw-JSON 404 looked), and it follows the saved
    theme / OS preference like the rest of the site."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="color-scheme" content="light dark">
  <meta name="robots" content="noindex">
  <title>{title} \u2014 Digital Diary</title>
  <script>
    (function () {{
      try {{
        var t = localStorage.getItem("dd-theme");
        if (t !== "dark" && t !== "light") t = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
        document.documentElement.setAttribute("data-theme", t);
      }} catch (e) {{}}
    }})();
  </script>
  <style>
    :root {{ --bg: #f9f9fb; --fg: #1c1b24; --muted: #5a586b; --accent: #c8153f; }}
    [data-theme="dark"] {{ --bg: #0f0d17; --fg: #f0eef7; --muted: #b3b0c6; --accent: #ff7a9c; }}
    html {{ background: var(--bg); }}
    body {{ margin: 0; min-height: 100vh; min-height: 100dvh; display: grid; place-items: center; padding: 1.5rem;
            box-sizing: border-box; background: var(--bg); color: var(--fg);
            font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; text-align: center; }}
    main {{ max-width: 32rem; }}
    h1 {{ font-family: Georgia, "Times New Roman", serif; font-size: clamp(1.75rem, 6vw, 2.5rem); margin: 0 0 .75rem; overflow-wrap: anywhere; }}
    p {{ color: var(--muted); line-height: 1.55; margin: 0 0 1.25rem; }}
    a {{ display: inline-block; min-height: 44px; box-sizing: border-box; padding: .7rem 1.4rem; border-radius: 8px;
         background: var(--accent); color: #fff; font-weight: 600; text-decoration: none; }}
    [data-theme="dark"] a {{ color: #1c0610; }}
    a:focus-visible {{ outline: 3px solid var(--fg); outline-offset: 3px; }}
  </style>
</head>
<body>
  <main>
    <h1>{heading}</h1>
    <p>{message}</p>
    <a href="/">Go back home</a>
  </main>
</body>
</html>"""


_GENERIC_ERROR_HTML = _error_page(
    "Something went wrong",
    "Something went wrong",
    "We hit an unexpected error. Please try again, and if it keeps happening, let us know.",
)
_NOT_FOUND_HTML = _error_page(
    "Page not found",
    "Page not found",
    "We couldn&rsquo;t find that page. It may have moved, or the link may be wrong.",
)


def create_app(app_settings: Settings | None = None) -> FastAPI:
    app_settings = app_settings or settings
    engine = create_engine_from_url(app_settings.database_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    Base.metadata.create_all(bind=engine)
    patch_missing_columns(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler_task = asyncio.create_task(run_reminder_scheduler(app_settings, session_factory))
        try:
            yield
        finally:
            scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler_task

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
    app.include_router(oauth_router, include_in_schema=False)
    app.include_router(api_router)

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        # Browsers that mistype a URL used to get the raw JSON {"detail":"Not Found"}.
        # Give page requests a real page; the JSON API and static files keep their default.
        path = request.url.path
        if exc.status_code == 404 and not path.startswith(("/api", "/static")):
            return HTMLResponse(status_code=404, content=_NOT_FOUND_HTML)
        return await http_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Full detail goes to the server log only — never to the browser.
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        if request.url.path.startswith("/api"):
            return JSONResponse(status_code=500, content={"detail": "Something went wrong. Please try again."})
        return HTMLResponse(status_code=500, content=_GENERIC_ERROR_HTML)

    return app


app = create_app()
