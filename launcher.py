"""MYRA — smart launcher: auto-update from GitHub, then start.

Every time MYRA starts (desktop icon / MYRA.bat / start.bat):

1. If the internet is available, check the project's GitHub
   ``main`` branch for a newer version.
2. If one exists, download it and update this folder automatically.
   Private files are NEVER overwritten: ``.env`` (your API keys) and
   ``data/`` (your memory/notes) always stay untouched.
3. If offline — or anything goes wrong — simply start the version
   that is already installed. An update problem never blocks MYRA.
4. Start MYRA. On Windows the native pure-Python desktop app
   (``MYRA.pyw`` via ``pythonw`` — no console window) is preferred;
   the legacy web app (run.py) remains available with ``--web``.

Flags:
  --no-update    skip the update check and start immediately
  --update-only  only check/download updates, then exit
  --web          start the legacy browser UI instead of the desktop app
Environment: MYRA_NO_UPDATE=1 also skips the check; MYRA_WEB=1 = --web.

Standard library only — light on an 8GB RAM laptop.
"""
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
REPO = "SaidulM/MYRA"
BRANCH = "main"
API_URL = f"https://api.github.com/repos/{REPO}/commits/{BRANCH}"
ZIP_URL = "https://codeload.github.com/{repo}/zip/{sha}"
VERSION_FILE = ROOT / ".myra-version"
LOG_FILE = ROOT / "launcher-log.txt"
TMP_ZIP = ROOT / ".myra-update.zip"
TMP_DIR = ROOT / ".myra-update"

# Names the updater must never touch (your private/local things).
PROTECTED_DIRS = {"data", ".git", "__pycache__", ".myra-update", ".venv", ".venv-desktop", ".venv-build", "build", "dist"}
PROTECTED_FILES = {".env", ".myra-version", "launcher-log.txt", ".myra-update.zip"}

HEADERS = {"User-Agent": "MYRA-Launcher/1.0"}


def say(line=""):
    """Print to the console and append to launcher-log.txt."""
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _open(url, timeout):
    # Verified TLS only: this download becomes running code, so a failed
    # certificate check must degrade to "start the installed version",
    # never to silently trusting an unverified connection.
    req = Request(url, headers=HEADERS)
    return urlopen(req, timeout=timeout)


def fetch_latest_sha():
    """Return the newest commit SHA of the main branch, or None."""
    with _open(API_URL, timeout=8) as res:
        data = json.loads(res.read().decode("utf-8"))
    sha = data.get("sha")
    return sha if isinstance(sha, str) and sha else None


def local_version():
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def save_version(sha):
    try:
        VERSION_FILE.write_text(sha + "\n", encoding="utf-8")
    except OSError:
        pass


def _download(url, dest):
    with _open(url, timeout=20) as res:
        total = int(res.headers.get("Content-Length") or 0)
        done = 0
        with open(dest, "wb") as f:
            while True:
                chunk = res.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total
                    print(f"\r   Downloading update… {pct:3d}%", end="", flush=True)
    print()


def _copy_update(src_root):
    """Copy extracted files over this folder, protecting private files."""
    copied, failed = 0, 0
    for current, dirs, files in os.walk(src_root):
        dirs[:] = [d for d in dirs if d not in PROTECTED_DIRS]
        rel = Path(current).relative_to(src_root)
        for name in files:
            if name in PROTECTED_FILES:
                continue
            src = Path(current) / name
            dst = ROOT / rel / name
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied += 1
            except OSError:
                failed += 1
    return copied, failed


def try_update():
    """Check GitHub and update if needed. Returns a short status word."""
    try:
        latest = fetch_latest_sha()
    except (URLError, TimeoutError, OSError, ValueError):
        say("📡 No internet (or GitHub unreachable) — starting the installed version.")
        return "offline"

    if not latest:
        say("📡 Could not read the latest version info — starting the installed version.")
        return "offline"

    current = local_version()
    if current == latest:
        say("✅ MYRA is already up to date.")
        return "current"

    say("⬇️ A new MYRA update found — downloading it now (your keys & data stay safe)…")
    try:
        _download(ZIP_URL.format(repo=REPO, sha=latest), TMP_ZIP)
        if TMP_DIR.exists():
            shutil.rmtree(TMP_DIR, ignore_errors=True)
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(TMP_ZIP) as zf:
            zf.extractall(TMP_DIR)
        inners = [p for p in TMP_DIR.iterdir() if p.is_dir()]
        if not inners:
            raise OSError("update package was empty")
        copied, failed = _copy_update(inners[0])
        save_version(latest)
        say(f"✅ Update installed ({copied} files refreshed"
            + (f", {failed} skipped" if failed else "") + ").")
        return "updated"
    except (URLError, TimeoutError, OSError, zipfile.BadZipFile) as exc:
        say(f"⚠️ Update could not finish ({type(exc).__name__}) — starting the installed version.")
        return "failed"
    finally:
        for p in (TMP_ZIP,):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
        shutil.rmtree(TMP_DIR, ignore_errors=True)


def _pythonw_candidates():
    """Windowless Python interpreters, best first (Windows only)."""
    venv_pythonw = ROOT / ".venv-desktop" / "Scripts" / "pythonw.exe"
    sibling = Path(sys.executable).with_name("pythonw.exe")
    return [p for p in (venv_pythonw, sibling) if p.exists()]


def start_desktop():
    """Launch the native PySide6 app without any console window.

    Returns True if the desktop process was spawned.  First-run package
    setup is handled inside MYRA.pyw itself (a Python setup window), so
    this works even before `.venv-desktop` exists.
    """
    entry = ROOT / "MYRA.pyw"
    if os.name != "nt" or not entry.exists():
        return False
    for pythonw in _pythonw_candidates():
        try:
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
            subprocess.Popen(
                [str(pythonw), str(entry)],
                cwd=str(ROOT),
                close_fds=True,
                creationflags=flags,
            )
            say("🖥️ MYRA desktop app is opening (no console window needed). "
                "This update window will now close.")
            return True
        except OSError:
            continue
    return False


def start_myra(prefer_desktop=True):
    if prefer_desktop and start_desktop():
        return 0
    run_py = ROOT / "run.py"
    if run_py.exists():
        return subprocess.run([sys.executable, str(run_py)], cwd=str(ROOT)).returncode
    # Fallback if run.py is missing: start the backend directly.
    say("⚠️ run.py not found — starting the backend directly.")
    return subprocess.run(
        [sys.executable, str(ROOT / "backend" / "server.py")], cwd=str(ROOT)
    ).returncode


def ensure_voice_engine():
    try:
        import edge_tts
    except ImportError:
        try:
            say("⬇️ Initializing neural voice engine (edge-tts)...")
            subprocess.run([sys.executable, "-m", "pip", "install", "edge-tts>=7.0.0"], capture_output=True)
        except Exception:
            pass


def main(argv):
    no_update = "--no-update" in argv or os.environ.get("MYRA_NO_UPDATE") == "1"
    update_only = "--update-only" in argv
    prefer_desktop = "--web" not in argv and os.environ.get("MYRA_WEB") != "1"

    say("")
    say("=" * 58)
    say(f"  🤖 MYRA launcher — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    say("=" * 58)

    if no_update:
        say("⏩ Update check skipped (--no-update).")
    else:
        say("🔍 Checking GitHub for MYRA updates…")
        try_update()

    ensure_voice_engine()

    if update_only:
        say("✔️ Update check finished (--update-only). MYRA was not started.")
        return 0

    if prefer_desktop:
        say("🚀 Starting the MYRA desktop app…")
    else:
        say("🚀 Starting MYRA (web)… (keep this window open while MYRA runs; "
            "close it or press Ctrl+C to quit)")
    try:
        return start_myra(prefer_desktop=prefer_desktop)
    except KeyboardInterrupt:
        say("\n👋 MYRA closed.")
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
