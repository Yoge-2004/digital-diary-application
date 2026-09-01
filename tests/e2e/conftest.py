"""Fixtures for the Playwright end-to-end suite.

Unlike tests/*.py (which drive the app in-process through FastAPI's
TestClient — no real sockets, no real browser), these tests need the app
listening on a real TCP port so a real Chromium instance can navigate to
it, click things, type things, and see what actually renders. That's the
whole point of this suite: it catches things TestClient-based tests
structurally cannot, like a horizontal scrollbar, a misaligned ruled
line, or a modal that doesn't actually block until you type DELETE.

`live_server` starts one full app per test function in a background
thread with defaults matching a normal deployment (SMTP unconfigured,
OAuth unconfigured), on an OS-assigned free port, against a throwaway
per-test SQLite file. `live_server_factory` is the same thing but lets a
test spin up additional servers with different Settings overrides (e.g.
SMTP configured, to check the forgot-password flow is *visible* when it
should be — actually sending mail is out of scope here and already
covered by tests/test_email_verification.py at the API level).
"""
from __future__ import annotations

import socket
import threading
import time
from dataclasses import replace

import pytest
import uvicorn

from app.core.config import Settings
from app.main import create_app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _ServerThread(threading.Thread):
    def __init__(self, app, port: int):
        super().__init__(daemon=True)
        self.port = port
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        self.server = uvicorn.Server(config)

    def run(self) -> None:
        self.server.run()

    def stop(self) -> None:
        self.server.should_exit = True


def _wait_until_up(port: int, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"Server on port {port} never came up")


_BASE_TEST_SETTINGS = dict(
    secret_key="e2e-test-secret-key-with-32-chars-min!!",
    cookie_secure=False,
    smtp_host="",
    google_client_id="",
    google_client_secret="",
)


@pytest.fixture
def live_server_factory(tmp_path):
    """Returns a callable that starts a live server and returns its base
    URL. Each call gets its own throwaway SQLite file and its own port,
    so tests that need contradictory settings (e.g. SMTP on vs off) can
    each start their own server instead of fighting over global state."""
    threads: list[_ServerThread] = []

    def _make(**overrides) -> str:
        db_path = tmp_path / f"e2e_{len(threads)}.db"
        settings = Settings(
            database_url=f"sqlite:///{db_path}",
            **{**_BASE_TEST_SETTINGS, **overrides},
        )
        app = create_app(settings)
        port = _free_port()
        thread = _ServerThread(app, port)
        thread.start()
        _wait_until_up(port)
        threads.append(thread)
        return f"http://127.0.0.1:{port}"

    yield _make

    for thread in threads:
        thread.stop()
    for thread in threads:
        thread.join(timeout=5)


@pytest.fixture
def live_server(live_server_factory) -> str:
    """The common case: one server, default settings (no SMTP, no
    OAuth — matching a fresh out-of-the-box deployment)."""
    return live_server_factory()


# ── Shared UI helpers ───────────────────────────────────────────────

def register_via_ui(page, base_url: str, username: str, email: str, password: str = "password123") -> None:
    page.goto(f"{base_url}/register")
    page.fill("#reg-username", username)
    page.fill("#reg-email", email)
    page.fill("#reg-password", password)
    page.fill("#reg-confirm", password)
    page.click("#registerForm button[type=submit]")
    page.wait_for_url(f"{base_url}/dashboard", timeout=10_000)


def register_via_api(page, base_url: str, username: str, email: str, password: str = "password123") -> dict:
    """Faster path for tests where registration itself isn't the thing
    under test — hits the JSON API directly via Playwright's own request
    context (same browser/cookie jar as `page`, so the session carries
    over to subsequent page.goto calls)."""
    resp = page.request.post(
        f"{base_url}/api/auth/register",
        data={"username": username, "email": email, "password": password},
        headers={"Content-Type": "application/json"},
    )
    assert resp.ok, resp.text()
    return resp.json()


def login_via_ui(page, base_url: str, username: str, password: str = "password123") -> None:
    page.goto(f"{base_url}/login")
    page.fill("#login-username", username)
    page.fill("#login-password", password)
    page.click("#loginForm button[type=submit]")
    page.wait_for_url(f"{base_url}/dashboard", timeout=10_000)


def assert_no_horizontal_overflow(page, context: str = "") -> None:
    """The regression guard for the exact bug class that kicked this
    whole suite off: something wider than the viewport forcing a
    page-wide horizontal scrollbar. scrollWidth > clientWidth is the
    real definition of 'this page has horizontal overflow', not an
    eyeballed screenshot."""
    overflow = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 1, (
        f"Horizontal overflow of {overflow}px detected{(' on ' + context) if context else ''} "
        f"(scrollWidth={page.evaluate('document.documentElement.scrollWidth')}, "
        f"clientWidth={page.evaluate('document.documentElement.clientWidth')})"
    )
