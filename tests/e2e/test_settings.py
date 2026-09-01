"""Settings: profile update, password change, appearance toggle, and the
delete-account type-to-confirm modal (this is the feature that started
this suite — see the modal implementation in app.js/app.css)."""
from __future__ import annotations

import uuid

from conftest import register_via_api


def _uniq(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def _login(page, base_url: str, prefix: str) -> tuple[str, str]:
    username = _uniq(prefix)
    email = f"{username}@example.com"
    register_via_api(page, base_url, username, email)
    page.goto(f"{base_url}/dashboard")
    page.wait_for_url(f"{base_url}/dashboard", timeout=10_000)
    return username, email


def test_profile_update_persists(page, live_server):
    _login(page, live_server, "profile")
    page.goto(f"{live_server}/settings")
    new_email = f"{_uniq('updated')}@example.com"
    page.fill("#set-email", new_email)
    page.click("#profileForm button[type=submit]")
    page.wait_for_timeout(800)
    page.goto(f"{live_server}/settings")
    assert page.locator("#set-email").input_value() == new_email


def test_password_change_then_relogin_with_new_password(page, live_server):
    username, _ = _login(page, live_server, "pwchange")
    page.goto(f"{live_server}/settings")
    page.click('.settings-tab[data-panel="password"]')
    page.fill("#cur-pw", "password123")
    page.fill("#new-pw", "newpassword456")
    page.fill("#confirm-new-pw", "newpassword456")
    page.click("#passwordForm button[type=submit]")
    page.wait_for_timeout(800)

    page.click('button:has-text("Sign out")')
    page.wait_for_timeout(500)
    page.goto(f"{live_server}/login")
    page.fill("#login-username", username)
    page.fill("#login-password", "newpassword456")
    page.click("#loginForm button[type=submit]")
    page.wait_for_url(f"{live_server}/dashboard", timeout=10_000)


# ── Delete-account type-to-confirm modal ──

def test_delete_account_button_opens_modal_not_native_confirm(page, live_server):
    _login(page, live_server, "modalopen")
    page.goto(f"{live_server}/settings")
    page.click('.settings-tab[data-panel="danger"]')
    fired = {"native_confirm": False}
    page.on("dialog", lambda d: (fired.__setitem__("native_confirm", True), d.dismiss()))
    page.click("#openDeleteAccountModal")
    page.wait_for_timeout(300)
    assert page.locator("#deleteAccountOverlay.open").is_visible()
    assert fired["native_confirm"] is False


def test_delete_account_confirm_button_disabled_until_exact_match(page, live_server):
    _login(page, live_server, "modalmatch")
    page.goto(f"{live_server}/settings")
    page.click('.settings-tab[data-panel="danger"]')
    page.click("#openDeleteAccountModal")
    confirm_btn = page.locator("#confirmDeleteAccount")
    assert confirm_btn.is_disabled()

    page.fill("#deleteAccountConfirmInput", "delete")  # wrong case
    assert confirm_btn.is_disabled()

    page.fill("#deleteAccountConfirmInput", "DELET")  # incomplete
    assert confirm_btn.is_disabled()

    page.fill("#deleteAccountConfirmInput", "DELETE")
    assert confirm_btn.is_enabled()


def test_delete_account_cancel_does_not_delete(page, live_server):
    username, _ = _login(page, live_server, "modalcancel")
    page.goto(f"{live_server}/settings")
    page.click('.settings-tab[data-panel="danger"]')
    page.click("#openDeleteAccountModal")
    page.fill("#deleteAccountConfirmInput", "DELETE")
    page.click("#cancelDeleteAccount")
    page.wait_for_timeout(300)
    assert not page.locator("#deleteAccountOverlay").is_visible()

    # Account should still exist and still be logged in
    page.goto(f"{live_server}/dashboard")
    assert page.url == f"{live_server}/dashboard"


def test_delete_account_escape_key_closes_modal(page, live_server):
    _login(page, live_server, "modalescape")
    page.goto(f"{live_server}/settings")
    page.click('.settings-tab[data-panel="danger"]')
    page.click("#openDeleteAccountModal")
    assert page.locator("#deleteAccountOverlay.open").is_visible()
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert not page.locator("#deleteAccountOverlay").is_visible()


def test_delete_account_full_flow_actually_deletes(page, live_server):
    username, _ = _login(page, live_server, "modaldelete")
    page.goto(f"{live_server}/settings")
    page.click('.settings-tab[data-panel="danger"]')
    page.click("#openDeleteAccountModal")
    page.fill("#deleteAccountConfirmInput", "DELETE")
    page.click("#confirmDeleteAccount")
    page.wait_for_url(lambda url: "/settings" not in url, timeout=10_000)

    # The account is gone: logging in with the old credentials must fail
    page.goto(f"{live_server}/login")
    page.fill("#login-username", username)
    page.fill("#login-password", "password123")
    page.click("#loginForm button[type=submit]")
    page.wait_for_timeout(800)
    assert "/dashboard" not in page.url
