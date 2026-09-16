"""
Knowledge-folder watcher.

Two layers, per spec section 3:
  1. `watchdog` gives near-instant detection of new/changed files while the
     app is running.
  2. `scan_knowledge_folder` is also run periodically by the scheduler as a
     safety net (catches files added while the watcher thread wasn't up,
     e.g. right at startup, or if a filesystem event was missed).

Deleted files are detected by diffing the DB's known paths against what's
actually on disk during a scan.
"""
from __future__ import annotations

from pathlib import Path

from app.config.settings import get_settings
from app.database.db import session_scope
from app.database.models import KnowledgeFile
from app.files.ingestion import ingest_file, remove_file
from app.core.logging_config import get_logger

logger = get_logger("jarvis.files")
settings = get_settings()

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".txt", ".md", ".csv", ".xlsx", ".pptx", ".zip",
    ".png", ".jpg", ".jpeg", ".webp",
}


def scan_knowledge_folder() -> dict:
    """One-shot scan: ingest new/changed files, remove DB entries for files no longer on disk."""
    folder = settings.knowledge_dir
    folder.mkdir(parents=True, exist_ok=True)

    disk_paths = {
        str(p) for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    }

    processed, failed, removed = 0, 0, 0
    with session_scope() as db:
        for path_str in disk_paths:
            record = ingest_file(db, Path(path_str))
            if record.status.value == "Failed":
                failed += 1
            else:
                processed += 1

        known = db.query(KnowledgeFile).all()
        for record in known:
            if record.file_path not in disk_paths:
                remove_file(db, record.id)
                removed += 1

    if processed or failed or removed:
        logger.info("Knowledge scan: %d processed, %d failed, %d removed", processed, failed, removed)
    return {"processed": processed, "failed": failed, "removed": removed}


def start_watchdog_observer():
    """
    Starts a real-time filesystem watcher. Returns the Observer instance so
    the caller can .stop() it on shutdown. Falls back gracefully (logs and
    returns None) if `watchdog` isn't available in this environment — the
    periodic scheduler scan still covers ingestion either way.
    """
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except Exception as exc:
        logger.warning("watchdog not available (%s) — relying on periodic scans only", exc)
        return None

    class _Handler(FileSystemEventHandler):
        def on_created(self, event):
            if not event.is_directory:
                scan_knowledge_folder()

        def on_modified(self, event):
            if not event.is_directory:
                scan_knowledge_folder()

        def on_deleted(self, event):
            scan_knowledge_folder()

    settings.knowledge_dir.mkdir(parents=True, exist_ok=True)
    observer = Observer()
    observer.schedule(_Handler(), str(settings.knowledge_dir), recursive=True)
    observer.start()
    logger.info("Watching knowledge folder: %s", settings.knowledge_dir)
    return observer
