"""
Persistent data model for JARVIS.

Covers: tasks, calendar events, reminders, knowledge-base files + chunks,
conversations/messages, long-term memory facts, user preferences, and a
daily activity log (used for briefings + "what did I do yesterday").
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, DateTime, Boolean, Integer, ForeignKey, Enum
)
from sqlalchemy.orm import relationship

from app.database.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TaskStatus(str, enum.Enum):
    PENDING = "Pending"
    IN_PROGRESS = "In Progress"
    COMPLETED = "Completed"
    OVERDUE = "Overdue"
    CANCELLED = "Cancelled"


class TaskPriority(str, enum.Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class FileStatus(str, enum.Enum):
    PROCESSING = "Processing"
    INDEXED = "Indexed"
    UPDATED = "Updated"
    FAILED = "Failed"


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# ---------------------------------------------------------------------------
# Association table: tasks <-> knowledge files (many-to-many)
# ---------------------------------------------------------------------------

class TaskFileLink(Base):
    __tablename__ = "task_file_links"

    id = Column(String, primary_key=True, default=_uuid)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    file_id = Column(String, ForeignKey("knowledge_files.id", ondelete="CASCADE"), nullable=False)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=_uuid)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    created_date = Column(DateTime, default=datetime.utcnow)
    due_date = Column(DateTime, nullable=True)          # date+time combined
    priority = Column(Enum(TaskPriority), default=TaskPriority.MEDIUM)
    category = Column(String, default="General")
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING)
    reminder_minutes_before = Column(Integer, nullable=True)
    recurring_rule = Column(String, nullable=True)      # e.g. "DAILY", "WEEKLY:MON,WED"
    notes = Column(Text, default="")
    completion_date = Column(DateTime, nullable=True)

    related_files = relationship(
        "KnowledgeFile", secondary="task_file_links", back_populates="related_tasks"
    )
    reminders = relationship("Reminder", back_populates="task", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "created_date": self.created_date.isoformat() if self.created_date else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "priority": self.priority.value if self.priority else None,
            "category": self.category,
            "status": self.status.value if self.status else None,
            "reminder_minutes_before": self.reminder_minutes_before,
            "recurring_rule": self.recurring_rule,
            "notes": self.notes,
            "completion_date": self.completion_date.isoformat() if self.completion_date else None,
            "related_files": [f.filename for f in self.related_files],
        }


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(String, primary_key=True, default=_uuid)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    remind_at = Column(DateTime, nullable=False)
    fired = Column(Boolean, default=False)
    message = Column(String, default="")

    task = relationship("Task", back_populates="reminders")


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id = Column(String, primary_key=True, default=_uuid)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    all_day = Column(Boolean, default=False)
    task_id = Column(String, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)


# ---------------------------------------------------------------------------
# Knowledge base (files ingested for RAG)
# ---------------------------------------------------------------------------

class KnowledgeFile(Base):
    __tablename__ = "knowledge_files"

    id = Column(String, primary_key=True, default=_uuid)
    filename = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    date_added = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow)
    status = Column(Enum(FileStatus), default=FileStatus.PROCESSING)
    num_chunks = Column(Integer, default=0)
    num_pages_or_records = Column(Integer, nullable=True)
    content_hash = Column(String, nullable=True)  # used to detect real changes
    error_message = Column(Text, nullable=True)

    related_tasks = relationship(
        "Task", secondary="task_file_links", back_populates="related_files"
    )


class DocumentChunk(Base):
    """
    Metadata row for each chunk. The actual embedding vector lives in the
    vector store (ChromaDB); this row lets us map a vector-store hit back to
    human-readable file/section info and lets SQL-only queries still work.
    """
    __tablename__ = "document_chunks"

    id = Column(String, primary_key=True, default=_uuid)
    file_id = Column(String, ForeignKey("knowledge_files.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer, nullable=True)
    section_title = Column(String, nullable=True)
    text = Column(Text, nullable=False)
    vector_store_id = Column(String, nullable=False)  # id used inside Chroma/FAISS


# ---------------------------------------------------------------------------
# Conversation + memory
# ---------------------------------------------------------------------------

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=_uuid)
    started_at = Column(DateTime, default=datetime.utcnow)
    title = Column(String, default="New conversation")

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=_uuid)
    conversation_id = Column(String, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")


class MemoryFact(Base):
    """
    Long-term / project memory. Distinct from raw conversation logs — only
    facts explicitly worth keeping are written here (see app/memory).
    """
    __tablename__ = "memory_facts"

    id = Column(String, primary_key=True, default=_uuid)
    scope = Column(String, default="long_term")  # long_term | project
    project_tag = Column(String, nullable=True)  # e.g. "DPI_Engine" when scope=project
    content = Column(Text, nullable=False)
    source = Column(String, default="conversation")  # conversation | file | user_set
    created_at = Column(DateTime, default=datetime.utcnow)


class UserPreference(Base):
    __tablename__ = "user_preferences"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)


class ActivityLog(Base):
    """Used for daily briefings and 'what did I work on yesterday'."""
    __tablename__ = "activity_log"

    id = Column(String, primary_key=True, default=_uuid)
    timestamp = Column(DateTime, default=datetime.utcnow)
    activity_type = Column(String, nullable=False)  # task_completed, file_added, command_run, ...
    description = Column(String, nullable=False)
    related_task_id = Column(String, nullable=True)
    related_file_id = Column(String, nullable=True)
