from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.calendar import crud

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


class EventCreate(BaseModel):
    title: str
    start_time: datetime
    end_time: datetime | None = None
    description: str = ""
    all_day: bool = False
    task_id: str | None = None


def _serialize(event) -> dict:
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "start_time": event.start_time.isoformat(),
        "end_time": event.end_time.isoformat() if event.end_time else None,
        "all_day": event.all_day,
        "task_id": event.task_id,
    }


@router.post("/events")
def create_event(payload: EventCreate, db: Session = Depends(get_db)):
    event = crud.create_event(db, **payload.model_dump())
    return _serialize(event)


@router.get("/day")
def day_view(date: datetime, db: Session = Depends(get_db)):
    return [_serialize(e) for e in crud.get_day_view(db, date)]


@router.get("/week")
def week_view(date: datetime, db: Session = Depends(get_db)):
    return [_serialize(e) for e in crud.get_week_view(db, date)]


@router.get("/month")
def month_view(date: datetime, db: Session = Depends(get_db)):
    return [_serialize(e) for e in crud.get_month_view(db, date)]


@router.get("/conflicts")
def conflicts(date: datetime, db: Session = Depends(get_db)):
    pairs = crud.find_schedule_conflicts(db, date)
    return [
        {"first": _serialize(a), "second": _serialize(b)}
        for a, b in pairs
    ]
