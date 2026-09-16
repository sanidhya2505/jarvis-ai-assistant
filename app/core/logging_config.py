"""
Structured logging for JARVIS.

Creates separate log files per subsystem (jarvis.log, errors.log, ai.log,
file_processor.log) so a failure in one component is easy to trace without
exposing secrets in the logs.
"""
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from app.config.settings import get_settings

_CONFIGURED = False


class _RedactSecretsFilter(logging.Filter):
    """Best-effort scrub of anything that looks like an API key."""

    REDACT_MARKERS = ("api_key", "apikey", "authorization", "bearer ")

    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.getMessage()).lower()
        if any(marker in msg for marker in self.REDACT_MARKERS):
            record.msg = "[redacted: message contained a potential secret]"
            record.args = ()
        return True


def _make_file_handler(path: Path, level: int) -> logging.Handler:
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    )
    handler.addFilter(_RedactSecretsFilter())
    return handler


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    logs_dir = settings.logs_dir
    logs_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(_make_file_handler(logs_dir / "jarvis.log", logging.INFO))
    root.addHandler(_make_file_handler(logs_dir / "errors.log", logging.ERROR))

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(levelname)-8s %(name)s: %(message)s"))
    root.addHandler(console)

    # Dedicated loggers for noisy/important subsystems
    ai_logger = logging.getLogger("jarvis.ai")
    ai_logger.addHandler(_make_file_handler(logs_dir / "ai.log", logging.INFO))

    files_logger = logging.getLogger("jarvis.files")
    files_logger.addHandler(_make_file_handler(logs_dir / "file_processor.log", logging.INFO))

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
