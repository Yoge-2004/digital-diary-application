# Handoff: Digital Diary (FastAPI + Jinja2)

Written so that **any AI (or person) given only this file and repo access can pick the project up,
push changes and fix issues efficiently**. Read section 0 first, sections 3, 8 and 9 save the most time.
Sections 5 to 7 are reference (the file tree, routes, init functions and test counts are generated from
the repo, so they are exact as of the commit named below).

- **Repo:** https://github.com/Yoge-2004/digital-diary-application (owner: Yoge-2004, the person you are talking to)
- **State described here:** `main` at the merge of PR #10 plus this handoff PR (see `git log`). No other branches, no other open PRs.
- **Stack:** Python 3.12, FastAPI, Jinja2 server-rendered pages, SQLAlchemy 2 (SQLite by default, Postgres in production),
  one vanilla-JS file, one CSS file. No frontend build step, no bundler, no framework.
- **CI:** GitHub Actions `.github/workflows/tests.yml`: a unit job (`pytest tests --ignore=tests/e2e`) and an e2e job
  (Playwright + Chromium, `pytest tests/e2e`). Both must be green before merging.

---

## 0. How to use this file (rules for the next AI)

1. **Work on a branch, open a PR, one commit per concern, explain the root cause and the evidence in the commit message.**
   Never commit to `main`. Commit identity: `Claude (AI assistant) <noreply@anthropic.com>` (set locally, not the owner's).
2. **Do not run the test suites unless the owner tells you to.** They said tests take too long. Targeted checks are fine:
   render the page in a real browser and measure (section 8), or run one small test file when a CI failure needs reproducing.
   Say plainly what you did and did not run.
3. **Verify visual and layout claims by rendering and measuring in a real browser**, not by reading CSS. Nearly every real bug
   found in this project was found that way. Look at the screenshot before believing a checker's finding (section 8 lists known false positives).
4. **Be honest about gaps.** Chromium is the only browser ever tested. Firefox, Safari, real phones, real fingerprint hardware and
   real screen readers have never been tried. Say so.
5. **Never write a secret into a file, a commit, `.git/config` or a PR description.** The owner has pasted a GitHub personal access token
   into chats many times; it must be rotated (github.com/settings/tokens). Ask for a fresh one when you need to push and use it only
   inline (section 3).
6. After a PR's CI is green the owner has said "merge everything", and usually merges themselves. Merge commits (not squash) so the
   one-commit-per-concern history survives; delete merged branches (the owner asked why merged branches are kept).
7. Prefer the owner's wording and priorities; they give terse follow-ups ("Continue"). When you are unsure which of two designs they
   mean, pick the safer one, say which you picked, and ask one short question at the end.

---

## 1. What the app is

A private diary. Server-rendered pages (Jinja2) plus a JSON API under `/api/*`. Features: entries with mood, tags, location,
favourite/pin/archive/bookmark flags, attachments (images inline), share links with optional expiry and username shares, search and
filters, calendar, stats (streaks, mood distribution), markdown/JSON export, daily reminders (email and web push), Google OAuth sign-in,
email verification and password reset by emailed code, **security PIN + fingerprint/face passkeys + PIN/passkey account recovery**
(sections 4.4), light/dark theme, a "book view" for reading entries page by page, a floating "island" quick-nav, installable PWA bits
(service worker for push).

Auth is JWT in HttpOnly cookies (`access_token`, `refresh_token`) plus a double-submit CSRF cookie (`csrf_token`) for web forms. The JSON
API accepts the same tokens without CSRF.

---

## 2. The owner's working agreements (stated by the owner)

- Fix, then explain root causes. They report visual bugs with screenshots after their own pushes and say "Continue".
- PRs: branch -> PR -> CI -> merge commit -> delete the branch. They merged some PRs themselves, once leaving conflict markers in
  `app.css` for one commit (fixed by them straight away). Always `git fetch` and look at `origin/main` before starting; they push to `main`.
- **Run tests only when they say so.** (They said it takes too long.)
- They asked for: app-styled dropdowns (not browser defaults), no text hidden by the bookmark ribbon, a book view that works, a visible
  page-turn animation, paper texture, no phantom empty lines in the editor, 12-15 lines per book page on phones, spacing on the home page,
  an "island" menu, a theme that doesn't flash between page loads, and security PIN / biometric features.
- Test data they use includes very long unbroken strings ("IIII...", random letters), which is why unbroken-word handling matters.

---

## 3. Pushing to GitHub (copy-paste)

The token is **not stored anywhere**. The owner provides it in chat. Put it in a shell variable for the command only.

```bash
cd <repo>
git config user.name  "Claude (AI assistant)"
git config user.email "noreply@anthropic.com"
T='<token from the owner>'                                   # never write this into a file
H="Authorization: Basic $(printf 'x-access-token:%s' "$T" | base64 -w0)"
git -c http.extraHeader="$H" fetch origin
git checkout -b fix/short-name origin/main
# ... edit, commit (one concern per commit) ...
git -c http.extraHeader="$H" push origin fix/short-name 2>&1 | sed "s/$T/***/g"
```
`http.extraHeader` is per-command, so nothing lands in `.git/config` (verify with `git config --list | grep -i extraheader` -> prints nothing).

Open / inspect / merge a PR and clean up (REST API, `R=Yoge-2004/digital-diary-application`, `A="Authorization: Bearer $T"`):

```bash
# open (put the description in a file, build the JSON with python so quoting is safe)
curl -s -X POST -H "$A" https://api.github.com/repos/$R/pulls -d @pr.json     # {"title","head","base":"main","body"}
# CI status of a PR head
SHA=$(curl -s -H "$A" https://api.github.com/repos/$R/pulls/N | python3 -c "import sys,json;print(json.load(sys.stdin)['head']['sha'])")
curl -s -H "$A" https://api.github.com/repos/$R/commits/$SHA/check-runs      # names: "Unit / API tests ...", "End-to-end tests (Playwright)"
# merge with a merge commit, then delete the branch
curl -s -X PUT -H "$A" https://api.github.com/repos/$R/pulls/N/merge -d '{"merge_method":"merge","commit_title":"Merge pull request #N: ..."}'
curl -s -X DELETE -H "$A" https://api.github.com/repos/$R/git/refs/heads/<branch>
```
Facts: PR `mergeable_state` is `unknown` for a few seconds after a push (poll); the e2e job takes ~9-11 minutes; the **job logs cannot be
downloaded from the sandbox** (GitHub redirects to a blob host that is not allow-listed), so when e2e fails, find which tests failed by
running only the e2e files that touch what you changed. If two PRs both append to the end of `app.css` they conflict; merge `main` into the
later one and keep both blocks.

---

## 4. Architecture

### 4.1 Backend (all under `app/`)
- `main.py`: `create_app(settings)` builds the app, mounts `/static`, registers routers (`web`, `oauth`, `security`, `api`), exception handlers
  (HTML 404 for page URLs; `/api` and `/static` keep default responses; generic HTML 500), creates tables and runs `patch_missing_columns`
  (additive ALTERs for new nullable/defaulted columns: **there is no Alembic usage even though `alembic` is listed in `pyproject.toml`**), starts the scheduler.
- `core/config.py`: `Settings` dataclass read from environment variables (table in 4.6). `email_service_enabled` auto-detects SMTP unless `EMAIL_SERVICE_ENABLED` is set.
- `core/security.py`: bcrypt password hashing (`bcrypt<5`), JWT create/decode (`decode_token` returns None for expired/tampered tokens).
  It signs with the module-level global `settings`, not `app.state.settings` (a latent inconsistency for tests that pass custom secrets).
- `core/email.py`, `core/push.py` (pywebpush, VAPID), `core/scheduler.py` (one in-process 60-second loop comparing HH:MM; can skip a minute on drift; documented trade-off).
- `deps.py`: `get_optional_user`, `ensure_csrf_cookie`, `verify_csrf(request, submitted_token)` (cookie vs form field or `X-CSRF-Token` header). `db/session.py`: `get_db`.
- `models.py`: `User`, `Diary`, `Tag`, `Attachment`, `DiaryShare`, `PushSubscription`, `WebAuthnCredential`.
  `User` carries `pin_hash`, `pin_failed_attempts`, `pin_locked_until`, `sec_version`, `reset_attempts`, reminder fields, OAuth fields, `reset_token(+_expires)`.
- `repositories.py` (queries), `services.py` (business rules: register/authenticate/issue tokens/password change/reset code/delete account/export/diaries),
  `schemas.py` (pydantic). SEO (robots.txt, sitemap.xml, JSON-LD) lives in `routers/web.py` and the templates; there is no separate SEO module.
- `security_factors.py` (new): the PIN, passkey, trusted-device and recovery logic (4.4). `routers/security.py`: its routes.
- `routers/web.py`: HTML pages and form posts. `routers/api.py`: JSON API (`/api/*`, documented at `/docs`). `routers/oauth.py`: Google OAuth.
  Gotcha: the JSON API's flag routes are `PATCH /api/diaries/{id}/favorite|pin|archive|bookmark` (not `PATCH /api/diaries/{id}`; updating content is `PUT`).
  `POST /api/diaries` ignores `is_bookmarked`/`is_pinned` (verified: the created entry has them false).

### 4.2 Frontend
- Templates in `app/templates/` (server-rendered). `base.html` is the shell for signed-in and public pages (sidebar, topbar, `.app-main`,
  the island, scripts). `auth.html`, `forgot_password.html`, `reset_password.html`, `login_verify.html`, `verify_email.html` are standalone
  pages with their own `<head>` (each has the before-paint theme script). `partials/` holds fragments.
- `app/static/js/app.js` (~2.9k lines): one IIFE, everything starts in one `DOMContentLoaded`. Helpers `$`, `$$`. Init functions:
  initTheme, initRipple, initCustomSelects, initIsland, initSidebar, initFlash, initPasswordToggle, initPasswordStrength, initRegisterForm, initLoginForm, initForgotPasswordForm, initResetPasswordForm, initMoodSelector, initTagInput, initWordCount, initTitleCounter, initAutosave, initDiaryFormValidation, initSettingsValidation, initSettingsTabs, initConfirmForms, initNotificationSettings, initDeleteAccountModal, initActiveNav, initCountUp, initCopyShareLink, initAjaxToggles, initAutoResize, initRuledLineAlignment, initAjaxUpload, initDownloadProgress, initMoodPills, initDiaryBookPaging. Also: `motion.js` (entrance animation, honours reduced motion), `security.js` (PIN/passkey pages), `sw.js` (service worker for push).
- `app/static/css/app.css` (~4.5k lines, one file). Tokens are CSS custom properties in `:root` with a `[data-theme="dark"]` block ("Confession Ink"
  palette). Text-safe tokens exist because the fill colours fail WCAG as text: `--txt-muted`, `--accent-text`, `--danger-text`, `--success-text`,
  `--warn-text`, `--lime-text`. Layout: `--sidebar-w` (270px), `--page-pad`, `--topbar-h`.
- **Theme:** `<html data-theme="light|dark">`, saved in `localStorage['dd-theme']`. A tiny inline script in every `<head>` applies it (saved value, else the OS
  preference) *before first paint*; `app.js initTheme` also does it and keeps the toggle labels and `<meta name="theme-color">` in sync.
  Without the head script the page painted light first and flashed on navigations (the site uses cross-document view transitions).
- **Sidebar drawer** (<1024px): off-canvas via `transform`, `visibility:hidden` when closed (so its links aren't tab stops), `.app-main` is `inert` while open,
  focus moves in on open and returns to the toggle, Escape closes. The close "X" is hidden on desktop by a real rule (Bootstrap's `d-lg-none` is not defined here).
- **Island** (`#island`, in `base.html` inside `.app-main`): Dynamic-Island style pill at bottom-centre of the **screen**. Collapsed shows the current section;
  tap expands to a grid of destinations (4 columns, 8 from 640px, 4 again at 1024-1199px so it can't slide under the sidebar). Disclosure pattern, closes on Escape /
  outside click / focus leaving. Adaptive: compacts to a 40px circle while scrolling down, hides while typing on phones, shows a scroll-progress hairline and a live word count
  on the write page, hidden in book view (it covered the page counter).
- **App-styled dropdowns** (`initCustomSelects`): every `select.form-select` gets a button + `role=listbox` (select-only combobox). The native `<select>` stays in the DOM,
  hidden, and receives `input`/`change`. The list is `position:fixed` appended to `body`. Playwright's `select_option` still works on the native element.
- **Book view** (entry page): `initDiaryBookPaging` in `app.js`. `pageCapacity()` fills the page with ~17,000px of dummy text and reads the real viewport height; `paginate()`
  packs word tokens into a hidden clone with galloping + binary search; a word is split only when it alone is taller than a page; the end-of-entry flourish is reserved on the last page.
  On screens <768px `fitPhoneViewport()` sizes the reading area to 12-15 lines (8 in landscape) and CSS lifts the card's `max-height`. Re-paginates on resize and after `document.fonts.ready`.
  **Page turn:** the page you are leaving is the leaf (`.page-turn-sheet`, 0.8s), the target page is rendered underneath first, Next hinges on the left, Previous on the right,
  a new turn finishes the running one. `prefers-reduced-motion` swaps instantly with no leaf.
- **Editor / ruled lines:** the textarea draws baseline-aligned lines (`initRuledLineAlignment` computes `--rule-offset` from padding + baseline); the paper draws only the margin line
  (3.25rem on desktop, 0.75rem on phones). **Paper grain**: one `::after` overlay on every `.journal-page` (SVG noise, `mix-blend-mode`, deliberately subtle).
- **Bookmark ribbon** (`#diaryRibbonBookmark`, `role=button`, `aria-pressed`): sits left of the header text with a clear gap; the real toggle button also exists.
- **Calendar:** days with entries are `div[role=gridcell] > a` (the link keeps its role); `.cal-cell{display:contents}`.
- **Accessibility conventions:** skip link, visible focus on every control, `aria-current`, live regions for toasts and the page counter, tap targets 44px min-height on `.btn`.

### 4.3 Data and uploads
SQLite file `digital_diary.db` in the repo root by default (git-ignored), uploads in `uploads/` (git-ignored). `DATABASE_URL` for Postgres. New columns on existing tables are added
automatically at startup by `patch_missing_columns`; new tables by `create_all`. Anything else (renames, data fixes) needs a manual step: **there is no migration framework in use**.

### 4.4 Security PIN, passkeys, recovery (`security_factors.py`, `routers/security.py`, `static/js/security.js`)
Opt-in per account. No PIN = sign in exactly as before.
- **PIN:** 6-8 digits, bcrypt-hashed, set/changed/removed in Settings > Security (needs the current password; OAuth-only accounts skip that). 5 wrong in a row lock it for 15 minutes and
  while locked even the right PIN is refused. Removing the PIN deletes the passkeys. A PIN is required before a passkey can be added (it's the fallback for devices without the passkey).
- **Sign-in:** after the password, an account with a PIN gets `/login/verify`. No access/refresh token exists until that passes; the half-signed-in state is the `mfa_token` cookie (JWT, 5 min, path `/login`).
  A device that registered a passkey is asked for fingerprint/face straight away (flag in `localStorage['dd-has-passkey']`); other devices with a sensor see a button; devices with no sensor/WebAuthn see only the PIN form
  (the passkey controls start `hidden`, and a global `[hidden]{display:none!important}` makes that true). JSON API: `POST /api/auth/login` answers 401 `{code:"second_factor_required", mfa_token}`, then `POST /api/auth/login/pin`.
- **"Remember this device":** `trusted_device` cookie (JWT, 30 days) skips the second step. Everything is invalidated by `users.sec_version` (bumped on PIN/passkey/password change, password reset).
- **Passkeys:** WebAuthn platform authenticators via the `webauthn` library, user verification required. Challenge in the `wa_challenge` cookie (JWT, 5 min). RP id / origin default to the request host / `Origin` header;
  set `WEBAUTHN_RP_ID` and `WEBAUTHN_ORIGIN` when a proxy rewrites host or scheme. HTTPS (or `localhost`) is a browser requirement. Passkeys are tied to the domain.
- **Recovery:** `/forgot-password` always exists. Without SMTP it shows only "Recover with your security PIN" (username + PIN + new password, or fingerprint/face). With SMTP it also has the emailed 6-digit code.
  Unknown user / no PIN / wrong PIN give one generic message and the same bcrypt cost. A passkey recovery yields a 10-minute `recover` grant used once to set the new password.
- **Emailed code hardening:** 5 wrong tries burn it; constant-time compare.
- **Known weaknesses (decisions for the owner):** a 6-8 digit PIN can be brute-forced offline if the database leaks; anyone can lock another user's PIN with 5 wrong guesses (email/passkey recovery still works);
  Google OAuth sign-in skips the PIN step; no IP rate limiting anywhere.

### 4.5 Email, push, OAuth
SMTP optional (`email_service_enabled`); verification email on register, reset code, reminders. Web push needs VAPID keys (the Settings "Notifications" tab only renders when configured).
Google OAuth needs `GOOGLE_CLIENT_ID/SECRET` (see `GOOGLE_OAUTH_SETUP.md`); the login/register pages show "Continue with Google" only when configured.

### 4.6 Environment variables (all of them; `app/core/config.py` is the source of truth)
| Variable | Default | Notes |
|---|---|---|
| `APP_NAME` | `Digital Diary` | UI and API docs title |
| `SECRET_KEY` | insecure placeholder | **set in production**; signs every JWT (access, refresh, mfa, trusted, challenge, recovery) |
| `DATABASE_URL` | `sqlite:///<repo>/digital_diary.db` | any SQLAlchemy URL (Postgres/Neon in production) |
| `ACCESS_TOKEN_MINUTES` | `1440` | |
| `REFRESH_TOKEN_DAYS` | `30` | |
| `COOKIE_SECURE` | `false` | `true` once on HTTPS |
| `COOKIE_SAMESITE` | `lax` | |
| `SMTP_HOST` `SMTP_PORT`(587) `SMTP_USER` `SMTP_PASSWORD` `SMTP_FROM` `SMTP_USE_TLS`(true) | empty | email is enabled when `SMTP_HOST` is set |
| `EMAIL_SERVICE_ENABLED` | auto | force on/off |
| `APP_BASE_URL` | `http://127.0.0.1:8000` | used in emailed links |
| `GOOGLE_CLIENT_ID` `GOOGLE_CLIENT_SECRET` | empty | enables Google sign-in |
| `VAPID_PUBLIC_KEY` `VAPID_PRIVATE_KEY` `VAPID_CLAIMS_SUB` | empty | enables web push |
| `WEBAUTHN_RP_ID` `WEBAUTHN_ORIGIN` `WEBAUTHN_RP_NAME` | derived / `Digital Diary` | passkeys; see 4.4 |
The app does **not** read a `.env` file; set real environment variables.

---

## 5. File map (generated)
```
.github/workflows/tests.yml  (37 lines)
.gitignore  (34 lines)
GOOGLE_OAUTH_SETUP.md  (62 lines)
README.md  (121 lines)
app/__init__.py  (2 lines)
app/core/__init__.py  (0 lines)
app/core/config.py  (120 lines)
app/core/email.py  (231 lines)
app/core/push.py  (64 lines)
app/core/scheduler.py  (79 lines)
app/core/security.py  (64 lines)
app/db/__init__.py  (0 lines)
app/db/session.py  (84 lines)
app/deps.py  (76 lines)
app/main.py  (154 lines)
app/models.py  (212 lines)
app/repositories.py  (445 lines)
app/routers/__init__.py  (0 lines)
app/routers/api.py  (531 lines)
app/routers/oauth.py  (123 lines)
app/routers/security.py  (270 lines)
app/routers/web.py  (1267 lines)
app/schemas.py  (139 lines)
app/security_factors.py  (387 lines)
app/services.py  (588 lines)
app/static/android-chrome-192x192.png  (70 lines)
app/static/android-chrome-512x512.png  (449 lines)
app/static/apple-touch-icon.png  (78 lines)
app/static/css/app.css  (4483 lines)
app/static/favicon-16x16.png  (4 lines)
app/static/favicon-32x32.png  (8 lines)
app/static/favicon.svg  (19 lines)
app/static/js/app.js  (2638 lines)
app/static/js/motion.js  (98 lines)
app/static/js/security.js  (203 lines)
app/static/og-image.png  (1728 lines)
app/static/site.webmanifest  (16 lines)
app/static/sw.js  (45 lines)
app/templates/auth.html  (333 lines)
app/templates/base.html  (279 lines)
app/templates/calendar.html  (128 lines)
app/templates/dashboard.html  (217 lines)
app/templates/diaries.html  (171 lines)
app/templates/diary_detail.html  (494 lines)
app/templates/diary_form.html  (271 lines)
app/templates/forgot_password.html  (185 lines)
app/templates/landing.html  (159 lines)
app/templates/login_verify.html  (118 lines)
app/templates/partials/diary_card.html  (78 lines)
app/templates/reset_password.html  (157 lines)
app/templates/search.html  (109 lines)
app/templates/settings.html  (351 lines)
app/templates/shared_list.html  (114 lines)
app/templates/stats.html  (164 lines)
app/templates/verify_email.html  (105 lines)
main.py  (12 lines)
pyproject.toml  (38 lines)
tests/conftest.py  (9 lines)
tests/e2e/README.md  (76 lines)
tests/e2e/conftest.py  (158 lines)
tests/e2e/test_accessibility_regressions.py  (157 lines)
tests/e2e/test_auth_flows.py  (104 lines)
tests/e2e/test_diaries_list.py  (119 lines)
tests/e2e/test_diary_crud.py  (146 lines)
tests/e2e/test_edit_form_values.py  (34 lines)
tests/e2e/test_frontend_interactions.py  (262 lines)
tests/e2e/test_island_menu.py  (315 lines)
tests/e2e/test_keyboard_focus.py  (214 lines)
tests/e2e/test_landing_page.py  (76 lines)
tests/e2e/test_narrow_layouts.py  (149 lines)
tests/e2e/test_notifications.py  (176 lines)
tests/e2e/test_phone_sweep_regressions.py  (307 lines)
tests/e2e/test_responsive_all_devices.py  (150 lines)
tests/e2e/test_seo_rendered.py  (99 lines)
tests/e2e/test_settings.py  (127 lines)
tests/e2e/test_theme_before_paint.py  (46 lines)
tests/e2e/test_theme_persistence.py  (113 lines)
tests/e2e/test_visual_regressions.py  (303 lines)
tests/test_app.py  (95 lines)
tests/test_email.py  (125 lines)
tests/test_email_service_toggle.py  (183 lines)
tests/test_email_verification.py  (108 lines)
tests/test_error_pages.py  (38 lines)
tests/test_oauth.py  (178 lines)
tests/test_pin_recovery.py  (148 lines)
tests/test_push_notifications.py  (326 lines)
tests/test_security_and_features.py  (657 lines)
tests/test_seo.py  (113 lines)
uv.lock  (1581 lines)
```

## 6. Routes (generated)
### app/routers/web.py  (46 routes)
```
GET    /sw.js
GET    /robots.txt
GET    /sitemap.xml
GET    /
GET    /register
POST   /register
GET    /login
POST   /login
POST   /logout
GET    /forgot-password
POST   /forgot-password/verify
GET    /reset-password
POST   /reset-password
GET    /dashboard
GET    /stats
GET    /calendar
GET    /diaries
GET    /diaries/new
POST   /diaries/new
GET    /diaries/{diary_id}
GET    /diaries/{diary_id}/edit
POST   /diaries/{diary_id}/edit
POST   /diaries/{diary_id}/favorite
POST   /diaries/{diary_id}/pin
POST   /diaries/{diary_id}/archive
POST   /diaries/{diary_id}/restore
POST   /diaries/{diary_id}/duplicate
POST   /diaries/{diary_id}/delete
GET    /diaries/{diary_id}/export/json
GET    /diaries/{diary_id}/export/markdown
GET    /search
POST   /diaries/{diary_id}/attachments
GET    /verify-email
POST   /verify-email/resend
POST   /verify-email/confirm
GET    /settings
POST   /settings/profile
POST   /settings/notifications
POST   /settings/password
POST   /settings/delete
POST   /diaries/{diary_id}/bookmark
POST   /diaries/{diary_id}/shares
POST   /diaries/{diary_id}/shares/{share_id}/revoke
GET    /shared
GET    /attachments/{attachment_id}/download
GET    /attachments/{attachment_id}/view
```

### app/routers/api.py  (28 routes, prefix /api)
```
POST   /auth/register
POST   /auth/login
POST   /auth/login/pin
POST   /auth/logout
POST   /auth/refresh
GET    /users/me
PUT    /users/me
DELETE /users/me
GET    /diaries
POST   /diaries
GET    /diaries/{diary_id}
PUT    /diaries/{diary_id}
DELETE /diaries/{diary_id}
PATCH  /diaries/{diary_id}/favorite
PATCH  /diaries/{diary_id}/pin
PATCH  /diaries/{diary_id}/archive
PATCH  /diaries/{diary_id}/bookmark
PATCH  /diaries/{diary_id}/restore
POST   /diaries/{diary_id}/duplicate
POST   /diaries/{diary_id}/shares
GET    /tags
DELETE /tags/{tag_id}
POST   /diaries/{diary_id}/attachments
DELETE /attachments/{attachment_id}
GET    /stats/dashboard
GET    /push/vapid-public-key
POST   /push/subscribe
POST   /push/unsubscribe
```

### app/routers/oauth.py  (2 routes)
```
GET    /auth/google/login
GET    /auth/google/callback
```

### app/routers/security.py  (13 routes)
```
GET    /login/verify
POST   /login/verify/pin
POST   /login/verify/webauthn/options
POST   /login/verify/webauthn/finish
POST   /settings/pin
POST   /settings/pin/remove
POST   /settings/passkeys/options
POST   /settings/passkeys/finish
POST   /settings/passkeys/{credential_id}/delete
POST   /forgot-password/pin-reset
POST   /forgot-password/webauthn/options
POST   /forgot-password/webauthn/finish
POST   /forgot-password/reset-with-grant
```

## 7. Tests (counts generated by `pytest --collect-only`)
```
  9  tests/e2e/test_accessibility_regressions.py
 10  tests/e2e/test_auth_flows.py
 11  tests/e2e/test_diaries_list.py
  8  tests/e2e/test_diary_crud.py
  2  tests/e2e/test_edit_form_values.py
  8  tests/e2e/test_frontend_interactions.py
 37  tests/e2e/test_island_menu.py
 11  tests/e2e/test_keyboard_focus.py
 11  tests/e2e/test_landing_page.py
 29  tests/e2e/test_narrow_layouts.py
  6  tests/e2e/test_notifications.py
 21  tests/e2e/test_phone_sweep_regressions.py
 11  tests/e2e/test_responsive_all_devices.py
  8  tests/e2e/test_seo_rendered.py
  7  tests/e2e/test_settings.py
  5  tests/e2e/test_theme_before_paint.py
  5  tests/e2e/test_theme_persistence.py
 14  tests/e2e/test_visual_regressions.py
  2  tests/test_app.py
  6  tests/test_email.py
 15  tests/test_email_service_toggle.py
  7  tests/test_email_verification.py
  3  tests/test_error_pages.py
  7  tests/test_oauth.py
 10  tests/test_pin_recovery.py
 18  tests/test_push_notifications.py
 20  tests/test_security_and_features.py
  8  tests/test_seo.py
```
- Unit: FastAPI `TestClient`, fresh temp SQLite per test; helpers `build_client()`, `api_register()`, `web_csrf()` in `tests/test_security_and_features.py`.
  Web forms need a CSRF token: `GET` a page first, then post the `csrf_token` cookie as the field (or the `X-CSRF-Token` header for JSON endpoints).
- E2E: `pytest-playwright`; `tests/e2e/conftest.py` starts the app in-process on a free port (`live_server`, `live_server_factory(**settings)` for SMTP/VAPID variants) and has helpers like `register_via_api`.
  Settings used by tests: SQLite temp file, `cookie_secure=False`, SMTP off.
- Commands: `pip install -e ".[test]"`; `pytest tests --ignore=tests/e2e -q` (~40s); `pytest tests/e2e -q` (~9-11 min, one Chromium).
- Conventions that paid off: **mutation-check every new regression test** (`git worktree add /tmp/m <old-commit>`, copy the test file in, it must FAIL there);
  wait for animations (`document.getAnimations()`), never fixed sleeps; hover tests must assert `:hover` really is true (entrance animations move elements); measure real boxes, not CSS.
- Playwright version: with the Chromium revision pre-installed in the sandbox (`/opt/pw-browsers`, revision 1194) use `playwright==1.56.0`.

---

## 8. Tooling and how to see the UI (read this)

### Browser and fonts
Chromium for Playwright is pre-installed in the sandbox at `/opt/pw-browsers` (revision 1194, use `playwright==1.56.0`); if you are elsewhere run `playwright install chromium`.
**The sandbox blocks Google Fonts, jsdelivr and Playwright's CDNs** (npm, PyPI, github.com, api.github.com and Ubuntu apt are reachable). The app loads Inter/Playfair/Lora/Caveat and Bootstrap Icons from
those hosts, so without help every screenshot uses fallback fonts and has no icons and layout measurements are wrong. `tools/browser/fonts.py` serves the same fonts/icons from npm.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e . pytest respx "playwright==1.56.0" pytest-playwright        # add --break-system-packages outside a venv
(cd tools/browser && npm install)                                          # axe-core, bootstrap-icons, @fontsource/*
```

### Scripts in `tools/browser/` (each starts a throwaway app copy with a fresh SQLite DB; run from the repo root with the venv active)
- `responsive_sweep.py all|dev1,dev2 out.jsonl`: 20 device sizes x ~30 pages/states with hostile data, reports overflow/clipping/overlap/small targets/console errors and saves screenshots to `/tmp/resp_shots`. ~25 min for all; use a subset.
- `axe_sweep.py phone|desktop`: axe-core WCAG A/AA over every page x light/dark including hidden-by-default states. Re-run after changing any colour token.
- `keyboard_probe.py desktop|phone`: tabs through every page and reports focus order/indicators.
- `fonts.py`: `fonts.install(context)` for your own ad-hoc Playwright scripts.
Ad-hoc pattern that worked every time: start the app in-process with `tests/e2e/conftest.py` helpers (`_ServerThread`, `_free_port`, `_wait_until_up`, `_BASE_TEST_SETTINGS`), register a user with `page.request.post("/api/auth/register")`,
seed entries over the API, drive the page, `page.evaluate` to measure boxes, `page.screenshot` then **look at it**.

### Techniques that found real bugs
- **Measure, don't eyeball:** ruled lines vs text (render capital H lines and compare ink rows), overlap = intersect every descendant of one block with the other block's box (comparing block boxes missed a bug once), contrast with opacity/translucent backgrounds composited.
- **A/B on the same page** by injecting old CSS (`add_style_tag`) to prove a cause.
- **Freeze a mid-animation frame** or sample `getComputedStyle(sheet).transform` every 50-100ms. Disable transitions (`*{transition:none!important}`) before comparing focus styles.
- **Test the "unsupported" case on purpose:** delete `window.PublicKeyCredential` / stub `isUserVerifyingPlatformAuthenticatorAvailable` to false (found the always-visible fingerprint button).
- **WebAuthn without hardware:** CDP virtual authenticator: `cdp = ctx.new_cdp_session(page); cdp.send("WebAuthn.enable"); cdp.send("WebAuthn.addVirtualAuthenticator", {"options": {"protocol":"ctap2","transport":"internal","hasResidentKey":False,"hasUserVerification":True,"isUserVerified":True,"automaticPresenceSimulation":True}})`. Use a `http://localhost:<port>` URL (an IP address is not a valid RP id).

### Sandbox gotchas (each cost time)
1. A single tool call is limited to ~300s. Run long jobs detached: `(setsid nohup sh -c '... > log 2>&1; echo ok > done' >/dev/null 2>&1 </dev/null &)` then poll with `sleep N; tail log`. One heavy job at a time. Background jobs can still die (an e2e run died after 52 tests once): check `pgrep` and the log, relaunch.
2. `pkill -f <text>` kills your own shell when the text is in your command (tool returns -1). Use `pkill -x name` or anchored patterns, or just wait.
3. Screenshots are slow because blur/backdrop/grain are software-rendered; use clip/element shots. `page.mouse.wheel` hung once; use `scrollTo({top, behavior:'instant'})` (the site sets `scroll-behavior:smooth`).
4. `getComputedStyle` right after `blur()` returns pre-transition values; sweeps sample mid-fade colours unless you wait for finite animations to finish (see `run_axe` in `axe_sweep.py`).
5. Non-UTF-8 output (box-drawing characters in CSS/JS comments) makes the tool refuse to print: pipe through `iconv -f utf-8 -t ascii//TRANSLIT`.
6. `git worktree add /tmp/m <rev>` + copy a test file in is the cheap way to mutation-check; remove with `git worktree remove --force`.
7. CI logs are not downloadable from the sandbox (section 3). Delete any stray `digital_diary_application.egg-info` before `git add -A`.

---

## 9. Root causes worth remembering (they generalise)

| Symptom | Cause | Rule |
|---|---|---|
| Ruled lines ~13px high | `background-position-y` is measured from the padding box; JS measured from the line box | CSS origin vs measured origin |
| Phantom blank lines (view mode, then editor) | `white-space: pre-wrap` inherits into whitespace-only text nodes between tags (editor: 2 lines above and 2 below the textarea, `offsetTop` 102 not 16) | put `pre-wrap` only on the element that holds the text |
| Turn sheet lost its lines | `.x{background-image}` wiped by a later same-specificity `.y{background:...}` shorthand | never mix longhand and shorthand across rules |
| Landing hero text flush to the screen edge | `.landing-hero{padding: X 0}` shorthand zeroed the left/right padding `.full-bleed` provides | use `padding-block` when you mean vertical only |
| Double ruled lines on phones only | an old rule inside `@media (max-width:767px)` painted a second set on `.journal-paper` | grep media queries for stray overrides; dead copies hide there |
| `[hidden]` buttons visible | `.btn{display:inline-flex}` overrides the UA `[hidden]{display:none}` | global `[hidden]{display:none!important}` |
| Closed drawer / island links were tab stops | off-canvas via transform is not hidden | `visibility:hidden` when closed, delayed by the close animation |
| Entry header text under the Edit button | `flex:1` (basis 0) never wraps; the other group takes its width and the block is crushed | give the flexible block a real basis (`1 1 14rem`) |
| Theme flashes between pages | saved theme applied only by `app.js` at end of `<body>`; cross-document view transitions can snapshot the light default | inline head script |
| "Location: None" | Jinja prints `None`; saving stored the text "None" | `{% if x %}{{ x }}{% endif %}` |
| Book page overflow / text after the end mark | one unbroken word taller than a page counted as "always fits" | split only a word that cannot fit |
| Page turn invisible, pages skipped | 0.38s front-loaded easing, 180deg swing clipped, page swapped halfway; later 0.8s turns ignored clicks | render the target first, leaf = page you leave, interruptible |
| Book view only 5-6 lines on phones | card `max-height: clamp(460px,75vh,620px)` includes header + controls | size the reading area in lines on phones |
| Dark contrast everywhere | `--txt-muted` and a hover shade used as text; tokens checked on page surfaces but drawn on tints (calendar cell, upload zone hover, fixed-colour cards) | text-safe tokens; check a token on the component's own background; redefine tokens on fixed-colour surfaces |
| Nested `<a>` on dashboard cards | card wrapped in `<a>` containing tag `<a>`s; the parser "repairs" it | stretched-link pattern |
| Unknown URL returned raw JSON | no viewport meta tag -> phones lay it out at 980px | real HTML 404 page |
| Textarea/mood-pill "overlap" in sweeps | the writing paper is a scroll container (`max-height:58vh`) | known false positive |
| An `if (!found) return` path counted a probe artifact as a bug | scrolled page, start `bottom` at 0 | start from `-Infinity`; sanity-check the probe |

Process lessons: re-run the axe sweep after changing any colour token; a first test that passes on the broken code proves nothing (mutation-check); fixed `wait_for_timeout` values flake under suite load; a checker's flag is a lead, not a verdict;
when a theory is wrong, say so (twice a suspected vulnerability was disproved by testing before reporting).

---

## 10. History (merged PRs, newest last)

| PR | What |
|---|---|
| #1 | skip link, `.sr-only` duplicate text, expired/tampered JWT -> 500 fixed, attachment filename collisions, password meter/toggle dead on settings/reset, download progress, `innerHTML` XSS in `appendAttachment` |
| #2 | theme-adaptive scrollbars, `theme-color` follows theme, stale dark colours, end flourish only on last page, filename contrast, ruled-line offset + phantom lines, turn-sheet background, book view paginates by measurement, axe sweep fixes (nested links, calendar ARIA, tokens), 14+ e2e tests |
| #3 | phone-sweep a11y: `--danger-text` etc., autosave opacity, paperclip text, upload-zone nested interactive + keyboard, Danger tab, password-strength colours, dark calendar cells, forgot-password links, calendar `gridcell > link`, reduced-motion page turn, flake fixes |
| #4 | keyboard pass: drawer out of tab order, focus management, desktop close "X", book view arrow keys no longer swallow Alt/Ctrl/Shift+arrows or `<select>` arrows, page counter live region, header search no longer submits on IME composition Enter, bookmark ribbon `aria-pressed` |
| #5 | the island quick-nav + adaptive behaviour (compact on scroll, hide while typing on phones, progress hairline, word count, wide layout) |
| #6 | theme before paint, island centred on the screen, edit form `None`, entry header wrap, narrow-screen text wrapping (buttons, headings, breadcrumb, location), 404 page, 500 page viewport |
| #7 | editor phantom lines, book paginator for oversized words, page-turn redesign (interruptible), ribbon gap, paper grain, app-styled dropdowns, island hidden in book view |
| #8 | security PIN, passkeys (fingerprint/face), PIN/passkey recovery without email, trusted device, emailed-code hardening, `[hidden]` rule, no-sensor behaviour |
| #9 | double ruled lines + margin line on phones |
| #10 | landing hero side padding, 12-15 lines per book page on phones |
| #11 | this handoff, cleanup (removed `test_main.http` and six unused functions, README commands/env table fixed), `tools/browser/` |
Owner commits on `main` in between (e.g. `a2bd565` page aesthetics, `46514c6` frontend interaction tests) are already in the history.

---

## 11. Open items (prioritised)

**Data**
1. Entries saved while the edit-form `None` bug existed have the literal text `"None"` as their location. Needs a one-off script (dry-run by default); the app has no migration framework. Not done.

**Product / design decisions for the owner**
2. Tap targets: many standalone links/tags are 13-22px tall (WCAG 2.5.8 wants 24px). Candidates: "Browse them all", "Forgot password?", tag badges, diary card titles, "My Diaries" crumb, "View archived".
3. Memorabilia (polaroid/paperclip) cards are always light with fixed dark text; an older rule set implied dark-adapted cards. Pick one.
4. Island + sidebar are both navigation on desktop; keep both or hide the island there?
5. Pressing Enter in the entry title submits the whole form (native implicit submission). Many editors move focus to the body instead.
6. Tablets (768px+) keep the card `max-height` book layout (~13 lines on desktop); say if tablets should get the phone treatment.
7. PIN hardening: IP rate limiting, longer minimum, or alerting; Google OAuth skipping the PIN step.

**Small known defects**
8. The visibility dropdown in the editor header overhangs the screen by ~2px at 280px width (`/diaries/new`, edit). Found by `responsive_sweep.py fold-280`.
9. `alembic` is listed in `pyproject.toml` but never imported (also in `uv.lock`); remove with `uv lock` when convenient. Dead CSS remains: the "Polaroid dark mode fix" selectors match inline `background:#fff` styles the class-based cards no longer have.
10. `mood` is only `max_length=50` server-side; unknown values reach the CSS fallback path. Validate against the known list.
11. The scheduler is a single 60s in-process loop and can skip a minute.

**Never tested:** Firefox and Safari (scrollbar styling: Chrome >= 121 ignores `::-webkit-scrollbar` when `scrollbar-color` is set; `display: contents` row semantics; `:focus-within`), real phones/tablets, a real on-screen keyboard, real fingerprint/face hardware, any screen reader, passkeys on a real HTTPS domain.

---

## 12. Prompt to paste into the next AI

> You are continuing work on the FastAPI/Jinja2 diary app at https://github.com/Yoge-2004/digital-diary-application. Read `HANDOFF.md` fully first (sections 0, 3, 8, 9 matter most).
> Rules: work on a branch and open a PR; one commit per concern with the root cause and evidence in the message; **do not run the test suites unless the owner says to** (targeted browser checks are fine);
> verify every visual or layout claim by rendering in Chromium and measuring (`tools/browser/`, fonts/icons come from npm because the CDNs are blocked); look at screenshots before trusting a checker;
> be explicit about what you did not test (Firefox, Safari, real devices). Never write a secret into a file or git config: ask the owner for a fresh GitHub token, use it inline, and remind them to rotate the old one.
> After CI is green merge with a merge commit and delete the branch (the owner usually says "merge everything"). Start with the owner's request; if there is none, pick from section 11.
