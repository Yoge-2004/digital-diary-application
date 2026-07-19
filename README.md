# Digital Diary

A personal, private-by-default digital diary. FastAPI backend, server-rendered
HTML frontend (Jinja2 + a bit of vanilla JS — no React/build step), SQLAlchemy
+ SQLite/Postgres for storage.

## Features

- Email/username + password auth (JWT access + refresh tokens in httponly cookies)
- Diary entries with title, rich content, mood, tags, and an optional location
- Favourite, pin, archive, and bookmark each entry independently
- Visibility per entry: `private` (default) or `public`
- Sharing: grant a specific user access, or generate a public link — either
  can carry an expiry
- File attachments per entry (images render inline; other files as a download)
- Dashboard stats: totals, current/longest writing streak, mood distribution
- A JSON REST API under `/api/*` (see [API docs](#api-documentation)) alongside
  the browser-facing pages

## Quick start

```bash
git clone <this repo>
cd digital-diary-application
pip install -r requirements.txt   # or: uv sync
uvicorn app.main:app --reload
```

Visit `http://127.0.0.1:8000`. With no configuration at all, it runs against
a local SQLite file (`digital_diary.db`, created automatically) — good enough
to try it out, but set `DATABASE_URL` to Postgres (e.g. [Neon](https://neon.tech))
for anything beyond local experimentation.

### Environment variables

| Variable | Default | Notes |
|---|---|---|
| `APP_NAME` | `Digital Diary` | Shown in the UI and API docs title |
| `SECRET_KEY` | *(insecure placeholder)* | **Set this** in any deployed environment — signs the JWTs |
| `DATABASE_URL` | local SQLite file | Any SQLAlchemy-compatible URL, e.g. a Neon Postgres connection string |
| `ACCESS_TOKEN_MINUTES` | `1440` (24h) | Access token lifetime |
| `REFRESH_TOKEN_DAYS` | `30` | Refresh token lifetime |
| `COOKIE_SECURE` | `false` | Set `true` once served over HTTPS |
| `COOKIE_SAMESITE` | `lax` | Cookie `SameSite` policy |

Uploaded attachments are written to `./uploads` by default. That directory is
**not** persistent on most scale-to-zero hosts (e.g. Hugging Face Spaces,
Koyeb free tier) — point it at mounted/persistent storage, or an external
object store, before relying on attachments in production.

## Project structure

```
app/
├── main.py            # create_app(), app factory + lifespan
├── deps.py             # get_current_user, CSRF helpers
├── models.py           # SQLAlchemy models (User, Diary, Tag, Attachment, DiaryShare)
├── schemas.py          # Pydantic request/response models for the API
├── services.py         # business logic + authorization rules (see below)
├── repositories.py      # plain data-access queries, no auth logic
├── core/
│   ├── config.py       # Settings (env-var driven)
│   └── security.py     # password hashing, JWT encode/decode
├── db/session.py        # engine/session factory, per-app via app.state
├── routers/
│   ├── web.py           # server-rendered HTML pages + form endpoints
│   └── api.py            # JSON REST API (mounted at /api, documented in Swagger)
├── templates/            # Jinja2 templates
└── static/                # CSS/JS (see the "luxury physical-diary" motion layer
                            #  appended to static/css/app.css + static/js/motion.js)
```

**Authorization pattern to know about:** `services.get_diary()` checks *view*
access (owner, public visibility, or an active share) — it's used for
read-only routes. `services.get_owned_diary()` additionally requires the
caller to be the owner, and is used for every route that mutates an entry
(edit, delete, duplicate, restore, favourite/pin/archive/bookmark, attachment
upload). If you add a new mutating route, use `get_owned_diary`, not
`get_diary`.

## API documentation

Interactive Swagger UI is at `/docs` (ReDoc at `/redoc`) once the app is
running — it only lists the JSON `/api/*` surface, not the HTML pages, so
it stays focused on what's actually meant to be called programmatically.

## Running tests

```bash
pip install pytest
pytest tests/ -v
```

Tests spin up a fresh app instance against a temporary SQLite database per
test (see `tests/test_app.py::build_client`), so they don't touch your real
database or uploads folder.

- `tests/test_app.py` — basic end-to-end auth + diary flow (web and API)
- `tests/test_security_and_features.py` — CSRF correctness, ownership/
  authorization checks, visibility, sharing (including expiry and public
  links), bookmark/favourite toggling, attachment access control, and
  location tagging

## Deployment notes

This has been built with free-tier-friendly deployment in mind:
- **Database:** [Neon](https://neon.tech) (serverless Postgres) via `DATABASE_URL`
- **Hosting:** any Docker-friendly host that runs the app on `$PORT`/a fixed
  port (e.g. Koyeb, Render, Hugging Face Spaces) — remember `COOKIE_SECURE=true`
  once you're on HTTPS, and a real `SECRET_KEY`
- **Attachments:** see the storage note above — mount persistent storage or
  swap `attach_file`'s destination for an object store before depending on
  uploads surviving a redeploy
