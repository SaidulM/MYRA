"""Smooth GPU-rendered MYRA desktop shell.

This is MYRA's default window.  It displays the owner's original MYRA
interface (``ui/index.html`` + Three.js hologram) inside a native app
window powered by the operating system's GPU web engine (WebView2 on
Windows).  It is deliberately *not* an external Chrome/browser window:
there is no address bar, no browser tabs and no console window, and the
backend runs in this same Python process through ``EmbeddedBackend``.

The older all-Qt window remains available as an advanced/fallback UI via
``MYRA_UI=qt`` or ``--qt``.  The Qt hologram used QPainter on the CPU;
this shell lets WebGL use the GPU, which is why it feels smooth on an
8GB-RAM laptop.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from .embedded_backend import EmbeddedBackend

ROOT = Path(__file__).resolve().parent.parent


def _data_dir() -> Path:
    configured = os.environ.get("MYRA_DATA_DIR", "").strip()
    if configured:
        path = Path(configured).expanduser()
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        path = Path(base) / "MYRA"
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / "MYRA"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _health(base_url: str, timeout: float = 0.6) -> bool:
    try:
        with urllib.request.urlopen(base_url + "/api/health", timeout=timeout) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8") or "{}")
        return payload.get("app") == "MYRA" or payload.get("status") == "ok"
    except (OSError, ValueError, urllib.error.URLError):
        return False


def _wait_for_backend(base_url: str, timeout: float = 12.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _health(base_url):
            return True
        time.sleep(0.15)
    return False


def _backend_base_url(port: int) -> str:
    configured = os.environ.get("MYRA_BACKEND_URL", "").strip().rstrip("/")
    return configured or f"http://127.0.0.1:{port}"


def self_test() -> int:
    """Headless smoke test for the packaged build.

    It proves the webview package imports, the embedded backend starts,
    the health route answers and the original UI HTML is served.  It does
    not open a real WebView2 window (that needs the owner's Windows
    desktop session).
    """
    import webview  # noqa: F401  (import is the test)

    port = int(os.environ.get("MYRA_SELFTEST_PORT", "8876") or 8876)
    base_url = f"http://127.0.0.1:{port}"
    backend = EmbeddedBackend(port=port)
    backend.start()
    try:
        if not _wait_for_backend(base_url, timeout=10):
            return 3
        with urllib.request.urlopen(base_url + "/", timeout=3) as response:
            html = response.read().decode("utf-8", errors="ignore")
        return 0 if "MYRA" in html else 4
    finally:
        backend.stop()


def main() -> int:
    # Import first so run_desktop.py can bootstrap a missing dependency
    # (or fall back to the Qt window) before any backend is started.
    import webview

    port = int(os.environ.get("MYRA_PORT", "8765") or 8765)
    base_url = _backend_base_url(port)

    backend = None
    if not _health(base_url):
        backend = EmbeddedBackend(port=port)
        backend.start()
        if not _wait_for_backend(base_url):
            backend.stop()
            raise RuntimeError(
                "MYRA's embedded backend did not become ready on "
                f"{base_url}. Another program may be using port {port}."
            )

    # Downloads (exports/backups/reports) use the native save dialog.
    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True

    storage_path = _data_dir() / "webview-profile"
    storage_path.mkdir(parents=True, exist_ok=True)
    icon_name = "myra.ico" if os.name == "nt" else "myra.png"
    icon_path = ROOT / "assets" / icon_name

    window = webview.create_window(
        "MYRA",
        url=base_url + "/?shell=desktop",
        width=1460,
        height=920,
        min_size=(980, 640),
        background_color="#02070c",
        text_select=True,
    )
    if window is None:
        if backend is not None:
            backend.stop()
        raise RuntimeError("MYRA could not create its desktop window.")

    try:
        webview.start(
            gui="edgechromium" if os.name == "nt" else None,
            debug=False,
            private_mode=False,
            storage_path=str(storage_path),
            icon=str(icon_path) if icon_path.exists() else None,
        )
    finally:
        if backend is not None:
            backend.stop()
    return 0
