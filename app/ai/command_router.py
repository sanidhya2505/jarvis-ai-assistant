"""
Command interpreter / router (spec section 17).

Intent detection here is rule-based (keyword/regex) rather than an LLM
classifier call for every command — it's instant, free, offline-capable,
and covers the explicit command list in the spec exactly. Anything that
doesn't match a known pattern falls through to the RAG-backed "ask a
question" handler, which is where the LLM actually gets used.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy.orm import Session

from app.tasks import crud as task_crud
from app.tasks.nlp_parser import parse_task_text
from app.tasks.schemas import TaskCreate, TaskUpdate
from app.database.models import TaskStatus
from app.rag.retrieval import answer_from_knowledge_base
from app.core.briefing import generate_daily_briefing, generate_daily_plan, format_plan
from app.config.settings import get_settings

settings = get_settings()


@dataclass
class CommandResult:
    intent: str
    message: str
    data: dict | None = None
    needs_confirmation: bool = False


_PATTERNS: list[tuple[str, str]] = [
    (r"^(add|create|new) (a )?task\b", "add_task"),
    (r"^remind me\b", "add_task"),
    (r"\bdelete (this )?task\b", "delete_task"),
    (r"\bmark (this )?task (as )?complete", "complete_task"),
    (r"\bmove (this )?task to\b", "reschedule_task"),
    (r"what.*(do i have|is on).*(today|schedule)", "today_tasks"),
    (r"what.*deadlines?.*(this week|coming|upcoming)", "upcoming_deadlines"),
    (r"what('s| is) overdue|overdue tasks?", "overdue_tasks"),
    (r"what did i (work on|do) yesterday", "activity_yesterday"),
    (r"\bplan my day\b|\bsmart (daily )?plan\b", "plan_day"),
    (r"what should i work on next", "plan_day"),
    (r"(daily )?briefing|good morning", "daily_briefing"),
    (r"search (my )?(project )?files|find where|compare (these|this)", "search_files"),
    (r"what is missing from my project", "search_files"),
]


def _match_intent(text: str) -> str:
    lowered = text.lower().strip()
    for pattern, intent in _PATTERNS:
        if re.search(pattern, lowered):
            return intent
    return "ask_knowledge_base"


def route_command(db: Session, text: str) -> CommandResult:
    intent = _match_intent(text)
    handler: Callable[[Session, str], CommandResult] = _HANDLERS.get(intent, _handle_ask_kb)
    return handler(db, text)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _handle_add_task(db: Session, text: str) -> CommandResult:
    parsed = parse_task_text(text)
    if parsed.ambiguous:
        return CommandResult(
            intent="add_task",
            message=f"I need a bit more detail: {parsed.ambiguity_reason}",
            data={"draft_title": parsed.title, "raw_text": text},
            needs_confirmation=True,
        )
    task = task_crud.create_task(db, TaskCreate(
        title=parsed.title, due_date=parsed.due_date,
        priority=parsed.priority, recurring_rule=parsed.recurring_rule,
    ))
    due_str = task.due_date.strftime("%A, %B %d at %I:%M %p").lstrip("0") if task.due_date else "no due date"
    return CommandResult(
        intent="add_task",
        message=f"Added '{task.title}' — due {due_str}.",
        data=task.to_dict(),
    )


def _handle_today_tasks(db: Session, text: str) -> CommandResult:
    tasks = task_crud.get_today_tasks(db)
    if not tasks:
        return CommandResult("today_tasks", "You have no tasks scheduled for today.", data={"tasks": []})
    lines = [f"- {t.title} ({t.priority.value})" for t in tasks]
    return CommandResult(
        "today_tasks",
        f"You have {len(tasks)} task(s) today:\n" + "\n".join(lines),
        data={"tasks": [t.to_dict() for t in tasks]},
    )


def _handle_upcoming_deadlines(db: Session, text: str) -> CommandResult:
    tasks = task_crud.get_upcoming_deadlines(db, days=7)
    if not tasks:
        return CommandResult("upcoming_deadlines", "No deadlines in the next 7 days.", data={"tasks": []})
    lines = [f"- {t.title} — {t.due_date.strftime('%B %d')}" for t in tasks]
    return CommandResult(
        "upcoming_deadlines",
        "Deadlines this week:\n" + "\n".join(lines),
        data={"tasks": [t.to_dict() for t in tasks]},
    )


def _handle_overdue_tasks(db: Session, text: str) -> CommandResult:
    tasks = task_crud.get_overdue_tasks(db)
    if not tasks:
        return CommandResult("overdue_tasks", "Nothing overdue — you're all caught up.", data={"tasks": []})
    lines = [f"- {t.title} (was due {t.due_date.strftime('%B %d')})" for t in tasks]
    return CommandResult(
        "overdue_tasks",
        f"You have {len(tasks)} overdue task(s):\n" + "\n".join(lines),
        data={"tasks": [t.to_dict() for t in tasks]},
    )


def _handle_activity_yesterday(db: Session, text: str) -> CommandResult:
    now = datetime.now()
    start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    activity = task_crud.get_activity_between(db, start, end)
    if not activity:
        return CommandResult("activity_yesterday", "No recorded activity yesterday.", data={"activity": []})
    lines = [f"- {a.description}" for a in activity]
    return CommandResult(
        "activity_yesterday",
        "Yesterday you:\n" + "\n".join(lines),
        data={"activity": [a.description for a in activity]},
    )


def _handle_plan_day(db: Session, text: str) -> CommandResult:
    plan = generate_daily_plan(db)
    return CommandResult(
        "plan_day",
        "Here's a proposed plan for today:\n" + format_plan(plan),
        data={"blocks": [
            {"start": b.start.isoformat(), "end": b.end.isoformat(), "label": b.label, "task_id": b.task_id}
            for b in plan
        ]},
    )


def _handle_daily_briefing(db: Session, text: str) -> CommandResult:
    briefing = generate_daily_briefing(db)
    return CommandResult("daily_briefing", briefing.text, data={"date": briefing.date_str})


def _handle_search_files(db: Session, text: str) -> CommandResult:
    result = answer_from_knowledge_base(text, allow_general_knowledge=settings.enable_web_search)
    return CommandResult(
        "search_files",
        result.answer,
        data={"found_in_files": result.found_in_files, "sources": result.sources},
    )


def _handle_complete_task(db: Session, text: str) -> CommandResult:
    """
    Without a task ID in the text, completes the single most-recently-due
    pending task from today (best-effort). The UI/voice layer should prefer
    calling PATCH /api/tasks/{id} directly once a specific task is selected
    — this handler exists for the free-text command path in the spec.
    """
    today = task_crud.get_today_tasks(db)
    pending = [t for t in today if t.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)]
    if not pending:
        return CommandResult("complete_task", "I couldn't find an obvious task to mark complete today.")
    task = pending[0]
    task_crud.update_task(db, task.id, TaskUpdate(status=TaskStatus.COMPLETED))
    return CommandResult("complete_task", f"Marked '{task.title}' as completed.", data={"task_id": task.id})


def _handle_reschedule_task(db: Session, text: str) -> CommandResult:
    match = re.search(r"move (this )?task to (.+)", text, re.IGNORECASE)
    target_text = match.group(2) if match else text
    parsed = parse_task_text(target_text)
    if not parsed.date_detected:
        return CommandResult(
            "reschedule_task",
            "Which task, and what new date/time should I move it to?",
            needs_confirmation=True,
        )
    today = task_crud.get_today_tasks(db) or task_crud.get_overdue_tasks(db)
    if not today:
        return CommandResult("reschedule_task", "I don't have a task in context to reschedule.")
    task = today[0]
    task_crud.update_task(db, task.id, TaskUpdate(due_date=parsed.due_date, status=TaskStatus.PENDING))
    return CommandResult(
        "reschedule_task",
        f"Moved '{task.title}' to {parsed.due_date.strftime('%A, %B %d at %I:%M %p').lstrip('0')}.",
        data={"task_id": task.id},
    )


def _handle_delete_task(db: Session, text: str) -> CommandResult:
    return CommandResult(
        "delete_task",
        "To delete a task, open it in the Task view and confirm deletion — "
        "this avoids accidentally removing the wrong task from a voice command.",
        needs_confirmation=True,
    )


def _handle_ask_kb(db: Session, text: str) -> CommandResult:
    """Fallback: treat any unmatched command as a knowledge-base question."""
    result = answer_from_knowledge_base(text, allow_general_knowledge=settings.enable_web_search)
    return CommandResult(
        "ask_knowledge_base",
        result.answer,
        data={"found_in_files": result.found_in_files, "sources": result.sources},
    )


_HANDLERS: dict[str, Callable[[Session, str], CommandResult]] = {
    "add_task": _handle_add_task,
    "complete_task": _handle_complete_task,
    "reschedule_task": _handle_reschedule_task,
    "delete_task": _handle_delete_task,
    "today_tasks": _handle_today_tasks,
    "upcoming_deadlines": _handle_upcoming_deadlines,
    "overdue_tasks": _handle_overdue_tasks,
    "activity_yesterday": _handle_activity_yesterday,
    "plan_day": _handle_plan_day,
    "daily_briefing": _handle_daily_briefing,
    "search_files": _handle_search_files,
    "ask_knowledge_base": _handle_ask_kb,
}
