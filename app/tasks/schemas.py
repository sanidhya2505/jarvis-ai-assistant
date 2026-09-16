from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, Field

from app.database.models import TaskStatus, TaskPriority


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    due_date: Optional[datetime] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    category: str = "General"
    reminder_minutes_before: Optional[int] = None
    recurring_rule: Optional[str] = None
    notes: str = ""
    related_file_ids: List[str] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: Optional[TaskPriority] = None
    category: Optional[str] = None
    status: Optional[TaskStatus] = None
    reminder_minutes_before: Optional[int] = None
    recurring_rule: Optional[str] = None
    notes: Optional[str] = None


class NaturalLanguageTaskRequest(BaseModel):
    text: str


class TaskOut(BaseModel):
    id: str
    title: str
    description: str
    created_date: Optional[datetime]
    due_date: Optional[datetime]
    priority: str
    category: str
    status: str
    reminder_minutes_before: Optional[int]
    recurring_rule: Optional[str]
    notes: str
    completion_date: Optional[datetime]
    related_files: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
