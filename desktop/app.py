"""MYRA native desktop window (pure Python / PySide6).

This is MYRA's primary interface: persistent Chat, Agent, realtime voice,
live sampled vision, web research, semantic Windows control, Skills,
Memory, Notes, Reminders, World headlines, Settings and Diagnostics.
The local backend runs in a daemon thread inside this same Python GUI
process — no browser window, Command Prompt, PowerShell or child Python
backend process is started.
"""
import base64
import html
import json
import os
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
from PySide6.QtGui import QDesktopServices, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
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
from .embedded_backend import EmbeddedBackend
from .particle_orb import HologramWidget
from .voice_tools import VoiceActivitySegmenter, pcm16_rms, wav_bytes


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


class StreamSignals(QObject):
    event = Signal(object)
    error = Signal(str)
    finished = Signal()


class StreamWorker(QRunnable):
    def __init__(self, iterator_factory):
        super().__init__()
        self.iterator_factory = iterator_factory
        self.signals = StreamSignals()

    def run(self):
        try:
            for event in self.iterator_factory():
                self.signals.event.emit(event)
            self.signals.finished.emit()
        except Exception as exc:
            self.signals.error.emit(str(exc))


class MyraWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MYRA")
        self.resize(1480, 900)
        self.setMinimumSize(1080, 660)
        icon_path = ROOT / "assets" / "myra.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.api = ApiClient()
        self.pool = QThreadPool.globalInstance()
        # Strong references to in-flight QRunnable workers.  PySide6 does
        # not keep the Python wrapper alive after QThreadPool.start(), so
        # without this set a worker can be garbage-collected before it
        # runs and its result would silently never be delivered.
        self._workers = set()
        self.embedded_backend = EmbeddedBackend(port=int(os.environ.get("MYRA_PORT", "8765") or 8765))
        self.backend_ready = False
        self.current_conversation_id = None
        self.chat_messages = []
        self.chat_wait_cancelled = False
        self._pending_chat_image = None
        self._streaming_text = ""
        self.current_task_id = None
        self.skills_by_id = {}
        self.current_skill_id = None
        self.current_memory_id = None
        self.current_note_id = None
        self.profile = {"assistant_name": "MYRA", "owner_name": "Boss", "personality": "Balanced"}
        self._agent_poll_inflight = False
        # Realtime voice / live vision runtime objects are created lazily
        # so MYRA still opens on machines without QtMultimedia devices.
        self._voice_active = False
        self._voice_source = None
        self._voice_io = None
        self._voice_segmenter = VoiceActivitySegmenter()
        self._voice_turn_inflight = False
        self._media_player = None
        self._audio_output = None
        self._live_session_id = None
        self._live_active = False
        self._live_paused = False
        self._live_timer = None
        self._camera = None
        self._camera_session = None
        self._camera_sink = None
        self._live_last_sent = 0.0
        self._live_inflight = False
        self._live_analyze_now = False
        self._live_analysis_count = 0
        self.current_reminder_id = None
        self._reminder_poll_inflight = False
        self._notified_reminders = set()

        self._build_ui()
        self._apply_style()
        QTimer.singleShot(150, self.ensure_backend)

        self.agent_timer = QTimer(self)
        self.agent_timer.setInterval(1800)
        self.agent_timer.timeout.connect(self._poll_agent_task)
        self.agent_timer.start()

        self.reminder_timer = QTimer(self)
        self.reminder_timer.setInterval(30000)
        self.reminder_timer.timeout.connect(self._poll_reminders)
        self.reminder_timer.start()

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
        sidebar.setFixedWidth(190)
        side_layout = QVBoxLayout(sidebar)
        title = QLabel("MYRA")
        title.setObjectName("brand")
        title.setAlignment(Qt.AlignCenter)
        side_layout.addWidget(title)
        subtitle = QLabel("PURE PYTHON • NATIVE")
        subtitle.setObjectName("subtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        side_layout.addWidget(subtitle)

        self.nav = QListWidget()
        self.nav.addItems([
            "Chat", "Agent", "Voice", "Live Vision", "Research", "Computer",
            "Skills", "Memory", "Notes", "Reminders", "World", "Settings", "Diagnostics",
        ])
        self.nav.currentRowChanged.connect(self._nav_changed)
        side_layout.addWidget(self.nav, 1)
        self.status_label = QLabel("Starting embedded Python backend…")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("status")
        side_layout.addWidget(self.status_label)

        visual = QFrame()
        visual.setObjectName("sidebar")
        visual.setFixedWidth(330)
        visual_layout = QVBoxLayout(visual)
        visual_title = QLabel("HOLOGRAM CORE")
        visual_title.setAlignment(Qt.AlignCenter)
        visual_layout.addWidget(visual_title)
        self.orb = HologramWidget()
        self.orb.setMinimumHeight(390)
        visual_layout.addWidget(self.orb, 1)
        self.orb_caption = QLabel("Native dotted CORE / MALE / FEMALE busts • drag to rotate • formation only on first open")
        self.orb_caption.setWordWrap(True)
        self.orb_caption.setObjectName("hint")
        self.orb_caption.setAlignment(Qt.AlignCenter)
        visual_layout.addWidget(self.orb_caption)
        form = QFormLayout()
        self.character_combo = QComboBox()
        self.character_combo.addItems(["CORE", "MALE", "FEMALE"])
        self.character_combo.currentTextChanged.connect(lambda text: self.orb.set_form(text.lower()))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Normal", "Friendly", "Hacker"])
        self.theme_combo.currentTextChanged.connect(self._theme_changed)
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["Auto", "Gemini", "Groq", "OpenRouter", "OpenAI", "Anthropic", "DeepSeek", "Mistral", "Ollama"])
        form.addRow("Character", self.character_combo)
        form.addRow("Theme", self.theme_combo)
        form.addRow("Provider", self.provider_combo)
        visual_layout.addLayout(form)
        self.control_banner = QLabel("")
        self.control_banner.setWordWrap(True)
        self.control_banner.setAlignment(Qt.AlignCenter)
        self.control_banner.setStyleSheet("color:#ffb3ba; border:1px solid #8f2432; border-radius:5px; padding:6px;")
        self.control_banner.hide()
        visual_layout.addWidget(self.control_banner)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_chat_page())
        self.pages.addWidget(self._build_agent_page())
        self.pages.addWidget(self._build_voice_page())
        self.pages.addWidget(self._build_live_vision_page())
        self.pages.addWidget(self._build_research_page())
        self.pages.addWidget(self._build_computer_page())
        self.pages.addWidget(self._build_skills_page())
        self.pages.addWidget(self._build_memory_page())
        self.pages.addWidget(self._build_notes_page())
        self.pages.addWidget(self._build_reminders_page())
        self.pages.addWidget(self._build_world_page())
        self.pages.addWidget(self._build_settings_page())
        self.pages.addWidget(self._build_diagnostics_page())

        layout.addWidget(sidebar)
        layout.addWidget(visual)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self.nav.setCurrentRow(0)

    def _apply_style(self, theme="normal"):
        style = """
            QMainWindow, QWidget { background: #02070c; color: #d7f7ff; font-family: Consolas, monospace; }
            QFrame#sidebar { background: #03101a; border: 1px solid #07556b; border-radius: 8px; }
            QLabel#brand { color: #57eaff; font-size: 31px; font-weight: 700; letter-spacing: 5px; }
            QLabel#subtitle, QLabel#hint { color: #6db8c9; font-size: 10px; }
            QLabel#status { color: #9fefff; border-top: 1px solid #07556b; padding-top: 8px; }
            QListWidget, QTextBrowser, QTextEdit, QPlainTextEdit, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
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
            QGroupBox { border: 1px solid #07556b; border-radius: 6px; margin-top: 10px; padding-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #57eaff; }
            QSplitter::handle { background: #06475f; width: 3px; height: 3px; }
            """
        palettes = {
            "friendly": {
                "#02070c": "#021006", "#03101a": "#031a0a", "#02101b": "#021508",
                "#07556b": "#126b32", "#57eaff": "#61ff9d", "#6db8c9": "#6fc98a",
                "#9fefff": "#a9ffc5", "#06475f": "#075c27", "#043044": "#043318",
                "#0795b8": "#20a84f", "#06536f": "#0a6e35", "#d7f7ff": "#dcffe8", "#d9f8ff": "#dcffe8",
            },
            "hacker": {
                "#02070c": "#100204", "#03101a": "#1a0308", "#02101b": "#150308",
                "#07556b": "#7b1220", "#57eaff": "#ff5268", "#6db8c9": "#c96d78",
                "#9fefff": "#ffb0b8", "#06475f": "#5c0714", "#043044": "#33040c",
                "#0795b8": "#a82035", "#06536f": "#6e0a1a", "#d7f7ff": "#ffe1e5", "#d9f8ff": "#ffe1e5",
            },
        }
        for old, new in palettes.get(str(theme).lower(), {}).items():
            style = style.replace(old, new)
        self.setStyleSheet(style)

    def _theme_changed(self, text):
        theme = str(text or "Normal").lower()
        self.orb.set_theme(theme)
        self._apply_style(theme)

    def _nav_changed(self, index):
        self.pages.setCurrentIndex(index)
        if not self.backend_ready:
            return
        refreshers = {
            0: self.refresh_conversations,
            1: self.refresh_tasks,
            2: self.refresh_voice_status,
            3: self.refresh_live_devices,
            5: self.refresh_computer_status,
            6: self.refresh_skills,
            7: self.refresh_memories,
            8: self.refresh_notes,
            9: self.refresh_reminders,
            10: self.refresh_world,
            11: self.refresh_settings,
            12: self.refresh_diagnostics,
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
        self._start_worker(worker)
        return worker

    def _start_worker(self, worker):
        """Start a QRunnable and keep it alive until it reports back."""
        self._workers.add(worker)

        def _release(_arg=None, _worker=worker):
            # Deferred one event-loop turn so the signals object is never
            # destroyed in the middle of its own emission.
            QTimer.singleShot(0, lambda: self._workers.discard(_worker))

        signals = getattr(worker, "signals", None)
        if signals is not None:
            for name in ("finished", "error"):
                signal = getattr(signals, name, None)
                if signal is not None:
                    signal.connect(_release)
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
            try:
                self.embedded_backend.start()
            except Exception as exc:
                self._api_failed("Embedded backend failed", f"MYRA could not start its in-process backend: {exc}")
                return

            def wait_for_backend():
                last = None
                for _ in range(50):
                    try:
                        return self.api.get("/api/health", timeout=1)
                    except ApiError as exc:
                        last = exc
                        time.sleep(0.2)
                raise ApiError(f"Embedded backend did not start: {last}")

            self.run_api(wait_for_backend, lambda _result: self._backend_is_ready(), status="Waiting for embedded backend…")

        self.run_api(check, checked, status="Checking embedded MYRA backend…")

    def _backend_is_ready(self):
        self.backend_ready = True
        self.set_status("Embedded Python backend connected locally. No browser/CMD/PowerShell process is used.")
        self.refresh_conversations()
        self.refresh_settings()
        self.refresh_skills()
        self.refresh_memories()
        self.refresh_notes()
        self.refresh_tasks()
        self.refresh_reminders()
        self.refresh_voice_status()
        self.refresh_computer_status()
        self.refresh_diagnostics()

    def closeEvent(self, event):
        try:
            self.stop_voice_session()
        except Exception:
            pass
        try:
            self._stop_live_local()
            if self._live_session_id:
                self.api.post(f"/api/v1/live-vision/sessions/{self._live_session_id}/stop", {}, timeout=3)
        except Exception:
            pass
        try:
            if self.backend_ready:
                self.api.post("/api/v1/windows/emergency-stop", {}, timeout=3)
        except Exception:
            pass
        try:
            self.embedded_backend.stop()
        except Exception:
            pass
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
        new_button = QPushButton("+ New")
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
        attach_button = QPushButton("Attach image…")
        attach_button.clicked.connect(self.attach_chat_image)
        buttons.addWidget(send_button)
        buttons.addWidget(stop_button)
        buttons.addWidget(regenerate_button)
        buttons.addWidget(copy_button)
        buttons.addStretch(1)
        buttons.addWidget(attach_button)
        buttons.addWidget(screenshot_button)
        right_layout.addLayout(buttons)
        self.chat_attachment_label = QLabel("No image attached")
        self.chat_attachment_label.setObjectName("hint")
        right_layout.addWidget(self.chat_attachment_label)
        note = QLabel("Chat Mode streams text when the selected provider supports it and never receives computer-control tools. Images/screenshots are sent only when you explicitly attach/share them.")
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

    def attach_chat_image(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Attach an image", "", "Images (*.jpg *.jpeg *.png *.webp)"
        )
        if not filename:
            return
        path = Path(filename)
        try:
            raw = path.read_bytes()
        except OSError as exc:
            QMessageBox.warning(self, "Could not read image", str(exc))
            return
        if len(raw) > 6 * 1024 * 1024:
            QMessageBox.warning(self, "Image too large", "Please choose an image under 6 MB.")
            return
        mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(path.suffix.lower())
        if not mime:
            QMessageBox.warning(self, "Unsupported image", "Use JPEG, PNG or WebP.")
            return
        self._pending_chat_image = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
        self.chat_attachment_label.setText(f"Attached: {path.name} ({len(raw)} bytes) — sent only with your next message")

    def send_chat(self, forced_text=None):
        text = forced_text if isinstance(forced_text, str) else self.chat_input.toPlainText().strip()
        if not text:
            return
        self.chat_wait_cancelled = False
        self._streaming_text = ""
        payload = {
            "message": text,
            "conversation_id": self.current_conversation_id,
            "character": self.character_combo.currentText().lower(),
            "provider": self.provider_combo.currentText().lower(),
            "image": self._pending_chat_image,
            **self.profile,
        }
        if not forced_text:
            self.chat_input.clear()
        self._pending_chat_image = None
        self.chat_attachment_label.setText("No image attached")
        self.chat_messages.append({"role": "user", "content": text})
        self.chat_messages.append({"role": "assistant", "content": ""})
        self._render_chat()
        self.orb.set_state("thinking")
        self.set_status("MYRA is thinking…")

        def on_event(event):
            if self.chat_wait_cancelled:
                return
            if not isinstance(event, dict):
                return
            if event.get("type") == "start":
                self.current_conversation_id = event.get("conversation_id") or self.current_conversation_id
            elif event.get("type") == "delta":
                self._streaming_text += str(event.get("text") or "")
                if self.chat_messages and self.chat_messages[-1].get("role") == "assistant":
                    self.chat_messages[-1]["content"] = self._streaming_text
                    self.chat_messages[-1]["provider"] = event.get("provider")
                    self.chat_messages[-1]["model"] = event.get("model")
                self._render_chat()
            elif event.get("type") == "final":
                self.current_conversation_id = event.get("conversation_id") or self.current_conversation_id
                conversation_id = self.current_conversation_id
                if conversation_id:
                    self.run_api(
                        lambda: self.api.get(f"/api/v1/conversations/{conversation_id}"),
                        lambda full: self._loaded_after_chat(full),
                    )
            elif event.get("type") == "error":
                self.orb.set_state("idle")
                self._api_failed("MYRA streaming error", str(event.get("error") or "Streaming failed"))

        def on_error(message):
            self.orb.set_state("idle")
            if not self.chat_wait_cancelled:
                self._api_failed("MYRA streaming error", message)

        worker = StreamWorker(lambda: self.api.stream_post("/api/v1/chat/stream", payload, timeout=220))
        worker.signals.event.connect(on_event)
        worker.signals.error.connect(on_error)
        self._start_worker(worker)

    def _loaded_after_chat(self, result):
        self.chat_messages = result["conversation"].get("messages", [])
        self._render_chat()
        self.refresh_conversations()
        self.orb.set_state("speaking")
        QTimer.singleShot(1400, lambda: self.orb.set_state("idle"))
        self.set_status("Reply saved to persistent local chat history.")

    def stop_chat_waiting(self):
        self.chat_wait_cancelled = True
        self.orb.set_state("idle")
        self.set_status("Stop requested locally. If the provider already received the request, it may still finish server-side; no further tokens will be shown here.")

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
        start = QPushButton("Create && Start")
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
        self._start_worker(worker)

    # ------------------------------------------------------------------
    # Realtime voice page (QtMultimedia -> faster-whisper -> chat -> TTS)
    # ------------------------------------------------------------------
    def _build_voice_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        intro = QLabel(
            "REALTIME VOICE — Microphone → faster-whisper (local STT) → MYRA cloud chat → Edge Neural TTS → Speaker. "
            "Speaking while MYRA plays a reply interrupts playback. Offline STT/TTS does not make cloud reasoning offline."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.voice_model_combo = QComboBox()
        self.voice_model_combo.addItems(["base", "small", "tiny"])
        self.voice_language_combo = QComboBox()
        self.voice_language_combo.addItem("Auto detect", "auto")
        self.voice_language_combo.addItem("Bengali", "bn")
        self.voice_language_combo.addItem("Hindi", "hi")
        self.voice_language_combo.addItem("English", "en")
        self.voice_threshold = QSpinBox()
        self.voice_threshold.setRange(100, 5000)
        self.voice_threshold.setValue(650)
        self.voice_silence = QSpinBox()
        self.voice_silence.setRange(300, 2000)
        self.voice_silence.setValue(750)
        form.addRow("Whisper model", self.voice_model_combo)
        form.addRow("Language", self.voice_language_combo)
        form.addRow("Mic VAD threshold", self.voice_threshold)
        form.addRow("End-of-speech silence (ms)", self.voice_silence)
        layout.addLayout(form)

        self.voice_start_button = QPushButton("Start realtime")
        self.voice_start_button.clicked.connect(self.start_voice_session)
        self.voice_stop_button = QPushButton("End call")
        self.voice_stop_button.clicked.connect(self.stop_voice_session)
        self.voice_mute = QCheckBox("Mute microphone")
        self.voice_mute.stateChanged.connect(self._voice_mute_changed)
        interrupt = QPushButton("Interrupt speech")
        interrupt.clicked.connect(self.interrupt_speech)
        install = QPushButton("Download STT model…")
        install.clicked.connect(self.install_voice_model)
        remove_model = QPushButton("Remove model…")
        remove_model.clicked.connect(self.remove_voice_model)
        refresh = QPushButton("Refresh status")
        refresh.clicked.connect(self.refresh_voice_status)
        voice_row = QHBoxLayout()
        for widget in (self.voice_start_button, self.voice_stop_button, self.voice_mute, interrupt):
            voice_row.addWidget(widget)
        voice_row.addStretch(1)
        layout.addLayout(voice_row)
        model_row = QHBoxLayout()
        for widget in (install, remove_model, refresh):
            model_row.addWidget(widget)
        model_row.addStretch(1)
        layout.addLayout(model_row)

        self.voice_status_text = QTextEdit()
        self.voice_status_text.setReadOnly(True)
        self.voice_status_text.setMaximumHeight(145)
        layout.addWidget(self.voice_status_text)
        self.voice_log = QTextEdit()
        self.voice_log.setReadOnly(True)
        layout.addWidget(self.voice_log, 1)

        tts_row = QHBoxLayout()
        self.tts_text = QLineEdit()
        self.tts_text.setPlaceholderText("Type text to test MYRA's voice…")
        speak = QPushButton("Speak")
        speak.clicked.connect(self.speak_typed_text)
        tts_row.addWidget(self.tts_text, 1)
        tts_row.addWidget(speak)
        layout.addLayout(tts_row)
        return page

    def refresh_voice_status(self):
        if not self.backend_ready or not hasattr(self, "voice_status_text"):
            return
        self.run_api(
            lambda: self.api.get("/api/v1/voice/status"),
            lambda result: self.voice_status_text.setPlainText(json.dumps(result.get("voice"), indent=2, ensure_ascii=False)),
        )

    def install_voice_model(self):
        model_id = self.voice_model_combo.currentText()
        sizes = {"tiny": "≈75 MB", "base": "≈145 MB", "small": "≈488 MB"}
        answer = QMessageBox.question(
            self,
            "Download speech model?",
            f"Download faster-whisper '{model_id}' ({sizes.get(model_id, 'large')}) from Hugging Face into MYRA app data? "
            "It is a one-time persistent download and will not be downloaded again on every start.",
        )
        if answer != QMessageBox.Yes:
            return
        payload = {"model_id": model_id, "confirmed": True}
        self.run_api(
            lambda: self.api.post("/api/v1/voice/models/install", payload, timeout=1200),
            lambda _result: (self.refresh_voice_status(), QMessageBox.information(self, "Voice model ready", f"faster-whisper {model_id} is installed.")),
            status=f"Downloading faster-whisper {model_id} model…",
        )

    def remove_voice_model(self):
        model_id = self.voice_model_combo.currentText()
        answer = QMessageBox.question(
            self,
            "Remove speech model?",
            f"Remove faster-whisper '{model_id}' and delete its files from MYRA app data? You can download it again later.",
        )
        if answer != QMessageBox.Yes:
            return
        self.run_api(
            lambda: self.api.delete(f"/api/v1/voice/models/faster-whisper/{model_id}?delete_file=1"),
            lambda _r: self.refresh_voice_status(),
            status=f"Removing faster-whisper {model_id}…",
        )

    def _ensure_player(self):
        if self._media_player is not None:
            return True
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer
        except Exception as exc:
            QMessageBox.warning(self, "Audio playback unavailable", f"QtMultimedia could not be loaded: {exc}")
            return False
        output = QMediaDevices.defaultAudioOutput()
        if output.isNull():
            QMessageBox.warning(self, "No speaker", "No default audio output device was found.")
            return False
        self._audio_output = QAudioOutput(output, self)
        self._audio_output.setVolume(0.9)
        self._media_player = QMediaPlayer(self)
        self._media_player.setAudioOutput(self._audio_output)
        self._media_player.mediaStatusChanged.connect(self._player_status_changed)
        return True

    def _player_status_changed(self, status):
        try:
            from PySide6.QtMultimedia import QMediaPlayer
            if status == QMediaPlayer.MediaStatus.EndOfMedia:
                self.orb.set_state("listening" if self._voice_active else "idle")
        except Exception:
            pass

    def _player_is_playing(self):
        if not self._media_player:
            return False
        try:
            from PySide6.QtMultimedia import QMediaPlayer
            return self._media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        except Exception:
            return False

    def interrupt_speech(self):
        if self._media_player:
            self._media_player.stop()
        self.orb.set_state("listening" if self._voice_active else "idle")
        self.set_status("Speech interrupted.")

    def _voice_mute_changed(self, _state):
        if self._voice_segmenter:
            self._voice_segmenter.reset()
        if self._voice_active:
            self.orb.set_state("idle" if self.voice_mute.isChecked() else "listening")
            self.set_status("Microphone muted in realtime voice." if self.voice_mute.isChecked() else "Microphone live in realtime voice.")

    def start_voice_session(self):
        if self._voice_active:
            return
        try:
            from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices
        except Exception as exc:
            QMessageBox.warning(self, "Microphone unavailable", f"QtMultimedia could not be loaded: {exc}")
            return
        device = QMediaDevices.defaultAudioInput()
        if device.isNull():
            QMessageBox.warning(self, "No microphone", "No default microphone was found. Check Windows Sound settings and microphone privacy permission.")
            return
        audio_format = QAudioFormat()
        audio_format.setSampleRate(16000)
        audio_format.setChannelCount(1)
        audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if not device.isFormatSupported(audio_format):
            QMessageBox.warning(self, "Unsupported microphone format", "The microphone does not support 16 kHz mono PCM16 capture.")
            return
        self._voice_segmenter = VoiceActivitySegmenter(
            sample_rate=16000,
            threshold=self.voice_threshold.value(),
            silence_ms=self.voice_silence.value(),
        )
        self._voice_source = QAudioSource(device, audio_format, self)
        self._voice_io = self._voice_source.start()
        if self._voice_io is None:
            QMessageBox.warning(self, "Microphone failed", "MYRA could not open the microphone. Windows may have denied permission.")
            self._voice_source = None
            return
        self._voice_io.readyRead.connect(self._voice_audio_ready)
        self._voice_active = True
        self.orb.set_state("listening")
        self.voice_log.append("<b>Realtime voice started.</b> Speak naturally; MYRA sends each completed utterance after a short silence.")
        self.set_status("Realtime voice is listening. Use End call to release the microphone immediately.")

    def stop_voice_session(self):
        self._voice_active = False
        self._voice_turn_inflight = False
        if self._voice_source:
            try:
                self._voice_source.stop()
            finally:
                self._voice_source.deleteLater()
                self._voice_source = None
        self._voice_io = None
        if self._voice_segmenter:
            self._voice_segmenter.reset()
        if self._media_player:
            self._media_player.stop()
        self.orb.set_state("idle")
        if hasattr(self, "voice_log"):
            self.voice_log.append("<i>Realtime voice ended; microphone released.</i>")
        self.set_status("Realtime voice stopped; microphone released.")

    def _voice_audio_ready(self):
        if not self._voice_active or self._voice_io is None:
            return
        data = bytes(self._voice_io.readAll())
        if not data:
            return
        if self._player_is_playing() and pcm16_rms(data) >= self.voice_threshold.value() * 1.15:
            self.interrupt_speech()
        if self.voice_mute.isChecked():
            return
        utterance = self._voice_segmenter.feed(data)
        if utterance and not self._voice_turn_inflight:
            self._send_voice_utterance(utterance)

    def _send_voice_utterance(self, pcm):
        self._voice_turn_inflight = True
        self.orb.set_state("thinking")
        payload = {
            "audio_base64": base64.b64encode(wav_bytes(pcm)).decode("ascii"),
            "language": self.voice_language_combo.currentData(),
            "model": self.voice_model_combo.currentText(),
            "conversation_id": self.current_conversation_id,
            "character": self.character_combo.currentText().lower(),
            "provider": self.provider_combo.currentText().lower(),
            "speak": True,
            **self.profile,
        }

        def done(result):
            self._voice_turn_inflight = False
            transcript = result.get("transcript") or {}
            heard = html.escape(str(transcript.get("text") or ""))
            reply = html.escape(str(result.get("reply") or ""))
            if heard:
                self.voice_log.append(f"<b>You:</b> {heard}")
            if reply:
                self.voice_log.append(f"<b>MYRA:</b> {reply}")
            if result.get("tts_error"):
                self.voice_log.append(f"<i>TTS note: {html.escape(result['tts_error'])}</i>")
            self.current_conversation_id = result.get("conversation_id") or self.current_conversation_id
            if self.current_conversation_id:
                self.run_api(
                    lambda: self.api.get(f"/api/v1/conversations/{self.current_conversation_id}"),
                    self._loaded_after_chat,
                )
            audio = result.get("audio") or {}
            if audio.get("audio_base64"):
                self._play_audio_base64(audio["audio_base64"])
            else:
                self.orb.set_state("listening" if self._voice_active else "idle")

        def failed(message):
            self._voice_turn_inflight = False
            self.orb.set_state("listening" if self._voice_active else "idle")
            self.voice_log.append(f"<b>Voice error:</b> {html.escape(message)}")
            self._api_failed("Realtime voice error", message)

        worker = ApiWorker(lambda: self.api.post("/api/v1/voice/turn", payload, timeout=220))
        worker.signals.finished.connect(done)
        worker.signals.error.connect(failed)
        self._start_worker(worker)

    def _play_audio_base64(self, encoded):
        if not self._ensure_player():
            return
        try:
            raw = base64.b64decode(encoded, validate=True)
            folder = data_dir() / "voice-temp"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / "myra-reply.mp3"
            path.write_bytes(raw)
        except Exception as exc:
            QMessageBox.warning(self, "Speech playback failed", str(exc))
            return
        self.orb.set_state("speaking")
        self._media_player.stop()
        self._media_player.setSource(QUrl.fromLocalFile(str(path)))
        self._media_player.play()

    def speak_typed_text(self):
        text = self.tts_text.text().strip()
        if not text:
            return
        payload = {"text": text, "character": self.character_combo.currentText().lower()}
        self.run_api(
            lambda: self.api.post("/api/v1/voice/synthesize", payload, timeout=120),
            lambda result: self._play_audio_base64((result.get("audio") or {}).get("audio_base64", "")),
            status="Synthesizing speech…",
        )

    # ------------------------------------------------------------------
    # Live sampled screen/camera vision
    # ------------------------------------------------------------------
    def _build_live_vision_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        intro = QLabel(
            "LIVE VISION — explicit consent only. MYRA previews locally and sends sampled frames at the chosen analysis interval; "
            "it does not keep capturing after Stop. This is frame-based live understanding through Gemini vision."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.live_source_combo = QComboBox()
        self.live_source_combo.addItem("Screen", "screen")
        self.live_source_combo.addItem("Camera", "camera")
        self.live_source_combo.currentIndexChanged.connect(lambda _i: self.refresh_live_devices())
        self.live_screen_combo = QComboBox()
        self.live_camera_combo = QComboBox()
        self.live_prompt = QLineEdit("Watch for important changes and help me understand what is visible.")
        self.live_interval = QDoubleSpinBox()
        self.live_interval.setRange(1.0, 60.0)
        self.live_interval.setValue(4.0)
        self.live_interval.setSuffix(" sec / analysis")
        self.live_fps = QDoubleSpinBox()
        self.live_fps.setRange(0.5, 10.0)
        self.live_fps.setValue(2.0)
        self.live_fps.setSuffix(" preview fps")
        self.live_quality = QSpinBox()
        self.live_quality.setRange(35, 92)
        self.live_quality.setValue(72)
        self.live_quality.setSuffix(" JPEG quality")
        self.live_max_width = QSpinBox()
        self.live_max_width.setRange(640, 1920)
        self.live_max_width.setValue(1280)
        self.live_max_width.setSuffix(" px max width")
        form.addRow("Source", self.live_source_combo)
        form.addRow("Screen", self.live_screen_combo)
        form.addRow("Camera", self.live_camera_combo)
        form.addRow("Instruction", self.live_prompt)
        form.addRow("Analysis interval", self.live_interval)
        form.addRow("Preview rate", self.live_fps)
        form.addRow("Frame quality", self.live_quality)
        form.addRow("Frame width", self.live_max_width)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.live_start_button = QPushButton("▶ Start with consent")
        self.live_start_button.clicked.connect(self.start_live_vision)
        self.live_pause_button = QPushButton("Pause")
        self.live_pause_button.clicked.connect(self.pause_live_vision)
        self.live_resume_button = QPushButton("Resume")
        self.live_resume_button.clicked.connect(self.resume_live_vision)
        self.live_stop_button = QPushButton("Stop && release")
        self.live_stop_button.clicked.connect(self.stop_live_vision)
        analyze = QPushButton("Analyze next frame now")
        analyze.clicked.connect(lambda: setattr(self, "_live_analyze_now", True))
        refresh = QPushButton("Refresh devices")
        refresh.clicked.connect(self.refresh_live_devices)
        for button in (self.live_start_button, self.live_pause_button, self.live_resume_button, self.live_stop_button, analyze, refresh):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.live_indicator = QLabel("● LIVE OFF")
        self.live_indicator.setStyleSheet("color:#7fa8b5; font-weight:700;")
        layout.addWidget(self.live_indicator)
        self.live_preview = QLabel("No live preview. Camera/screen is OFF.")
        self.live_preview.setAlignment(Qt.AlignCenter)
        self.live_preview.setMinimumHeight(300)
        self.live_preview.setStyleSheet("border:1px solid #07556b; background:#010509;")
        layout.addWidget(self.live_preview, 1)
        self.live_log = QTextEdit()
        self.live_log.setReadOnly(True)
        self.live_log.setMaximumHeight(190)
        layout.addWidget(self.live_log)
        self.refresh_live_devices()
        return page

    def refresh_live_devices(self):
        if not hasattr(self, "live_screen_combo"):
            return
        current_screen = self.live_screen_combo.currentText()
        self.live_screen_combo.clear()
        for index, screen in enumerate(QGuiApplication.screens()):
            self.live_screen_combo.addItem(screen.name() or f"Screen {index + 1}", index)
        idx = self.live_screen_combo.findText(current_screen)
        if idx >= 0:
            self.live_screen_combo.setCurrentIndex(idx)
        self.live_camera_combo.clear()
        try:
            from PySide6.QtMultimedia import QMediaDevices
            for device in QMediaDevices.videoInputs():
                self.live_camera_combo.addItem(device.description() or "Camera", device.id().data().decode("utf-8", errors="ignore"))
            if self.live_camera_combo.count() == 0:
                self.live_camera_combo.addItem("No camera found", "")
        except Exception as exc:
            self.live_camera_combo.addItem(f"QtMultimedia unavailable: {exc}", "")

    def start_live_vision(self):
        if self._live_active:
            return
        source = self.live_source_combo.currentData()
        answer = QMessageBox.question(
            self,
            "Start live sharing?",
            f"Start {source} sharing? MYRA will preview locally and send sampled frames every {self.live_interval.value():.1f} seconds to Gemini vision until you press Stop.",
        )
        if answer != QMessageBox.Yes:
            return
        payload = {
            "source": source,
            "consent": True,
            "analysis_interval_seconds": self.live_interval.value(),
            "prompt": self.live_prompt.text().strip(),
            "max_analyses": 60,
        }

        def done(result):
            session = result.get("session") or {}
            self._live_session_id = session.get("id")
            self._live_analysis_count = 0
            if not self._live_session_id:
                QMessageBox.warning(self, "Live vision failed", "Backend did not return a session id.")
                return
            if self._start_live_local(source):
                self._live_active = True
                self._live_paused = False
                self.live_indicator.setText("● LIVE — capture is ON")
                self.live_indicator.setStyleSheet("color:#ff5b6a; font-weight:700;")
                self.live_log.append(f"Live {source} session started.")
            else:
                self.api.post(f"/api/v1/live-vision/sessions/{self._live_session_id}/stop", {})
                self._live_session_id = None

        self.run_api(lambda: self.api.post("/api/v1/live-vision/sessions", payload), done, status="Starting consented live-vision session…")

    def _start_live_local(self, source):
        if source == "screen":
            if self._live_timer is None:
                self._live_timer = QTimer(self)
                self._live_timer.timeout.connect(self._capture_live_screen)
            self._live_timer.setInterval(max(100, int(1000 / max(0.5, self.live_fps.value()))))
            self._live_timer.start()
            self._capture_live_screen()
            return True
        try:
            from PySide6.QtMultimedia import QCamera, QMediaCaptureSession, QMediaDevices, QVideoSink
        except Exception as exc:
            QMessageBox.warning(self, "Camera unavailable", f"QtMultimedia could not be loaded: {exc}")
            return False
        devices = QMediaDevices.videoInputs()
        if not devices:
            QMessageBox.warning(self, "No camera", "No camera device was found or Windows denied camera permission.")
            return False
        selected = max(0, self.live_camera_combo.currentIndex())
        device = devices[min(selected, len(devices) - 1)]
        self._camera = QCamera(device, self)
        self._camera_session = QMediaCaptureSession(self)
        self._camera_session.setCamera(self._camera)
        self._camera_sink = QVideoSink(self)
        self._camera_session.setVideoSink(self._camera_sink)
        self._camera_sink.videoFrameChanged.connect(self._camera_frame)
        self._camera.start()
        return True

    def _capture_live_screen(self):
        if not self._live_active or self._live_paused:
            return
        screens = QGuiApplication.screens()
        if not screens:
            return
        index = self.live_screen_combo.currentData()
        screen = screens[index] if isinstance(index, int) and 0 <= index < len(screens) else QGuiApplication.primaryScreen()
        if screen is None:
            return
        pixmap = screen.grabWindow(0)
        self._handle_live_pixmap(pixmap)

    def _camera_frame(self, frame):
        if not self._live_active or self._live_paused:
            return
        try:
            image = frame.toImage()
            if image.isNull():
                return
            self._handle_live_pixmap(QPixmap.fromImage(image))
        except Exception:
            return

    def _handle_live_pixmap(self, pixmap):
        if pixmap.isNull():
            return
        preview = pixmap.scaled(
            self.live_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ) if self.live_preview.width() > 20 else pixmap
        self.live_preview.setPixmap(preview)
        now = time.monotonic()
        due = self._live_analyze_now or (now - self._live_last_sent >= self.live_interval.value())
        if not due or self._live_inflight or not self._live_session_id:
            return
        self._live_analyze_now = False
        frame = pixmap
        if frame.width() > self.live_max_width.value():
            frame = frame.scaledToWidth(self.live_max_width.value(), Qt.SmoothTransformation)
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.WriteOnly)
        if not frame.save(buffer, "JPG", self.live_quality.value()):
            return
        encoded = base64.b64encode(bytes(byte_array.data())).decode("ascii")
        self._live_last_sent = now
        self._live_inflight = True
        session_id = self._live_session_id
        payload = {"image_base64": encoded, "mime_type": "image/jpeg", "analyze_now": True}

        def done(result):
            self._live_inflight = False
            session = result.get("session") or {}
            analyses = session.get("analyses") or []
            if len(analyses) > self._live_analysis_count:
                latest = analyses[-1]
                self._live_analysis_count = len(analyses)
                self.live_log.append(f"<b>{html.escape(str(latest.get('at', '')))}</b>: {html.escape(str(latest.get('text') or ''))}")
            if session.get("errors"):
                self.live_log.append(f"<i>{html.escape(str(session['errors'][-1]))}</i>")

        def failed(message):
            self._live_inflight = False
            self.live_log.append(f"<b>Live analysis error:</b> {html.escape(message)}")

        worker = ApiWorker(lambda: self.api.post(f"/api/v1/live-vision/sessions/{session_id}/frame", payload, timeout=120))
        worker.signals.finished.connect(done)
        worker.signals.error.connect(failed)
        self._start_worker(worker)

    def pause_live_vision(self):
        if not self._live_session_id:
            return
        self._live_paused = True
        self.live_indicator.setText("LIVE PAUSED — frames are not sent")
        session_id = self._live_session_id
        self.run_api(lambda: self.api.post(f"/api/v1/live-vision/sessions/{session_id}/pause", {}), lambda _r: self.set_status("Live vision paused."))

    def resume_live_vision(self):
        if not self._live_session_id:
            return
        self._live_paused = False
        self.live_indicator.setText("● LIVE — capture is ON")
        session_id = self._live_session_id
        self.run_api(lambda: self.api.post(f"/api/v1/live-vision/sessions/{session_id}/resume", {}), lambda _r: self.set_status("Live vision resumed."))

    def _stop_live_local(self):
        self._live_active = False
        self._live_paused = False
        self._live_inflight = False
        if self._live_timer:
            self._live_timer.stop()
        if self._camera:
            try:
                self._camera.stop()
            finally:
                self._camera.deleteLater()
                self._camera = None
        self._camera_session = None
        self._camera_sink = None
        if hasattr(self, "live_indicator"):
            self.live_indicator.setText("● LIVE OFF")
            self.live_indicator.setStyleSheet("color:#7fa8b5; font-weight:700;")
            self.live_preview.setPixmap(QPixmap())
            self.live_preview.setText("No live preview. Camera/screen is OFF.")

    def stop_live_vision(self):
        session_id = self._live_session_id
        self._stop_live_local()
        if not session_id:
            return
        self._live_session_id = None
        self.run_api(
            lambda: self.api.post(f"/api/v1/live-vision/sessions/{session_id}/stop", {}),
            lambda _r: self.live_log.append("Live session stopped; backend will reject further frames."),
            status="Stopping live vision and releasing device…",
        )

    # ------------------------------------------------------------------
    # Web research + browser/Windows computer control
    # ------------------------------------------------------------------
    def _build_research_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        intro = QLabel("WEB RESEARCH — searches public sources, fetches bounded readable pages and returns a cited report. Private/local URLs are blocked by the research engine.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        row = QHBoxLayout()
        self.research_query = QLineEdit()
        self.research_query.setPlaceholderText("What should MYRA research?")
        self.research_query.returnPressed.connect(self.run_research)
        self.research_sources = QSpinBox()
        self.research_sources.setRange(1, 8)
        self.research_sources.setValue(5)
        run = QPushButton("Research")
        run.clicked.connect(self.run_research)
        save = QPushButton("Save report…")
        save.clicked.connect(self.save_research_report)
        row.addWidget(self.research_query, 1)
        row.addWidget(QLabel("Sources"))
        row.addWidget(self.research_sources)
        row.addWidget(run)
        row.addWidget(save)
        layout.addLayout(row)
        self.research_result = QTextEdit()
        self.research_result.setReadOnly(True)
        layout.addWidget(self.research_result, 1)
        return page

    def run_research(self):
        query = self.research_query.text().strip()
        if not query:
            QMessageBox.information(self, "Query needed", "Type a research question first.")
            return
        payload = {"query": query, "max_sources": self.research_sources.value()}
        self.orb.set_state("thinking")

        def done(result):
            self.orb.set_state("idle")
            lines = [str(result.get("report") or "")]
            lines.extend(["", "Sources:"])
            for citation in result.get("citations") or []:
                lines.append(f"[{citation.get('index')}] {citation.get('title')} — {citation.get('url')}")
            if result.get("errors"):
                lines.extend(["", "Notes/errors:", json.dumps(result["errors"], indent=2, ensure_ascii=False)])
            self.research_result.setPlainText("\n".join(lines))

        worker = ApiWorker(lambda: self.api.post("/api/v1/research", payload, timeout=150))
        worker.signals.finished.connect(done)
        worker.signals.error.connect(lambda message: (self.orb.set_state("idle"), self._api_failed("Research error", message)))
        self._start_worker(worker)
        self.set_status("Researching public web sources…")

    def save_research_report(self):
        if not self.research_result.toPlainText().strip():
            return
        filename, _ = QFileDialog.getSaveFileName(self, "Save research report", "myra-research.txt", "Text (*.txt);;Markdown (*.md)")
        if filename:
            Path(filename).write_text(self.research_result.toPlainText(), encoding="utf-8")
            self.set_status(f"Research report saved: {filename}")

    def _build_computer_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        warning = QLabel(
            "COMPUTER CONTROL — semantic Windows UI Automation is preferred; coordinate fallback is separate. "
            "Actions require the confirmation box and show a red MYRA IS CONTROLLING banner. Password, OTP, CAPTCHA and MFA steps are refused."
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)

        windows_box = QGroupBox("Windows UI Automation (pywinauto) + PyAutoGUI fallback")
        win_layout = QVBoxLayout(windows_box)
        top = QHBoxLayout()
        self.windows_list = QListWidget()
        self.windows_list.setMaximumHeight(110)
        self.windows_list.itemSelectionChanged.connect(self._window_selected)
        top.addWidget(self.windows_list, 1)
        self.computer_status = QTextEdit()
        self.computer_status.setReadOnly(True)
        self.computer_status.setMaximumHeight(110)
        top.addWidget(self.computer_status, 1)
        win_layout.addLayout(top)
        form = QFormLayout()
        self.win_title = QLineEdit()
        self.win_name = QLineEdit()
        self.win_automation = QLineEdit()
        self.win_type = QLineEdit()
        self.win_class = QLineEdit()
        self.win_index = QSpinBox()
        self.win_index.setRange(0, 100)
        self.win_text = QLineEdit()
        self.win_text.setPlaceholderText("Text / pywinauto keys / hotkey keys separated by commas")
        self.win_x = QSpinBox(); self.win_x.setRange(0, 20000)
        self.win_y = QSpinBox(); self.win_y.setRange(0, 20000)
        coords = QHBoxLayout(); coords.addWidget(QLabel("X")); coords.addWidget(self.win_x); coords.addWidget(QLabel("Y")); coords.addWidget(self.win_y); coords.addStretch(1)
        form.addRow("Window title contains", self.win_title)
        form.addRow("Control name contains", self.win_name)
        form.addRow("Automation ID", self.win_automation)
        form.addRow("Control type", self.win_type)
        form.addRow("Class contains", self.win_class)
        form.addRow("Match index", self.win_index)
        form.addRow("Text / keys", self.win_text)
        form.addRow("Coordinate", coords)
        win_layout.addLayout(form)
        self.windows_confirm = QCheckBox("I confirm this Windows-control action")
        win_layout.addWidget(self.windows_confirm)
        buttons = QHBoxLayout()
        specs = [
            ("List windows", lambda: self.windows_action("list_windows", {}, confirmed=False)),
            ("Observe", lambda: self.windows_action("observe", {"window_title": self.win_title.text()}, confirmed=False)),
            ("Focus", lambda: self.windows_action("focus", {"window_title": self.win_title.text()})),
            ("Invoke control", lambda: self.windows_action("invoke_control", self._window_query())),
            ("Set text", lambda: self.windows_action("set_text", {**self._window_query(), "text": self.win_text.text()})),
            ("Send keys", lambda: self.windows_action("send_keys", {"keys": self.win_text.text(), "window_title": self.win_title.text()})),
            ("Click X/Y", lambda: self.windows_action("click_point", {"x": self.win_x.value(), "y": self.win_y.value()})),
            ("Type text", lambda: self.windows_action("type_text", {"text": self.win_text.text()})),
            ("Hotkey", lambda: self.windows_action("hotkey", {"keys": [p.strip() for p in self.win_text.text().replace("+", ",").split(",") if p.strip()]})),
        ]
        for label, action in specs:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, fn=action: fn())
            buttons.addWidget(button)
        buttons.addStretch(1)
        win_layout.addLayout(buttons)
        danger = QHBoxLayout()
        stop = QPushButton("EMERGENCY STOP")
        stop.clicked.connect(self.windows_emergency_stop)
        reset = QPushButton("Reset emergency stop")
        reset.clicked.connect(lambda: self.windows_action("reset_emergency_stop", {}))
        refresh = QPushButton("Refresh status")
        refresh.clicked.connect(self.refresh_computer_status)
        danger.addWidget(stop); danger.addWidget(reset); danger.addWidget(refresh); danger.addStretch(1)
        win_layout.addLayout(danger)
        layout.addWidget(windows_box)

        browser_box = QGroupBox("Visible browser automation (optional Playwright + Edge/Chrome)")
        browser_layout = QVBoxLayout(browser_box)
        bform = QFormLayout()
        self.browser_url = QLineEdit("https://example.com")
        self.browser_selector = QLineEdit()
        self.browser_text_value = QLineEdit()
        self.browser_submit = QCheckBox("Press Enter after fill")
        self.browser_confirm = QCheckBox("I confirm this browser action")
        bform.addRow("URL", self.browser_url)
        bform.addRow("CSS selector", self.browser_selector)
        bform.addRow("Visible text / fill value", self.browser_text_value)
        bform.addRow("", self.browser_submit)
        bform.addRow("", self.browser_confirm)
        browser_layout.addLayout(bform)
        browser_buttons = QHBoxLayout()
        for label, action in [
            ("Snapshot", "snapshot"), ("Screenshot", "screenshot"), ("Click", "click"), ("Fill", "fill")
        ]:
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, a=action: self.browser_action(a))
            browser_buttons.addWidget(button)
        browser_buttons.addStretch(1)
        browser_layout.addLayout(browser_buttons)
        layout.addWidget(browser_box)

        self.computer_result = QTextEdit()
        self.computer_result.setReadOnly(True)
        layout.addWidget(self.computer_result, 1)
        return page

    def refresh_computer_status(self):
        if not self.backend_ready or not hasattr(self, "computer_status"):
            return

        def load():
            return {"windows": self.api.get("/api/v1/windows/status"), "browser": self.api.get("/api/v1/browser/status")}

        self.run_api(load, lambda result: self.computer_status.setPlainText(json.dumps(result, indent=2, ensure_ascii=False)))

    def _show_control_banner(self, text, milliseconds=15000):
        self.control_banner.setText(text)
        self.control_banner.show()
        QTimer.singleShot(milliseconds, self.control_banner.hide)

    def _window_query(self):
        return {
            "window_title": self.win_title.text().strip(),
            "name": self.win_name.text().strip(),
            "automation_id": self.win_automation.text().strip(),
            "control_type": self.win_type.text().strip(),
            "class_name": self.win_class.text().strip(),
            "index": self.win_index.value(),
        }

    def _window_selected(self):
        items = self.windows_list.selectedItems()
        if items:
            self.win_title.setText(items[0].data(Qt.UserRole) or items[0].text())

    def windows_action(self, action, arguments, confirmed=True):
        if confirmed and not self.windows_confirm.isChecked():
            QMessageBox.information(self, "Confirmation required", "Tick the Windows-control confirmation box first.")
            return
        if confirmed:
            self._show_control_banner("● MYRA IS CONTROLLING THE COMPUTER — use Emergency Stop to interrupt")
        payload = {"action": action, "arguments": arguments, "confirmed": bool(confirmed and self.windows_confirm.isChecked())}

        def done(result):
            inner = result.get("result") or result
            if action == "list_windows":
                self.windows_list.clear()
                for window in inner.get("windows") or []:
                    title = window.get("name") or window.get("title") or "(untitled)"
                    item = QListWidgetItem(title)
                    item.setData(Qt.UserRole, title)
                    self.windows_list.addItem(item)
            self.computer_result.setPlainText(json.dumps(inner, indent=2, ensure_ascii=False)[:30000])
            if confirmed:
                QTimer.singleShot(1200, self.control_banner.hide)
                self.windows_confirm.setChecked(False)

        def failed(message):
            QTimer.singleShot(800, self.control_banner.hide)
            self._api_failed("Windows control error", message)

        worker = ApiWorker(lambda: self.api.post("/api/v1/windows/action", payload, timeout=90))
        worker.signals.finished.connect(done)
        worker.signals.error.connect(failed)
        self._start_worker(worker)

    def windows_emergency_stop(self):
        self._show_control_banner("🛑 MYRA WINDOWS CONTROL EMERGENCY-STOPPED", 20000)
        self.run_api(
            lambda: self.api.post("/api/v1/windows/emergency-stop", {}),
            lambda result: self.computer_result.setPlainText(json.dumps(result, indent=2)),
        )

    def browser_action(self, action):
        needs_confirm = action != "snapshot"
        if needs_confirm and not self.browser_confirm.isChecked():
            QMessageBox.information(self, "Confirmation required", "Tick the browser-action confirmation box first.")
            return
        if needs_confirm:
            self._show_control_banner("🔴 MYRA IS CONTROLLING THE BROWSER")
        payload = {
            "url": self.browser_url.text().strip(),
            "selector": self.browser_selector.text().strip(),
            "text": self.browser_text_value.text(),
            "value": self.browser_text_value.text(),
            "submit": self.browser_submit.isChecked(),
            "filename": "browser.png",
            "confirmed": bool(needs_confirm and self.browser_confirm.isChecked()),
        }

        def done(result):
            self.computer_result.setPlainText(json.dumps(result.get("result") or result, indent=2, ensure_ascii=False)[:30000])
            QTimer.singleShot(1200, self.control_banner.hide)
            self.browser_confirm.setChecked(False)

        def failed(message):
            QTimer.singleShot(800, self.control_banner.hide)
            self._api_failed("Browser control error", message)

        worker = ApiWorker(lambda: self.api.post(f"/api/v1/browser/{action}", payload, timeout=120))
        worker.signals.finished.connect(done)
        worker.signals.error.connect(failed)
        self._start_worker(worker)

    # ------------------------------------------------------------------
    # Reminders + World pages
    # ------------------------------------------------------------------
    def _build_reminders_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.reminder_list = QListWidget()
        self.reminder_list.itemSelectionChanged.connect(self._reminder_selected)
        layout.addWidget(self.reminder_list, 1)
        form = QFormLayout()
        self.reminder_text = QLineEdit()
        self.reminder_text.setPlaceholderText("Reminder text")
        self.reminder_minutes = QSpinBox()
        self.reminder_minutes.setRange(0, 525600)
        self.reminder_minutes.setValue(10)
        self.reminder_minutes.setSuffix(" minutes from now")
        self.reminder_due = QLineEdit()
        self.reminder_due.setPlaceholderText("Optional ISO time, e.g. 2026-10-30T09:00:00")
        form.addRow("Text", self.reminder_text)
        form.addRow("Due in", self.reminder_minutes)
        form.addRow("Or ISO due", self.reminder_due)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        for label, action in [
            ("Add reminder", self.add_reminder),
            ("Mark complete", self.complete_reminder),
            ("Delete", self.delete_reminder),
            ("Refresh", self.refresh_reminders),
            ("Check due now", lambda: self._poll_reminders(force_dialog=True)),
        ]:
            button = QPushButton(label)
            button.clicked.connect(action)
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        note = QLabel("The desktop checks due reminders every 30 seconds while MYRA is open. Reminders live in the same unified SQLite database as Memory and Notes.")
        note.setWordWrap(True)
        note.setObjectName("hint")
        layout.addWidget(note)
        return page

    def refresh_reminders(self):
        if not self.backend_ready or not hasattr(self, "reminder_list"):
            return

        def done(result):
            self.reminder_list.blockSignals(True)
            self.reminder_list.clear()
            for reminder in result.get("reminders") or []:
                item = QListWidgetItem(f"{reminder.get('due_str')} — {reminder.get('text')}")
                item.setData(Qt.UserRole, reminder)
                self.reminder_list.addItem(item)
            self.reminder_list.blockSignals(False)

        self.run_api(lambda: self.api.get("/api/v1/reminders?active=0"), done)

    def _reminder_selected(self):
        items = self.reminder_list.selectedItems()
        if items:
            reminder = items[0].data(Qt.UserRole)
            self.current_reminder_id = reminder.get("id")
            self.reminder_text.setText(reminder.get("text", ""))

    def add_reminder(self):
        payload = {"text": self.reminder_text.text().strip()}
        if self.reminder_due.text().strip():
            payload["due_at"] = self.reminder_due.text().strip()
        else:
            payload["minutes"] = self.reminder_minutes.value()
        self.run_api(lambda: self.api.post("/api/v1/reminders", payload), lambda _r: self.refresh_reminders())

    def complete_reminder(self):
        if not self.current_reminder_id:
            return
        reminder_id = self.current_reminder_id
        self.run_api(
            lambda: self.api.put(f"/api/v1/reminders/{reminder_id}", {"completed": True}),
            lambda _r: self.refresh_reminders(),
        )

    def delete_reminder(self):
        if not self.current_reminder_id:
            return
        if QMessageBox.question(self, "Delete reminder", "Delete this reminder?") != QMessageBox.Yes:
            return
        reminder_id = self.current_reminder_id
        self.run_api(lambda: self.api.delete(f"/api/v1/reminders/{reminder_id}"), lambda _r: self.refresh_reminders())

    def _poll_reminders(self, force_dialog=False):
        if not self.backend_ready or self._reminder_poll_inflight:
            return
        self._reminder_poll_inflight = True

        def done(result):
            self._reminder_poll_inflight = False
            due = result.get("due") or []
            fresh = [item for item in due if item.get("id") not in self._notified_reminders]
            for item in fresh:
                self._notified_reminders.add(item.get("id"))
            if fresh:
                text = "\n".join(f"• {item.get('text')}" for item in fresh)
                self.orb.set_state("speaking")
                QTimer.singleShot(1800, lambda: self.orb.set_state("idle"))
                if force_dialog or self.isVisible():
                    QMessageBox.information(self, "⏰ MYRA reminder", text)
                self.refresh_reminders()
            elif force_dialog:
                QMessageBox.information(self, "Reminders", "No due reminders right now.")

        def failed(_message):
            self._reminder_poll_inflight = False

        worker = ApiWorker(lambda: self.api.get("/api/v1/reminders/due?mark=1", timeout=10))
        worker.signals.finished.connect(done)
        worker.signals.error.connect(failed)
        self._start_worker(worker)

    def _build_world_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        row = QHBoxLayout()
        self.world_region = QComboBox()
        self.world_region.addItem("All", "all")
        self.world_region.addItem("Global", "global")
        self.world_region.addItem("Middle East", "mideast")
        self.world_region.addItem("Tech", "tech")
        self.world_region.addItem("Asia", "asia")
        refresh = QPushButton("Refresh headlines")
        refresh.clicked.connect(self.refresh_world)
        open_monitor = QPushButton("Open worldmonitor.app")
        open_monitor.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://worldmonitor.app")))
        row.addWidget(QLabel("Region"))
        row.addWidget(self.world_region)
        row.addWidget(refresh)
        row.addWidget(open_monitor)
        row.addStretch(1)
        layout.addLayout(row)
        self.world_list = QListWidget()
        self.world_list.itemSelectionChanged.connect(self._world_selected)
        layout.addWidget(self.world_list, 1)
        self.world_detail = QTextEdit()
        self.world_detail.setReadOnly(True)
        self.world_detail.setMaximumHeight(180)
        layout.addWidget(self.world_detail)
        open_article = QPushButton("Open selected article")
        open_article.clicked.connect(self.open_world_article)
        layout.addWidget(open_article)
        return page

    def refresh_world(self):
        if not self.backend_ready or not hasattr(self, "world_list"):
            return
        region = self.world_region.currentData() or "all"

        def done(result):
            self.world_list.blockSignals(True)
            self.world_list.clear()
            for article in result.get("articles") or []:
                item = QListWidgetItem(f"[{article.get('source')}] {article.get('title')}")
                item.setData(Qt.UserRole, article)
                self.world_list.addItem(item)
            self.world_list.blockSignals(False)
            if not (result.get("articles") or []):
                self.world_detail.setPlainText("No headlines are available yet. If offline, MYRA will show the last cached headlines after the first successful online fetch.")

        self.run_api(lambda: self.api.get(f"/api/v1/world/news?region={region}&refresh=1", timeout=60), done, status="Refreshing World Monitor headlines…")

    def _world_selected(self):
        items = self.world_list.selectedItems()
        if not items:
            return
        article = items[0].data(Qt.UserRole)
        self.world_detail.setPlainText(
            f"{article.get('title')}\n\nSource: {article.get('source')}\nTime: {article.get('time')}\n\n{article.get('snippet')}\n\n{article.get('link')}"
        )

    def open_world_article(self):
        items = self.world_list.selectedItems()
        if not items:
            return
        url = (items[0].data(Qt.UserRole) or {}).get("link")
        if url:
            QDesktopServices.openUrl(QUrl(url))

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
        self.extra_provider_combo = QComboBox()
        for label, key in [
            ("OpenRouter", "openrouter"), ("OpenAI", "openai"), ("Anthropic", "anthropic"),
            ("DeepSeek", "deepseek"), ("Mistral", "mistral"),
        ]:
            self.extra_provider_combo.addItem(label, key)
        self.extra_key_input = QLineEdit()
        self.extra_key_input.setEchoMode(QLineEdit.Password)
        self.extra_key_status = QLabel("Choose a provider above; masked statuses for all providers appear below after refresh.")
        self.extra_key_status.setWordWrap(True)
        form.addRow("Other provider", self.extra_provider_combo)
        form.addRow("New other-provider key", self.extra_key_input)
        form.addRow("", self.extra_key_status)
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
        remove_extra = QPushButton("Remove selected other provider")
        remove_extra.clicked.connect(lambda: self.remove_key(self.extra_provider_combo.currentData()))
        key_buttons.addWidget(remove_extra)
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
        save_profile = QPushButton("Save profile && models")
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
            selected = keys.get(self.extra_provider_combo.currentData()) or {}
            self.extra_key_status.setText(
                f"{self.extra_provider_combo.currentText()}: {'saved ' + selected.get('masked', '') if selected.get('set') else 'not saved'} ({selected.get('storage', 'unknown')})"
            )
            self.provider_detail.setPlainText(json.dumps(
                {"core_providers": result.get("providers"), "all_key_status": keys}, indent=2, ensure_ascii=False
            ))

        self.run_api(load, done)

    def save_keys(self):
        payload = {}
        if self.gemini_key_input.text().strip():
            payload["gemini"] = self.gemini_key_input.text().strip()
        if self.groq_key_input.text().strip():
            payload["groq"] = self.groq_key_input.text().strip()
        if self.extra_key_input.text().strip():
            payload[self.extra_provider_combo.currentData()] = self.extra_key_input.text().strip()
        if not payload:
            QMessageBox.information(self, "No key entered", "Paste a new key first. Saved keys are never shown back.")
            return

        def done(_result):
            self.gemini_key_input.clear()
            self.groq_key_input.clear()
            self.extra_key_input.clear()
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
        migrate = QPushButton("Import legacy data")
        migrate.clicked.connect(self.migrate_legacy_data)
        for button in (refresh, backup, export, open_workspace, migrate):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        note = QLabel("All MYRA data now uses one unified SQLite database in app data. Diagnostics show whether the voice pipeline, Playwright and Windows-control optional packages are installed; physical microphone/camera/speaker checks still depend on this PC.")
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

    def migrate_legacy_data(self):
        self.run_api(
            lambda: self.api.post("/api/v1/data/migrate-legacy", {}, timeout=120),
            lambda result: QMessageBox.information(
                self, "Legacy import complete", json.dumps(result.get("migration"), indent=2, ensure_ascii=False)
            ),
            status="Importing any remaining legacy MYRA data…",
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
