from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.ai.command_router import route_command
from app.core.briefing import generate_daily_briefing, generate_daily_plan, format_plan

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class CommandRequest(BaseModel):
    text: str


@router.post("/command")
def run_command(payload: CommandRequest, db: Session = Depends(get_db)):
    result = route_command(db, payload.text)
    return {
        "intent": result.intent,
        "message": result.message,
        "data": result.data,
        "needs_confirmation": result.needs_confirmation,
    }


@router.get("/briefing")
def daily_briefing(db: Session = Depends(get_db)):
    briefing = generate_daily_briefing(db)
    return {
        "date": briefing.date_str,
        "text": briefing.text,
        "high_priority_count": briefing.high_priority_count,
        "overdue_count": len(briefing.overdue),
    }


@router.get("/plan")
def daily_plan(db: Session = Depends(get_db)):
    plan = generate_daily_plan(db)
    return {
        "text": format_plan(plan),
        "blocks": [
            {"start": b.start.isoformat(), "end": b.end.isoformat(), "label": b.label, "task_id": b.task_id}
            for b in plan
        ],
    }
