from __future__ import annotations

import tempfile
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from pywebpush import WebPushException

from app.core.config import Settings
from app.main import create_app
from tests.test_security_and_features import api_register, web_csrf


VALID_VAPID_PUBLIC = "BCGCn-yeILV0uhDO8aZnbcxUm6NUWsz0wM_bYhnaE8R1XSFPovf-94ksfCVfuJGgtGKj0o1FanNT9eg_CYxuDgU"
VALID_VAPID_PRIVATE = "ixTDQ6Ph0wSAp7t4kkegB9bhvg45y2nQiK0kB2wk5dk"


def build_client_with_push():
    tmp = tempfile.TemporaryDirectory()
    settings = Settings(
        database_url=f"sqlite:///{tmp.name}/test.db",
        secret_key="dev-secret-key-with-32-chars-minimum!!",
        vapid_public_key=VALID_VAPID_PUBLIC,
        vapid_private_key=VALID_VAPID_PRIVATE,
    )
    app = create_app(settings)
    return TestClient(app), tmp


def build_client_no_push():
    tmp = tempfile.TemporaryDirectory()
    settings = Settings(
        database_url=f"sqlite:///{tmp.name}/test.db",
        secret_key="dev-secret-key-with-32-chars-minimum!!",
    )
    app = create_app(settings)
    return TestClient(app), tmp


# ── Config toggle (mirrors test_email_service_toggle.py's pattern) ──

def test_push_notifications_disabled_by_default():
    settings = Settings(database_url="sqlite:///:memory:", secret_key="x" * 32)
    assert settings.push_notifications_enabled is False


def test_push_notifications_enabled_when_both_vapid_keys_set():
    settings = Settings(
        database_url="sqlite:///:memory:",
        secret_key="x" * 32,
        vapid_public_key=VALID_VAPID_PUBLIC,
        vapid_private_key=VALID_VAPID_PRIVATE,
    )
    assert settings.push_notifications_enabled is True


def test_push_notifications_disabled_if_only_one_key_set():
    settings = Settings(
        database_url="sqlite:///:memory:",
        secret_key="x" * 32,
        vapid_public_key=VALID_VAPID_PUBLIC,
        vapid_private_key="",
    )
    assert settings.push_notifications_enabled is False


# ── UI gating ──

def test_notifications_tab_hidden_when_push_not_configured():
    client, tmp = build_client_no_push()
    api_register(client, "pushoff", "pushoff@example.com")
    resp = client.get("/settings")
    assert "reminderToggle" not in resp.text
    tmp.cleanup()


def test_notifications_tab_shown_when_push_configured():
    client, tmp = build_client_with_push()
    api_register(client, "pushon", "pushon@example.com")
    resp = client.get("/settings")
    assert "reminderToggle" in resp.text
    assert VALID_VAPID_PUBLIC in resp.text
    tmp.cleanup()


# ── /settings/notifications validation ──

def test_settings_notifications_404s_when_push_not_configured():
    client, tmp = build_client_no_push()
    api_register(client, "pushoff2", "pushoff2@example.com")
    csrf = web_csrf(client, "/settings")
    resp = client.post(
        "/settings/notifications",
        data={"csrf_token": csrf, "reminder_enabled": "true", "reminder_time": "20:00", "reminder_timezone": "UTC"},
    )
    assert resp.status_code == 404
    tmp.cleanup()


def test_settings_notifications_rejects_bad_time_format():
    client, tmp = build_client_with_push()
    api_register(client, "badtime", "badtime@example.com")
    csrf = web_csrf(client, "/settings")
    resp = client.post(
        "/settings/notifications",
        data={"csrf_token": csrf, "reminder_enabled": "true", "reminder_time": "8pm", "reminder_timezone": "UTC"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert "err=" in resp.headers["location"]
    tmp.cleanup()


def test_settings_notifications_rejects_bad_timezone():
    client, tmp = build_client_with_push()
    api_register(client, "badtz", "badtz@example.com")
    csrf = web_csrf(client, "/settings")
    resp = client.post(
        "/settings/notifications",
        data={"csrf_token": csrf, "reminder_enabled": "true", "reminder_time": "20:00", "reminder_timezone": "Mars/Nowhere"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert "err=" in resp.headers["location"]
    tmp.cleanup()


def test_settings_notifications_saves_valid_preferences():
    client, tmp = build_client_with_push()
    api_register(client, "goodprefs", "goodprefs@example.com")
    csrf = web_csrf(client, "/settings")
    resp = client.post(
        "/settings/notifications",
        data={"csrf_token": csrf, "reminder_enabled": "true", "reminder_time": "07:30", "reminder_timezone": "America/Chicago"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert "err=" not in resp.headers["location"]

    settings_page = client.get("/settings")
    assert 'value="07:30"' in settings_page.text
    tmp.cleanup()


def test_settings_notifications_disable_does_not_require_time_or_timezone():
    client, tmp = build_client_with_push()
    api_register(client, "turnoff", "turnoff@example.com")
    csrf = web_csrf(client, "/settings")
    resp = client.post(
        "/settings/notifications",
        data={"csrf_token": csrf, "reminder_enabled": "false"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert "err=" not in resp.headers["location"]
    tmp.cleanup()


# ── /api/push/subscribe + unsubscribe ──

def test_push_subscribe_404s_when_not_configured():
    client, tmp = build_client_no_push()
    api_register(client, "subnoconf", "subnoconf@example.com")
    resp = client.post("/api/push/subscribe", json={"endpoint": "https://example.com/ep", "keys": {"p256dh": "a", "auth": "b"}})
    assert resp.status_code == 404
    tmp.cleanup()


def test_push_subscribe_rejects_malformed_payload():
    client, tmp = build_client_with_push()
    api_register(client, "submalformed", "submalformed@example.com")
    resp = client.post("/api/push/subscribe", json={"endpoint": "https://example.com/ep"})  # missing keys
    assert resp.status_code == 400
    tmp.cleanup()


def test_push_subscribe_and_unsubscribe_round_trip():
    client, tmp = build_client_with_push()
    api_register(client, "roundtrip", "roundtrip@example.com")
    sub_payload = {"endpoint": "https://fcm.example.com/abc123", "keys": {"p256dh": "somekey", "auth": "someauth"}}
    resp = client.post("/api/push/subscribe", json=sub_payload)
    assert resp.status_code == 200, resp.text

    resp2 = client.post("/api/push/subscribe", json=sub_payload)
    assert resp2.status_code == 200  # re-subscribing the same endpoint updates, doesn't error

    resp3 = client.post("/api/push/unsubscribe", json={"endpoint": sub_payload["endpoint"]})
    assert resp3.status_code == 200
    tmp.cleanup()


def test_push_subscribe_requires_auth():
    client, tmp = build_client_with_push()
    resp = client.post("/api/push/subscribe", json={"endpoint": "https://example.com/ep", "keys": {"p256dh": "a", "auth": "b"}})
    assert resp.status_code in (401, 403)
    tmp.cleanup()


# ── send_reminder_push: failure handling ──

def test_send_reminder_push_deletes_subscription_on_410_gone():
    from app import repositories, services

    client, tmp = build_client_with_push()
    api_register(client, "gonesub", "gonesub@example.com")
    client.post("/api/push/subscribe", json={"endpoint": "https://fcm.example.com/gone", "keys": {"p256dh": "a", "auth": "b"}})

    db_sessionmaker = client.app.state.db_sessionmaker
    db = db_sessionmaker()
    try:
        user = repositories.get_user_by_email(db, "gonesub@example.com")
        assert len(repositories.list_push_subscriptions(db, user.id)) == 1

        fake_response = MagicMock(status_code=410)
        with patch("app.core.push.webpush", side_effect=WebPushException("gone", response=fake_response)):
            sent = services.send_reminder_push(client.app.state.settings, db, user)

        assert sent == 0
        assert len(repositories.list_push_subscriptions(db, user.id)) == 0
    finally:
        db.close()
    tmp.cleanup()


def test_send_reminder_push_continues_after_one_subscription_fails():
    from app import repositories, services

    client, tmp = build_client_with_push()
    api_register(client, "twosubs", "twosubs@example.com")
    client.post("/api/push/subscribe", json={"endpoint": "https://fcm.example.com/one", "keys": {"p256dh": "a", "auth": "b"}})
    client.post("/api/push/subscribe", json={"endpoint": "https://fcm.example.com/two", "keys": {"p256dh": "c", "auth": "d"}})

    db_sessionmaker = client.app.state.db_sessionmaker
    db = db_sessionmaker()
    try:
        user = repositories.get_user_by_email(db, "twosubs@example.com")
        assert len(repositories.list_push_subscriptions(db, user.id)) == 2

        call_count = {"n": 0}

        def flaky_webpush(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("simulated transient failure")
            return None

        with patch("app.core.push.webpush", side_effect=flaky_webpush):
            sent = services.send_reminder_push(client.app.state.settings, db, user)

        assert sent == 1  # one succeeded, one failed
        assert len(repositories.list_push_subscriptions(db, user.id)) == 2  # neither deleted -- not a 410
    finally:
        db.close()
    tmp.cleanup()


# ── Scheduler: who's actually due right now ──

def test_scheduler_sends_only_to_users_due_at_current_local_time():
    import asyncio
    from app import repositories
    from app.core.scheduler import _run_one_check

    client, tmp = build_client_with_push()
    api_register(client, "duenow", "duenow@example.com")
    api_register(client, "duelater", "duelater@example.com")
    client.post("/api/push/subscribe", json={"endpoint": "https://fcm.example.com/due", "keys": {"p256dh": "a", "auth": "b"}})

    db_sessionmaker = client.app.state.db_sessionmaker
    db = db_sessionmaker()
    try:
        user_due = repositories.get_user_by_email(db, "duenow@example.com")
        user_not_due = repositories.get_user_by_email(db, "duelater@example.com")

        now_utc = datetime.now(ZoneInfo("UTC"))
        user_due.reminder_enabled = True
        user_due.reminder_time = now_utc.strftime("%H:%M")
        user_due.reminder_timezone = "UTC"

        user_not_due.reminder_enabled = True
        # A time guaranteed not to be "now" in UTC right now.
        not_due_hour = (now_utc.hour + 6) % 24
        user_not_due.reminder_time = f"{not_due_hour:02d}:00"
        user_not_due.reminder_timezone = "UTC"
        db.commit()

        with patch("app.services.send_reminder_push", return_value=1) as mock_send:
            asyncio.run(_run_one_check(client.app.state.settings, db_sessionmaker))

        sent_to_user_ids = [call.args[2].id for call in mock_send.call_args_list]
        assert user_due.id in sent_to_user_ids
        assert user_not_due.id not in sent_to_user_ids
    finally:
        db.close()
    tmp.cleanup()


def test_scheduler_does_not_double_send_same_day():
    import asyncio
    from app import repositories
    from app.core.scheduler import _run_one_check

    client, tmp = build_client_with_push()
    api_register(client, "alreadysent", "alreadysent@example.com")

    db_sessionmaker = client.app.state.db_sessionmaker
    db = db_sessionmaker()
    try:
        user = repositories.get_user_by_email(db, "alreadysent@example.com")
        now_utc = datetime.now(ZoneInfo("UTC"))
        user.reminder_enabled = True
        user.reminder_time = now_utc.strftime("%H:%M")
        user.reminder_timezone = "UTC"
        user.last_reminder_sent_on = now_utc.strftime("%Y-%m-%d")  # already sent today
        db.commit()

        with patch("app.services.send_reminder_push", return_value=1) as mock_send:
            asyncio.run(_run_one_check(client.app.state.settings, db_sessionmaker))

        mock_send.assert_not_called()
    finally:
        db.close()
    tmp.cleanup()
