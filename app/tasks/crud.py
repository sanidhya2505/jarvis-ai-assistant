from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.database.models import (
    Task, TaskStatus, TaskPriority, Reminder, KnowledgeFile, ActivityLog
)
from app.tasks.schemas import TaskCreate, TaskUpdate
from app.config.settings import get_settings

settings = get_settings()


def log_activity(db: Session, activity_type: str, description: str,
                  task_id: Optional[str] = None, file_id: Optional[str] = None) -> None:
    db.add(ActivityLog(
        activity_type=activity_type,
        description=description,
        related_task_id=task_id,
        related_file_id=file_id,
    ))
    db.commit()


def create_task(db: Session, data: TaskCreate) -> Task:
    task = Task(
        title=data.title,
        description=data.description,
        due_date=data.due_date,
        priority=data.priority,
        category=data.category,
        reminder_minutes_before=data.reminder_minutes_before,
        recurring_rule=data.recurring_rule,
        notes=data.notes,
        status=TaskStatus.PENDING,
    )
    if data.related_file_ids:
        files = db.query(KnowledgeFile).filter(KnowledgeFile.id.in_(data.related_file_ids)).all()
        task.related_files = files

    db.add(task)
    db.commit()
    db.refresh(task)

    # Auto-create a reminder if requested (or default) and there's a due date
    minutes_before = data.reminder_minutes_before
    if minutes_before is None and task.due_date is not None:
        minutes_before = settings.default_reminder_minutes_before
    if task.due_date is not None and minutes_before is not None:
        remind_at = task.due_date - timedelta(minutes=minutes_before)
        if remind_at > datetime.now():
            db.add(Reminder(
                task_id=task.id,
                remind_at=remind_at,
                message=f"Upcoming: {task.title}",
            ))
            db.commit()

    log_activity(db, "task_created", f"Created task '{task.title}'", task_id=task.id)
    return task


def get_task(db: Session, task_id: str) -> Optional[Task]:
    return db.query(Task).filter(Task.id == task_id).first()


def list_tasks(
    db: Session,
    status: Optional[TaskStatus] = None,
    due_before: Optional[datetime] = None,
    due_after: Optional[datetime] = None,
    category: Optional[str] = None,
) -> list[Task]:
    query = db.query(Task)
    filters = []
    if status:
        filters.append(Task.status == status)
    if due_before:
        filters.append(Task.due_date <= due_before)
    if due_after:
        filters.append(Task.due_date >= due_after)
    if category:
        filters.append(Task.category == category)
    if filters:
        query = query.filter(and_(*filters))
    return query.order_by(Task.due_date.is_(None), Task.due_date.asc()).all()


def get_today_tasks(db: Session) -> list[Task]:
    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return list_tasks(db, due_after=start, due_before=end)


def get_overdue_tasks(db: Session) -> list[Task]:
    now = datetime.now()
    return (
        db.query(Task)
        .filter(
            Task.due_date < now,
            Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.OVERDUE]),
        )
        .order_by(Task.due_date.asc())
        .all()
    )


def get_upcoming_deadlines(db: Session, days: int = 7) -> list[Task]:
    now = datetime.now()
    end = now + timedelta(days=days)
    return list_tasks(db, due_after=now, due_before=end)


def update_task(db: Session, task_id: str, data: TaskUpdate) -> Optional[Task]:
    task = get_task(db, task_id)
    if not task:
        return None
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    if data.status == TaskStatus.COMPLETED and task.completion_date is None:
        task.completion_date = datetime.now()
        log_activity(db, "task_completed", f"Completed task '{task.title}'", task_id=task.id)
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task_id: str) -> bool:
    task = get_task(db, task_id)
    if not task:
        return False
    db.delete(task)
    db.commit()
    return True


def mark_overdue_tasks(db: Session) -> int:
    """Run periodically by the scheduler: flips PENDING tasks past due -> OVERDUE."""
    now = datetime.now()
    overdue = (
        db.query(Task)
        .filter(Task.due_date < now, Task.status == TaskStatus.PENDING)
        .all()
    )
    for task in overdue:
        task.status = TaskStatus.OVERDUE
    if overdue:
        db.commit()
    return len(overdue)


def get_activity_between(db: Session, start: datetime, end: datetime) -> list[ActivityLog]:
    return (
        db.query(ActivityLog)
        .filter(ActivityLog.timestamp >= start, ActivityLog.timestamp < end)
        .order_by(ActivityLog.timestamp.asc())
        .all()
    )
