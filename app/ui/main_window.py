"""
JARVIS desktop UI (PySide6).

Talks to the local FastAPI backend over HTTP (127.0.0.1:{api_port}) rather
than importing the backend modules directly — this keeps UI and backend
decoupled per the architecture diagram (spec section 10), and means the
same backend could later serve a web or mobile client unchanged.

Dark, minimal, glass-card styling per spec section 18 (implemented with Qt
stylesheets — no external theme dependency).
"""
from __future__ import annotations

import sys
import requests

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem, QTabWidget,
    QProgressBar, QFileDialog, QMessageBox, QTextEdit,
)

from app.config.settings import get_settings

settings = get_settings()
API_BASE = f"http://{settings.api_host}:{settings.api_port}"

DARK_STYLESHEET = """
QMainWindow, QWidget { background-color: #0f1115; color: #e6e6e6; font-family: 'Segoe UI', sans-serif; }
QLabel#Title { font-size: 22px; font-weight: 600; color: #ffffff; }
QLabel#SubTitle { font-size: 13px; color: #9aa0ab; }
QFrame, QWidget#Card {
    background-color: #171a21; border: 1px solid #262b36; border-radius: 12px;
}
QPushButton {
    background-color: #2563eb; color: white; border-radius: 8px; padding: 8px 14px;
    font-weight: 500;
}
QPushButton:hover { background-color: #3b82f6; }
QLineEdit, QTextEdit {
    background-color: #1c202a; border: 1px solid #2b3040; border-radius: 8px;
    padding: 8px; color: #e6e6e6;
}
QListWidget { background-color: #171a21; border: 1px solid #262b36; border-radius: 10px; }
QTabWidget::pane { border: none; }
QTabBar::tab {
    background: #171a21; padding: 8px 16px; color: #9aa0ab; border-top-left-radius: 8px; border-top-right-radius: 8px;
}
QTabBar::tab:selected { background: #2563eb; color: white; }
QProgressBar { background-color: #1c202a; border-radius: 6px; text-align: center; color: white; }
QProgressBar::chunk { background-color: #22c55e; border-radius: 6px; }
"""


def _api_get(path: str, params: dict | None = None):
    try:
        resp = requests.get(f"{API_BASE}{path}", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        return {"error": str(exc)}


def _api_post(path: str, json: dict | None = None):
    try:
        resp = requests.post(f"{API_BASE}{path}", json=json, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        return {"error": str(exc)}


class DashboardTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        header = QHBoxLayout()
        greeting = QLabel(f"Good day, {settings.user_name}")
        greeting.setObjectName("Title")
        header.addWidget(greeting)
        header.addStretch()
        layout.addLayout(header)

        self.progress_label = QLabel("Today's Progress")
        self.progress_label.setObjectName("SubTitle")
        layout.addWidget(self.progress_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        tasks_label = QLabel("Today's Tasks")
        tasks_label.setObjectName("SubTitle")
        layout.addWidget(tasks_label)
        self.task_list = QListWidget()
        layout.addWidget(self.task_list)

        briefing_label = QLabel("Daily Briefing")
        briefing_label.setObjectName("SubTitle")
        layout.addWidget(briefing_label)
        self.briefing_box = QTextEdit()
        self.briefing_box.setReadOnly(True)
        self.briefing_box.setMaximumHeight(160)
        layout.addWidget(self.briefing_box)

        ask_row = QHBoxLayout()
        self.ask_input = QLineEdit()
        self.ask_input.setPlaceholderText("Ask JARVIS...")
        self.ask_input.returnPressed.connect(self.ask_jarvis)
        ask_button = QPushButton("Send")
        ask_button.clicked.connect(self.ask_jarvis)
        ask_row.addWidget(self.ask_input)
        ask_row.addWidget(ask_button)
        layout.addLayout(ask_row)

        self.answer_box = QTextEdit()
        self.answer_box.setReadOnly(True)
        self.answer_box.setMaximumHeight(140)
        layout.addWidget(self.answer_box)

        self.refresh()

    def refresh(self):
        tasks = _api_get("/api/tasks/today")
        self.task_list.clear()
        if isinstance(tasks, list):
            done = sum(1 for t in tasks if t["status"] == "Completed")
            self.progress_bar.setValue(int(100 * done / len(tasks)) if tasks else 0)
            for t in tasks:
                mark = "✓" if t["status"] == "Completed" else ("◉" if t["status"] == "In Progress" else "○")
                self.task_list.addItem(QListWidgetItem(f"{mark}  {t['title']}  ({t['priority']})"))

        briefing = _api_get("/api/assistant/briefing")
        if "text" in briefing:
            self.briefing_box.setPlainText(briefing["text"])

    def ask_jarvis(self):
        text = self.ask_input.text().strip()
        if not text:
            return
        self.answer_box.setPlainText("Thinking...")
        result = _api_post("/api/assistant/command", {"text": text})
        self.answer_box.setPlainText(result.get("message", result.get("error", "No response.")))
        self.ask_input.clear()
        self.refresh()


class TasksTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        add_row = QHBoxLayout()
        self.new_task_input = QLineEdit()
        self.new_task_input.setPlaceholderText(
            "e.g. Add task: Complete ML playlist on September 18 at 8 PM, high priority"
        )
        self.new_task_input.returnPressed.connect(self.add_task)
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self.add_task)
        add_row.addWidget(self.new_task_input)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        self.task_list = QListWidget()
        layout.addWidget(self.task_list)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(refresh_btn)

        self.refresh()

    def add_task(self):
        text = self.new_task_input.text().strip()
        if not text:
            return
        result = _api_post("/api/tasks/from-text", {"text": text})
        if result.get("created") is False:
            QMessageBox.information(self, "Need more detail", result.get("reason", "Ambiguous task."))
        self.new_task_input.clear()
        self.refresh()

    def refresh(self):
        tasks = _api_get("/api/tasks")
        self.task_list.clear()
        if isinstance(tasks, list):
            for t in tasks:
                due = t["due_date"] or "no due date"
                self.task_list.addItem(QListWidgetItem(f"[{t['status']}] {t['title']} — {due} ({t['priority']})"))


class KnowledgeBaseTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        upload_row = QHBoxLayout()
        upload_btn = QPushButton("Add File to Knowledge Base")
        upload_btn.clicked.connect(self.upload_file)
        upload_row.addWidget(upload_btn)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh)
        upload_row.addWidget(refresh_btn)
        layout.addLayout(upload_row)

        self.file_list = QListWidget()
        layout.addWidget(self.file_list)

        self.refresh()

    def upload_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select a file to add to your knowledge base")
        if not path:
            return
        try:
            with open(path, "rb") as f:
                requests.post(f"{API_BASE}/api/files/upload", files={"file": f}, timeout=60)
        except Exception as exc:
            QMessageBox.warning(self, "Upload failed", str(exc))
        self.refresh()

    def refresh(self):
        files = _api_get("/api/files")
        self.file_list.clear()
        if isinstance(files, list):
            for f in files:
                self.file_list.addItem(QListWidgetItem(
                    f"[{f['status']}] {f['filename']} — {f['num_chunks']} chunks"
                ))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JARVIS")
        self.resize(900, 700)
        self.setStyleSheet(DARK_STYLESHEET)

        tabs = QTabWidget()
        self.dashboard_tab = DashboardTab()
        tabs.addTab(self.dashboard_tab, "Dashboard")
        tabs.addTab(TasksTab(), "Tasks")
        tabs.addTab(KnowledgeBaseTab(), "Knowledge Base")
        self.setCentralWidget(tabs)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.dashboard_tab.refresh)
        self._refresh_timer.start(60_000)

    def closeEvent(self, event):
        if settings.minimize_to_tray_on_close:
            event.ignore()
            self.hide()
        else:
            event.accept()


def run_ui() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    window.show()

    from app.ui.tray import build_tray_icon
    tray = build_tray_icon(app, window)
    tray.show()

    sys.exit(app.exec())
