"""
utils/scheduler.py
Background APScheduler that fires daily summary emails.
Starts automatically when the Streamlit app loads.
"""

import logging
import threading
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config.settings import settings

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_lock = threading.Lock()


def _run_summaries():
    """Wrapper so import errors surface cleanly."""
    try:
        from services.email_service import send_department_summaries
        logger.info("Scheduler: running daily department summaries (%s)", datetime.utcnow())
        results = send_department_summaries()
        logger.info("Scheduler: summary results — %s", results)
    except Exception as exc:
        logger.error("Scheduler job failed: %s", exc, exc_info=True)


def start_scheduler():
    """Start the background scheduler (idempotent)."""
    global _scheduler
    with _lock:
        if _scheduler is not None and _scheduler.running:
            return

        _scheduler = BackgroundScheduler(timezone="UTC")
        _scheduler.add_job(
            _run_summaries,
            trigger=CronTrigger(
                hour=settings.email.summary_hour,
                minute=settings.email.summary_minute,
            ),
            id="daily_summary",
            name="Daily Department Email Summary",
            replace_existing=True,
        )
        _scheduler.start()
        logger.info(
            "Scheduler started — daily summary at %02d:%02d UTC",
            settings.email.summary_hour,
            settings.email.summary_minute,
        )


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")


def trigger_now() -> dict:
    """Manually trigger the summary job (used from the admin page)."""
    from services.email_service import send_department_summaries
    return send_department_summaries()
