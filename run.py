"""MYRA — launch with one command 🚀

Usage:  python run.py
Starts the server and opens the UI in a desktop-like app window.
"""
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOST = os.environ.get("MYRA_HOST", os.environ.get("STONIC_HOST", "127.0.0.1"))
PORT = os.environ.get("MYRA_PORT", os.environ.get("STONIC_PORT", "8765"))


def open_browser():
    time.sleep(1.2)  # give the server a moment to come up
    url = f"http://127.0.0.1:{PORT}"
    # If Edge/Chrome exists, open in "app window" mode (feels like a desktop app)
    for exe in ("msedge", "chrome", "google-chrome", "chromium"):
        try:
            subprocess.Popen(
                [exe, f"--app={url}", "--window-size=1500,950"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return
        except FileNotFoundError:
            continue
    webbrowser.open(url)  # fallback: default browser


if __name__ == "__main__":
    if "--no-browser" not in sys.argv:
        threading.Thread(target=open_browser, daemon=True).start()
    sys.path.insert(0, str(ROOT / "backend"))
    import server
    server.main()
