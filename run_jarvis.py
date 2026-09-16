"""
JARVIS entry point.

Run this to start the whole application:

    python run_jarvis.py            # normal start (API + UI + tray)
    python run_jarvis.py --no-ui    # headless: API + scheduler only (e.g. for testing)
    python run_jarvis.py --enable-startup   # register JARVIS to start with Windows, then exit

This is also what the Windows Startup shortcut (app/core/windows_startup.py)
points at via pythonw.exe, so JARVIS launches quietly on login.
"""
from __future__ import annotations

import sys
import threading
import time
import argparse
from pathlib import Path

import uvicorn

from app.config.settings import get_settings
from app.core.logging_config import configure_logging, get_logger

PROJECT_ROOT = Path(__file__).resolve().parent


def _run_api_server(host: str, port: int) -> None:
    from app.api.app import app as fastapi_app
    uvicorn.run(fastapi_app, host=host, port=port, log_level="warning")


def _wait_for_api(host: str, port: int, timeout: float = 15.0) -> bool:
    import requests
    deadline = time.time() + timeout
    url = f"http://{host}:{port}/api/health"
    while time.time() < deadline:
        try:
            if requests.get(url, timeout=1).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS personal assistant")
    parser.add_argument("--no-ui", action="store_true", help="Run the backend only, no desktop window")
    parser.add_argument("--enable-startup", action="store_true", help="Register JARVIS to start with Windows and exit")
    parser.add_argument("--disable-startup", action="store_true", help="Remove JARVIS from Windows startup and exit")
    args = parser.parse_args()

    configure_logging()
    logger = get_logger("jarvis.main")
    settings = get_settings()

    if args.enable_startup:
        from app.core.windows_startup import enable_start_with_windows
        enable_start_with_windows(PROJECT_ROOT)
        return
    if args.disable_startup:
        from app.core.windows_startup import disable_start_with_windows
        disable_start_with_windows()
        return

    api_thread = threading.Thread(
        target=_run_api_server, args=(settings.api_host, settings.api_port), daemon=True
    )
    api_thread.start()
    logger.info("API server starting on %s:%s...", settings.api_host, settings.api_port)

    if not _wait_for_api(settings.api_host, settings.api_port):
        logger.error("API server did not come up in time — exiting.")
        sys.exit(1)

    if args.no_ui:
        logger.info("Running headless (--no-ui). Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return

    from app.ui.main_window import run_ui
    run_ui()


if __name__ == "__main__":
    main()
