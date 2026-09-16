from datetime import datetime, timedelta

from app.ai.command_router import route_command
from app.tasks import crud
from app.tasks.schemas import TaskCreate


def test_add_task_command(db_session):
    result = route_command(db_session, "Add task: finish resume on September 20 at 6pm")
    assert result.intent == "add_task"
    assert result.needs_confirmation is False


def test_ambiguous_add_task_needs_confirmation(db_session):
    result = route_command(db_session, "Add task: think about the future")
    assert result.intent == "add_task"
    assert result.needs_confirmation is True


def test_today_tasks_command(db_session):
    crud.create_task(db_session, TaskCreate(title="Today thing", due_date=datetime.now()))
    result = route_command(db_session, "What do I have to do today?")
    assert result.intent == "today_tasks"
    assert "Today thing" in result.message


def test_overdue_tasks_command(db_session):
    crud.create_task(db_session, TaskCreate(title="Late thing", due_date=datetime.now() - timedelta(days=2)))
    crud.mark_overdue_tasks(db_session)
    result = route_command(db_session, "What's overdue?")
    assert result.intent == "overdue_tasks"
    assert "Late thing" in result.message


def test_plan_day_command(db_session):
    crud.create_task(db_session, TaskCreate(title="Deep work block"))
    result = route_command(db_session, "Plan my day")
    assert result.intent == "plan_day"
    assert result.data is not None
