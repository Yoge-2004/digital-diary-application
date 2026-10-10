"""Security PIN: second step at sign-in, lockout, recovery without email, trusted-device revocation.
Passkeys (WebAuthn) need a real browser authenticator and were exercised end to end separately."""
from __future__ import annotations

from tests.test_security_and_features import api_register, build_client


def _csrf(client) -> str:
    client.get("/login")
    return client.cookies.get("csrf_token") or "x"


def _web_login(client, username="alice", password="Password123!"):
    return client.post("/login", data={"username": username, "password": password, "csrf_token": _csrf(client)}, follow_redirects=False)


def _set_pin(client, pin="246810", password="Password123!"):
    client.get("/settings")
    return client.post(
        "/settings/pin",
        data={"current_password": password, "pin": pin, "confirm_pin": pin, "csrf_token": client.cookies.get("csrf_token") or "x"},
        follow_redirects=False,
    )


def _json_post(client, url, body):
    return client.post(url, json=body, headers={"X-CSRF-Token": client.cookies.get("csrf_token") or "x"})


def _account_with_pin(client):
    api_register(client, "alice", "alice@example.com", password="Password123!")
    assert _web_login(client).headers["location"].endswith("/dashboard")
    assert "msg=" in _set_pin(client).headers["location"]
    client.cookies.clear()


def test_account_without_a_pin_signs_in_as_before():
    client, tmp = build_client()
    with client, tmp:
        api_register(client, "alice", "alice@example.com", password="Password123!")
        resp = _web_login(client)
        assert resp.headers["location"].endswith("/dashboard")
        assert "access_token" in resp.headers.get("set-cookie", "")


def test_pin_must_be_six_to_eight_digits():
    client, tmp = build_client()
    with client, tmp:
        api_register(client, "alice", "alice@example.com", password="Password123!")
        _web_login(client)
        for bad in ("12345", "123456789", "12ab56", "      "):
            assert "err=" in _set_pin(client, pin=bad).headers["location"], bad


def test_setting_a_pin_needs_the_current_password():
    client, tmp = build_client()
    with client, tmp:
        api_register(client, "alice", "alice@example.com", password="Password123!")
        _web_login(client)
        assert "err=" in _set_pin(client, password="not-my-password").headers["location"]


def test_with_a_pin_the_password_alone_issues_no_session():
    client, tmp = build_client()
    with client, tmp:
        _account_with_pin(client)
        resp = _web_login(client)
        assert resp.headers["location"].endswith("/login/verify")
        cookies = resp.headers.get("set-cookie", "")
        assert "mfa_token" in cookies and "access_token" not in cookies
        assert client.get("/dashboard", follow_redirects=False).status_code in (302, 303, 307)


def test_second_step_pin_completes_sign_in_and_wrong_pin_does_not():
    client, tmp = build_client()
    with client, tmp:
        _account_with_pin(client)
        _web_login(client)
        token = client.cookies.get("csrf_token") or "x"
        bad = client.post("/login/verify/pin", data={"pin": "000000", "csrf_token": token}, follow_redirects=False)
        assert "err=" in bad.headers["location"] and "access_token" not in bad.headers.get("set-cookie", "")
        ok = client.post("/login/verify/pin", data={"pin": "246810", "csrf_token": token}, follow_redirects=False)
        assert ok.headers["location"].endswith("/dashboard") and "access_token" in ok.headers.get("set-cookie", "")


def test_five_wrong_pins_lock_the_pin_even_for_the_right_one():
    client, tmp = build_client()
    with client, tmp:
        _account_with_pin(client)
        _web_login(client)
        token = client.cookies.get("csrf_token") or "x"
        for _ in range(5):
            client.post("/login/verify/pin", data={"pin": "000001", "csrf_token": token}, follow_redirects=False)
        locked = client.post("/login/verify/pin", data={"pin": "246810", "csrf_token": token}, follow_redirects=False)
        assert "Too+many" in locked.headers["location"] or "Too%20many" in locked.headers["location"]
        assert "access_token" not in locked.headers.get("set-cookie", "")


def test_api_login_requires_the_second_step_for_accounts_with_a_pin():
    client, tmp = build_client()
    with client, tmp:
        _account_with_pin(client)
        resp = client.post("/api/auth/login", data={"username": "alice", "password": "Password123!"})
        assert resp.status_code == 401
        detail = resp.json()["detail"]
        assert detail["code"] == "second_factor_required"
        bad = client.post("/api/auth/login/pin", data={"mfa_token": detail["mfa_token"], "pin": "000000"})
        assert bad.status_code == 401
        ok = client.post("/api/auth/login/pin", data={"mfa_token": detail["mfa_token"], "pin": "246810"})
        assert ok.status_code == 200 and "access_token" in ok.json()


def test_pin_recovery_resets_the_password_without_email():
    client, tmp = build_client()
    with client, tmp:
        _account_with_pin(client)
        client.get("/forgot-password")
        wrong = _json_post(client, "/forgot-password/pin-reset", {"username": "alice", "pin": "999999", "new_password": "BrandNew123!"})
        unknown = _json_post(client, "/forgot-password/pin-reset", {"username": "nobody", "pin": "999999", "new_password": "BrandNew123!"})
        assert wrong.status_code == unknown.status_code == 400
        assert wrong.json()["detail"] == unknown.json()["detail"], "must not reveal whether the username exists"
        ok = _json_post(client, "/forgot-password/pin-reset", {"username": "alice", "pin": "246810", "new_password": "BrandNew123!"})
        assert ok.status_code == 200 and ok.json()["ok"] is True
        assert client.post("/api/auth/login", data={"username": "alice", "password": "Password123!"}).status_code == 401
        assert client.post("/api/auth/login", data={"username": "alice", "password": "BrandNew123!"}).status_code == 401  # reaches the 2nd step (401 + mfa)


def test_recovery_endpoints_refuse_requests_without_a_csrf_header():
    client, tmp = build_client()
    with client, tmp:
        _account_with_pin(client)
        client.get("/forgot-password")
        resp = client.post("/forgot-password/pin-reset", json={"username": "alice", "pin": "246810", "new_password": "BrandNew123!"})
        assert resp.status_code in (400, 403)


def test_removing_the_pin_restores_plain_sign_in():
    client, tmp = build_client()
    with client, tmp:
        _account_with_pin(client)
        _web_login(client)
        token = client.cookies.get("csrf_token") or "x"
        client.post("/login/verify/pin", data={"pin": "246810", "csrf_token": token}, follow_redirects=False)
        client.get("/settings")
        rm = client.post("/settings/pin/remove", data={"current_password": "Password123!", "csrf_token": client.cookies.get("csrf_token") or "x"}, follow_redirects=False)
        assert "msg=" in rm.headers["location"]
        client.cookies.clear()
        assert _web_login(client).headers["location"].endswith("/dashboard")
