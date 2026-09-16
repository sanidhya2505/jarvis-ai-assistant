from datetime import datetime

from app.tasks.nlp_parser import parse_task_text
from app.database.models import TaskPriority


def test_parse_explicit_date_and_time():
    now = datetime(2026, 9, 17, 9, 0)
    parsed = parse_task_text("Add task: Complete ML playlist on September 18 at 8 PM", now=now)
    assert "Complete ML playlist" in parsed.title
    assert parsed.date_detected is True
    assert parsed.due_date.month == 9
    assert parsed.due_date.day == 18
    assert parsed.due_date.hour == 20


def test_parse_relative_date():
    now = datetime(2026, 9, 17, 9, 0)
    parsed = parse_task_text("Remind me tomorrow at 10 AM to review the PR", now=now)
    assert parsed.date_detected is True
    assert parsed.due_date.day == 18
    assert parsed.due_date.hour == 10


def test_parse_priority_keyword():
    parsed = parse_task_text("Add task: fix critical bug in payments today at 5pm")
    assert parsed.priority == TaskPriority.CRITICAL


def test_parse_no_date_is_ambiguous():
    parsed = parse_task_text("Add task: think about grad school")
    assert parsed.ambiguous is True
    assert parsed.date_detected is False


def test_parse_recurring_rule():
    parsed = parse_task_text("Add task: daily standup every day at 9am")
    assert parsed.recurring_rule == "DAILY"
