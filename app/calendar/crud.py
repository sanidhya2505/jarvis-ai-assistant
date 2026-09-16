from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.database.models import CalendarEvent


def create_event(
    db: Session, title: str, start_time: datetime,
    end_time: Optional[datetime] = None, description: str = "",
    all_day: bool = False, task_id: Optional[str] = None,
) -> CalendarEvent:
    event = CalendarEvent(
        title=title, start_time=start_time, end_time=end_time,
        description=description, all_day=all_day, task_id=task_id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_events_in_range(db: Session, start: datetime, end: datetime) -> list[CalendarEvent]:
    return (
        db.query(CalendarEvent)
        .filter(CalendarEvent.start_time >= start, CalendarEvent.start_time < end)
        .order_by(CalendarEvent.start_time.asc())
        .all()
    )


def get_day_view(db: Session, day: datetime) -> list[CalendarEvent]:
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    return get_events_in_range(db, start, start + timedelta(days=1))


def get_week_view(db: Session, any_day_in_week: datetime) -> list[CalendarEvent]:
    start = any_day_in_week - timedelta(days=any_day_in_week.weekday())
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    return get_events_in_range(db, start, start + timedelta(days=7))


def get_month_view(db: Session, any_day_in_month: datetime) -> list[CalendarEvent]:
    start = any_day_in_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return get_events_in_range(db, start, end)


def find_schedule_conflicts(db: Session, day: datetime) -> list[tuple[CalendarEvent, CalendarEvent]]:
    """Flag overlapping events on the same day (spec: 'schedule conflict' proactive alert)."""
    events = sorted(get_day_view(db, day), key=lambda e: e.start_time)
    conflicts = []
    for i in range(len(events) - 1):
        a, b = events[i], events[i + 1]
        a_end = a.end_time or a.start_time
        if b.start_time < a_end:
            conflicts.append((a, b))
    return conflicts
