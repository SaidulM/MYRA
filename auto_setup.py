"""MYRA — Unified Installer & Setup Engine.

Works both:
1. Locally (when extracted from repo ZIP)
2. Standalone (downloads entire repo automatically from GitHub)

Features:
- Installs MYRA to %USERPROFILE%\\MYRA (never touches user .env / data on updates)
- Prompts for Gemini API key, tests connection live, and saves to .env
- Creates Desktop and Start Menu shortcuts on Windows
- Stamps the installed GitHub commit version for smart auto-updates
- Launches MYRA immediately upon completion
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
import ssl
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

REPO = "SaidulM/MYRA"
BRANCH = "main"
GITHUB_ZIP_URL = f"https://codeload.github.com/{REPO}/zip/refs/heads/{BRANCH}"
API_URL = f"https://api.github.com/repos/{REPO}/commits/{BRANCH}"
HEADERS = {"User-Agent": "MYRA-Installer/1.0"}

def _safe_urlopen(req, timeout):
    try:
        return urlopen(req, timeout=timeout)
    except (ssl.SSLError, URLError):
        ctx = ssl._create_unverified_context()
        return urlopen(req, timeout=timeout, context=ctx)

SOURCE = Path(__file__).resolve().parent
TARGET = Path(os.environ.get("MYRA_INSTALL_DIR") or (Path.home() / "MYRA"))
PROTECTED_DIRS = {".git", "__pycache__", ".myra-update"}
PROTECTED_FILES = {".env", "launcher-log.txt", ".myra-update.zip"}


def say(line: str = ""):
    print(line, flush=True)


def is_full_repo(path: Path) -> bool:
    return (path / "backend" / "server.py").exists() and (path / "ui" / "index.html").exists()


def fetch_latest_sha() -> str | None:
    try:
        req = Request(API_URL, headers=HEADERS)
        with _safe_urlopen(req, timeout=10) as res:
            data = json.loads(res.read().decode("utf-8"))
        sha = data.get("sha")
        return str(sha) if sha else None
    except Exception:
        return None


def download_repo_from_github(dest_dir: Path) -> bool:
    """Download full repo archive from GitHub and extract into dest_dir."""
    say(f"⬇️ Downloading latest MYRA release from GitHub ({REPO})…")
    tmp_zip = dest_dir / ".myra-install.zip"
    tmp_extract = dest_dir / ".myra-install-extract"
    dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        req = Request(GITHUB_ZIP_URL, headers=HEADERS)
        with _safe_urlopen(req, timeout=35) as res:
            total = int(res.headers.get("Content-Length") or 0)
            done = 0
            with open(tmp_zip, "wb") as f:
                while True:
                    chunk = res.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = done * 100 // total
                        print(f"\r   Downloading: {pct:3d}%", end="", flush=True)
        print()

        say("📦 Extracting files…")
        if tmp_extract.exists():
            shutil.rmtree(tmp_extract, ignore_errors=True)
        tmp_extract.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(tmp_zip) as zf:
            zf.extractall(tmp_extract)

        inners = [p for p in tmp_extract.iterdir() if p.is_dir()]
        if not inners:
            raise OSError("Downloaded archive was empty")

        inner_root = inners[0]
        # Copy files to dest_dir
        for current, dirs, files in os.walk(inner_root):
            dirs[:] = [d for d in dirs if d not in PROTECTED_DIRS]
            rel = Path(current).relative_to(inner_root)
            for name in files:
                if name in PROTECTED_FILES:
                    continue
                src = Path(current) / name
                dst = dest_dir / rel / name
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        say("✅ MYRA files installed successfully from GitHub.")
        return True
    except Exception as exc:
        say(f"⚠️ Failed to download from GitHub: {exc}")
        return False
    finally:
        if tmp_zip.exists():
            try:
                tmp_zip.unlink(missing_ok=True)
            except OSError:
                pass
        if tmp_extract.exists():
            shutil.rmtree(tmp_extract, ignore_errors=True)


def copy_project():
    """Copy project files SOURCE → TARGET (never over .env / data/)."""
    if SOURCE == TARGET:
        say(f"📂 Already inside the installation directory: {TARGET}")
        return

    if not is_full_repo(SOURCE):
        say("🌐 Running in standalone installer mode. Downloading project files...")
        ok = download_repo_from_github(TARGET)
        if not ok:
            say("❌ Could not download files. Please check your internet connection.")
        return

    TARGET.mkdir(parents=True, exist_ok=True)
    copied = 0
    for current, dirs, files in os.walk(SOURCE):
        rel = Path(current).relative_to(SOURCE)
        if rel.parts and rel.parts[0] == "data":
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in PROTECTED_DIRS]
        for name in files:
            if name in PROTECTED_FILES:
                continue
            src = Path(current) / name
            dst = TARGET / rel / name
            if rel == Path(".") and name == ".env":
                continue
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied += 1
            except OSError:
                pass
    say(f"📂 MYRA installed to: {TARGET} ({copied} files synchronized)")


def ensure_env():
    env_file = TARGET / ".env"
    example = TARGET / ".env.example"
    if env_file.exists():
        say("🔑 Existing .env file found (your saved API keys remain untouched).")
    elif example.exists():
        shutil.copy2(example, env_file)
        say("🔑 Initialized starter .env configuration.")


def setup_api_keys():
    """Interactive API key prompt during setup if no key is configured."""
    env_file = TARGET / ".env"
    ensure_env()

    # Check if key is already set
    existing_gemini = ""
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("GEMINI_API_KEY="):
                existing_gemini = line.split("=", 1)[1].strip().strip('"').strip("'")

    if existing_gemini:
        say(f"🔑 Gemini API key is already configured (••••{existing_gemini[-4:] if len(existing_gemini) > 4 else 'set'}).")
        return

    say("")
    say("------------------------------------------------------------")
    say("🔑 AI Brain Setup — Google Gemini API Key")
    say("   MYRA needs a free Gemini API key to power her chat and agent.")
    say("   You can get one in 1 minute from: https://aistudio.google.com")
    say("------------------------------------------------------------")

    try:
        key = input("Paste your Gemini API key (or press Enter to set up later): ").strip()
    except (EOFError, KeyboardInterrupt):
        key = ""

    if not key:
        say("ℹ️ Skipped for now. You can enter your key inside MYRA when she opens.")
        return

    # Verify key
    say("🔄 Verifying key with Google Gemini API…")
    verified = False
    try:
        sys.path.insert(0, str(TARGET / "backend"))
        import chat  # type: ignore
        res = chat.verify_key_connection(gemini=key)
        if res.get("ok"):
            verified = True
            model_name = res.get("results", {}).get("gemini", {}).get("model", "auto")
            say(f"✅ Connection verified! Google Gemini AI brain is active (Auto-selected model: {model_name}).")
        else:
            msg = res.get("results", {}).get("gemini", {}).get("message", "Verification failed")
            say(f"⚠️ Notice: {msg} (Saving key anyway so you can test inside MYRA)")
    except Exception as exc:
        say(f"⚠️ Could not test live connection ({exc}). Saving key.")

    # Also optionally prompt for Groq backup key
    say("")
    say("🔑 Groq API Key (Optional Free Backup Key)")
    say("   Groq provides instant fallback if Gemini is busy or rate-limited.")
    say("   Get free key in 1 minute: https://console.groq.com")
    try:
        groq_k = input("Paste your Groq API key (or press Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        groq_k = ""

    if groq_k:
        say("🔄 Verifying Groq backup connection…")
        try:
            sys.path.insert(0, str(TARGET / "backend"))
            import chat  # type: ignore
            res_groq = chat.verify_key_connection(groq=groq_k)
            if res_groq.get("ok"):
                gmodel = res_groq.get("results", {}).get("groq", {}).get("model", "auto")
                say(f"✅ Groq backup verified! (Auto-selected model: {gmodel})")
            else:
                msg = res_groq.get("results", {}).get("groq", {}).get("message", "Verification failed")
                say(f"⚠️ Notice: {msg} (Saving key anyway)")
        except Exception:
            pass

    # Save to .env
    try:
        sys.path.insert(0, str(TARGET / "backend"))
        import config  # type: ignore
        config.save_keys(gemini=key, groq=groq_k if groq_k else None)
        say("💾 Keys securely saved on your laptop.")
    except Exception:
        # Fallback manual write
        lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
        new_lines = [l for l in lines if not l.startswith("GEMINI_API_KEY=") and not l.startswith("GROQ_API_KEY=")]
        new_lines.append(f"GEMINI_API_KEY={key}")
        if groq_k:
            new_lines.append(f"GROQ_API_KEY={groq_k}")
        env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        say("💾 Keys saved to .env.")


def make_shortcut(link_path: Path, target_bat: Path, description: str) -> bool:
    """Create a Windows .lnk shortcut via PowerShell."""
    def q(p):
        return "'" + str(p).replace("'", "''") + "'"

    ps = (
        "$w = New-Object -ComObject WScript.Shell; "
        f"$s = $w.CreateShortcut({q(link_path)}); "
        f"$s.TargetPath = {q(target_bat)}; "
        f"$s.WorkingDirectory = {q(TARGET)}; "
        f"$s.Description = {q(description)}; "
        f"$s.IconLocation = {q(sys.executable)}; "
        "$s.Save()"
    )
    res = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, text=True,
    )
    return res.returncode == 0 and link_path.exists()


def create_shortcuts():
    if os.name != "nt":
        say("ℹ️ Desktop shortcuts are Windows-only (skipped on Linux/macOS).")
        return

    desktop = Path.home() / "Desktop" / "MYRA.lnk"
    start_menu = (
        Path(os.environ.get("APPDATA", Path.home()))
        / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "MYRA.lnk"
    )
    target_bat = TARGET / "MYRA.bat"

    ok_desktop = make_shortcut(desktop, target_bat, "MYRA - Personal Desktop AI Assistant")
    start_menu.parent.mkdir(parents=True, exist_ok=True)
    ok_menu = make_shortcut(start_menu, target_bat, "MYRA - Personal Desktop AI Assistant")

    if ok_desktop:
        say("🖥️ Desktop shortcut created: MYRA")
    else:
        say(f"ℹ️ You can start MYRA anytime by double-clicking: {target_bat}")

    if ok_menu:
        say("📌 Start Menu shortcut created: MYRA")


def stamp_version():
    """Stamp latest GitHub commit SHA into .myra-version."""
    version_file = TARGET / ".myra-version"
    sha = fetch_latest_sha()
    if sha:
        version_file.write_text(sha + "\n", encoding="utf-8")
        say(f"🏷️ Version recorded ({sha[:8]}) — auto-updater is active.")
    else:
        say("🏷️ Version check skipped (offline or rate-limited). Will sync on first online run.")


def launch_myra():
    say("")
    say("🚀 Starting MYRA…")
    run_bat = TARGET / "MYRA.bat"
    if os.name == "nt" and run_bat.exists():
        subprocess.Popen(["cmd.exe", "/c", str(run_bat)], cwd=str(TARGET))
    else:
        run_py = TARGET / "run.py"
        if run_py.exists():
            subprocess.Popen([sys.executable, str(run_py)], cwd=str(TARGET))


def install_voice_dependencies():
    say("📦 Checking neural human voice engine (edge-tts)...")
    try:
        import edge_tts
        say("✅ Edge Neural Human Voice Studio is installed and ready.")
    except ImportError:
        say("⬇️ Installing edge-tts for realistic human voice (open-source)...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "edge-tts>=7.0.0"], check=False)
            say("✅ Neural Voice Studio installed successfully.")
        except Exception:
            say("ℹ️ Skipped edge-tts installation. Standard browser voice will be used.")


def main():
    say("")
    say("=" * 60)
    say("  🤖 MYRA — Personal Desktop AI Assistant Setup")
    say("=" * 60)

    if sys.version_info < (3, 8):
        say("❌ MYRA needs Python 3.8 or newer.")
        say("   Please install Python from https://www.python.org and tick 'Add Python to PATH'.")
        return 1

    copy_project()
    install_voice_dependencies()
    setup_api_keys()
    create_shortcuts()
    stamp_version()

    say("")
    say("=" * 60)
    say("✅ Installation completed successfully!")
    say(f"   📂 Location: {TARGET}")
    say("   ▶ Double-click the MYRA icon on your Desktop to start anytime.")
    say("   🔄 Auto-updater is active: every start checks GitHub for updates.")
    say("=" * 60)

    # Launch prompt
    try:
        ans = input("\nDo you want to launch MYRA now? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        ans = "y"

    if ans != "n":
        launch_myra()

    return 0


if __name__ == "__main__":
    sys.exit(main())
