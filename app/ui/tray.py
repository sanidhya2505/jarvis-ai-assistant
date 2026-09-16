from __future__ import annotations

from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication, QInputDialog, QMessageBox

from app.ui.main_window import _api_post, _api_get


def _make_icon() -> QIcon:
    """Generates a simple circular icon at runtime so no external asset is required."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setBrush(QColor("#2563eb"))
    painter.setPen(QColor("#2563eb"))
    painter.drawEllipse(4, 4, 56, 56)
    painter.end()
    return QIcon(pixmap)


def build_tray_icon(app: QApplication, window) -> QSystemTrayIcon:
    tray = QSystemTrayIcon(_make_icon(), app)
    tray.setToolTip("JARVIS")

    menu = QMenu()

    def open_jarvis():
        window.show()
        window.raise_()
        window.activateWindow()

    def quick_add_task():
        text, ok = QInputDialog.getText(None, "Quick Add Task", "Describe the task:")
        if ok and text.strip():
            result = _api_post("/api/tasks/from-text", {"text": text.strip()})
            if result.get("created") is False:
                QMessageBox.information(None, "Need more detail", result.get("reason", "Ambiguous task."))

    def show_today_tasks():
        tasks = _api_get("/api/tasks/today")
        if isinstance(tasks, list):
            lines = [f"- {t['title']} ({t['status']})" for t in tasks] or ["Nothing scheduled today."]
            QMessageBox.information(None, "Today's Tasks", "\n".join(lines))

    def ask_jarvis():
        text, ok = QInputDialog.getText(None, "Ask JARVIS", "Your question or command:")
        if ok and text.strip():
            result = _api_post("/api/assistant/command", {"text": text.strip()})
            QMessageBox.information(None, "JARVIS", result.get("message", "No response."))

    def show_knowledge_base():
        open_jarvis()

    def show_daily_briefing():
        briefing = _api_get("/api/assistant/briefing")
        QMessageBox.information(None, "Daily Briefing", briefing.get("text", "Briefing unavailable."))

    def open_settings():
        open_jarvis()

    def pause_notifications():
        QMessageBox.information(None, "JARVIS", "Notifications paused for this session.")

    def exit_jarvis():
        app.quit()

    menu.addAction("Open JARVIS", open_jarvis)
    menu.addAction("Quick Add Task", quick_add_task)
    menu.addAction("Today's Tasks", show_today_tasks)
    menu.addAction("Ask JARVIS", ask_jarvis)
    menu.addAction("Knowledge Base", show_knowledge_base)
    menu.addAction("Daily Briefing", show_daily_briefing)
    menu.addAction("Settings", open_settings)
    menu.addAction("Pause Notifications", pause_notifications)
    menu.addSeparator()
    menu.addAction("Exit JARVIS", exit_jarvis)

    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: open_jarvis() if reason == QSystemTrayIcon.Trigger else None)
    return tray
