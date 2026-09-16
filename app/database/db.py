"""
Database engine + session management (SQLite via SQLAlchemy ORM).

SQLite is used initially per the project spec; the DATABASE_URL setting
means swapping to Postgres/MySQL later only requires changing .env plus
installing the relevant driver.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base

from app.config.settings import get_settings

settings = get_settings()

# check_same_thread=False is required for SQLite when accessed from
# multiple threads (FastAPI + scheduler + voice thread, etc.)
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()


def init_db() -> None:
    """Create all tables that don't exist yet. Safe to call every startup."""
    from app.database import models  # noqa: F401  (ensures models are registered)
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a DB session, always closed after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """For use outside FastAPI (scheduler jobs, voice thread, CLI scripts)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
