"""
Background scheduler.

Runs as an APScheduler BackgroundScheduler inside the same process as the
API server (or the desktop UI, when the UI embeds the API — see run_jarvis.py).
Responsibilities:
  * Fire due reminders as desktop notifications.
  * Flip PENDING tasks that passed their due date to OVERDUE.
  * Run the proactive-intelligence sweep (deadline warnings, overdue
    summary, schedule conflicts, unfinished-task follow-ups).
  * Re-index knowledge files that changed on disk (delegates to app.files.watcher).

Any exception inside a job is caught and logged so one bad job never stops
the scheduler (spec section 22).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.logging_config import get_logger
from app.database.db import session_scope
from app.database import models
from app.tasks import crud as task_crud
from app.calendar import crud as calendar_crud
from app.notifications.notifier import send_notification, build_reminder_message

logger = get_logger("jarvis.scheduler")

_scheduler: BackgroundScheduler | None = None


def _safe_job(name: str):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            try:
                fn(*args, **kwargs)
            except Exception:
                logger.exception("Scheduled job '%s' failed", name)
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator


@_safe_job("fire_due_reminders")
def fire_due_reminders() -> None:
    now = datetime.now()
    with session_scope() as db:
        due = (
            db.query(models.Reminder)
            .filter(models.Reminder.remind_at <= now, models.Reminder.fired.is_(False))
            .all()
        )
        for reminder in due:
            task = reminder.task
            title = task.title if task else "Task reminder"
            send_notification("JARVIS", reminder.message or f"Reminder: {title}")
            reminder.fired = True
        if due:
            logger.info("Fired %d reminder(s)", len(due))


@_safe_job("mark_overdue")
def mark_overdue() -> None:
    with session_scope() as db:
        count = task_crud.mark_overdue_tasks(db)
        if count:
            logger.info("Marked %d task(s) overdue", count)


@_safe_job("proactive_sweep")
def proactive_sweep() -> None:
    """
    Implements spec section 14 (Proactive Intelligence):
      - deadline warnings (<=48h out)
      - overdue summary
      - same-day schedule conflicts
    Notifications are de-duplicated per run only (a fuller implementation
    would track 'already warned' state in the DB — noted as a limitation
    in the README).
    """
    now = datetime.now()
    with session_scope() as db:
        soon = task_crud.get_upcoming_deadlines(db, days=2)
        for task in soon:
            hours_left = (task.due_date - now).total_seconds() / 3600
            if 0 < hours_left <= 48:
                send_notification(
                    "JARVIS — Deadline approaching",
                    f"'{task.title}' is due in about {int(hours_left)} hour(s).",
                )

        overdue = task_crud.get_overdue_tasks(db)
        if overdue:
            send_notification(
                "JARVIS — Overdue tasks",
                f"You have {len(overdue)} overdue task(s). Say 'what's overdue' for details.",
            )

        conflicts = calendar_crud.find_schedule_conflicts(db, now)
        if conflicts:
            send_notification(
                "JARVIS — Schedule conflict",
                f"You have {len(conflicts)} overlapping event(s) today.",
            )


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(fire_due_reminders, "interval", minutes=1, id="fire_due_reminders")
    _scheduler.add_job(mark_overdue, "interval", minutes=5, id="mark_overdue")
    _scheduler.add_job(proactive_sweep, "interval", minutes=30, id="proactive_sweep")

    # Import here to avoid a circular import at module load time
    from app.files.watcher import scan_knowledge_folder
    _scheduler.add_job(
        _safe_job("scan_knowledge_folder")(scan_knowledge_folder),
        "interval", minutes=2, id="scan_knowledge_folder",
    )

    _scheduler.start()
    logger.info("Scheduler started with jobs: %s", [j.id for j in _scheduler.get_jobs()])
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
