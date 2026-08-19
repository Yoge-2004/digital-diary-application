from __future__ import annotations

import tempfile

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.test_security_and_features import api_register


def build_client_no_email():
    """Same as tests/test_security_and_features.py's build_client(), but
    with the email service turned off."""
    tmp = tempfile.TemporaryDirectory()
    settings = Settings(
        database_url=f"sqlite:///{tmp.name}/test.db",
        secret_key="dev-secret-key-with-32-chars-minimum!!",
        email_service_enabled=False,
    )
    app = create_app(settings)
    return TestClient(app), tmp


def build_client_with_email():
    tmp = tempfile.TemporaryDirectory()
    settings = Settings(
        database_url=f"sqlite:///{tmp.name}/test.db",
        secret_key="dev-secret-key-with-32-chars-minimum!!",
        email_service_enabled=True,
    )
    app = create_app(settings)
    return TestClient(app), tmp


# ── Sanity: the toggle defaults on, and the "on" behavior from earlier
#    sessions still works when explicitly enabled ──────────────────────

def test_email_service_enabled_by_default():
    from app.core.config import Settings as S
    assert S(database_url="sqlite:///:memory:", secret_key="x" * 32).email_service_enabled is True


def test_with_email_enabled_forgot_password_and_verify_email_still_work():
    client, tmp = build_client_with_email()
    with client, tmp:
        assert client.get("/forgot-password").status_code == 200
        assert client.get("/reset-password").status_code == 200

        api_register(client, "alice", "alice@example.com", password="Password123!")
        assert client.get("/verify-email").status_code == 200


# ── With the toggle off: routes must not exist (404), not just redirect ─

def test_forgot_password_page_404s_when_email_disabled():
    client, tmp = build_client_no_email()
    with client, tmp:
        resp = client.get("/forgot-password")
        assert resp.status_code == 404


def test_reset_password_page_404s_when_email_disabled():
    client, tmp = build_client_no_email()
    with client, tmp:
        resp = client.get("/reset-password")
        assert resp.status_code == 404


def test_forgot_password_post_404s_when_email_disabled():
    client, tmp = build_client_no_email()
    with client, tmp:
        resp = client.post("/forgot-password/verify", json={"username": "alice", "email": "alice@example.com"})
        assert resp.status_code == 404


def test_reset_password_post_404s_when_email_disabled():
    client, tmp = build_client_no_email()
    with client, tmp:
        resp = client.post("/reset-password", json={
            "identifier": "alice", "code": "123456", "new_password": "x", "confirm_new_password": "x",
        })
        assert resp.status_code == 404


def test_verify_email_page_404s_when_email_disabled():
    client, tmp = build_client_no_email()
    with client, tmp:
        api_register(client, "alice", "alice@example.com", password="Password123!")
        resp = client.get("/verify-email")
        assert resp.status_code == 404


def test_verify_email_confirm_and_resend_404_when_email_disabled():
    client, tmp = build_client_no_email()
    with client, tmp:
        api_register(client, "alice", "alice@example.com", password="Password123!")
        assert client.post("/verify-email/confirm", json={"code": "123456"}).status_code == 404
        assert client.post("/verify-email/resend").status_code == 404


# ── No hints anywhere in the UI ─────────────────────────────────────────

def test_login_page_has_no_forgot_password_link_when_email_disabled():
    client, tmp = build_client_no_email()
    with client, tmp:
        resp = client.get("/login")
        assert "Forgot password?" not in resp.text
        assert "/forgot-password" not in resp.text


def test_register_page_has_no_forgot_password_link_when_email_disabled():
    client, tmp = build_client_no_email()
    with client, tmp:
        resp = client.get("/register")
        assert "/forgot-password" not in resp.text


def test_dashboard_has_no_verify_email_banner_when_email_disabled():
    client, tmp = build_client_no_email()
    with client, tmp:
        api_register(client, "alice", "alice@example.com", password="Password123!")
        client.post("/login", data={
            "username": "alice", "password": "Password123!",
            "csrf_token": client.get("/login").cookies.get("csrf_token") or "x",
        })
        resp = client.get("/dashboard")
        assert "verify your email" not in resp.text.lower()
        assert "/verify-email" not in resp.text


# ── Registration must not attempt to send/generate a code at all ───────

def test_registration_does_not_generate_a_verification_code_when_email_disabled():
    import sqlite3

    client, tmp = build_client_no_email()
    with client, tmp:
        api_register(client, "alice", "alice@example.com", password="Password123!")

        conn = sqlite3.connect(f"{tmp.name}/test.db")
        row = conn.execute(
            "SELECT verification_code, email_verified FROM users WHERE username = ?", ("alice",)
        ).fetchone()
        conn.close()
        assert row[0] is None  # no code generated at all


def test_registration_and_full_app_usage_works_fine_with_email_disabled():
    """The whole point of the toggle: everything else about the app must
    work completely normally with email off."""
    client, tmp = build_client_no_email()
    with client, tmp:
        api_register(client, "alice", "alice@example.com", password="Password123!")
        dashboard = client.get("/dashboard")
        assert dashboard.status_code == 200

        create = client.post("/api/diaries", json={"title": "Entry", "content": "Works fine without email."})
        assert create.status_code in (200, 201)
