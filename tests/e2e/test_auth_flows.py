"""Registration, login, logout, and the two conditional-UI features that
have caused confusion in this codebase before: the Google OAuth button
(gated on GOOGLE_CLIENT_ID/SECRET) and the "Forgot password?" link
(gated on SMTP being configured)."""
from __future__ import annotations

import uuid

from conftest import login_via_ui, register_via_ui


def _uniq(prefix: str) -> tuple[str, str]:
    tag = uuid.uuid4().hex[:10]
    return f"{prefix}{tag}", f"{prefix}{tag}@example.com"


def test_register_then_redirected_to_dashboard(page, live_server):
    username, email = _uniq("newuser")
    register_via_ui(page, live_server, username, email)
    assert page.url == f"{live_server}/dashboard"
    assert page.locator(".page-title, h1").first.is_visible()


def test_register_password_mismatch_blocked(page, live_server):
    username, email = _uniq("mismatch")
    page.goto(f"{live_server}/register")
    page.fill("#reg-username", username)
    page.fill("#reg-email", email)
    page.fill("#reg-password", "password123")
    page.fill("#reg-confirm", "differentpassword")
    page.click("#registerForm button[type=submit]")
    # Should NOT reach the dashboard
    page.wait_for_timeout(500)
    assert "/dashboard" not in page.url


def test_login_with_valid_credentials(page, live_server):
    username, email = _uniq("loginok")
    register_via_ui(page, live_server, username, email)
    page.click('button:has-text("Sign out")')
    page.wait_for_timeout(500)
    login_via_ui(page, live_server, username)
    assert page.url == f"{live_server}/dashboard"


def test_login_with_wrong_password_shows_error(page, live_server):
    username, email = _uniq("wrongpw")
    register_via_ui(page, live_server, username, email)
    page.click('button:has-text("Sign out")')
    page.wait_for_timeout(500)
    page.goto(f"{live_server}/login")
    page.fill("#login-username", username)
    page.fill("#login-password", "totally-wrong-password")
    page.click("#loginForm button[type=submit]")
    page.wait_for_timeout(500)
    assert "/dashboard" not in page.url


def test_oauth_button_hidden_when_not_configured(page, live_server):
    # live_server defaults to no google_client_id/secret
    page.goto(f"{live_server}/login")
    assert page.locator('a[href="/auth/google/login"]').count() == 0
    page.goto(f"{live_server}/register")
    assert page.locator('a[href="/auth/google/login"]').count() == 0


def test_oauth_button_shown_when_configured(page, live_server_factory):
    url = live_server_factory(google_client_id="test-client-id", google_client_secret="test-client-secret")
    page.goto(f"{url}/login")
    btn = page.locator('a[href="/auth/google/login"]')
    assert btn.count() == 1
    assert btn.is_visible()
    assert "Google" in btn.inner_text()


def test_forgot_password_link_hidden_without_smtp(page, live_server):
    page.goto(f"{live_server}/login")
    assert page.locator('a[href="/forgot-password"]').count() == 0
    # And the route itself should 404, not just be unlinked
    resp = page.request.get(f"{live_server}/forgot-password")
    assert resp.status == 404


def test_forgot_password_link_shown_with_smtp_configured(page, live_server_factory):
    url = live_server_factory(smtp_host="smtp.example.invalid", smtp_from="diary@example.invalid")
    page.goto(f"{url}/login")
    link = page.locator('a[href="/forgot-password"]')
    assert link.count() == 1
    link.click()
    page.wait_for_url(f"{url}/forgot-password")
    assert page.locator("form").first.is_visible()


def test_verify_email_banner_hidden_without_smtp(page, live_server):
    username, email = _uniq("nobanner")
    register_via_ui(page, live_server, username, email)
    assert page.locator("text=Verify now").count() == 0


def test_verify_email_banner_shown_with_smtp_configured(page, live_server_factory):
    url = live_server_factory(smtp_host="smtp.example.invalid", smtp_from="diary@example.invalid")
    username, email = _uniq("banner")
    register_via_ui(page, url, username, email)
    assert page.locator("text=Verify now").first.is_visible()
