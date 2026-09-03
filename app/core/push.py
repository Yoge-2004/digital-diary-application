"""Web Push delivery for the daily "write today" reminder.

Mirrors core/email.py's shape deliberately: a single send_push_notification()
entry point that the rest of the app calls without needing to know
anything about pywebpush, VAPID, or the wire format, and that raises on
real failures instead of swallowing them (see routers/web.py and
routers/api.py for the "log, don't swallow silently" pattern applied
around every call site that sends something to a user).
"""
from __future__ import annotations

import json
import logging

from pywebpush import WebPushException, webpush

from app.core.config import Settings

logger = logging.getLogger("app.push")


class PushSubscriptionGone(Exception):
    """Raised when the push service reports this subscription no longer
    exists (410 Gone) or was never valid (404) -- the caller should
    delete the PushSubscription row rather than retry. This is a normal,
    expected outcome (the user uninstalled the browser, cleared site
    data, the OS revoked it, etc.), not an error to log loudly."""


def send_push_notification(
    settings: Settings,
    subscription_info: dict,
    title: str,
    body: str,
    url: str = "/dashboard",
) -> None:
    """Send one Web Push message to one subscription.

    subscription_info is the {endpoint, keys: {p256dh, auth}} shape the
    browser's PushManager.subscribe() produces and the frontend posts to
    /api/push/subscribe verbatim -- reassembled from the PushSubscription
    row's three columns by the caller (see services.send_reminder_push).
    """
    if not settings.push_notifications_enabled:
        raise RuntimeError(
            "send_push_notification called but push_notifications_enabled is False "
            "-- VAPID keys aren't configured. Callers must check this first."
        )

    payload = json.dumps({"title": title, "body": body, "url": url})

    try:
        webpush(
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_claims_sub},
        )
    except WebPushException as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in (404, 410):
            raise PushSubscriptionGone(str(exc)) from exc
        logger.exception("Web Push delivery failed (status=%s)", status)
        raise
