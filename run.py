"""MYRA — Desktop Application Launcher 🚀

Runs MYRA as a 100% native Python desktop software application.
No web browser tabs, no search/address bar — genuine desktop software window.

Architecture:
1. Backend HTTP server runs in a background daemon thread (powers local APIs).
2. Desktop window runs on the main thread:
   - Primary: 100% Native Python Tkinter Desktop Interface (myra_gui.py)
   - Alternative: PyWebView standalone desktop window frame (if --webview is passed)
3. Zero browser fallback: No external browser (Chrome, Edge, Firefox) is ever opened.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

import server

HOST = os.environ.get("MYRA_HOST", os.environ.get("STONIC_HOST", "127.0.0.1"))
PORT = os.environ.get("MYRA_PORT", os.environ.get("STONIC_PORT", "8765"))


def start_backend_daemon():
    """Run backend server on a background daemon thread."""
    t = threading.Thread(target=server.main, daemon=True)
    t.start()
    return t


def launch_pywebview():
    """Launch embedded desktop window frame via pywebview on the main thread."""
    import webview
    url = f"http://127.0.0.1:{PORT}"
    time.sleep(1.0)
    webview.create_window(
        "MYRA — Personal Desktop AI Assistant",
        url=url,
        width=1450,
        height=920,
        resizable=True,
        easy_drag=True,
    )
    webview.start()


def main():
    # 1. Start the backend services in a background thread
    start_backend_daemon()

    # 2. Check if user requested pywebview mode
    if "--webview" in sys.argv:
        try:
            launch_pywebview()
            return 0
        except Exception as exc:
            print(f"PyWebView not available ({exc}), falling back to native Python GUI.")

    # 3. Default & Primary: Native Python GUI Window (myra_gui)
    import myra_gui
    ok = myra_gui.start_gui()
    if not ok:
        print("Starting headless server (Ctrl+C to quit)...")
        while True:
            time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
