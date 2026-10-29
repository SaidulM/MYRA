"""MYRA Core 2.0 API v1 handler mixin.

This is deliberately separate from the legacy web routes so the newer
main-branch UI/features and the native desktop service API can coexist.
The host handler must provide ``_send_json(payload, status=200)``.
"""
import json
import traceback
from urllib.parse import parse_qs, unquote, urlparse

import chat
import config
from browser_control import BrowserControlError
from live_vision import LiveVisionError
from research import ResearchError
from service import APP_VERSION, get_service
from voice import VoiceModelError
from voice_engine import VoiceEngineError
from windows_control import WindowsControlError


class CoreApiMixin:
    def _read_json_v1(self, max_bytes=64_000, optional=False):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send_json({"ok": False, "error": "Bad Content-Length."}, status=400)
            return None
        if length == 0 and optional:
            return {}
        if length <= 0 or length > max_bytes:
            self._send_json(
                {"ok": False, "error": f"Request body must be 1..{max_bytes} bytes."},
                status=400,
            )
            return None
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send_json({"ok": False, "error": "Request body is not valid JSON."}, status=400)
            return None
        if not isinstance(payload, dict):
            self._send_json({"ok": False, "error": "JSON body must be an object."}, status=400)
            return None
        return payload

    def _bind_host(self):
        try:
            return str(self.server.server_address[0])
        except Exception:
            return ""

    def _api_v1_authorized(self, method, clean_path):
        token = config.get("MYRA_API_TOKEN").strip()
        if token:
            return self.headers.get("X-MYRA-Token", "") == token
        if self._bind_host() in {"127.0.0.1", "localhost", "::1"}:
            return True
        # Public read-only status is safe; anything that can read private
        # history or cause an action is refused on a non-loopback bind
        # unless the owner configured a token.
        return method == "GET" and clean_path in {
            "/api/v1/health",
            "/api/v1/providers",
            "/api/v1/skills",
        }

    def _api_v1_full_access(self):
        token = config.get("MYRA_API_TOKEN").strip()
        if token:
            return self.headers.get("X-MYRA-Token", "") == token
        return self._bind_host() in {"127.0.0.1", "localhost", "::1"}

    def _send_ndjson_stream(self, events):
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            for event in events:
                self.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
        except chat.ChatError as exc:
            payload = {"type": "error", "ok": False, "code": exc.code, "error": exc.message}
            self.wfile.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()
        except Exception as exc:
            payload = {"type": "error", "ok": False, "error": f"Streaming failed: {exc.__class__.__name__}: {exc}"[:500]}
            self.wfile.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()

    # ---------- API v1 ----------
    def _handle_api_v1(self, method):
        parsed = urlparse(self.path)
        clean_path = parsed.path.rstrip("/") or "/"
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        parts = [unquote(part) for part in clean_path.split("/") if part]

        if not self._api_v1_authorized(method, clean_path):
            self._send_json(
                {
                    "ok": False,
                    "code": "api_token_required",
                    "error": "API v1 action endpoints require loopback binding or MYRA_API_TOKEN.",
                },
                status=401,
            )
            return

        try:
            service = get_service()

            # Health / providers
            if method == "GET" and clean_path == "/api/v1/health":
                if self._api_v1_full_access():
                    self._send_json(service.health())
                else:
                    # Public health must not leak local filesystem paths.
                    self._send_json(
                        {"ok": True, "app": "MYRA", "version": APP_VERSION, "api_v1": True}
                    )
                return
            if method == "GET" and clean_path == "/api/v1/providers":
                self._send_json({"ok": True, "providers": service.providers()})
                return

            # Preferences (never secrets)
            if clean_path == "/api/v1/preferences" and method == "GET":
                self._send_json({"ok": True, "preferences": service.memory.all_preferences()})
                return
            if len(parts) == 4 and parts[:3] == ["api", "v1", "preferences"] and method in {"PUT", "PATCH"}:
                key = parts[3]
                lowered = key.lower()
                if any(word in lowered for word in ("secret", "token", "password", "api_key", "apikey")):
                    self._send_json(
                        {"ok": False, "error": "Secrets cannot be stored as preferences."},
                        status=400,
                    )
                    return
                payload = self._read_json_v1(32_000)
                if payload is None:
                    return
                value = service.memory.set_preference(key, payload.get("value"))
                self._send_json({"ok": True, "key": key, "value": value})
                return

            # Conversations / persistent chat
            if clean_path == "/api/v1/conversations" and method == "GET":
                conversations = service.memory.list_conversations(
                    limit=int(query.get("limit", 50)),
                    include_archived=query.get("archived") == "1",
                )
                self._send_json({"ok": True, "conversations": conversations})
                return
            if clean_path == "/api/v1/conversations" and method == "POST":
                payload = self._read_json_v1(8_000, optional=True)
                if payload is None:
                    return
                conversation = service.create_conversation(
                    title=payload.get("title", "New conversation"),
                    character=payload.get("character", "core"),
                )
                self._send_json({"ok": True, "conversation": conversation}, status=201)
                return
            if len(parts) == 4 and parts[:3] == ["api", "v1", "conversations"]:
                conversation_id = parts[3]
                if method == "GET":
                    conversation = service.memory.get_conversation(conversation_id)
                    if not conversation:
                        raise KeyError("conversation not found")
                    conversation["messages"] = service.memory.list_messages(conversation_id)
                    self._send_json({"ok": True, "conversation": conversation})
                    return
                if method in {"PUT", "PATCH"}:
                    payload = self._read_json_v1(8_000)
                    if payload is None:
                        return
                    conversation = service.memory.rename_conversation(
                        conversation_id, payload.get("title", "")
                    )
                    self._send_json({"ok": True, "conversation": conversation})
                    return
                if method == "DELETE":
                    service.memory.delete_conversation(conversation_id)
                    self._send_json({"ok": True, "deleted": conversation_id})
                    return
            if clean_path == "/api/v1/chat" and method == "POST":
                payload = self._read_json_v1(9_500_000)
                if payload is None:
                    return
                result = service.chat(payload)
                self._send_json(result)
                return
            if clean_path == "/api/v1/chat/stream" and method == "POST":
                payload = self._read_json_v1(9_500_000)
                if payload is None:
                    return
                self._send_ndjson_stream(service.chat_stream(payload))
                return
            if clean_path == "/api/v1/structured" and method == "POST":
                payload = self._read_json_v1(256_000)
                if payload is None:
                    return
                self._send_json({"ok": True, **service.structured(payload)})
                return

            # Memories
            if clean_path == "/api/v1/memories" and method == "GET":
                if query.get("query"):
                    memories = service.memory.search_memories(query["query"], limit=int(query.get("limit", 50)))
                else:
                    memories = service.memory.list_memories(limit=int(query.get("limit", 200)))
                self._send_json({"ok": True, "memories": memories})
                return
            if clean_path == "/api/v1/memories" and method == "POST":
                payload = self._read_json_v1(16_000)
                if payload is None:
                    return
                memory = service.memory.add_memory(
                    payload.get("text", ""),
                    category=payload.get("category", "general"),
                    source="user",
                    pinned=bool(payload.get("pinned", False)),
                )
                self._send_json({"ok": True, "memory": memory}, status=201)
                return
            if len(parts) == 4 and parts[:3] == ["api", "v1", "memories"]:
                memory_id = int(parts[3])
                if method in {"PUT", "PATCH"}:
                    payload = self._read_json_v1(16_000)
                    if payload is None:
                        return
                    memory = service.memory.update_memory(
                        memory_id,
                        text=payload.get("text"),
                        category=payload.get("category"),
                        pinned=payload.get("pinned"),
                    )
                    self._send_json({"ok": True, "memory": memory})
                    return
                if method == "DELETE":
                    service.memory.delete_memory(memory_id)
                    self._send_json({"ok": True, "deleted": memory_id})
                    return

            # Notes
            if clean_path == "/api/v1/notes" and method == "GET":
                notes = service.memory.list_notes(
                    query=query.get("query", ""), limit=int(query.get("limit", 200))
                )
                self._send_json({"ok": True, "notes": notes})
                return
            if clean_path == "/api/v1/notes" and method == "POST":
                payload = self._read_json_v1(64_000)
                if payload is None:
                    return
                note = service.memory.create_note(payload.get("title", ""), payload.get("body", ""))
                self._send_json({"ok": True, "note": note}, status=201)
                return
            if len(parts) == 4 and parts[:3] == ["api", "v1", "notes"]:
                note_id = int(parts[3])
                if method in {"PUT", "PATCH"}:
                    payload = self._read_json_v1(64_000)
                    if payload is None:
                        return
                    note = service.memory.update_note(
                        note_id, title=payload.get("title"), body=payload.get("body")
                    )
                    self._send_json({"ok": True, "note": note})
                    return
                if method == "DELETE":
                    service.memory.delete_note(note_id)
                    self._send_json({"ok": True, "deleted": note_id})
                    return

            # Reminders / unified legacy-data migration
            if clean_path == "/api/v1/reminders" and method == "GET":
                reminders = service.memory.list_reminders(
                    active_only=query.get("active", "1") != "0",
                    limit=int(query.get("limit", 200)),
                )
                self._send_json({"ok": True, "reminders": reminders})
                return
            if clean_path == "/api/v1/reminders/due" and method == "GET":
                self._send_json({"ok": True, "due": service.memory.due_reminders(mark_completed=query.get("mark", "0") == "1")})
                return
            if clean_path == "/api/v1/reminders" and method == "POST":
                payload = self._read_json_v1(16_000)
                if payload is None:
                    return
                reminder = service.memory.create_reminder(
                    payload.get("text", ""), due_at=payload.get("due_at"), minutes=payload.get("minutes")
                )
                self._send_json({"ok": True, "reminder": reminder}, status=201)
                return
            if len(parts) == 4 and parts[:3] == ["api", "v1", "reminders"]:
                reminder_id = int(parts[3])
                if method in {"PUT", "PATCH"}:
                    payload = self._read_json_v1(8_000)
                    if payload is None:
                        return
                    reminder = service.memory.complete_reminder(
                        reminder_id, completed=bool(payload.get("completed", True))
                    )
                    self._send_json({"ok": True, "reminder": reminder})
                    return
                if method == "DELETE":
                    service.memory.delete_reminder(reminder_id)
                    self._send_json({"ok": True, "deleted": reminder_id})
                    return
            if clean_path == "/api/v1/data/migrate-legacy" and method == "POST":
                payload = self._read_json_v1(4_000, optional=True)
                if payload is None:
                    return
                self._send_json({"ok": True, "migration": service.migrate_legacy(payload.get("path"))})
                return

            # Skills
            if clean_path == "/api/v1/skills" and method == "GET":
                self._send_json({"ok": True, "skills": service.registry.list()})
                return
            if len(parts) == 5 and parts[:3] == ["api", "v1", "skills"] and method == "POST":
                skill_id, action = parts[3], parts[4]
                if action == "enabled":
                    payload = self._read_json_v1(4_000)
                    if payload is None:
                        return
                    enabled = service.registry.set_enabled(skill_id, bool(payload.get("enabled")))
                    self._send_json({"ok": True, "skill_id": skill_id, "enabled": enabled})
                    return
                if action == "run":
                    payload = self._read_json_v1(64_000)
                    if payload is None:
                        return
                    result = service.execute_skill(
                        skill_id,
                        arguments=payload.get("arguments") or {},
                        confirmed=bool(payload.get("confirmed", False)),
                    )
                    self._send_json(result)
                    return

            # Agent tasks
            if clean_path == "/api/v1/agent/tasks" and method == "GET":
                self._send_json(
                    {"ok": True, "tasks": service.agent.list_tasks(limit=int(query.get("limit", 50)))}
                )
                return
            if clean_path == "/api/v1/agent/tasks" and method == "POST":
                payload = self._read_json_v1(32_000)
                if payload is None:
                    return
                approved = payload.get("approved_skill_ids")
                if approved is not None and not isinstance(approved, list):
                    raise ValueError("approved_skill_ids must be an array")
                task = service.agent.create_task(
                    payload.get("goal", ""),
                    max_steps=payload.get("max_steps", 6),
                    approval_mode=payload.get("approval_mode", "ask"),
                    approved_skill_ids=approved or [],
                    provider=payload.get("provider", "auto"),
                )
                if payload.get("start"):
                    task = service.agent.start_task(task["id"])
                self._send_json({"ok": True, "task": task}, status=201)
                return
            if len(parts) == 5 and parts[:3] == ["api", "v1", "agent"] and parts[3] == "tasks" and method == "GET":
                self._send_json({"ok": True, "task": service.agent.get_task(parts[4])})
                return
            if len(parts) == 6 and parts[:3] == ["api", "v1", "agent"] and parts[3] == "tasks" and method == "POST":
                task_id, action = parts[4], parts[5]
                if self._read_json_v1(4_000, optional=True) is None:
                    return
                actions = {
                    "start": service.agent.start_task,
                    "pause": service.agent.pause_task,
                    "resume": service.agent.resume_task,
                    "cancel": service.agent.cancel_task,
                    "approve": service.agent.approve_pending,
                    "deny": service.agent.deny_pending,
                }
                handler = actions.get(action)
                if not handler:
                    self._send_json({"ok": False, "error": "Unknown agent action."}, status=404)
                    return
                self._send_json({"ok": True, "task": handler(task_id)})
                return

            # Web research / World Monitor
            if clean_path == "/api/v1/research" and method == "POST":
                payload = self._read_json_v1(16_000)
                if payload is None:
                    return
                self._send_json(service.research(payload))
                return
            if clean_path == "/api/v1/world/news" and method == "GET":
                import news
                self._send_json(news.get_news(region=query.get("region", "all"), force_refresh=query.get("refresh") == "1"))
                return

            # Realtime voice pipeline (desktop owns microphone/speaker)
            if clean_path == "/api/v1/voice/status" and method == "GET":
                self._send_json({"ok": True, "voice": service.voice_status()})
                return
            if clean_path == "/api/v1/voice/models/install" and method == "POST":
                payload = self._read_json_v1(8_000)
                if payload is None:
                    return
                self._send_json({"ok": True, "model": service.install_voice_model(payload)}, status=201)
                return
            if len(parts) == 6 and parts[:4] == ["api", "v1", "voice", "models"] and method == "DELETE":
                removed = service.voice.remove_model_record(
                    parts[4], parts[5], delete_file=query.get("delete_file") == "1"
                )
                self._send_json({"ok": True, "removed": removed})
                return
            if clean_path == "/api/v1/voice/transcribe" and method == "POST":
                payload = self._read_json_v1(35_000_000)
                if payload is None:
                    return
                self._send_json({"ok": True, "transcript": service.transcribe_voice(payload)})
                return
            if clean_path == "/api/v1/voice/synthesize" and method == "POST":
                payload = self._read_json_v1(128_000)
                if payload is None:
                    return
                self._send_json({"ok": True, "audio": service.synthesize_voice(payload)})
                return
            if clean_path == "/api/v1/voice/turn" and method == "POST":
                payload = self._read_json_v1(35_000_000)
                if payload is None:
                    return
                self._send_json(service.voice_turn(payload))
                return

            # Live sampled screen/camera vision
            if clean_path == "/api/v1/live-vision/sessions" and method == "GET":
                self._send_json({"ok": True, "sessions": service.live_vision.list_sessions()})
                return
            if clean_path == "/api/v1/live-vision/sessions" and method == "POST":
                payload = self._read_json_v1(16_000)
                if payload is None:
                    return
                session = service.live_vision.start_session(
                    payload.get("source", ""),
                    consent=payload.get("consent") is True,
                    analysis_interval_seconds=payload.get("analysis_interval_seconds", 4),
                    prompt=payload.get("prompt", ""),
                    max_analyses=payload.get("max_analyses", 30),
                )
                self._send_json({"ok": True, "session": session}, status=201)
                return
            if clean_path == "/api/v1/live-vision/stop-all" and method == "POST":
                if self._read_json_v1(4_000, optional=True) is None:
                    return
                self._send_json({"ok": True, "sessions": service.live_vision.stop_all()})
                return
            if len(parts) == 5 and parts[:4] == ["api", "v1", "live-vision", "sessions"] and method == "GET":
                self._send_json({"ok": True, "session": service.live_vision.get_session(parts[4])})
                return
            if len(parts) == 6 and parts[:4] == ["api", "v1", "live-vision", "sessions"] and method == "POST":
                session_id, action = parts[4], parts[5]
                if action == "frame":
                    payload = self._read_json_v1(9_000_000)
                    if payload is None:
                        return
                    result = service.live_vision.submit_frame(
                        session_id,
                        payload.get("image_base64", ""),
                        mime_type=payload.get("mime_type", "image/jpeg"),
                        captured_at=payload.get("captured_at", ""),
                        analyze_now=bool(payload.get("analyze_now", False)),
                    )
                    self._send_json(result, status=200 if result.get("ok") else 502)
                    return
                if self._read_json_v1(4_000, optional=True) is None:
                    return
                actions = {
                    "pause": service.live_vision.pause_session,
                    "resume": service.live_vision.resume_session,
                    "stop": service.live_vision.stop_session,
                }
                handler = actions.get(action)
                if not handler:
                    self._send_json({"ok": False, "error": "Unknown live-vision action."}, status=404)
                    return
                self._send_json({"ok": True, "session": handler(session_id)})
                return

            # Optional browser automation / semantic Windows control
            if clean_path == "/api/v1/browser/status" and method == "GET":
                from browser_control import browser_status
                self._send_json({"ok": True, "browser": browser_status()})
                return
            if clean_path.startswith("/api/v1/browser/") and method == "POST":
                from browser_control import get_browser_controller
                payload = self._read_json_v1(64_000)
                if payload is None:
                    return
                action = parts[3] if len(parts) == 4 else ""
                controller = get_browser_controller()
                if action == "snapshot":
                    result = controller.snapshot(payload.get("url", ""))
                elif action in {"screenshot", "click", "fill"}:
                    if payload.get("confirmed") is not True:
                        self._send_json({"ok": False, "status": "confirmation_required", "error": "Browser action requires explicit confirmation."}, status=409)
                        return
                    if action == "screenshot":
                        result = controller.screenshot(payload.get("url", ""), payload.get("filename", "browser.png"))
                    elif action == "click":
                        result = controller.click(payload.get("url", ""), selector=payload.get("selector", ""), text=payload.get("text", ""))
                    else:
                        result = controller.fill(payload.get("url", ""), payload.get("selector", ""), payload.get("value", ""), submit=bool(payload.get("submit", False)))
                else:
                    self._send_json({"ok": False, "error": "Unknown browser action."}, status=404)
                    return
                self._send_json({"ok": True, "result": result})
                return

            if clean_path == "/api/v1/windows/status" and method == "GET":
                from windows_control import get_windows_controller
                self._send_json({"ok": True, "windows": get_windows_controller().status()})
                return
            if clean_path == "/api/v1/windows/emergency-stop" and method == "POST":
                if self._read_json_v1(4_000, optional=True) is None:
                    return
                from windows_control import get_windows_controller
                self._send_json({"ok": True, **get_windows_controller().emergency_stop()})
                return
            if clean_path == "/api/v1/windows/action" and method == "POST":
                from windows_control import get_windows_controller
                payload = self._read_json_v1(64_000)
                if payload is None:
                    return
                action = str(payload.get("action") or "")
                args = payload.get("arguments") or {}
                if not isinstance(args, dict):
                    raise ValueError("arguments must be an object")
                controller = get_windows_controller()
                read_only = {"list_windows", "observe", "status"}
                if action not in read_only and payload.get("confirmed") is not True:
                    self._send_json({"ok": False, "status": "confirmation_required", "error": "Windows control action requires explicit confirmation."}, status=409)
                    return
                if action == "status":
                    result = controller.status()
                elif action == "list_windows":
                    result = controller.list_windows()
                elif action == "observe":
                    result = controller.observe(args.get("window_title", ""), args.get("max_controls", 160))
                elif action == "focus":
                    result = controller.focus_window(args.get("window_title", ""))
                elif action == "invoke_control":
                    result = controller.invoke_control(**args)
                elif action == "set_text":
                    text = args.pop("text", "")
                    result = controller.set_text(text, **args)
                elif action == "send_keys":
                    result = controller.send_keys(args.get("keys", ""), window_title=args.get("window_title", ""))
                elif action == "click_point":
                    result = controller.click_point(args.get("x", 0), args.get("y", 0), button=args.get("button", "left"), double=bool(args.get("double", False)))
                elif action == "type_text":
                    result = controller.type_text(args.get("text", ""), interval_seconds=args.get("interval_seconds", 0.01))
                elif action == "hotkey":
                    result = controller.hotkey(args.get("keys") or [])
                elif action == "reset_emergency_stop":
                    result = controller.reset_emergency_stop()
                else:
                    self._send_json({"ok": False, "error": "Unknown Windows action."}, status=404)
                    return
                self._send_json({"ok": True, "result": result})
                return

            # Explicit vision, export/backup
            if clean_path == "/api/v1/vision/analyze" and method == "POST":
                payload = self._read_json_v1(9_000_000)
                if payload is None:
                    return
                result = service.analyze_image(payload)
                self._send_json({"ok": True, **result})
                return
            if clean_path == "/api/v1/export" and method == "GET":
                self._send_json({"ok": True, "export": service.memory.export_data()})
                return
            if clean_path == "/api/v1/backup" and method == "POST":
                if self._read_json_v1(4_000, optional=True) is None:
                    return
                self._send_json({"ok": True, "backup_path": service.memory.backup()})
                return
            self._send_json({"ok": False, "error": "Unknown API v1 route."}, status=404)
        except chat.ChatError as exc:
            self._send_json(
                {
                    "ok": False,
                    "code": exc.code,
                    "error_code": exc.code,
                    "error": exc.message,
                    "message": exc.message,
                },
                status=exc.status,
            )
        except KeyError as exc:
            self._send_json({"ok": False, "error": str(exc).strip("'\"")}, status=404)
        except PermissionError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=403)
        except ValueError as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=400)
        except (ResearchError, VoiceEngineError, VoiceModelError, BrowserControlError, WindowsControlError, LiveVisionError) as exc:
            message = str(exc)
            status = 503 if "not installed" in message.lower() or "no faster-whisper model" in message.lower() else 400
            self._send_json({"ok": False, "error": message}, status=status)
        except Exception as exc:  # keep details server-side / in local logs
            traceback.print_exc()
            self._send_json(
                {"ok": False, "error": f"Internal MYRA service error: {exc.__class__.__name__}"},
                status=500,
            )

    # ---------- HTTP verbs ----------

    # BaseHTTPRequestHandler verb entry points used only by API v1.
    def do_PUT(self):
        if urlparse(self.path).path.startswith("/api/v1/"):
            self._handle_api_v1("PUT")
            return
        self._send_json({"ok": False, "error": "Unknown endpoint."}, status=404)

    def do_PATCH(self):
        if urlparse(self.path).path.startswith("/api/v1/"):
            self._handle_api_v1("PATCH")
            return
        self._send_json({"ok": False, "error": "Unknown endpoint."}, status=404)

    def do_DELETE(self):
        if urlparse(self.path).path.startswith("/api/v1/"):
            self._handle_api_v1("DELETE")
            return
        self._send_json({"ok": False, "error": "Unknown endpoint."}, status=404)
