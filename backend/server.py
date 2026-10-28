"""MYRA — backend server.

Pure Python standard library only, so it stays very light on an
8GB RAM laptop.

Live routes:
  GET  /api/health          — liveness + current build stage
  GET  /api/settings        — masked API-key status (Stage 2)
  POST /api/settings/keys   — save Gemini/Groq keys into .env (Stage 2)
  POST /api/settings/remove — remove one saved key (Stage 2)

Planned routes: /api/chat (Stage 3), /api/memory (Stage 4),
/api/notes (Stage 7), /api/agent (Stage 8), /api/news (Stage 10).
"""
import json
import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config  # noqa: E402  (local backend/config.py)

ROOT = Path(__file__).resolve().parent.parent
UI_DIR = ROOT / "ui"

HOST = config.get("MYRA_HOST", config.get("STONIC_HOST", "127.0.0.1"))
PORT = int(config.get("MYRA_PORT", config.get("STONIC_PORT", "8765")))

MAX_BODY = 16 * 1024  # settings payloads are tiny


class MyraHandler(SimpleHTTPRequestHandler):
    """Serves the ui/ folder and answers /api/* routes with JSON."""

    # ---------- GET ----------
    def do_GET(self):
        if self.path.startswith("/api/health"):
            self._send_json({"status": "ok", "app": "MYRA", "stage": 2})
            return
        if self.path.startswith("/api/settings"):
            self._send_json(config.key_status())
            return
        if self.path.startswith("/api/"):
            self._send_json(
                {"error": "This feature arrives in a later stage."}, status=501
            )
            return
        super().do_GET()

    # ---------- POST ----------
    def do_POST(self):
        if self.path.startswith("/api/settings/keys"):
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
            print("🔑 API keys updated (values hidden for safety).")
            self._send_json({"ok": True, **status})
            return
        if self.path.startswith("/api/settings/remove"):
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
            print(f"🗑️ {which} API key removed.")
            self._send_json({"ok": True, **status})
            return
        if self.path.startswith("/api/"):
            self._send_json(
                {"error": "This feature arrives in a later stage."}, status=501
            )
            return
        self._send_json({"error": "Not found."}, status=404)

    # ---------- helpers ----------
    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
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

    def log_message(self, *args):  # keep the console quiet
        pass


def main():
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
