"""MYRA — launch with one command 🚀

Usage:  python run.py
Starts the server and opens the UI in a dedicated desktop app window.
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


def open_browser(scheme="http"):
    time.sleep(1.2)  # give the server a moment to come up
    url = f"{scheme}://127.0.0.1:{PORT}"

    # Search candidates: command names as well as standard Windows desktop browser paths
    candidates = ["msedge", "chrome", "google-chrome", "chromium"]
    if os.name == "nt":
        prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        prog_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local_app = os.environ.get("LOCALAPPDATA", "")
        windows_paths = [
            os.path.join(prog_files_x86, r"Microsoft\Edge\Application\msedge.exe"),
            os.path.join(prog_files, r"Microsoft\Edge\Application\msedge.exe"),
            os.path.join(prog_files, r"Google\Chrome\Application\chrome.exe"),
            os.path.join(prog_files_x86, r"Google\Chrome\Application\chrome.exe"),
            os.path.join(local_app, r"Microsoft\Edge\Application\msedge.exe"),
            os.path.join(local_app, r"Google\Chrome\Application\chrome.exe"),
        ]
        candidates = [p for p in windows_paths if os.path.exists(p)] + candidates

    # If Edge/Chrome exists, open in dedicated "app window" mode (frameless standalone desktop app)
    for exe in candidates:
        try:
            subprocess.Popen(
                [exe, f"--app={url}", "--window-size=1500,950"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return
        except (FileNotFoundError, OSError):
            continue
    webbrowser.open(url)  # fallback: default browser


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "backend"))
    import server
    scheme = "https" if server.TLS_CERT_FILE and server.TLS_KEY_FILE else "http"
    if "--no-browser" not in sys.argv:
        threading.Thread(target=open_browser, args=(scheme,), daemon=True).start()
    server.main()
