"""Background loop that fires each user's daily "write today" reminder
at their own local time.

There's no cron/task-queue infrastructure in this project (see README/
handoff notes on the same theme as patch_missing_columns' docstring:
this is a small app, not a distributed system) -- a single in-process
asyncio loop, started from the FastAPI lifespan and checking once a
minute, is proportionate. It would need to become a real scheduled job
(Celery beat, APScheduler with a persistent job store, a cron hitting an
endpoint, etc.) the moment this app ever runs as more than one process,
since every process would otherwise fire the same users' reminders
independently.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import sessionmaker

from app import repositories, services
from app.core.config import Settings

logger = logging.getLogger("app.scheduler")

CHECK_INTERVAL_SECONDS = 60


async def _run_one_check(app_settings: Settings, session_factory: sessionmaker) -> None:
    db = session_factory()
    try:
        for user in repositories.list_users_with_reminders_enabled(db):
            try:
                tz = ZoneInfo(user.reminder_timezone) if user.reminder_timezone else None
            except ZoneInfoNotFoundError:
                logger.warning("User %s has an unrecognized reminder_timezone %r, skipping", user.id, user.reminder_timezone)
                continue
            if tz is None:
                continue

            now_local = datetime.now(tz)
            local_hhmm = now_local.strftime("%H:%M")
            local_date = now_local.strftime("%Y-%m-%d")

            if local_hhmm != user.reminder_time:
                continue
            if user.last_reminder_sent_on == local_date:
                continue  # already sent today -- the loop sees this same due minute at most a few times

            sent = services.send_reminder_push(app_settings, db, user)
            user.last_reminder_sent_on = local_date
            db.commit()
            logger.info("Sent daily reminder to user %s (%d device(s))", user.id, sent)
    finally:
        db.close()


async def run_reminder_scheduler(app_settings: Settings, session_factory: sessionmaker) -> None:
    """Runs until cancelled. Call as an asyncio.Task from the app's
    lifespan; cancel it on shutdown (see app/main.py)."""
    if not app_settings.push_notifications_enabled:
        logger.info("Push notifications not configured (no VAPID keys) -- reminder scheduler not starting")
        return

    logger.info("Reminder scheduler started (checking every %ds)", CHECK_INTERVAL_SECONDS)
    try:
        while True:
            try:
                await _run_one_check(app_settings, session_factory)
            except Exception:
                # A bad check this minute (DB hiccup, etc.) shouldn't
                # permanently kill the loop -- try again next minute.
                logger.exception("Reminder scheduler check failed")
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        logger.info("Reminder scheduler stopped")
        raise
