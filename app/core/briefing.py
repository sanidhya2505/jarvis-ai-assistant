"""
Daily briefing (spec section 6) and smart daily planner (spec section 15).

Both are deterministic-first (built from real task/calendar/activity data)
with an optional LLM pass to turn the structured summary into the friendlier
prose shown in the spec example. If no LLM is configured, the deterministic
version is returned as-is — still fully useful, never blocked on AI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, time as dtime

from sqlalchemy.orm import Session

from app.database.models import Task, TaskPriority
from app.tasks import crud as task_crud
from app.calendar import crud as calendar_crud
from app.ai.llm_client import chat, LLMUnavailableError


@dataclass
class Briefing:
    date_str: str
    priorities: list[Task]
    upcoming_deadlines: list[Task]
    overdue: list[Task]
    high_priority_count: int
    text: str


def _format_task_line(task: Task) -> str:
    time_str = task.due_date.strftime("%I:%M %p").lstrip("0") if task.due_date else "no time set"
    return f"{task.title} — {time_str}"


def generate_daily_briefing(db: Session, use_ai_summary: bool = True) -> Briefing:
    now = datetime.now()
    today_tasks = task_crud.get_today_tasks(db)
    deadlines = task_crud.get_upcoming_deadlines(db, days=7)
    overdue = task_crud.get_overdue_tasks(db)

    priorities = sorted(
        today_tasks,
        key=lambda t: (list(TaskPriority).index(t.priority) if t.priority else 99, t.due_date or now),
    )
    high_priority_count = sum(1 for t in today_tasks if t.priority in (TaskPriority.CRITICAL, TaskPriority.HIGH))

    lines = [f"Good {'morning' if now.hour < 12 else 'afternoon' if now.hour < 18 else 'evening'}.", ""]
    lines.append(f"Today is {now.strftime('%A, %B %d')}.")
    lines.append("")
    if priorities:
        lines.append("Today's priorities:")
        for i, t in enumerate(priorities, 1):
            lines.append(f"{i}. {_format_task_line(t)}")
    else:
        lines.append("You have no tasks scheduled for today.")
    lines.append("")
    if deadlines:
        lines.append("Upcoming deadlines:")
        for t in deadlines[:5]:
            lines.append(f"• {t.title} — {t.due_date.strftime('%B %d')}")
        lines.append("")
    if overdue:
        lines.append(f"You have {len(overdue)} overdue task(s) that need attention.")
        lines.append("")
    if high_priority_count:
        lines.append(f"You have {high_priority_count} high-priority task(s) today.")

    deterministic_text = "\n".join(lines).strip()

    final_text = deterministic_text
    if use_ai_summary:
        try:
            final_text = chat(
                system_prompt=(
                    "You are JARVIS, a concise personal assistant. Rewrite the following "
                    "structured daily summary as a short, natural spoken-style briefing, "
                    "in the same spirit as the input. Do not invent tasks or deadlines that "
                    "aren't listed. End with one short 'recommended focus' sentence."
                ),
                user_prompt=deterministic_text,
                max_tokens=400,
            )
        except LLMUnavailableError:
            pass  # deterministic version is already a complete, useful briefing

    return Briefing(
        date_str=now.strftime("%A, %B %d"),
        priorities=priorities,
        upcoming_deadlines=deadlines,
        overdue=overdue,
        high_priority_count=high_priority_count,
        text=final_text,
    )


# ---------------------------------------------------------------------------
# Smart daily planner
# ---------------------------------------------------------------------------

@dataclass
class PlanBlock:
    start: datetime
    end: datetime
    label: str
    task_id: str | None = None


DEFAULT_WORK_START = dtime(9, 0)
DEFAULT_WORK_END = dtime(20, 0)
DEFAULT_TASK_DURATION_MINUTES = 60
BREAK_MINUTES = 15


def generate_daily_plan(db: Session, day: datetime | None = None) -> list[PlanBlock]:
    """
    Greedy scheduler: sorts pending/overdue tasks by (priority, due date),
    then lays them into open slots for the day around existing calendar
    events, inserting short breaks between blocks. This is intentionally
    simple/deterministic (no LLM) so the plan is reproducible and fast;
    the user can accept/modify/reject per spec section 15.
    """
    day = day or datetime.now()
    day_start = datetime.combine(day.date(), DEFAULT_WORK_START)
    day_end = datetime.combine(day.date(), DEFAULT_WORK_END)

    existing_events = calendar_crud.get_day_view(db, day)
    busy = sorted(
        [(e.start_time, e.end_time or e.start_time + timedelta(hours=1)) for e in existing_events],
        key=lambda x: x[0],
    )

    candidates = [
        t for t in task_crud.list_tasks(db)
        if t.status.value in ("Pending", "In Progress", "Overdue")
    ]
    candidates.sort(key=lambda t: (
        list(TaskPriority).index(t.priority) if t.priority else 99,
        t.due_date or day_end,
    ))

    plan: list[PlanBlock] = []
    cursor = day_start

    def next_free_slot(after: datetime) -> datetime:
        slot = after
        for b_start, b_end in busy:
            if slot < b_end and slot >= b_start:
                slot = b_end
        return slot

    for task in candidates:
        cursor = next_free_slot(cursor)
        if cursor >= day_end:
            break
        block_end = min(cursor + timedelta(minutes=DEFAULT_TASK_DURATION_MINUTES), day_end)
        plan.append(PlanBlock(start=cursor, end=block_end, label=task.title, task_id=task.id))
        cursor = block_end + timedelta(minutes=BREAK_MINUTES)

    return plan


def format_plan(plan: list[PlanBlock]) -> str:
    if not plan:
        return "No tasks to schedule — your day is open."
    lines = []
    for block in plan:
        lines.append(f"{block.start.strftime('%H:%M')}–{block.end.strftime('%H:%M')}  {block.label}")
    return "\n".join(lines)
