from __future__ import annotations

import tempfile
from urllib.parse import parse_qs, urlparse

import httpx
import respx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.models import User
from app.db.session import create_engine_from_url
from sqlalchemy.orm import sessionmaker


def build_oauth_client():
    """Like tests/test_app.py's build_client(), but with fake Google OAuth
    credentials configured so the /auth/google/* routes are active."""
    tmp = tempfile.TemporaryDirectory()
    settings = Settings(
        database_url=f"sqlite:///{tmp.name}/test.db",
        secret_key="dev-secret-key-with-32-chars-minimum!!",
        google_client_id="fake-client-id.apps.googleusercontent.com",
        google_client_secret="fake-client-secret",
    )
    app = create_app(settings)
    client = TestClient(app)
    return client, tmp, settings


def _mock_google(router, sub="1234567890", email="newuser@gmail.com", name="New User", verified=True):
    router.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(200, json={"access_token": "fake-google-access-token"})
    )
    router.get("https://www.googleapis.com/oauth2/v3/userinfo").mock(
        return_value=httpx.Response(200, json={
            "sub": sub, "email": email, "email_verified": verified, "name": name,
        })
    )


def test_google_oauth_disabled_by_default():
    """With no Google credentials configured, the routes must redirect
    with a clear error rather than attempting a real OAuth flow."""
    tmp = tempfile.TemporaryDirectory()
    settings = Settings(
        database_url=f"sqlite:///{tmp.name}/test.db",
        secret_key="dev-secret-key-with-32-chars-minimum!!",
    )
    app = create_app(settings)
    client = TestClient(app)
    with client, tmp:
        assert settings.google_oauth_enabled is False
        response = client.get("/auth/google/login", follow_redirects=False)
        assert response.status_code == 303
        assert "not+configured" in response.headers["location"]

        # The button must not render on login/register when disabled.
        assert "Continue with Google" not in client.get("/login").text
        assert "Continue with Google" not in client.get("/register").text


def test_google_oauth_login_redirects_to_google_with_state():
    client, tmp, settings = build_oauth_client()
    with client, tmp:
        assert "Continue with Google" in client.get("/login").text

        response = client.get("/auth/google/login", follow_redirects=False)
        assert response.status_code == 302
        location = response.headers["location"]
        assert location.startswith("https://accounts.google.com/o/oauth2/v2/auth")

        params = parse_qs(urlparse(location).query)
        assert params["client_id"][0] == settings.google_client_id
        assert params["redirect_uri"][0].endswith("/auth/google/callback")
        assert "state" in params
        assert client.cookies.get("oauth_state") == params["state"][0]


def test_google_oauth_callback_creates_new_user_and_logs_in():
    client, tmp, settings = build_oauth_client()
    with client, tmp:
        login_resp = client.get("/auth/google/login", follow_redirects=False)
        state = parse_qs(urlparse(login_resp.headers["location"]).query)["state"][0]

        with respx.mock(assert_all_called=True) as respx_mock:
            _mock_google(respx_mock, sub="1234567890", email="newuser@gmail.com", name="New User")
            callback_resp = client.get(
                f"/auth/google/callback?code=fake-code&state={state}", follow_redirects=False
            )

        assert callback_resp.status_code == 303
        assert callback_resp.headers["location"] == "/dashboard"
        assert client.cookies.get("access_token")
        assert client.cookies.get("refresh_token")

        dashboard = client.get("/dashboard")
        assert dashboard.status_code == 200
        assert "newuser" in dashboard.text


def test_google_oauth_second_login_reuses_same_account():
    """Signing in with the same Google identity twice must not create a
    duplicate user."""
    client, tmp, settings = build_oauth_client()
    with client, tmp:
        for _ in range(2):
            login_resp = client.get("/auth/google/login", follow_redirects=False)
            state = parse_qs(urlparse(login_resp.headers["location"]).query)["state"][0]
            with respx.mock(assert_all_called=True) as respx_mock:
                _mock_google(respx_mock, sub="1234567890", email="newuser@gmail.com")
                client.get(f"/auth/google/callback?code=fake&state={state}", follow_redirects=False)

        engine = create_engine_from_url(settings.database_url)
        db = sessionmaker(bind=engine)()
        try:
            users = db.query(User).filter(User.email == "newuser@gmail.com").all()
            assert len(users) == 1
        finally:
            db.close()


def test_google_oauth_links_to_existing_password_account():
    """A user who already has a password account should have their Google
    identity linked to it (same account, not a second one) when they sign
    in with Google using the same email address."""
    client, tmp, settings = build_oauth_client()
    with client, tmp:
        csrf_token = client.get("/register").cookies.get("csrf_token")
        reg_resp = client.post(
            "/register",
            data={
                "username": "existinguser",
                "email": "existing@gmail.com",
                "password": "password123",
                "confirm_password": "password123",
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )
        assert reg_resp.status_code == 303

        client.cookies.clear()
        login_resp = client.get("/auth/google/login", follow_redirects=False)
        state = parse_qs(urlparse(login_resp.headers["location"]).query)["state"][0]
        with respx.mock(assert_all_called=True) as respx_mock:
            _mock_google(respx_mock, sub="9999999999", email="existing@gmail.com", name="Existing User")
            client.get(f"/auth/google/callback?code=fake&state={state}", follow_redirects=False)

        engine = create_engine_from_url(settings.database_url)
        db = sessionmaker(bind=engine)()
        try:
            users = db.query(User).filter(User.email == "existing@gmail.com").all()
            assert len(users) == 1
            assert users[0].username == "existinguser"
            assert users[0].oauth_provider == "google"
            assert users[0].password_hash is not None
        finally:
            db.close()


def test_google_oauth_callback_rejects_bad_state():
    client, tmp, settings = build_oauth_client()
    with client, tmp:
        response = client.get(
            "/auth/google/callback?code=fake&state=not-the-real-state", follow_redirects=False
        )
        assert response.status_code == 303
        assert "invalid" in response.headers["location"].lower()


def test_google_oauth_callback_handles_user_cancellation():
    client, tmp, settings = build_oauth_client()
    with client, tmp:
        response = client.get("/auth/google/callback?error=access_denied", follow_redirects=False)
        assert response.status_code == 303
        assert "cancelled" in response.headers["location"].lower()
