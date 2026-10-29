"""First-run/update GUI setup for MYRA source installs.

When ``MYRA.pyw`` is opened with a Python that does not yet have MYRA's
desktop packages (pywebview/PySide6), this module shows a small Tkinter
setup window, creates or updates ``.venv-desktop`` with Python's own
``venv`` module, installs MYRA's packages without a shell/console window,
then relaunches MYRA through ``pythonw.exe``.
"""
from __future__ import annotations

import os
import subprocess
import threading
import venv
from pathlib import Path


def _venv_executable(venv_dir: Path, windowed=True) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / ("pythonw.exe" if windowed else "python.exe")
    return venv_dir / "bin" / "python"


def _no_window_flags():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def bootstrap_and_launch(root: Path) -> bool:
    root = Path(root)
    venv_dir = root / ".venv-desktop"
    python = _venv_executable(venv_dir, windowed=False)
    pythonw = _venv_executable(venv_dir, windowed=True)

    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
    except Exception:
        return False

    window = tk.Tk()
    window.title("MYRA — first-time Python setup")
    window.geometry("680x430")
    window.resizable(False, False)

    title = tk.Label(window, text="Setting up MYRA Desktop", font=("Segoe UI", 15, "bold"))
    title.pack(pady=(16, 6))
    note = tk.Label(
        window,
        text="MYRA will create its own Python environment and install the desktop, voice and automation packages once.\nNo Command Prompt or PowerShell window is used.",
        justify="center",
        font=("Segoe UI", 10),
    )
    note.pack(pady=(0, 10))
    progress = ttk.Progressbar(window, mode="indeterminate", length=560)
    progress.pack(pady=6)
    progress.start(12)
    log = tk.Text(window, height=14, width=82, font=("Consolas", 8))
    log.pack(padx=14, pady=8)
    status = tk.StringVar(value="Preparing…")
    tk.Label(window, textvariable=status, font=("Segoe UI", 9)).pack(pady=(0, 10))

    launched = {"value": False}

    def write(message):
        def append():
            log.insert("end", str(message) + "\n")
            log.see("end")
        window.after(0, append)

    def set_status(message):
        window.after(0, lambda: status.set(str(message)))

    def run_pip():
        requirements = [
            root / "requirements-desktop.txt",
            root / "requirements-voice.txt",
            root / "requirements-automation.txt",
        ]
        command = [str(python), "-m", "pip", "install", "--upgrade", "pip"]
        write("Upgrading pip inside MYRA's Python environment…")
        result = subprocess.run(
            command, cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", creationflags=_no_window_flags(),
        )
        if result.stdout:
            write(result.stdout[-4000:])
        if result.returncode != 0:
            raise RuntimeError("pip upgrade failed. Check the internet connection and try again.")

        command = [str(python), "-m", "pip", "install"]
        for requirement in requirements:
            command += ["-r", str(requirement)]
        write("Installing MYRA desktop (smooth GPU shell), voice and automation packages…")
        result = subprocess.run(
            command, cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", creationflags=_no_window_flags(),
        )
        if result.stdout:
            write(result.stdout[-8000:])
        if result.returncode != 0:
            raise RuntimeError("MYRA package installation failed. Check the internet connection and try again.")

    def worker():
        try:
            if not python.exists():
                set_status("Creating MYRA Python environment…")
                write(f"Creating {venv_dir}")
                venv.EnvBuilder(with_pip=True, upgrade_deps=True).create(venv_dir)
            set_status("Installing MYRA Python packages…")
            run_pip()
            set_status("Launching MYRA…")
            env = os.environ.copy()
            env["MYRA_BOOTSTRAPPED"] = "1"
            subprocess.Popen(
                [str(pythonw), str(root / "MYRA.pyw")],
                cwd=str(root),
                env=env,
                creationflags=_no_window_flags(),
                close_fds=True,
            )
            launched["value"] = True
            window.after(300, window.destroy)
        except Exception as exc:
            error_message = str(exc)

            def fail(message=error_message):
                progress.stop()
                messagebox.showerror("MYRA setup failed", message, parent=window)
                window.destroy()

            window.after(0, fail)

    threading.Thread(target=worker, name="myra-python-bootstrap", daemon=True).start()
    window.mainloop()
    return launched["value"]
