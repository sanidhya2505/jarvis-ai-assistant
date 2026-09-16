"""
Notification system.

Uses `plyer` for cross-platform desktop notifications (backed by
win10toast / Windows Runtime toasts on Windows). If notifications fail for
any reason (headless environment, missing DLLs, etc.) we log the failure
and continue — per spec section 22, one failed component must never crash
the assistant.
"""
from __future__ import annotations

from app.core.logging_config import get_logger

logger = get_logger("jarvis.notifications")

try:
    from plyer import notification as _plyer_notification
    _PLYER_AVAILABLE = True
except Exception:  # pragma: no cover - environment dependent
    _PLYER_AVAILABLE = False


def send_notification(title: str, message: str, timeout: int = 10) -> bool:
    """
    Sends a desktop notification. Returns True on success, False if it
    failed (caller should not treat False as fatal).
    """
    if not _PLYER_AVAILABLE:
        logger.warning("Notification backend unavailable — skipped: %s | %s", title, message)
        return False
    try:
        _plyer_notification.notify(
            title=title,
            message=message,
            app_name="JARVIS",
            timeout=timeout,
        )
        return True
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.error("Failed to send notification '%s': %s", title, exc)
        return False


REMINDER_PRESETS_MINUTES = [5, 15, 30, 60]


def build_reminder_message(task_title: str, minutes_before: int) -> str:
    if minutes_before >= 60:
        hours = minutes_before // 60
        unit = "hour" if hours == 1 else "hours"
        return f"'{task_title}' starts in {hours} {unit}."
    return f"'{task_title}' starts in {minutes_before} minutes."
