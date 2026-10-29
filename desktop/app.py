"""MYRA native desktop window (PySide6).

This is a real native operational shell for persistent Chat, Agent,
Skills, Memory, Notes, Settings and Diagnostics.  It does not claim to
have reproduced the full Three.js MALE/FEMALE hologram yet; the existing
web interface remains available while native visual parity is completed.
"""
import base64
import html
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import (
    QBuffer,
    QByteArray,
    QEvent,
    QIODevice,
    QObject,
    QRunnable,
    QThreadPool,
    QTimer,
    Qt,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .api_client import ApiClient, ApiError
from .particle_orb import ParticleOrb


ROOT = Path(__file__).resolve().parent.parent


def data_dir():
    configured = os.environ.get("MYRA_DATA_DIR", "").strip()
    if configured:
        path = Path(configured).expanduser()
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        path = Path(base) / "MYRA"
    else:
        path = Path.home() / ".local" / "share" / "MYRA"
    path.mkdir(parents=True, exist_ok=True)
    return path


class WorkerSignals(QObject):
    finished = Signal(object)
    error = Signal(str)


class ApiWorker(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()

    def run(self):
        try:
            self.signals.finished.emit(self.function())
        except Exception as exc:
            self.signals.error.emit(str(exc))


class MyraWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MYRA")
        self.resize(1380, 880)
        self.setMinimumSize(980, 640)
        icon_path = ROOT / "assets" / "myra.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.api = ApiClient()
        self.pool = QThreadPool.globalInstance()
        self.backend_process = None
        self._backend_log = None
        self.backend_ready = False
        self.current_conversation_id = None
        self.chat_messages = []
        self.chat_wait_cancelled = False
        self.current_task_id = None
        self.skills_by_id = {}
        self.current_skill_id = None
        self.current_memory_id = None
        self.current_note_id = None
        self.profile = {"assistant_name": "MYRA", "owner_name": "Boss", "personality": "Balanced"}
        self._agent_poll_inflight = False

        self._build_ui()
        self._apply_style()
        QTimer.singleShot(150, self.ensure_backend)

        self.agent_timer = QTimer(self)
        self.agent_timer.setInterval(1800)
        self.agent_timer.timeout.connect(self._poll_agent_task)
        self.agent_timer.start()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(225)
        side_layout = QVBoxLayout(sidebar)
        title = QLabel("MYRA")
        title.setObjectName("brand")
        title.setAlignment(Qt.AlignCenter)
        side_layout.addWidget(title)
        subtitle = QLabel("NATIVE DESKTOP • CORE 2.0")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        side_layout.addWidget(subtitle)
        self.orb = ParticleOrb()
        self.orb.setFixedHeight(190)
        side_layout.addWidget(self.orb)
        self.orb_caption = QLabel("CORE visual • full bust parity is a later native milestone")
        self.orb_caption.setWordWrap(True)
        self.orb_caption.setObjectName("hint")
        self.orb_caption.setAlignment(Qt.AlignCenter)
        side_layout.addWidget(self.orb_caption)

        form = QFormLayout()
        self.character_combo = QComboBox()
        self.character_combo.addItems(["CORE", "MALE", "FEMALE"])
        form.addRow("Character", self.character_combo)
        side_layout.addLayout(form)

        self.nav = QListWidget()
        self.nav.addItems(["Chat", "Agent", "Skills", "Memory", "Notes", "Settings", "Diagnostics"])
        self.nav.currentRowChanged.connect(self._nav_changed)
        side_layout.addWidget(self.nav, 1)
        self.status_label = QLabel("Starting MYRA backend…")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("status")
        side_layout.addWidget(self.status_label)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_chat_page())
        self.pages.addWidget(self._build_agent_page())
        self.pages.addWidget(self._build_skills_page())
        self.pages.addWidget(self._build_memory_page())
        self.pages.addWidget(self._build_notes_page())
        self.pages.addWidget(self._build_settings_page())
        self.pages.addWidget(self._build_diagnostics_page())

        layout.addWidget(sidebar)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self.nav.setCurrentRow(0)

    def _apply_style(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #02070c; color: #d7f7ff; font-family: Consolas, monospace; }
            QFrame#sidebar { background: #03101a; border: 1px solid #07556b; border-radius: 8px; }
            QLabel#brand { color: #57eaff; font-size: 31px; font-weight: 700; letter-spacing: 5px; }
            QLabel#subtitle, QLabel#hint { color: #6db8c9; font-size: 10px; }
            QLabel#status { color: #9fefff; border-top: 1px solid #07556b; padding-top: 8px; }
            QListWidget, QTextBrowser, QTextEdit, QPlainTextEdit, QLineEdit, QComboBox, QSpinBox {
                background: #02101b; color: #d9f8ff; border: 1px solid #07556b; border-radius: 5px; padding: 5px;
            }
            QListWidget::item { padding: 7px; }
            QListWidget::item:selected { background: #06475f; color: white; }
            QPushButton {
                background: #043044; color: #a8f3ff; border: 1px solid #0795b8; border-radius: 5px; padding: 6px 9px;
            }
            QPushButton:hover { background: #06536f; }
            QPushButton:disabled { color: #527d89; border-color: #24424c; }
            QCheckBox { spacing: 6px; }
            QSplitter::handle { background: #06475f; width: 3px; height: 3px; }
            """
        )

    def _nav_changed(self, index):
        self.pages.setCurrentIndex(index)
        if not self.backend_ready:
            return
        refreshers = {
            0: self.refresh_conversations,
            1: self.refresh_tasks,
            2: self.refresh_skills,
            3: self.refresh_memories,
            4: self.refresh_notes,
            5: self.refresh_settings,
            6: self.refresh_diagnostics,
        }
        action = refreshers.get(index)
        if action:
            action()

    # ------------------------------------------------------------------
    # Backend lifecycle / worker helpers
    # ------------------------------------------------------------------
    def set_status(self, text):
        self.status_label.setText(text)

    def run_api(self, function, success, failure_title="MYRA API error", status=None):
        if status:
            self.set_status(status)
        worker = ApiWorker(function)
        worker.signals.finished.connect(success)
        worker.signals.error.connect(lambda message: self._api_failed(failure_title, message))
        self.pool.start(worker)
        return worker

    def _api_failed(self, title, message):
        self.set_status(f"Backend error: {message}")
        QMessageBox.warning(self, title, message)

    def ensure_backend(self):
        def check():
            try:
                return self.api.get("/api/health", timeout=1)
            except ApiError:
                return None

        def checked(result):
            if result:
                self._backend_is_ready()
                return
            self._start_backend_process()

            def wait_for_backend():
                last = None
                for _ in range(50):
                    try:
                        return self.api.get("/api/health", timeout=1)
                    except ApiError as exc:
                        last = exc
                        time.sleep(0.2)
                raise ApiError(f"Backend did not start: {last}")

            self.run_api(wait_for_backend, lambda _result: self._backend_is_ready(), status="Waiting for backend…")

        self.run_api(check, checked, status="Checking MYRA backend…")

    def _start_backend_process(self):
        if self.backend_process and self.backend_process.poll() is None:
            return
        log_dir = data_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self._backend_log = (log_dir / "desktop-backend.log").open("ab")
        env = os.environ.copy()
        env.setdefault("MYRA_HOST", "127.0.0.1")
        env.setdefault("MYRA_PORT", "8765")
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--backend"]
            cwd = str(Path(sys.executable).parent)
        else:
            command = [sys.executable, str(ROOT / "run_desktop.py"), "--backend"]
            cwd = str(ROOT)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.backend_process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=self._backend_log,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )

    def _backend_is_ready(self):
        self.backend_ready = True
        self.set_status("Backend connected locally. Personal data stays on this computer.")
        self.refresh_conversations()
        self.refresh_settings()
        self.refresh_skills()
        self.refresh_memories()
        self.refresh_notes()
        self.refresh_tasks()
        self.refresh_diagnostics()

    def closeEvent(self, event):
        if self.backend_process and self.backend_process.poll() is None:
            self.backend_process.terminate()
            try:
                self.backend_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.backend_process.kill()
        if self._backend_log:
            self._backend_log.close()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Chat page
    # ------------------------------------------------------------------
    def _build_chat_page(self):
        page = QWidget()
        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Conversations"))
        self.conversation_list = QListWidget()
        self.conversation_list.itemSelectionChanged.connect(self._conversation_selected)
        left_layout.addWidget(self.conversation_list, 1)
        conv_buttons = QHBoxLayout()
        new_button = QPushButton("＋ New")
        new_button.clicked.connect(self.new_conversation)
        delete_button = QPushButton("Delete")
        delete_button.clicked.connect(self.delete_conversation)
        refresh_button = QPushButton("↻")
        refresh_button.clicked.connect(self.refresh_conversations)
        conv_buttons.addWidget(new_button)
        conv_buttons.addWidget(delete_button)
        conv_buttons.addWidget(refresh_button)
        left_layout.addLayout(conv_buttons)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.chat_view = QTextBrowser()
        self.chat_view.setOpenExternalLinks(True)
        right_layout.addWidget(self.chat_view, 1)
        self.chat_input = QPlainTextEdit()
        self.chat_input.setPlaceholderText("Message MYRA…  (Ctrl+Enter to send)")
        self.chat_input.setMaximumHeight(90)
        self.chat_input.installEventFilter(self)
        right_layout.addWidget(self.chat_input)
        buttons = QHBoxLayout()
        send_button = QPushButton("Send")
        send_button.clicked.connect(self.send_chat)
        stop_button = QPushButton("Stop waiting")
        stop_button.clicked.connect(self.stop_chat_waiting)
        regenerate_button = QPushButton("Regenerate")
        regenerate_button.clicked.connect(self.regenerate_chat)
        copy_button = QPushButton("Copy last reply")
        copy_button.clicked.connect(self.copy_last_reply)
        screenshot_button = QPushButton("Share one screenshot")
        screenshot_button.clicked.connect(self.share_screenshot)
        buttons.addWidget(send_button)
        buttons.addWidget(stop_button)
        buttons.addWidget(regenerate_button)
        buttons.addWidget(copy_button)
        buttons.addStretch(1)
        buttons.addWidget(screenshot_button)
        right_layout.addLayout(buttons)
        note = QLabel("Chat Mode never receives computer-control tools. One screenshot is sent only after the confirmation dialog.")
        note.setObjectName("hint")
        note.setWordWrap(True)
        right_layout.addWidget(note)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([280, 850])
        layout = QVBoxLayout(page)
        layout.addWidget(splitter)
        return page

    def eventFilter(self, watched, event):
        if watched is self.chat_input and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and (event.modifiers() & Qt.ControlModifier):
                self.send_chat()
                return True
        return super().eventFilter(watched, event)

    def refresh_conversations(self):
        if not self.backend_ready:
            return

        def done(result):
            selected = self.current_conversation_id
            self.conversation_list.blockSignals(True)
            self.conversation_list.clear()
            selected_item = None
            for conversation in result.get("conversations", []):
                item = QListWidgetItem(conversation.get("title") or "New conversation")
                item.setData(Qt.UserRole, conversation["id"])
                self.conversation_list.addItem(item)
                if conversation["id"] == selected:
                    selected_item = item
            if selected_item:
                self.conversation_list.setCurrentItem(selected_item)
            self.conversation_list.blockSignals(False)

        self.run_api(lambda: self.api.get("/api/v1/conversations"), done)

    def new_conversation(self):
        character = self.character_combo.currentText().lower()

        def done(result):
            conversation = result["conversation"]
            self.current_conversation_id = conversation["id"]
            self.chat_messages = []
            self._render_chat()
            self.refresh_conversations()

        self.run_api(
            lambda: self.api.post("/api/v1/conversations", {"character": character}),
            done,
            status="Creating conversation…",
        )

    def delete_conversation(self):
        if not self.current_conversation_id:
            return
        answer = QMessageBox.question(self, "Delete conversation", "Delete this saved conversation permanently?")
        if answer != QMessageBox.Yes:
            return
        conversation_id = self.current_conversation_id

        def done(_result):
            self.current_conversation_id = None
            self.chat_messages = []
            self._render_chat()
            self.refresh_conversations()

        self.run_api(lambda: self.api.delete(f"/api/v1/conversations/{conversation_id}"), done)

    def _conversation_selected(self):
        items = self.conversation_list.selectedItems()
        if not items:
            return
        conversation_id = items[0].data(Qt.UserRole)
        if conversation_id == self.current_conversation_id and self.chat_messages:
            return
        self.current_conversation_id = conversation_id

        def done(result):
            conversation = result["conversation"]
            self.chat_messages = conversation.get("messages", [])
            character = (conversation.get("character") or "core").upper()
            index = self.character_combo.findText(character)
            if index >= 0:
                self.character_combo.setCurrentIndex(index)
            self._render_chat()

        self.run_api(lambda: self.api.get(f"/api/v1/conversations/{conversation_id}"), done)

    def _render_chat(self):
        parts = []
        for message in self.chat_messages:
            role = "YOU" if message.get("role") == "user" else "MYRA"
            provider = ""
            if message.get("provider"):
                provider = f" <span style='color:#5da8bd'>({html.escape(str(message['provider']))} · {html.escape(str(message.get('model') or ''))})</span>"
            text = html.escape(message.get("content", "")).replace("\n", "<br>")
            parts.append(f"<p><b>{role}</b>{provider}<br>{text}</p><hr>")
        self.chat_view.setHtml("".join(parts) or "<p><i>No messages yet.</i></p>")
        scrollbar = self.chat_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def send_chat(self, forced_text=None):
        text = forced_text if isinstance(forced_text, str) else self.chat_input.toPlainText().strip()
        if not text:
            return
        self.chat_wait_cancelled = False
        payload = {
            "message": text,
            "conversation_id": self.current_conversation_id,
            "character": self.character_combo.currentText().lower(),
            **self.profile,
        }
        if not forced_text:
            self.chat_input.clear()
        self.set_status("MYRA is thinking…")

        def done(result):
            if self.chat_wait_cancelled:
                self.set_status("Stopped waiting locally; the non-streaming provider request may already have completed server-side.")
                return
            self.current_conversation_id = result.get("conversation_id")
            conversation_id = self.current_conversation_id
            self.run_api(
                lambda: self.api.get(f"/api/v1/conversations/{conversation_id}"),
                lambda full: self._loaded_after_chat(full),
            )

        self.run_api(lambda: self.api.post("/api/v1/chat", payload, timeout=100), done)

    def _loaded_after_chat(self, result):
        self.chat_messages = result["conversation"].get("messages", [])
        self._render_chat()
        self.refresh_conversations()
        self.set_status("Reply saved to persistent local chat history.")

    def stop_chat_waiting(self):
        self.chat_wait_cancelled = True
        self.set_status("Stop requested. Current providers are non-streaming, so MYRA can stop waiting locally but cannot cancel a request already at the provider.")

    def regenerate_chat(self):
        user_messages = [m for m in self.chat_messages if m.get("role") == "user"]
        if not user_messages:
            QMessageBox.information(self, "Nothing to regenerate", "Send a message first.")
            return
        self.send_chat(forced_text=user_messages[-1].get("content", ""))

    def copy_last_reply(self):
        replies = [m for m in self.chat_messages if m.get("role") == "assistant"]
        if not replies:
            return
        QGuiApplication.clipboard().setText(replies[-1].get("content", ""))
        self.set_status("Last reply copied.")

    def share_screenshot(self):
        prompt = self.chat_input.toPlainText().strip() or "Describe this screenshot and help me understand it."
        answer = QMessageBox.question(
            self,
            "Share one screenshot?",
            "MYRA will hide briefly, capture ONE screenshot, and send that single frame to the configured Gemini vision model. This is not continuous sharing. Continue?",
        )
        if answer != QMessageBox.Yes:
            return
        self.hide()
        QTimer.singleShot(400, lambda: self._capture_and_analyze(prompt))

    def _capture_and_analyze(self, prompt):
        try:
            screen = QGuiApplication.primaryScreen()
            if screen is None:
                raise RuntimeError("No display screen is available")
            pixmap = screen.grabWindow(0)
            if pixmap.width() > 1600:
                pixmap = pixmap.scaledToWidth(1600, Qt.SmoothTransformation)
            byte_array = QByteArray()
            buffer = QBuffer(byte_array)
            buffer.open(QIODevice.WriteOnly)
            if not pixmap.save(buffer, "JPG", 80):
                raise RuntimeError("Could not encode screenshot")
            encoded = base64.b64encode(bytes(byte_array.data())).decode("ascii")
        finally:
            self.show()
            self.raise_()
            self.activateWindow()
        payload = {
            "image_base64": encoded,
            "mime_type": "image/jpeg",
            "prompt": prompt,
            "consent": True,
            "source": "screen",
        }

        def done(result):
            self.chat_messages.append(
                {
                    "role": "assistant",
                    "content": "SCREENSHOT ANALYSIS\n" + result.get("text", ""),
                    "provider": result.get("provider"),
                    "model": result.get("model"),
                }
            )
            self._render_chat()
            self.set_status("Single screenshot analyzed; no continuous capture is running.")

        self.run_api(
            lambda: self.api.post("/api/v1/vision/analyze", payload, timeout=100),
            done,
            status="Analyzing one explicit screenshot…",
        )

    # ------------------------------------------------------------------
    # Agent page
    # ------------------------------------------------------------------
    def _build_agent_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        warning = QLabel("AGENT MODE — registered safe skills only. Write/launch/open actions stop for confirmation unless this task is explicitly pre-approved.")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self.agent_goal = QPlainTextEdit()
        self.agent_goal.setPlaceholderText("Example: Create a note called Shopping with rice and lentils")
        self.agent_goal.setMaximumHeight(80)
        layout.addWidget(self.agent_goal)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Max steps"))
        self.agent_steps = QSpinBox()
        self.agent_steps.setRange(1, 12)
        self.agent_steps.setValue(6)
        controls.addWidget(self.agent_steps)
        self.agent_preapprove = QCheckBox("Approve all registered skill actions in this task")
        controls.addWidget(self.agent_preapprove)
        start = QPushButton("Create & Start")
        start.clicked.connect(self.start_agent_task)
        controls.addWidget(start)
        controls.addStretch(1)
        layout.addLayout(controls)

        splitter = QSplitter(Qt.Horizontal)
        self.task_list = QListWidget()
        self.task_list.itemSelectionChanged.connect(self._task_selected)
        splitter.addWidget(self.task_list)
        self.task_detail = QTextEdit()
        self.task_detail.setReadOnly(True)
        splitter.addWidget(self.task_detail)
        splitter.setSizes([320, 800])
        layout.addWidget(splitter, 1)

        buttons = QHBoxLayout()
        for label, action in [
            ("Approve pending", "approve"),
            ("Deny", "deny"),
            ("Pause", "pause"),
            ("Resume", "resume"),
            ("Cancel / Emergency stop", "cancel"),
        ]:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, a=action: self.agent_action(a))
            buttons.addWidget(button)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_tasks)
        buttons.addWidget(refresh)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return page

    def start_agent_task(self):
        goal = self.agent_goal.toPlainText().strip()
        if not goal:
            QMessageBox.information(self, "Goal needed", "Describe the task first.")
            return
        payload = {
            "goal": goal,
            "max_steps": self.agent_steps.value(),
            "approval_mode": "allow_all" if self.agent_preapprove.isChecked() else "ask",
            "start": True,
        }

        def done(result):
            self.current_task_id = result["task"]["id"]
            self._render_task(result["task"])
            self.refresh_tasks()

        self.run_api(lambda: self.api.post("/api/v1/agent/tasks", payload), done, status="Agent task started…")

    def refresh_tasks(self):
        if not self.backend_ready:
            return

        def done(result):
            current = self.current_task_id
            self.task_list.blockSignals(True)
            self.task_list.clear()
            selected = None
            for task in result.get("tasks", []):
                item = QListWidgetItem(f"[{task['status']}] {task['goal'][:70]}")
                item.setData(Qt.UserRole, task["id"])
                self.task_list.addItem(item)
                if task["id"] == current:
                    selected = item
                    self._render_task(task)
            if selected:
                self.task_list.setCurrentItem(selected)
            self.task_list.blockSignals(False)

        self.run_api(lambda: self.api.get("/api/v1/agent/tasks"), done)

    def _task_selected(self):
        items = self.task_list.selectedItems()
        if not items:
            return
        self.current_task_id = items[0].data(Qt.UserRole)
        task_id = self.current_task_id
        self.run_api(
            lambda: self.api.get(f"/api/v1/agent/tasks/{task_id}"),
            lambda result: self._render_task(result["task"]),
        )

    def _render_task(self, task):
        lines = [
            f"Status: {task.get('status')}",
            f"Goal: {task.get('goal')}",
            f"Budget: {len(task.get('steps') or [])}/{task.get('max_steps')} steps",
            "",
        ]
        if task.get("pending"):
            lines.extend(["⚠ CONFIRMATION REQUIRED", json.dumps(task["pending"], indent=2, ensure_ascii=False), ""])
        if task.get("error"):
            lines.extend([f"Error: {task['error']}", ""])
        lines.append("Steps:")
        for step in task.get("steps") or []:
            lines.append(f"{step.get('index')}. {step.get('skill_id')} — {step.get('status')}")
            lines.append("   " + json.dumps(step.get("result"), ensure_ascii=False)[:1200])
        if task.get("final_summary"):
            lines.extend(["", "Final summary:", task["final_summary"]])
        self.task_detail.setPlainText("\n".join(lines))

    def agent_action(self, action):
        if not self.current_task_id:
            QMessageBox.information(self, "No task selected", "Select an Agent task first.")
            return
        task_id = self.current_task_id

        def done(result):
            self._render_task(result["task"])
            self.refresh_tasks()

        self.run_api(
            lambda: self.api.post(f"/api/v1/agent/tasks/{task_id}/{action}", {}),
            done,
            status=f"Agent {action} requested…",
        )

    def _poll_agent_task(self):
        if not self.backend_ready or not self.current_task_id or self._agent_poll_inflight:
            return
        if self.pages.currentIndex() != 1:
            return
        self._agent_poll_inflight = True
        task_id = self.current_task_id

        def done(result):
            self._agent_poll_inflight = False
            self._render_task(result["task"])

        def failed(_message):
            self._agent_poll_inflight = False

        worker = ApiWorker(lambda: self.api.get(f"/api/v1/agent/tasks/{task_id}", timeout=10))
        worker.signals.finished.connect(done)
        worker.signals.error.connect(failed)
        self.pool.start(worker)

    # ------------------------------------------------------------------
    # Skills page
    # ------------------------------------------------------------------
    def _build_skills_page(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        self.skill_list = QListWidget()
        self.skill_list.itemSelectionChanged.connect(self._skill_selected)
        layout.addWidget(self.skill_list, 1)
        right = QVBoxLayout()
        self.skill_enabled = QCheckBox("Skill enabled")
        self.skill_enabled.stateChanged.connect(self._skill_enabled_changed)
        right.addWidget(self.skill_enabled)
        self.skill_detail = QTextEdit()
        self.skill_detail.setReadOnly(True)
        right.addWidget(self.skill_detail, 2)
        right.addWidget(QLabel("Arguments JSON"))
        self.skill_args = QPlainTextEdit("{}")
        self.skill_args.setMaximumHeight(90)
        right.addWidget(self.skill_args)
        self.skill_confirm = QCheckBox("I confirm this direct skill run")
        right.addWidget(self.skill_confirm)
        run_button = QPushButton("Run selected skill")
        run_button.clicked.connect(self.run_skill)
        right.addWidget(run_button)
        self.skill_result = QTextEdit()
        self.skill_result.setReadOnly(True)
        right.addWidget(self.skill_result, 1)
        layout.addLayout(right, 2)
        return page

    def refresh_skills(self):
        if not self.backend_ready:
            return

        def done(result):
            self.skill_list.blockSignals(True)
            self.skill_list.clear()
            self.skills_by_id = {}
            selected = None
            for skill in result.get("skills", []):
                self.skills_by_id[skill["id"]] = skill
                item = QListWidgetItem(f"{skill['id']} — {skill['name']}")
                item.setData(Qt.UserRole, skill["id"])
                self.skill_list.addItem(item)
                if skill["id"] == self.current_skill_id:
                    selected = item
            if selected:
                self.skill_list.setCurrentItem(selected)
                self._show_skill(self.current_skill_id)
            self.skill_list.blockSignals(False)

        self.run_api(lambda: self.api.get("/api/v1/skills"), done)

    def _show_skill(self, skill_id):
        skill = self.skills_by_id.get(skill_id)
        if not skill:
            return
        self.current_skill_id = skill_id
        self.skill_enabled.blockSignals(True)
        self.skill_enabled.setChecked(bool(skill.get("enabled")))
        self.skill_enabled.blockSignals(False)
        self.skill_detail.setPlainText(json.dumps(skill, indent=2, ensure_ascii=False))
        self.skill_confirm.setChecked(False)

    def _skill_selected(self):
        items = self.skill_list.selectedItems()
        if items:
            self._show_skill(items[0].data(Qt.UserRole))

    def _skill_enabled_changed(self, _state):
        if not self.current_skill_id:
            return
        skill_id = self.current_skill_id
        enabled = self.skill_enabled.isChecked()
        self.run_api(
            lambda: self.api.post(f"/api/v1/skills/{skill_id}/enabled", {"enabled": enabled}),
            lambda _result: self.refresh_skills(),
        )

    def run_skill(self):
        if not self.current_skill_id:
            return
        try:
            arguments = json.loads(self.skill_args.toPlainText() or "{}")
            if not isinstance(arguments, dict):
                raise ValueError("Arguments must be a JSON object")
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid JSON", str(exc))
            return
        skill_id = self.current_skill_id
        payload = {"arguments": arguments, "confirmed": self.skill_confirm.isChecked()}

        def done(result):
            self.skill_result.setPlainText(json.dumps(result, indent=2, ensure_ascii=False))

        self.run_api(lambda: self.api.post(f"/api/v1/skills/{skill_id}/run", payload), done)

    # ------------------------------------------------------------------
    # Memory page
    # ------------------------------------------------------------------
    def _build_memory_page(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        left = QVBoxLayout()
        self.memory_search = QLineEdit()
        self.memory_search.setPlaceholderText("Search memories")
        self.memory_search.returnPressed.connect(self.refresh_memories)
        left.addWidget(self.memory_search)
        self.memory_list = QListWidget()
        self.memory_list.itemSelectionChanged.connect(self._memory_selected)
        left.addWidget(self.memory_list, 1)
        refresh = QPushButton("Search / Refresh")
        refresh.clicked.connect(self.refresh_memories)
        left.addWidget(refresh)
        layout.addLayout(left, 1)

        right = QVBoxLayout()
        self.memory_text = QPlainTextEdit()
        self.memory_text.setPlaceholderText("A fact you explicitly want MYRA to remember")
        right.addWidget(self.memory_text, 1)
        form = QFormLayout()
        self.memory_category = QLineEdit("general")
        self.memory_pinned = QCheckBox("Pinned")
        form.addRow("Category", self.memory_category)
        form.addRow("", self.memory_pinned)
        right.addLayout(form)
        buttons = QHBoxLayout()
        for label, action in [("Add memory", self.add_memory), ("Save changes", self.save_memory), ("Delete", self.delete_memory)]:
            button = QPushButton(label)
            button.clicked.connect(action)
            buttons.addWidget(button)
        right.addLayout(buttons)
        layout.addLayout(right, 1)
        return page

    def refresh_memories(self):
        if not self.backend_ready:
            return
        query = self.memory_search.text().strip() if hasattr(self, "memory_search") else ""
        path = f"/api/v1/memories?query={QUrl.toPercentEncoding(query).data().decode()}" if query else "/api/v1/memories"

        def done(result):
            self.memory_list.blockSignals(True)
            self.memory_list.clear()
            for memory in result.get("memories", []):
                item = QListWidgetItem(memory["text"][:90])
                item.setData(Qt.UserRole, memory)
                self.memory_list.addItem(item)
            self.memory_list.blockSignals(False)

        self.run_api(lambda: self.api.get(path), done)

    def _memory_selected(self):
        items = self.memory_list.selectedItems()
        if not items:
            return
        memory = items[0].data(Qt.UserRole)
        self.current_memory_id = memory["id"]
        self.memory_text.setPlainText(memory.get("text", ""))
        self.memory_category.setText(memory.get("category", "general"))
        self.memory_pinned.setChecked(bool(memory.get("pinned")))

    def add_memory(self):
        payload = {
            "text": self.memory_text.toPlainText().strip(),
            "category": self.memory_category.text().strip() or "general",
            "pinned": self.memory_pinned.isChecked(),
        }
        self.run_api(lambda: self.api.post("/api/v1/memories", payload), lambda _r: self.refresh_memories())

    def save_memory(self):
        if not self.current_memory_id:
            return
        payload = {
            "text": self.memory_text.toPlainText().strip(),
            "category": self.memory_category.text().strip() or "general",
            "pinned": self.memory_pinned.isChecked(),
        }
        memory_id = self.current_memory_id
        self.run_api(lambda: self.api.put(f"/api/v1/memories/{memory_id}", payload), lambda _r: self.refresh_memories())

    def delete_memory(self):
        if not self.current_memory_id:
            return
        if QMessageBox.question(self, "Delete memory", "Delete this memory permanently?") != QMessageBox.Yes:
            return
        memory_id = self.current_memory_id
        self.run_api(lambda: self.api.delete(f"/api/v1/memories/{memory_id}"), lambda _r: self.refresh_memories())

    # ------------------------------------------------------------------
    # Notes page
    # ------------------------------------------------------------------
    def _build_notes_page(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        self.note_list = QListWidget()
        self.note_list.itemSelectionChanged.connect(self._note_selected)
        layout.addWidget(self.note_list, 1)
        right = QVBoxLayout()
        self.note_title = QLineEdit()
        self.note_title.setPlaceholderText("Note title")
        right.addWidget(self.note_title)
        self.note_body = QPlainTextEdit()
        right.addWidget(self.note_body, 1)
        buttons = QHBoxLayout()
        for label, action in [("New", self.new_note), ("Save", self.save_note), ("Delete", self.delete_note), ("Refresh", self.refresh_notes)]:
            button = QPushButton(label)
            button.clicked.connect(action)
            buttons.addWidget(button)
        right.addLayout(buttons)
        layout.addLayout(right, 2)
        return page

    def refresh_notes(self):
        if not self.backend_ready:
            return

        def done(result):
            self.note_list.blockSignals(True)
            self.note_list.clear()
            for note in result.get("notes", []):
                item = QListWidgetItem(note["title"])
                item.setData(Qt.UserRole, note)
                self.note_list.addItem(item)
            self.note_list.blockSignals(False)

        self.run_api(lambda: self.api.get("/api/v1/notes"), done)

    def _note_selected(self):
        items = self.note_list.selectedItems()
        if not items:
            return
        note = items[0].data(Qt.UserRole)
        self.current_note_id = note["id"]
        self.note_title.setText(note.get("title", ""))
        self.note_body.setPlainText(note.get("body", ""))

    def new_note(self):
        self.current_note_id = None
        self.note_title.clear()
        self.note_body.clear()

    def save_note(self):
        payload = {"title": self.note_title.text().strip(), "body": self.note_body.toPlainText()}
        if self.current_note_id:
            note_id = self.current_note_id
            self.run_api(lambda: self.api.put(f"/api/v1/notes/{note_id}", payload), lambda _r: self.refresh_notes())
        else:
            self.run_api(lambda: self.api.post("/api/v1/notes", payload), lambda _r: self.refresh_notes())

    def delete_note(self):
        if not self.current_note_id:
            return
        if QMessageBox.question(self, "Delete note", "Delete this note permanently?") != QMessageBox.Yes:
            return
        note_id = self.current_note_id
        self.run_api(lambda: self.api.delete(f"/api/v1/notes/{note_id}"), lambda _r: (self.new_note(), self.refresh_notes()))

    # ------------------------------------------------------------------
    # Settings page
    # ------------------------------------------------------------------
    def _build_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("API keys are saved locally. MYRA only displays masked status, never a saved full key."))
        form = QFormLayout()
        self.gemini_key_input = QLineEdit()
        self.gemini_key_input.setEchoMode(QLineEdit.Password)
        self.groq_key_input = QLineEdit()
        self.groq_key_input.setEchoMode(QLineEdit.Password)
        self.gemini_key_status = QLabel("Gemini: checking…")
        self.groq_key_status = QLabel("Groq: checking…")
        form.addRow("New Gemini key", self.gemini_key_input)
        form.addRow("", self.gemini_key_status)
        form.addRow("New Groq key", self.groq_key_input)
        form.addRow("", self.groq_key_status)
        layout.addLayout(form)
        key_buttons = QHBoxLayout()
        save_keys = QPushButton("Save entered key(s)")
        save_keys.clicked.connect(self.save_keys)
        remove_gemini = QPushButton("Remove Gemini")
        remove_gemini.clicked.connect(lambda: self.remove_key("gemini"))
        remove_groq = QPushButton("Remove Groq")
        remove_groq.clicked.connect(lambda: self.remove_key("groq"))
        key_buttons.addWidget(save_keys)
        key_buttons.addWidget(remove_gemini)
        key_buttons.addWidget(remove_groq)
        key_buttons.addStretch(1)
        layout.addLayout(key_buttons)

        layout.addWidget(QLabel("Profile and provider models"))
        profile_form = QFormLayout()
        self.assistant_name_input = QLineEdit("MYRA")
        self.owner_name_input = QLineEdit("Boss")
        self.personality_combo = QComboBox()
        self.personality_combo.addItems(["Balanced", "Professional", "Friendly", "Romantic", "Funny"])
        self.gemini_model_input = QLineEdit()
        self.gemini_model_input.setPlaceholderText("Blank = MYRA default")
        self.groq_model_input = QLineEdit()
        self.groq_model_input.setPlaceholderText("Blank = MYRA default")
        profile_form.addRow("Assistant name", self.assistant_name_input)
        profile_form.addRow("Owner name", self.owner_name_input)
        profile_form.addRow("Personality", self.personality_combo)
        profile_form.addRow("Gemini model", self.gemini_model_input)
        profile_form.addRow("Groq model", self.groq_model_input)
        layout.addLayout(profile_form)
        save_profile = QPushButton("Save profile & models")
        save_profile.clicked.connect(self.save_profile_models)
        layout.addWidget(save_profile)
        self.provider_detail = QTextEdit()
        self.provider_detail.setReadOnly(True)
        layout.addWidget(self.provider_detail, 1)
        return page

    def refresh_settings(self):
        if not self.backend_ready:
            return

        def load():
            return {
                "keys": self.api.get("/api/settings/keys"),
                "preferences": self.api.get("/api/v1/preferences"),
                "providers": self.api.get("/api/v1/providers"),
            }

        def done(result):
            keys = (result.get("keys") or {}).get("keys") or {}
            gemini = keys.get("gemini") or {}
            groq = keys.get("groq") or {}
            self.gemini_key_status.setText(
                f"Gemini: {'saved ' + gemini.get('masked', '') if gemini.get('set') else 'not saved'} ({gemini.get('storage', 'unknown')})"
            )
            self.groq_key_status.setText(
                f"Groq: {'saved ' + groq.get('masked', '') if groq.get('set') else 'not saved'} ({groq.get('storage', 'unknown')})"
            )
            preferences = (result.get("preferences") or {}).get("preferences") or {}
            profile = preferences.get("profile") or {}
            if profile:
                self.profile.update(profile)
                self.assistant_name_input.setText(self.profile.get("assistant_name", "MYRA"))
                self.owner_name_input.setText(self.profile.get("owner_name", "Boss"))
                idx = self.personality_combo.findText(self.profile.get("personality", "Balanced"))
                if idx >= 0:
                    self.personality_combo.setCurrentIndex(idx)
            models = preferences.get("provider_models") or {}
            self.gemini_model_input.setText(models.get("gemini", ""))
            self.groq_model_input.setText(models.get("groq", ""))
            self.provider_detail.setPlainText(json.dumps(result.get("providers"), indent=2, ensure_ascii=False))

        self.run_api(load, done)

    def save_keys(self):
        payload = {}
        if self.gemini_key_input.text().strip():
            payload["gemini"] = self.gemini_key_input.text().strip()
        if self.groq_key_input.text().strip():
            payload["groq"] = self.groq_key_input.text().strip()
        if not payload:
            QMessageBox.information(self, "No key entered", "Paste a new key first. Saved keys are never shown back.")
            return

        def done(_result):
            self.gemini_key_input.clear()
            self.groq_key_input.clear()
            self.refresh_settings()
            self.set_status("API key saved locally.")

        self.run_api(lambda: self.api.post("/api/settings/keys", payload), done)

    def remove_key(self, which):
        if QMessageBox.question(self, "Remove API key", f"Remove the saved {which.title()} key?") != QMessageBox.Yes:
            return
        self.run_api(
            lambda: self.api.post("/api/settings/keys", {which: ""}),
            lambda _r: self.refresh_settings(),
        )

    def save_profile_models(self):
        self.profile = {
            "assistant_name": self.assistant_name_input.text().strip() or "MYRA",
            "owner_name": self.owner_name_input.text().strip() or "Boss",
            "personality": self.personality_combo.currentText(),
        }
        models = {}
        if self.gemini_model_input.text().strip():
            models["gemini"] = self.gemini_model_input.text().strip()
        if self.groq_model_input.text().strip():
            models["groq"] = self.groq_model_input.text().strip()

        def save():
            self.api.put("/api/v1/preferences/profile", {"value": self.profile})
            return self.api.put("/api/v1/preferences/provider_models", {"value": models})

        self.run_api(save, lambda _r: self.refresh_settings(), status="Saving profile and models…")

    # ------------------------------------------------------------------
    # Diagnostics page
    # ------------------------------------------------------------------
    def _build_diagnostics_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.diagnostics_text = QTextEdit()
        self.diagnostics_text.setReadOnly(True)
        layout.addWidget(self.diagnostics_text, 1)
        buttons = QHBoxLayout()
        refresh = QPushButton("Refresh diagnostics")
        refresh.clicked.connect(self.refresh_diagnostics)
        backup = QPushButton("Create SQLite backup")
        backup.clicked.connect(self.create_backup)
        export = QPushButton("Export JSON…")
        export.clicked.connect(self.export_json)
        open_workspace = QPushButton("Open workspace")
        open_workspace.clicked.connect(self.open_workspace)
        for button in (refresh, backup, export, open_workspace):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        note = QLabel("Voice status is honest: model storage is ready, but realtime native voice is not marked ready until Windows microphone/STT/TTS/interruption tests pass.")
        note.setWordWrap(True)
        note.setObjectName("hint")
        layout.addWidget(note)
        return page

    def refresh_diagnostics(self):
        if not self.backend_ready:
            return

        def load():
            return {
                "health": self.api.get("/api/v1/health"),
                "voice": self.api.get("/api/v1/voice/status"),
            }

        self.run_api(
            load,
            lambda result: self.diagnostics_text.setPlainText(json.dumps(result, indent=2, ensure_ascii=False)),
        )

    def create_backup(self):
        self.run_api(
            lambda: self.api.post("/api/v1/backup", {}),
            lambda result: QMessageBox.information(self, "Backup created", result.get("backup_path", "")),
        )

    def export_json(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Export MYRA data", "myra-export.json", "JSON (*.json)")
        if not filename:
            return

        def done(result):
            Path(filename).write_text(json.dumps(result.get("export"), indent=2, ensure_ascii=False), encoding="utf-8")
            QMessageBox.information(self, "Export complete", filename)

        self.run_api(lambda: self.api.get("/api/v1/export", timeout=60), done)

    def open_workspace(self):
        workspace = data_dir() / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(workspace)))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("MYRA")
    app.setOrganizationName("MYRA")
    window = MyraWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
