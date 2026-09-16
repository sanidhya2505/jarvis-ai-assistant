"""
Main FastAPI app. This runs as JARVIS's local backend (bound to 127.0.0.1
only — never exposed externally) and is what both the desktop UI and the
voice engine talk to. Running the "brain" as a local HTTP service (rather
than baking everything directly into the UI) keeps the architecture in
spec section 10 modular: UI, voice, and any future client all go through
the same Command Router.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.logging_config import configure_logging, get_logger
from app.database.db import init_db
from app.scheduler.jobs import start_scheduler, stop_scheduler
from app.files.watcher import start_watchdog_observer, scan_knowledge_folder
from app.tasks.router import router as tasks_router
from app.calendar.router import router as calendar_router
from app.files.router import router as files_router
from app.ai.router import router as assistant_router

configure_logging()
logger = get_logger("jarvis.api")

_observer = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("JARVIS starting up...")
    init_db()
    scan_knowledge_folder()  # catch anything added while the app was closed
    start_scheduler()

    global _observer
    _observer = start_watchdog_observer()

    logger.info("JARVIS ready.")
    yield

    logger.info("JARVIS shutting down...")
    if _observer:
        _observer.stop()
        _observer.join(timeout=2)
    stop_scheduler()


app = FastAPI(title="JARVIS", version="1.0.0", lifespan=lifespan)

# Local-only UI (desktop webview / PySide6) talks over localhost; CORS is
# permissive for localhost origins only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:*", "http://localhost:*", "*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks_router)
app.include_router(calendar_router)
app.include_router(files_router)
app.include_router(assistant_router)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "JARVIS"}
