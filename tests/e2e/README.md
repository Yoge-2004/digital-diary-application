# End-to-end tests (Playwright)

`tests/*.py` (the original suite) drives the app in-process through
FastAPI's `TestClient` — no real socket, no real browser, no CSS/JS.
Fast, and correct for what it checks: request/response contracts,
status codes, database state.

`tests/e2e/*.py` is a different layer entirely: it starts the real app
listening on a real port and drives it with a real, headless Chromium
through Playwright — the same rendering engine and JS runtime an actual
user gets. It's the only layer that can catch a horizontal scrollbar, a
CSS background misaligned from the text it's supposed to line up with,
a confirmation modal that doesn't actually block until you type
something, or a form `name=` attribute that doesn't match what the
backend route expects. All four of those are real bugs found and fixed
in this repo — see the git log — and none of them would be caught by
`TestClient` alone, because none of them are about the HTTP
request/response contract; they're about what actually renders and how
it actually behaves when clicked.

## Running it

```bash
pip install -e ".[e2e]"
playwright install chromium      # one-time, downloads the browser binary
pytest tests/e2e                 # runs the whole e2e suite
pytest tests/e2e/test_settings.py -k delete_account   # just one area
```

It is **not** run by a bare `pytest` (see `addopts` in `pyproject.toml`)
— it's slower (a real server + real browser per test, ~1-2 minutes for
the full suite vs ~20 seconds for the unit suite) and needs the browser
binary installed. CI (`.github/workflows/tests.yml`) runs both suites
as separate jobs on every push/PR.

Useful flags while debugging locally:

```bash
pytest tests/e2e --headed            # watch it click through the UI
pytest tests/e2e --headed --slowmo=300
pytest tests/e2e/test_diary_crud.py -x -v
```

## Structure

- `conftest.py` — the `live_server` / `live_server_factory` fixtures
  that boot a real app instance per test (own throwaway SQLite file,
  own port), plus small UI helpers (`register_via_ui`, `login_via_ui`,
  `assert_no_horizontal_overflow`).
- `test_landing_page.py` — landing page rendering + overflow sweep
  across 7 viewport widths (360px through 2560px).
- `test_auth_flows.py` — register/login/logout, OAuth button visibility
  (on/off), forgot-password + verify-email banner visibility (on/off,
  driven by whether SMTP is configured).
- `test_diary_crud.py` — create/view/edit/delete an entry, plus the two
  regression guards for the ruled-line and scrollbar bugs specifically.
- `test_diaries_list.py` — search (both via a hand-built URL and by
  actually typing into the search box and clicking "Apply filters"),
  mood filter, favourite/bookmark toggles, overflow sweep.
- `test_settings.py` — profile update, password change + re-login, and
  the delete-account type-to-confirm modal (open, exact-match gating,
  cancel, Escape, and the full destructive flow).
- `test_seo_rendered.py` — meta tags actually present in the rendered
  DOM (canonical, OG, Twitter Card, JSON-LD), `robots.txt` /
  `sitemap.xml` reachability, noindex on authenticated pages.

## What's not covered yet

This is a solid first pass through the app's main flows, not
exhaustive coverage. Not yet exercised: calendar view, statistics page,
shared/social features, tag management, image/file attachments, the
autosave indicator, dark/light theme toggle persistence, and mobile
viewport-specific interactions (the sidebar hamburger menu). Worth
adding as the app grows — the `live_server` / `live_server_factory`
fixtures in `conftest.py` are meant to be reused for any of that
without new plumbing.
