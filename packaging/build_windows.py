"""Build MYRA.exe using only Python tooling.

Run on Windows from the repository root:

    py packaging\\build_windows.py

No batch/PowerShell logic is required.  Child build tools are invoked
without a shell and with CREATE_NO_WINDOW on Windows; output is mirrored
to ``packaging/build-log.txt``.  The resulting ``dist/MYRA/MYRA.exe`` is
itself a windowed GUI executable.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv-build"
LOG = ROOT / "packaging" / "build-log.txt"


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(command, *, cwd=ROOT, timeout=None):
    printable = " ".join(str(part) for part in command)
    print(f"\n>>> {printable}", flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    with LOG.open("a", encoding="utf-8") as log:
        log.write(f"\n>>> {printable}\n")
        log.flush()
        process = subprocess.Popen(
            [str(part) for part in command],
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=flags,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
        code = process.wait(timeout=timeout)
    if code != 0:
        raise SystemExit(f"Build step failed ({code}): {printable}\nSee {LOG}")
    return code


def ensure_venv():
    python = venv_python()
    if python.exists():
        return python
    print(f"Creating build environment: {VENV}")
    builder = venv.EnvBuilder(with_pip=True, upgrade_deps=True)
    builder.create(VENV)
    if not python.exists():
        raise SystemExit(f"Build Python was not created at {python}")
    return python


def main():
    parser = argparse.ArgumentParser(description="Build the MYRA Windows GUI executable with Python only")
    parser.add_argument("--skip-tests", action="store_true", help="Skip unittest discovery")
    parser.add_argument("--skip-smoke", action="store_true", help="Skip MYRA.exe --self-test")
    parser.add_argument("--installer", action="store_true", help="Also compile packaging/MYRA.iss if Inno Setup ISCC is available")
    parser.add_argument("--minimal", action="store_true", help="Skip optional Voice/Automation packages for a smaller EXE")
    args = parser.parse_args()

    LOG.write_text("MYRA Windows build log\n", encoding="utf-8")
    python = ensure_venv()
    requirements = [ROOT / "requirements-desktop.txt", ROOT / "requirements-build.txt"]
    if not args.minimal:
        requirements += [ROOT / "requirements-voice.txt", ROOT / "requirements-automation.txt"]

    run([python, "-m", "pip", "install", "--upgrade", "pip"])
    install_command = [python, "-m", "pip", "install"]
    for requirement in requirements:
        install_command += ["-r", requirement]
    run(install_command)

    if not args.skip_tests:
        run([python, "-m", "unittest", "discover", "-s", "tests", "-v"])

    run([python, "-m", "PyInstaller", "--clean", "--noconfirm", ROOT / "packaging" / "MYRA.spec"])
    exe = ROOT / "dist" / "MYRA" / ("MYRA.exe" if os.name == "nt" else "MYRA")
    if not exe.exists():
        raise SystemExit(f"PyInstaller finished but executable was not found: {exe}")

    if not args.skip_smoke:
        env = os.environ.copy()
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
        print(f"\n>>> Smoke test: {exe} --self-test")
        original_env = os.environ.copy()
        os.environ.update(env)
        try:
            run([exe, "--self-test"], timeout=45)
        finally:
            os.environ.clear()
            os.environ.update(original_env)

    if args.installer:
        iscc = shutil.which("ISCC") or shutil.which("ISCC.exe")
        candidates = [
            Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
            Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
        ]
        if not iscc:
            iscc = next((str(path) for path in candidates if path.exists()), "")
        if not iscc:
            print("Inno Setup ISCC.exe was not found; MYRA.exe build is ready, installer was skipped.")
        else:
            run([iscc, ROOT / "packaging" / "MYRA.iss"])

    print(f"\nBuild complete: {exe}")
    print("Double-click MYRA.exe — it is a windowed Python GUI and opens no CMD/PowerShell window.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
