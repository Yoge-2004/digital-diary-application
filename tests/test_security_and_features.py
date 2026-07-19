"""Coverage for the authorization fixes plus the feature areas that were
specifically flagged for a correctness pass: bookmarking, visibility,
sharing, attachments, and location tagging.

Multi-user scenarios use two (or three) independent `TestClient`
instances wrapping the *same* app/db, so each user gets their own
cookie jar while sharing backend state — this is how "alice" and
"bob" interact with each other's diaries in these tests.
"""

from __future__ import annotations

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
        alice.post("/register", data={"username": "alice", "email": "alice@example.com", "password": "password123", "csrf_token": csrf}, follow_redirects=False)

        csrf = web_csrf(bob, "/register")
        bob.post("/register", data={"username": "bob", "email": "bob@example.com", "password": "password123", "csrf_token": csrf}, follow_redirects=False)

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
# Location tagging
# ---------------------------------------------------------------------

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
