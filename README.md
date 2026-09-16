# JARVIS — Personal AI Desktop Assistant

A local-first, file-first personal assistant for Windows: task/calendar
management, a RAG knowledge base built from your own files, a natural
language + voice command interface, proactive reminders, and a daily
briefing — all backed by a local SQLite database and a local vector store.

This delivery covers **Phases 1–7** of the build plan end to end, with
real, tested code (no mocked/fake logic) plus a documented Phase 8
(testing/security hardening) checklist for what to do before daily use.

---

## 1. Architecture

```
JARVIS UI (PySide6, tabs: Dashboard / Tasks / Knowledge Base)
        │  HTTP (localhost only)
        ▼
FastAPI backend (app/api/app.py)
        │
  ┌─────┼──────────────┬──────────────┬───────────────┐
  ▼     ▼              ▼              ▼               ▼
Tasks  Calendar   Knowledge Engine  Command Router   Scheduler
  │     │          (RAG: parse →     (intent match →  (reminders,
  ▼     ▼           chunk → embed →   task/calendar/   overdue sweep,
SQLite (SQLAlchemy)  ChromaDB)        RAG/planner)     proactive alerts,
  │                       │                              file rescans)
  ▼                       ▼
Reminders/Activity    LLM client (OpenAI-compatible or
   log tables           Anthropic; "local" mode disables
                         AI text generation but keeps
                         tasks/calendar/file-search working)
```

The UI never touches the database directly — everything goes through the
local FastAPI service. This keeps the same backend usable from the voice
engine, a future web UI, or scripts/tests without duplicating logic.

## 2. Project layout

```
JARVIS/
├── app/
│   ├── config/settings.py       # all configuration, from .env
│   ├── core/                    # logging, briefing/planner, Windows startup
│   ├── database/                # SQLAlchemy engine + full schema
│   ├── tasks/                   # CRUD, NL parser, FastAPI router
│   ├── calendar/                # day/week/month views, conflict detection
│   ├── files/                   # parsers (pdf/docx/xlsx/pptx/csv/zip/img),
│   │                             # ingestion pipeline, folder watcher
│   ├── rag/                     # chunking, embeddings, vector store, retrieval
│   ├── ai/                      # LLM client, command router (intent dispatch)
│   ├── memory/                  # short/long-term/project memory
│   ├── scheduler/               # background jobs (reminders, proactive sweep)
│   ├── notifications/           # desktop notifications (plyer)
│   ├── voice/                   # STT/TTS, wake-word listener (modular)
│   └── ui/                      # PySide6 main window + system tray
├── data/                        # knowledge/, database/, vector_store/, memory/
├── logs/                        # jarvis.log, errors.log, ai.log, file_processor.log
├── tests/                       # pytest unit + integration tests
├── run_jarvis.py                # entry point
├── requirements.txt
└── .env.example
```

## 3. Setup

```bash
python -m venv venv
venv\Scripts\activate            # Windows
pip install -r requirements.txt
copy .env.example .env           # then edit .env with your LLM_API_KEY etc.
python run_jarvis.py
```

First run creates the SQLite database, the ChromaDB vector store, and
scans `data/knowledge/` for any files you've already dropped in.

To register JARVIS to start automatically when you log into Windows:

```bash
python run_jarvis.py --enable-startup
```

This creates a shortcut in your Windows Startup folder (no admin rights
needed). `--disable-startup` removes it.

## 4. Using it

- **Add files**: drop them into `data/knowledge/` (or use the Knowledge
  Base tab's "Add File" button). They're auto-detected, parsed, chunked,
  embedded, and indexed within ~2 minutes (or instantly if `watchdog` is
  available on your platform).
- **Ask questions**: use the "Ask JARVIS" bar, the tray's "Ask JARVIS", or
  voice ("Hey JARVIS, ..." once `ENABLE_VOICE=true`). Answers from your
  files are always preferred and cited by filename/page; if nothing
  relevant is found, JARVIS says so explicitly rather than guessing —
  see `app/rag/retrieval.py`.
- **Natural-language tasks**: "Add task: finish resume on September 20 at
  6 PM, high priority" is parsed into a structured task automatically. If
  the date is ambiguous, JARVIS asks for confirmation instead of guessing.
- **Daily briefing / smart plan**: available from the Dashboard tab, the
  tray menu, or by asking "give me my daily briefing" / "plan my day".

## 5. Testing

```bash
pytest                    # full suite
pytest --cov=app          # with coverage
```

19 tests currently cover: task CRUD + auto-reminders + overdue detection,
natural-language date/priority/recurrence parsing (including the
"date-fragmentation" edge case where a naive parser misreads "September 18
at 8 PM" — see the docstring in `app/tasks/nlp_parser.py`), RAG chunking,
and command-router intent dispatch. All were run against a real SQLite
database and a real (in-process) FastAPI server during development, not
just mocked — see the smoke-test transcript in the project history for
the exact `curl` calls exercised (task creation from text, listing,
command routing, briefing, and the daily planner all verified against
live HTTP responses).

## 6. Configuration reference

See `.env.example` for the full list. Key switches:

- `LLM_PROVIDER=local` disables AI-generated prose entirely. Tasks,
  calendar, reminders, and file search (returning raw matching excerpts)
  keep working fully offline — only the "make it sound natural" layer is
  skipped.
- `ENABLE_WEB_SEARCH=false` (default) — per the file-first rule, JARVIS
  will not silently blend in outside information; it only reaches beyond
  your files if you explicitly enable this.
- Embeddings fall back automatically to a local `sentence-transformers`
  model if no `LLM_API_KEY` is set, so semantic search never requires an
  API key or internet connection.

## 7. Known limitations (documented per spec section 27)

These are real, working features with a scoped implementation rather than
placeholders — noted here so you know exactly what to harden before
relying on JARVIS for anything safety-critical:

- **Wake-word detection** uses continuous local STT rather than a
  dedicated low-power wake-word engine (e.g. Porcupine). It works, but
  uses more CPU than a purpose-built wake-word model. Swapping it in
  later only touches `app/voice/voice_engine.py`.
- **Proactive alerts** (deadline/overdue/conflict warnings) don't yet
  track "already warned" state, so the same warning can repeat on the
  30-minute sweep interval until the task is resolved. Adding a
  `last_warned_at` column to `Task`/`CalendarEvent` is the natural next
  step.
- **Voice task editing** (delete/reschedule via free text) resolves "this
  task" to the most relevant task heuristically rather than tracking UI
  selection state — the command router intentionally asks for
  confirmation on delete rather than guessing.
- **OCR** (image files) requires `pytesseract` + the Tesseract binary
  installed separately on Windows; without it, images are still indexed
  by filename so they stay linkable to tasks.
- **ZIP ingestion** indexes text-based files inside the archive; binaries
  (compiled code, media) are listed by name only, not content-searchable.

## 8. Security notes

- No API keys are hardcoded; all secrets load from `.env` (git-ignored —
  see `.gitignore`).
- The FastAPI server binds to `127.0.0.1` only.
- Logs redact any line containing `api_key`/`authorization`/`bearer` markers.
- The database and vector store are local files under `data/`; nothing is
  uploaded anywhere unless you explicitly configure a cloud LLM provider
  and ask a question that needs it.
