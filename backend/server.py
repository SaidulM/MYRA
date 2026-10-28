"""MYRA — backend server (Stage 1: serve UI + health check).

Pure Python standard library only, so it stays very light on an
8GB RAM laptop. Planned routes: /api/settings (Stage 2),
/api/chat (Stage 3), /api/memory (Stage 4), /api/notes (Stage 7),
/api/agent (Stage 8), /api/news (Stage 10).
"""
import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_DIR = ROOT / "ui"

HOST = os.environ.get("MYRA_HOST", os.environ.get("STONIC_HOST", "127.0.0.1"))
PORT = int(os.environ.get("MYRA_PORT", os.environ.get("STONIC_PORT", "8765")))


class MyraHandler(SimpleHTTPRequestHandler):
    """Serves the ui/ folder and answers /api/* routes with JSON."""

    def do_GET(self):
        if self.path.startswith("/api/health"):
            self._send_json({"status": "ok", "app": "MYRA", "stage": 1})
            return
        if self.path.startswith("/api/"):
            self._send_json(
                {"error": "This feature arrives in a later stage."}, status=501
            )
            return
        super().do_GET()

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
