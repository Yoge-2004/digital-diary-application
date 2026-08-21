"""Coverage for the authorization fixes plus the feature areas that were
specifically flagged for a correctness pass: bookmarking, visibility,
sharing, attachments, and location tagging.

Multi-user scenarios use two (or three) independent `TestClient`
instances wrapping the *same* app/db, so each user gets their own
cookie jar while sharing backend state — this is how "alice" and
"bob" interact with each other's diaries in these tests.
"""

from __future__ import annotations

import datetime as dt
import re
import tempfile

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

CSRF_META_RE = re.compile(r'name="csrf-token"\s+content="([^"]+)"')


def build_app():
    tmp = tempfile.TemporaryDirectory()
    settings = Settings(
        database_url=f"sqlite:///{tmp.name}/test.db",
        secret_key="dev-secret-key-with-32-chars-minimum!!",
    )
    app = create_app(settings)
    return app, tmp


def build_client():
    app, tmp = build_app()
    return TestClient(app), tmp


def api_register(client: TestClient, username: str, email: str, password: str = "password123"):
    response = client.post(
        "/api/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    assert response.status_code == 201, response.text
    return response.json()


def web_csrf(client: TestClient, page: str = "/login") -> str:
    """Load a web page like a browser would and pull the CSRF token straight
    out of the rendered <meta> tag — not the cookie jar — so these tests
    actually exercise the same value a browser would submit."""
    response = client.get(page)
    match = CSRF_META_RE.search(response.text)
    assert match, f"no csrf meta tag found on {page}"
    return match.group(1)


# ---------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------

def test_first_visit_csrf_token_matches_cookie():
    """A brand-new visitor (no prior csrf_token cookie) must see the same
    token in the page as gets set in their cookie — otherwise their very
    first form submission fails CSRF validation. Regression test for the
    request.state caching fix in ensure_csrf_cookie."""
    client, tmp = build_client()
    with client, tmp:
        rendered_token = web_csrf(client, "/register")
        cookie_token = client.cookies.get("csrf_token")
        assert rendered_token == cookie_token

        response = client.post(
            "/register",
            data={
                "username": "firsttimer",
                "email": "firsttimer@example.com",
                "password": "password123",
                "confirm_password": "password123",
                "csrf_token": rendered_token,
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/dashboard"


# ---------------------------------------------------------------------
# Ownership / authorization
# ---------------------------------------------------------------------

def test_only_owner_can_mutate_via_api():
    app, tmp = build_app()
    alice, bob = TestClient(app), TestClient(app)
    with alice, bob, tmp:
        api_register(alice, "alice", "alice@example.com")
        api_register(bob, "bob", "bob@example.com")

        created = alice.post(
            "/api/diaries",
            json={"title": "Alice's public thought", "content": "...", "visibility": "public"},
        ).json()
        diary_id = created["id"]

        # Bob can view it (public) ...
        assert bob.get(f"/api/diaries/{diary_id}").status_code == 200

        # ... but every mutation must be refused.
        assert bob.put(f"/api/diaries/{diary_id}", json={"title": "hacked"}).status_code == 403
        assert bob.patch(f"/api/diaries/{diary_id}/favorite").status_code == 403
        assert bob.patch(f"/api/diaries/{diary_id}/pin").status_code == 403
        assert bob.patch(f"/api/diaries/{diary_id}/archive").status_code == 403
        assert bob.patch(f"/api/diaries/{diary_id}/bookmark").status_code == 403
        assert bob.post(f"/api/diaries/{diary_id}/duplicate").status_code == 403
        assert bob.delete(f"/api/diaries/{diary_id}").status_code == 403

        # Content is untouched, and the entry still exists.
        still_there = alice.get(f"/api/diaries/{diary_id}").json()
        assert still_there["title"] == "Alice's public thought"


def test_only_owner_can_mutate_via_web():
    app, tmp = build_app()
    alice, bob = TestClient(app), TestClient(app)
    with alice, bob, tmp:
        csrf = web_csrf(alice, "/register")
        alice.post("/register", data={"username": "alice", "email": "alice@example.com", "password": "password123", "confirm_password": "password123", "csrf_token": csrf}, follow_redirects=False)

        csrf = web_csrf(bob, "/register")
        bob.post("/register", data={"username": "bob", "email": "bob@example.com", "password": "password123", "confirm_password": "password123", "csrf_token": csrf}, follow_redirects=False)

        csrf = web_csrf(alice, "/diaries/new")
        alice.post(
            "/diaries/new",
            data={"title": "Alice web entry", "content": "hello", "mood": "calm", "visibility": "public", "csrf_token": csrf},
            follow_redirects=False,
        )
        diary_id = alice.get("/api/diaries").json()[0]["id"]

        bob_csrf = bob.cookies.get("csrf_token") or web_csrf(bob, "/dashboard")

        # Bob can view the public page...
        assert bob.get(f"/diaries/{diary_id}").status_code == 200
        # ...but can't edit, delete, or re-flag it.
        bob.post(f"/diaries/{diary_id}/edit", data={"title": "hacked", "content": "x", "mood": "sad", "visibility": "private", "csrf_token": bob_csrf}, follow_redirects=False)
        bob.post(f"/diaries/{diary_id}/delete", data={"csrf_token": bob_csrf}, follow_redirects=False)
        bob.post(f"/diaries/{diary_id}/favorite", data={"csrf_token": bob_csrf}, follow_redirects=False)

        unchanged = alice.get(f"/api/diaries/{diary_id}").json()
        assert unchanged["title"] == "Alice web entry"
        assert unchanged["is_favorite"] is False


# ---------------------------------------------------------------------
# Visibility
# ---------------------------------------------------------------------

def test_private_vs_public_visibility():
    app, tmp = build_app()
    alice, bob = TestClient(app), TestClient(app)
    with alice, bob, tmp:
        api_register(alice, "alice", "alice@example.com")
        api_register(bob, "bob", "bob@example.com")

        private_id = alice.post("/api/diaries", json={"title": "Private", "content": "shh", "visibility": "private"}).json()["id"]
        public_id = alice.post("/api/diaries", json={"title": "Public", "content": "hi world", "visibility": "public"}).json()["id"]

        assert bob.get(f"/api/diaries/{private_id}").status_code == 403
        assert bob.get(f"/api/diaries/{public_id}").status_code == 200


# ---------------------------------------------------------------------
# Sharing
# ---------------------------------------------------------------------

def test_share_with_specific_user_and_expiry():
    app, tmp = build_app()
    alice, bob = TestClient(app), TestClient(app)
    with alice, bob, tmp:
        api_register(alice, "alice", "alice@example.com")
        api_register(bob, "bob", "bob@example.com")

        diary_id = alice.post("/api/diaries", json={"title": "For Bob's eyes", "content": "secret", "visibility": "private"}).json()["id"]

        # Not shared yet — Bob is refused.
        assert bob.get(f"/api/diaries/{diary_id}").status_code == 403

        share = alice.post(f"/api/diaries/{diary_id}/shares", json={"shared_to_username": "bob"})
        assert share.status_code == 201
        assert share.json()["shared_to_username"] == "bob"

        # Now Bob can view it.
        assert bob.get(f"/api/diaries/{diary_id}").status_code == 200

        # An *expired* share must not grant access.
        expired_diary_id = alice.post("/api/diaries", json={"title": "Old share", "content": "...", "visibility": "private"}).json()["id"]
        alice.post(f"/api/diaries/{expired_diary_id}/shares", json={"shared_to_username": "bob", "expires_in_hours": -1})
        assert bob.get(f"/api/diaries/{expired_diary_id}").status_code == 403

        # Sharing is owner-only.
        other_diary_id = bob.post("/api/diaries", json={"title": "Bob's own", "content": "..."}).json()["id"]
        assert alice.post(f"/api/diaries/{other_diary_id}/shares", json={"shared_to_username": "alice"}).status_code == 403


def test_public_share_link_works_for_anyone():
    app, tmp = build_app()
    alice, carol = TestClient(app), TestClient(app)
    with alice, carol, tmp:
        api_register(alice, "alice", "alice@example.com")
        api_register(carol, "carol", "carol@example.com")

        diary_id = alice.post("/api/diaries", json={"title": "Link only", "content": "...", "visibility": "private"}).json()["id"]
        # No shared_to_username -> a public link anyone with it can use.
        share = alice.post(f"/api/diaries/{diary_id}/shares", json={})
        assert share.status_code == 201
        assert share.json()["shared_to_username"] is None

        assert carol.get(f"/api/diaries/{diary_id}").status_code == 200


# ---------------------------------------------------------------------
# Bookmarking / favourites
# ---------------------------------------------------------------------

def test_owner_can_toggle_bookmark_and_favorite():
    client, tmp = build_client()
    with client, tmp:
        api_register(client, "alice", "alice@example.com")
        diary_id = client.post("/api/diaries", json={"title": "Diary", "content": "..."}).json()["id"]

        assert client.patch(f"/api/diaries/{diary_id}/bookmark").json()["is_bookmarked"] is True
        assert client.patch(f"/api/diaries/{diary_id}/bookmark").json()["is_bookmarked"] is False

        assert client.patch(f"/api/diaries/{diary_id}/favorite").json()["is_favorite"] is True
        assert client.patch(f"/api/diaries/{diary_id}/favorite").json()["is_favorite"] is False


# ---------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------

def test_attachment_upload_and_visibility_on_page():
    app, tmp = build_app()
    alice, bob = TestClient(app), TestClient(app)
    with alice, bob, tmp:
        api_register(alice, "alice", "alice@example.com")
        api_register(bob, "bob", "bob@example.com")

        diary_id = alice.post("/api/diaries", json={"title": "With a photo", "content": "...", "visibility": "private"}).json()["id"]

        upload = alice.post(
            f"/api/diaries/{diary_id}/attachments",
            files={"file": ("photo.png", b"\x89PNG\r\n fake but fine for a test", "image/png")},
        )
        assert upload.status_code == 201

        attachment_id = alice.get(f"/api/diaries/{diary_id}").json()["attachments"][0]["id"]

        # It shows up as an <img> on the rendered entry page for the owner.
        detail_html = alice.get(f"/diaries/{diary_id}").text
        assert f"/attachments/{attachment_id}/view" in detail_html
        assert "<img" in detail_html

        # A random user with no access can't view the file directly.
        assert bob.get(f"/attachments/{attachment_id}/view").status_code == 403

        # Once Alice makes the entry public, Bob can see the attachment too.
        alice.put(f"/api/diaries/{diary_id}", json={"visibility": "public"})
        assert bob.get(f"/attachments/{attachment_id}/view").status_code == 200

        # Only the uploader (not just the diary owner in general, though here
        # they're the same person) can delete it.
        assert bob.delete(f"/api/attachments/{attachment_id}").status_code == 404


# ---------------------------------------------------------------------
# Button feedback (AJAX toggles shouldn't trigger a full navigation)
# ---------------------------------------------------------------------

def test_card_list_toggle_is_ajax_not_a_page_reload():
    """Regression test: the diary-card list view's favorite/bookmark/pin
    buttons used to be plain <form> submits, which redirected (303) back
    to the same page — triggering a full page-turn view-transition just
    to toggle an icon. They should now behave exactly like the entry
    detail page's toggles: an instant JSON response, no redirect."""
    client, tmp = build_client()
    with client, tmp:
        api_register(client, "alice", "alice@example.com")
        diary_id = client.post("/api/diaries", json={"title": "Card toggle test", "content": "..."}).json()["id"]

        list_html = client.get("/diaries").text
        assert f'data-toggle-url="/diaries/{diary_id}/favorite"' in list_html
        assert f'action="/diaries/{diary_id}/favorite"' not in list_html

        csrf = client.cookies.get("csrf_token")
        response = client.post(
            f"/diaries/{diary_id}/favorite",
            data={"csrf_token": csrf},
            headers={"X-Requested-With": "fetch"},
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        assert response.json() == {"ok": True, "flag": "is_favorite", "value": True}


# ---------------------------------------------------------------------
# Archived entries should be hidden from the default list
# ---------------------------------------------------------------------

def test_archived_entries_hidden_from_default_list():
    """Regression test: archived=None was being passed through explicitly
    from the route handler, which skipped the repository's hide-archived
    -by-default filter entirely, so archived entries leaked into the main
    /diaries list and /api/diaries response."""
    client, tmp = build_client()
    with client, tmp:
        api_register(client, "alice", "alice@example.com")
        diary_id = client.post("/api/diaries", json={"title": "To archive", "content": "..."}).json()["id"]
        client.patch(f"/api/diaries/{diary_id}/archive")

        assert client.get("/api/diaries").json() == []

        list_html = client.get("/diaries").text
        assert "To archive" not in list_html

        # explicitly asking for archived should still find it
        archived_html = client.get("/diaries?archived=true").text
        assert "To archive" in archived_html


# ---------------------------------------------------------------------
# Backdating entries
# ---------------------------------------------------------------------

def test_entry_can_be_backdated_but_not_future_dated():
    client, tmp = build_client()
    with client, tmp:
        api_register(client, "alice", "alice@example.com")

        past = (dt.date.today() - dt.timedelta(days=5)).isoformat()
        created = client.post(
            "/api/diaries",
            json={"title": "Forgot to write this", "content": "...", "entry_date": past},
        )
        assert created.status_code == 201
        diary_id = created.json()["id"]
        assert client.get(f"/api/diaries/{diary_id}").json()["created_at"].startswith(past)

        future = (dt.date.today() + dt.timedelta(days=1)).isoformat()
        rejected = client.post(
            "/api/diaries",
            json={"title": "Scheduling ahead", "content": "...", "entry_date": future},
        )
        assert rejected.status_code == 400

        # editing to a future date is rejected too
        bad_edit = client.put(f"/api/diaries/{diary_id}", json={"entry_date": future})
        assert bad_edit.status_code == 400


def test_search_page_survives_empty_month_year_params():
    """Regression test: HTML forms always submit every named field, so an
    untouched month/year select sends month=&year= (empty strings, not
    absent). These were typed as `int | None`, and FastAPI/Pydantic reject
    an empty string as invalid int input with a raw 422, instead of
    treating it as 'not provided'."""
    client, tmp = build_client()
    with client, tmp:
        api_register(client, "alice", "alice@example.com")
        response = client.get("/search?q=&mood=&tag=&month=&year=")
        assert response.status_code == 200


# ---------------------------------------------------------------------
# Password confirmation must actually be checked server-side
# ---------------------------------------------------------------------

def test_registration_rejects_mismatched_confirm_password():
    """Regression test: the backend accepted `password` without ever
    reading or checking `confirm_password`, relying entirely on
    client-side JS to catch a typo — a JS-disabled or scripted client
    could register with a password that didn't match what was shown."""
    client, tmp = build_client()
    with client, tmp:
        csrf = web_csrf(client, "/register")
        response = client.post(
            "/register",
            data={
                "username": "mismatched",
                "email": "mismatched@example.com",
                "password": "password123",
                "confirm_password": "somethingElse123",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "do+not+match" in response.headers["location"] or "do not match" in response.headers["location"]
        # account must not have been created
        assert client.cookies.get("access_token") is None


def test_password_change_rejects_mismatched_confirmation():
    client, tmp = build_client()
    with client, tmp:
        api_register(client, "alice", "alice@example.com", password="OldPass123!")
        csrf = web_csrf(client, "/settings")
        response = client.post(
            "/settings/password",
            data={
                "current_password": "OldPass123!",
                "new_password": "NewPass456!",
                "confirm_new_password": "Typo789!",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "do+not+match" in response.headers["location"]

        # old password must still work; new one must not have been set
        login_csrf = web_csrf(client, "/login")
        login_resp = client.post(
            "/login",
            data={"username": "alice", "password": "OldPass123!", "csrf_token": login_csrf},
            follow_redirects=False,
        )
        assert login_resp.status_code == 303
        assert login_resp.headers["location"] == "/dashboard"


# ---------------------------------------------------------------------
# Password reset must require a real, single-use, expiring token —
# not just knowledge of a username + email (which may be publicly
# visible, e.g. on a shared/public entry).
# ---------------------------------------------------------------------

def _get_reset_token(tmp, username="alice"):
    """Despite the name (kept for git-blame continuity), this now reads
    a 6-digit OTP code, not a URL token."""
    import sqlite3
    conn = sqlite3.connect(f"{tmp.name}/test.db")
    row = conn.execute("SELECT reset_token FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return row[0] if row else None


def test_password_reset_requires_a_real_code_not_just_credentials():
    client, tmp = build_client()
    with client, tmp:
        api_register(client, "alice", "alice@example.com", password="OldPass123!")

        # Old vulnerable behavior must be gone: this endpoint no longer
        # accepts a new_password directly from username+email.
        old_style = client.post(
            "/forgot-password/reset",
            json={"username": "alice", "email": "alice@example.com", "new_password": "Hacked123!"},
        )
        assert old_style.status_code == 404  # route no longer exists

        # Requesting a reset with correct credentials generates a code...
        request = client.post("/forgot-password/verify", json={"username": "alice", "email": "alice@example.com"})
        assert request.status_code == 200
        code = _get_reset_token(tmp)
        assert code and len(code) == 6 and code.isdigit()  # a real 6-digit code was actually generated

        # ...a made-up code is rejected...
        fake = client.post("/reset-password", json={
            "identifier": "alice", "code": "000000", "new_password": "Hacked123!", "confirm_new_password": "Hacked123!",
        })
        assert fake.status_code == 400

        # ...the right code with the wrong identifier is also rejected...
        wrong_identifier = client.post("/reset-password", json={
            "identifier": "someone-else", "code": code, "new_password": "Hacked123!", "confirm_new_password": "Hacked123!",
        })
        assert wrong_identifier.status_code == 400

        # ...but the real code with the right identifier works...
        real = client.post("/reset-password", json={
            "identifier": "alice", "code": code, "new_password": "BrandNew123!", "confirm_new_password": "BrandNew123!",
        })
        assert real.status_code == 200

        # ...old password is now invalid, new one works...
        old_login = client.post("/api/auth/login", data={"username": "alice", "password": "OldPass123!"})
        assert old_login.status_code == 401
        new_login = client.post("/api/auth/login", data={"username": "alice", "password": "BrandNew123!"})
        assert new_login.status_code == 200

        # ...and the code is now single-use: trying it again fails even
        # with everything else correct.
        reuse = client.post("/reset-password", json={
            "identifier": "alice", "code": code, "new_password": "AnotherOne123!", "confirm_new_password": "AnotherOne123!",
        })
        assert reuse.status_code == 400


def test_password_reset_request_does_not_leak_account_existence():
    """A request for a username/email that doesn't exist must get the
    exact same generic response as a real one, so this can't be used to
    enumerate which accounts exist."""
    client, tmp = build_client()
    with client, tmp:
        api_register(client, "alice", "alice@example.com")
        real = client.post("/forgot-password/verify", json={"username": "alice", "email": "alice@example.com"})
        fake = client.post("/forgot-password/verify", json={"username": "nobody-here", "email": "nobody@example.com"})
        assert real.status_code == fake.status_code == 200
        assert real.json() == fake.json()
        # and no token should exist for a nonexistent user, obviously
        assert _get_reset_token(tmp, "nobody-here") is None


def test_location_round_trips_through_api_and_page():
    client, tmp = build_client()
    with client, tmp:
        api_register(client, "alice", "alice@example.com")
        created = client.post(
            "/api/diaries",
            json={"title": "Somewhere nice", "content": "...", "location": "Paris, France"},
        ).json()
        diary_id = created["id"]
        assert created["location"] == "Paris, France"

        fetched = client.get(f"/api/diaries/{diary_id}").json()
        assert fetched["location"] == "Paris, France"

        detail_html = client.get(f"/diaries/{diary_id}").text
        assert "Paris, France" in detail_html


def test_standalone_pages_have_a_flash_container_for_js_error_toasts():
    """auth.html, forgot_password.html, and reset_password.html don't
    extend base.html, so they have their own standalone <head>/<body> --
    which meant they'd been missing the #flashContainer element that
    showFlash() (used for e.g. "that code is invalid" on a failed
    password reset) needs to render into. Without it, showFlash() was a
    silent no-op: the request failed but the page gave no visible
    feedback at all. This just checks the element exists on each page;
    tests/test_security_and_features's browser-driven flows already
    cover that submitting a wrong code fails server-side."""
    client, tmp = build_client()
    with client, tmp:
        for path in ["/login", "/register", "/forgot-password", "/reset-password"]:
            resp = client.get(path)
            assert 'id="flashContainer"' in resp.text, f"{path} is missing #flashContainer"
