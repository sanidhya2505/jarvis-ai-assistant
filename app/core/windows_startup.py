"""
Windows startup integration (spec section 7).

Uses the Windows Startup folder approach (simpler and more transparent to
the user than a hidden Task Scheduler entry, and doesn't require admin
rights). Creates/removes a .lnk shortcut pointing at run_jarvis.py via
pythonw.exe (no console window).

Only does anything on Windows; on other platforms these functions are
no-ops with a log message, so the rest of the app still runs fine during
development on macOS/Linux.
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

from app.core.logging_config import get_logger

logger = get_logger("jarvis.core")

SHORTCUT_NAME = "JARVIS.lnk"


def _startup_folder() -> Path | None:
    if sys.platform != "win32":
        return None
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def is_enabled() -> bool:
    folder = _startup_folder()
    if not folder:
        return False
    return (folder / SHORTCUT_NAME).exists()


def enable_start_with_windows(project_root: Path) -> bool:
    folder = _startup_folder()
    if not folder:
        logger.info("Auto-start is only implemented for Windows; skipping on this platform.")
        return False

    try:
        import win32com.client  # pywin32
    except Exception as exc:
        logger.error("pywin32 not available (%s) — cannot create Startup shortcut", exc)
        return False

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    target = pythonw if pythonw.exists() else Path(sys.executable)
    script = project_root / "run_jarvis.py"

    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(str(folder / SHORTCUT_NAME))
    shortcut.Targetpath = str(target)
    shortcut.Arguments = f'"{script}"'
    shortcut.WorkingDirectory = str(project_root)
    shortcut.WindowStyle = 7  # minimized
    shortcut.IconLocation = str(target)
    shortcut.save()

    logger.info("Created Windows Startup shortcut at %s", folder / SHORTCUT_NAME)
    return True


def disable_start_with_windows() -> bool:
    folder = _startup_folder()
    if not folder:
        return False
    shortcut_path = folder / SHORTCUT_NAME
    if shortcut_path.exists():
        shortcut_path.unlink()
        logger.info("Removed Windows Startup shortcut")
        return True
    return False
