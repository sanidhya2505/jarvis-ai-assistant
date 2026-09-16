from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.database.models import TaskStatus
from app.tasks import crud
from app.tasks.schemas import TaskCreate, TaskUpdate, TaskOut, NaturalLanguageTaskRequest
from app.tasks.nlp_parser import parse_task_text

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("", response_model=TaskOut)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    task = crud.create_task(db, payload)
    return TaskOut.model_validate(task)


@router.post("/from-text")
def create_task_from_text(payload: NaturalLanguageTaskRequest, db: Session = Depends(get_db)):
    """
    Parses free text like:
      "Add task: Complete ML playlist on September 18 at 8 PM"
    If the parse is ambiguous (no date found, etc.) it returns the parsed
    draft WITHOUT saving, so the UI/voice layer can ask for confirmation
    per spec section 4.
    """
    parsed = parse_task_text(payload.text)

    if parsed.ambiguous:
        return {
            "created": False,
            "reason": parsed.ambiguity_reason,
            "draft": {
                "title": parsed.title,
                "due_date": parsed.due_date.isoformat() if parsed.due_date else None,
                "priority": parsed.priority.value,
                "recurring_rule": parsed.recurring_rule,
            },
        }

    task = crud.create_task(db, TaskCreate(
        title=parsed.title,
        due_date=parsed.due_date,
        priority=parsed.priority,
        recurring_rule=parsed.recurring_rule,
    ))
    return {"created": True, "task": TaskOut.model_validate(task).model_dump()}


@router.get("", response_model=list[TaskOut])
def list_tasks(status: TaskStatus | None = None, db: Session = Depends(get_db)):
    return crud.list_tasks(db, status=status)


@router.get("/today", response_model=list[TaskOut])
def today_tasks(db: Session = Depends(get_db)):
    return crud.get_today_tasks(db)


@router.get("/overdue", response_model=list[TaskOut])
def overdue_tasks(db: Session = Depends(get_db)):
    return crud.get_overdue_tasks(db)


@router.get("/upcoming", response_model=list[TaskOut])
def upcoming_tasks(days: int = 7, db: Session = Depends(get_db)):
    return crud.get_upcoming_deadlines(db, days=days)


@router.get("/{task_id}", response_model=TaskOut)
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = crud.get_task(db, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@router.patch("/{task_id}", response_model=TaskOut)
def update_task(task_id: str, payload: TaskUpdate, db: Session = Depends(get_db)):
    task = crud.update_task(db, task_id, payload)
    if not task:
        raise HTTPException(404, "Task not found")
    return task


@router.delete("/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db)):
    ok = crud.delete_task(db, task_id)
    if not ok:
        raise HTTPException(404, "Task not found")
    return {"deleted": True}
