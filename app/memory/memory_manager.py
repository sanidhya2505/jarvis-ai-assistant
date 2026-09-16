"""
Three-tier memory system (spec section 12).

- Short-term: the current Conversation + its Messages (already modeled in
  app.database.models). Nothing extra needed here beyond helpers.
- Long-term: MemoryFact rows with scope='long_term' — durable user facts/
  preferences worth keeping across sessions.
- Project memory: MemoryFact rows with scope='project', tagged by
  project_tag, extracted from uploaded project files or explicit user
  statements about a project.

Per spec: "Do not blindly save every conversation. Only save information
when it is useful and persistent." `remember()` is therefore an explicit
call the command router makes when it recognizes a save-worthy statement —
it is never invoked automatically on every message.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.models import Conversation, Message, MemoryFact, MessageRole


def start_conversation(db: Session, title: str = "New conversation") -> Conversation:
    conv = Conversation(title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def add_message(db: Session, conversation_id: str, role: MessageRole, content: str) -> Message:
    msg = Message(conversation_id=conversation_id, role=role, content=content)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def get_recent_messages(db: Session, conversation_id: str, limit: int = 20) -> list[Message]:
    return (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
        .all()[::-1]
    )


def remember(db: Session, content: str, scope: str = "long_term",
             project_tag: str | None = None, source: str = "conversation") -> MemoryFact:
    fact = MemoryFact(content=content, scope=scope, project_tag=project_tag, source=source)
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return fact


def get_long_term_facts(db: Session) -> list[MemoryFact]:
    return db.query(MemoryFact).filter(MemoryFact.scope == "long_term").order_by(MemoryFact.created_at.desc()).all()


def get_project_facts(db: Session, project_tag: str) -> list[MemoryFact]:
    return (
        db.query(MemoryFact)
        .filter(MemoryFact.scope == "project", MemoryFact.project_tag == project_tag)
        .order_by(MemoryFact.created_at.desc())
        .all()
    )


def clear_memory(db: Session, scope: str | None = None, project_tag: str | None = None) -> int:
    """User-facing 'clear my memory' — scoped so a user can wipe just one project's memory."""
    query = db.query(MemoryFact)
    if scope:
        query = query.filter(MemoryFact.scope == scope)
    if project_tag:
        query = query.filter(MemoryFact.project_tag == project_tag)
    count = query.count()
    query.delete(synchronize_session=False)
    db.commit()
    return count
