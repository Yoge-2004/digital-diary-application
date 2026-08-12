from __future__ import annotations

import sqlite3

from tests.test_security_and_features import build_client, api_register


def _get_verification_code(tmp, username="alice"):
    conn = sqlite3.connect(f"{tmp.name}/test.db")
    row = conn.execute("SELECT verification_code FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return row[0] if row else None


def _get_email_verified(tmp, username="alice"):
    conn = sqlite3.connect(f"{tmp.name}/test.db")
    row = conn.execute("SELECT email_verified FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return bool(row[0]) if row else None


def test_registration_sends_a_verification_code_and_account_starts_unverified():
    client, tmp = build_client()
    with client, tmp:
        api_register(client, "alice", "alice@example.com", password="Password123!")
        assert _get_email_verified(tmp) is False
        code = _get_verification_code(tmp)
        assert code and len(code) == 6 and code.isdigit()


def test_unverified_account_is_never_blocked_from_using_the_app():
    """The reminder is purely informational -- an unverified account must
    be able to use every feature, not just log in."""
    client, tmp = build_client()
    with client, tmp:
        api_register(client, "alice", "alice@example.com", password="Password123!")
        assert _get_email_verified(tmp) is False

        dashboard = client.get("/dashboard")
        assert dashboard.status_code == 200

        create = client.post("/api/diaries", json={
            "title": "First entry", "content": "Still works even though I haven't verified my email.",
        })
        assert create.status_code in (200, 201)


def test_verify_email_with_correct_code_succeeds():
    client, tmp = build_client()
    with client, tmp:
        api_register(client, "alice", "alice@example.com", password="Password123!")
        code = _get_verification_code(tmp)

        resp = client.post("/verify-email/confirm", json={"code": code})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert _get_email_verified(tmp) is True

        # The code is now cleared/single-use.
        assert _get_verification_code(tmp) is None


def test_verify_email_with_wrong_code_fails():
    client, tmp = build_client()
    with client, tmp:
        api_register(client, "alice", "alice@example.com", password="Password123!")

        resp = client.post("/verify-email/confirm", json={"code": "000000"})
        assert resp.status_code == 400
        assert _get_email_verified(tmp) is False


def test_verify_email_requires_login():
    client, tmp = build_client()
    with client, tmp:
        resp = client.post("/verify-email/confirm", json={"code": "123456"})
        assert resp.status_code == 401


def test_resend_verification_code_issues_a_new_code():
    client, tmp = build_client()
    with client, tmp:
        api_register(client, "alice", "alice@example.com", password="Password123!")
        first_code = _get_verification_code(tmp)

        resp = client.post("/verify-email/resend")
        assert resp.status_code == 200
        second_code = _get_verification_code(tmp)

        assert second_code is not None
        # Old code should no longer work even though a new one was issued.
        stale = client.post("/verify-email/confirm", json={"code": first_code})
        # (Extremely unlikely, but if the two codes randomly collided this
        # assertion would be wrong -- guard against that flake.)
        if first_code != second_code:
            assert stale.status_code == 400


def test_verify_email_page_redirects_already_verified_users():
    client, tmp = build_client()
    with client, tmp:
        api_register(client, "alice", "alice@example.com", password="Password123!")
        code = _get_verification_code(tmp)
        client.post("/verify-email/confirm", json={"code": code})

        resp = client.get("/verify-email", follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"].startswith("/dashboard")
