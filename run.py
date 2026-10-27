"""Stonic AI — এক কমান্ডে চালু করো 🚀

ব্যবহার:  python run.py
সার্ভার চালু হয়ে ব্রাউজারে ডেস্কটপ উইন্ডোর মতো UI নিজে খুলে যাবে।
"""
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOST = os.environ.get("STONIC_HOST", "127.0.0.1")
PORT = os.environ.get("STONIC_PORT", "8765")


def open_browser():
    time.sleep(1.2)  # সার্ভার প্রস্তুত হওয়ার জন্য সামান্য অপেক্ষা
    url = f"http://127.0.0.1:{PORT}"
    # Edge/Chrome থাকলে "app window" মোডে খোলা হবে (ডেস্কটপ অ্যাপের মতো লাগবে)
    for exe in ("msedge", "chrome", "google-chrome", "chromium"):
        try:
            subprocess.Popen(
                [exe, f"--app={url}", "--window-size=1500,950"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return
        except FileNotFoundError:
            continue
    webbrowser.open(url)  # ফলব্যাক: ডিফল্ট ব্রাউজার


if __name__ == "__main__":
    if "--no-browser" not in sys.argv:
        threading.Thread(target=open_browser, daemon=True).start()
    sys.path.insert(0, str(ROOT / "backend"))
    import server
    server.main()
