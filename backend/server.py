"""Stonic AI — ব্যাকএন্ড সার্ভার (ধাপ ১: UI সার্ভ + হেলথ চেক)

শুধু Python standard library ব্যবহার করে — কোনো অতিরিক্ত প্যাকেজ লাগে না,
তাই 8GB RAM ল্যাপটপে অত্যন্ত হালকা থাকবে।

পরের ধাপে এখানেই যোগ হবে: /api/settings (ধাপ ২), /api/chat (ধাপ ৩),
/api/memory (ধাপ ৪), /api/notes (ধাপ ৭), /api/agent (ধাপ ৮), /api/news (ধাপ ১০)।
"""
import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_DIR = ROOT / "ui"

HOST = os.environ.get("STONIC_HOST", "127.0.0.1")
PORT = int(os.environ.get("STONIC_PORT", "8765"))


class StonicHandler(SimpleHTTPRequestHandler):
    """ui/ ফোল্ডার সার্ভ করে + /api/* রাউটগুলো JSON উত্তর দেয়।"""

    def do_GET(self):
        if self.path.startswith("/api/health"):
            self._send_json({"status": "ok", "app": "Stonic AI", "stage": 1})
            return
        if self.path.startswith("/api/"):
            self._send_json(
                {"error": "এই ফিচারটি পরের ধাপে চালু হবে।"}, status=501
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

    def log_message(self, *args):  # কনসোলে অযথা আওয়াজ কমানো
        pass


def main():
    handler = partial(StonicHandler, directory=str(UI_DIR))
    server = ThreadingHTTPServer((HOST, PORT), handler)
    print(f"🤖 Stonic AI চালু হয়েছে: http://{HOST}:{PORT}")
    print("বন্ধ করতে Ctrl+C চাপুন।")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Stonic AI বন্ধ হলো।")


if __name__ == "__main__":
    main()
