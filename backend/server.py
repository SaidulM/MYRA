"""MYRA — Unified Backend Server.

Lightweight Python standard library server powering UI, API routes,
local memory (SQLite), notes, skills, agent tasks, news feeds,
and auto-update detection.
"""
from __future__ import annotations

import json
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import agent  # noqa: E402
import chat  # noqa: E402
import config  # noqa: E402
import memory  # noqa: E402
import news  # noqa: E402
import notes  # noqa: E402
import skills_manager  # noqa: E402

try:
    import launcher
except Exception:
    launcher = None

UI_DIR = ROOT / "ui"

HOST = config.get("MYRA_HOST", config.get("STONIC_HOST", "127.0.0.1"))
PORT = int(config.get("MYRA_PORT", config.get("STONIC_PORT", "8765")))

MAX_BODY = 32 * 1024
MAX_CHAT_BODY = 128 * 1024


class MyraHandler(SimpleHTTPRequestHandler):
    """Serves ui/ and answers all /api/* routes with JSON."""

    # ---------- GET ----------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/health":
            self._send_json({
                "status": "ok",
                "app": "MYRA",
                "stage": 11,
                "version": "1.0.0",
                "ready": True,
            })
            return

        if path == "/api/settings":
            self._send_json(config.key_status())
            return

        if path == "/api/memory":
            self._send_json({
                "ok": True,
                "memories": memory.list_memories(),
            })
            return

        if path == "/api/notes":
            self._send_json({
                "ok": True,
                "notes": notes.get_notes(),
            })
            return

        if path == "/api/skills":
            self._send_json({
                "ok": True,
                "skills": skills_manager.list_skills(),
            })
            return

        if path == "/api/news":
            region = query.get("region", ["all"])[0]
            force = query.get("refresh", ["0"])[0] in {"1", "true"}
            self._send_json(news.get_news(region=region, force_refresh=force))
            return

        if path == "/api/system/update-check":
            current_ver = ""
            latest_ver = None
            update_available = False
            error_msg = None

            if launcher:
                try:
                    current_ver = launcher.local_version()
                    latest_ver = launcher.fetch_latest_sha()
                    if latest_ver and current_ver and latest_ver != current_ver:
                        update_available = True
                except Exception as exc:
                    error_msg = str(exc)
            else:
                error_msg = "Launcher module not available"

            self._send_json({
                "ok": True,
                "update_available": update_available,
                "current_version": current_ver[:8] if current_ver else "local",
                "latest_version": latest_ver[:8] if latest_ver else "unknown",
                "error": error_msg,
            })
            return

        if path.startswith("/api/"):
            self._send_json({"error": "Unknown API endpoint."}, status=404)
            return

        super().do_GET()

    # ---------- POST ----------
    def do_POST(self):
        path = urlparse(self.path).path

        # 1. Chat
        if path == "/api/chat":
            data = self._read_json(max_bytes=MAX_CHAT_BODY)
            if data is None:
                return
            try:
                result = chat.get_reply(data)
            except chat.ChatError as exc:
                self._send_json(
                    {
                        "ok": False,
                        "error_code": exc.code,
                        "message": exc.message,
                        "provider": exc.provider,
                    },
                    status=exc.status,
                )
                return
            except Exception as exc:
                self._send_json(
                    {
                        "ok": False,
                        "error_code": "internal_error",
                        "message": f"MYRA encountered an unexpected problem: {exc}",
                    },
                    status=500,
                )
                return
            self._send_json(result)
            return

        # 2. Key settings save
        if path == "/api/settings/keys":
            data = self._read_json()
            if data is None:
                return
            gemini = data.get("gemini_key")
            groq = data.get("groq_key")
            for value in (gemini, groq):
                if value is not None and (not isinstance(value, str) or len(value) > 300):
                    self._send_json({"error": "Invalid key format."}, status=400)
                    return
            status = config.save_keys(gemini=gemini, groq=groq)
            self._send_json({"ok": True, **status})
            return

        # 3. Key verification
        if path == "/api/settings/verify":
            data = self._read_json()
            if data is None:
                return
            gemini = data.get("gemini_key") or config.gemini_key()
            groq = data.get("groq_key") or config.groq_key()
            res = chat.verify_key_connection(gemini=gemini, groq=groq)
            self._send_json(res)
            return

        # 4. Remove saved key
        if path == "/api/settings/remove":
            data = self._read_json()
            if data is None:
                return
            which = data.get("which")
            if which == "gemini":
                status = config.save_keys(gemini="")
            elif which == "groq":
                status = config.save_keys(groq="")
            else:
                self._send_json({"error": "Unknown key name."}, status=400)
                return
            self._send_json({"ok": True, **status})
            return

        # 5. Memory routes
        if path == "/api/memory":
            data = self._read_json()
            if data is None:
                return
            text = data.get("text", "")
            cat = data.get("category", "general")
            mem_id = memory.add_memory(text, cat)
            self._send_json({"ok": bool(mem_id), "id": mem_id})
            return

        if path == "/api/memory/delete":
            data = self._read_json()
            if data is None:
                return
            mem_id = data.get("id")
            deleted = memory.delete_memory(mem_id)
            self._send_json({"ok": deleted})
            return

        if path == "/api/memory/clear":
            self._send_json({"ok": memory.clear_memories()})
            return

        # 6. Notes routes
        if path == "/api/notes":
            data = self._read_json()
            if data is None:
                return
            content = data.get("content", "")
            title = data.get("title", "")
            res = notes.add_note(content, title)
            self._send_json({"ok": bool(res), "note": res})
            return

        if path == "/api/notes/delete":
            data = self._read_json()
            if data is None:
                return
            note_id = data.get("id")
            deleted = notes.delete_note(note_id)
            self._send_json({"ok": deleted})
            return

        # 7. Agent Mode route
        if path == "/api/agent/run":
            data = self._read_json(max_bytes=MAX_CHAT_BODY)
            if data is None:
                return
            task = data.get("task", "")
            res = agent.run_agent_task(task)
            self._send_json(res)
            return

        # 8. Auto-update apply route
        if path == "/api/system/update-apply":
            if launcher:
                status = launcher.try_update()
                self._send_json({"ok": True, "status": status})
            else:
                self._send_json({"ok": False, "error": "Launcher not found"}, status=500)
            return

        self._send_json({"error": "Not found."}, status=404)

    # ---------- helpers ----------
    def _read_json(self, max_bytes=MAX_BODY):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > max_bytes:
            self._send_json({"error": "Bad request body."}, status=400)
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send_json({"error": "Body must be JSON."}, status=400)
            return None

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    # Initialize SQLite database
    memory.init_db()
    notes.init_db()

    handler = partial(MyraHandler, directory=str(UI_DIR))
    server = ThreadingHTTPServer((HOST, PORT), handler)
    print(f"🤖 MYRA is running at http://{HOST}:{PORT}")
    print("Press Ctrl+C to quit.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 MYRA shut down.")


if __name__ == "__main__":
    main()
