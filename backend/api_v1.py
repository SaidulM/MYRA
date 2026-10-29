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
from service import APP_VERSION, get_service


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
                payload = self._read_json_v1(128_000)
                if payload is None:
                    return
                result = service.chat(payload)
                self._send_json(result)
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

            # Explicit vision, export/backup, voice status
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
            if clean_path == "/api/v1/voice/status" and method == "GET":
                self._send_json({"ok": True, "voice": service.voice.status()})
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
