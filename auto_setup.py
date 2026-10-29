"""MYRA — one-time setup for Windows (safe to run again any time).

What it does:
  1. Installs MYRA into  %USERPROFILE%\\MYRA  (a fixed home on the laptop).
     Your existing .env (API keys) and data/ are never overwritten.
  2. Creates a "MYRA" shortcut on the Desktop and in the Start Menu.
     From then on, double-clicking that icon auto-updates MYRA from
     GitHub and starts her (see launcher.py).
  3. Makes sure a starter .env file exists.
  4. Records the installed version so the launcher only downloads
     when something actually changed on GitHub.

Run it via MYRA-Setup.bat (which also installs Python if needed),
or directly:  python auto_setup.py
Override the install folder with the MYRA_INSTALL_DIR env variable.
Standard library only.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
TARGET = Path(os.environ.get("MYRA_INSTALL_DIR") or Path.home() / "MYRA")
PROTECTED_DIRS = {".git", "__pycache__", ".myra-update", ".venv", ".venv-desktop", ".venv-build", "build", "dist"}
PROTECTED_FILES = {".env", "launcher-log.txt", ".myra-update.zip"}


def say(line=""):
    print(line, flush=True)


def copy_project():
    """Copy project files SOURCE → TARGET (never over .env / data/)."""
    if SOURCE == TARGET:
        say("📂 Already running from the install folder — no copy needed.")
        return
    TARGET.mkdir(parents=True, exist_ok=True)
    copied = 0
    for current, dirs, files in os.walk(SOURCE):
        rel = Path(current).relative_to(SOURCE)
        if rel.parts and rel.parts[0] == "data":
            dirs[:] = []
            continue  # never copy local private data around
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
    say(f"📂 MYRA installed to: {TARGET}  ({copied} files)")


def ensure_env():
    env_file = TARGET / ".env"
    example = TARGET / ".env.example"
    if env_file.exists():
        say("🔑 Your existing .env (saved API keys) was kept as-is.")
    elif example.exists():
        shutil.copy2(example, env_file)
        say("🔑 Created a fresh .env — paste your keys later inside MYRA's SETTING window.")


def make_shortcut(link_path):
    """Create a Windows .lnk shortcut via PowerShell (WScript.Shell)."""
    target_bat = TARGET / "MYRA.bat"

    def q(p):  # PowerShell single-quote escaping
        return "'" + str(p).replace("'", "''") + "'"

    ps = (
        "$w = New-Object -ComObject WScript.Shell; "
        f"$s = $w.CreateShortcut({q(link_path)}); "
        f"$s.TargetPath = {q(target_bat)}; "
        f"$s.WorkingDirectory = {q(TARGET)}; "
        "$s.Description = 'MYRA - Personal Desktop AI Assistant'; "
        f"$s.IconLocation = {q(sys.executable)}; "
        "$s.Save()"
    )
    res = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, text=True,
    )
    return res.returncode == 0 and Path(link_path).exists()


def create_shortcuts():
    if os.name != "nt":
        say("ℹ️ Shortcuts are Windows-only — skipped on this system.")
        return
    desktop = Path.home() / "Desktop" / "MYRA.lnk"
    start_menu = (
        Path(os.environ.get("APPDATA", Path.home()))
        / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "MYRA.lnk"
    )
    ok_desktop = make_shortcut(desktop)
    start_menu.parent.mkdir(parents=True, exist_ok=True)
    ok_menu = make_shortcut(start_menu)
    if ok_desktop:
        say("🖥️ Desktop shortcut created:  MYRA")
    else:
        say("⚠️ Could not create the desktop shortcut automatically.")
        say(f"   You can still start MYRA by double-clicking: {TARGET / 'MYRA.bat'}")
    if ok_menu:
        say("📌 Start Menu shortcut created:  MYRA")


def stamp_version():
    """Record the GitHub version we just installed (if online)."""
    version_file = TARGET / ".myra-version"
    try:
        import launcher  # sits next to this file in the project
        sha = launcher.fetch_latest_sha()
    except Exception:
        sha = None
    if sha:
        version_file.write_text(sha + "\n", encoding="utf-8")
        say("🏷️ Version recorded — future starts will only download real changes.")
    else:
        say("🏷️ Offline right now — the first online start will sync to the latest version.")


def main():
    say("")
    say("=" * 58)
    say("  🤖 MYRA — one-time setup")
    say("=" * 58)
    if sys.version_info < (3, 10):
        say("❌ MYRA needs Python 3.10 or newer.")
        say("   Please install it from https://www.python.org (tick \"Add Python to PATH\")")
        say("   and then run MYRA-Setup.bat again.")
        return 1

    copy_project()
    ensure_env()
    create_shortcuts()
    stamp_version()

    say("")
    say("✅ Setup complete!")
    say("   ▶ To use MYRA: double-click the MYRA icon on your Desktop.")
    say("     Every start first checks GitHub and auto-downloads any")
    say("     new update, then opens MYRA. No manual downloading needed.")
    say("   ▶ First time inside MYRA: open SETTING and save your free")
    say("     Gemini + Groq API keys (they stay only on this laptop).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
