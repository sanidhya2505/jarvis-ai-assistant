from datetime import datetime, timedelta

from app.tasks import crud
from app.tasks.schemas import TaskCreate, TaskUpdate
from app.database.models import TaskStatus, TaskPriority


def test_create_task(db_session):
    task = crud.create_task(db_session, TaskCreate(
        title="Write report", due_date=datetime.now() + timedelta(days=1), priority=TaskPriority.HIGH,
    ))
    assert task.id
    assert task.title == "Write report"
    assert task.status == TaskStatus.PENDING
    assert task.priority == TaskPriority.HIGH


def test_create_task_auto_reminder(db_session):
    due = datetime.now() + timedelta(hours=2)
    task = crud.create_task(db_session, TaskCreate(title="Call client", due_date=due))
    assert len(task.reminders) == 1
    assert task.reminders[0].remind_at < due


def test_update_task_to_completed_sets_completion_date(db_session):
    task = crud.create_task(db_session, TaskCreate(title="Ship feature"))
    updated = crud.update_task(db_session, task.id, TaskUpdate(status=TaskStatus.COMPLETED))
    assert updated.status == TaskStatus.COMPLETED
    assert updated.completion_date is not None


def test_delete_task(db_session):
    task = crud.create_task(db_session, TaskCreate(title="Temp task"))
    assert crud.delete_task(db_session, task.id) is True
    assert crud.get_task(db_session, task.id) is None


def test_mark_overdue_tasks(db_session):
    past = datetime.now() - timedelta(days=1)
    crud.create_task(db_session, TaskCreate(title="Late task", due_date=past))
    count = crud.mark_overdue_tasks(db_session)
    assert count == 1
    overdue = crud.get_overdue_tasks(db_session)
    assert len(overdue) == 1
    assert overdue[0].title == "Late task"


def test_get_today_tasks_excludes_other_days(db_session):
    today = datetime.now().replace(hour=15, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    crud.create_task(db_session, TaskCreate(title="Today task", due_date=today))
    crud.create_task(db_session, TaskCreate(title="Tomorrow task", due_date=tomorrow))
    today_tasks = crud.get_today_tasks(db_session)
    titles = [t.title for t in today_tasks]
    assert "Today task" in titles
    assert "Tomorrow task" not in titles
