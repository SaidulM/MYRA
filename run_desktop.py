"""MYRA desktop entry point.

Preferred source launch on Windows: ``MYRA.pyw`` (uses pythonw, so no
console window appears).  In the packaged build this module is the
PyInstaller entry point for ``MYRA.exe`` with ``console=False``.

The default window is the smooth GPU shell (``desktop/web_shell.py``):
it shows MYRA's original interface inside a native app window while the
backend runs in a thread inside this same process.  The all-Qt window
remains available with ``--qt`` / ``MYRA_UI=qt`` as an advanced fallback.
``--backend`` remains only as a manual diagnostic mode; the desktop UI
never starts it as a child process.
"""
import os
import sys
from pathlib import Path

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
SOURCE_ROOT = Path(__file__).resolve().parent
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))


def _show_error(message):
    """Show a GUI error when possible; never require a console window."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("MYRA", message, parent=root)
        root.destroy()
    except Exception:
        # pythonw has no visible stderr; a diagnostic CLI run can still
        # show this if tkinter itself is unavailable.
        print(message, file=sys.stderr)


def _ui_mode():
    """Return 'web' (default smooth shell) or 'qt' (advanced fallback)."""
    if "--qt" in sys.argv:
        return "qt"
    if "--web-shell" in sys.argv:
        return "web"
    mode = (os.environ.get("MYRA_UI") or "web").strip().lower()
    if mode in {"qt", "pyside", "pyside6", "native-qt"}:
        return "qt"
    return "web"


def _self_test():
    """Headless packaged-build smoke test used by build_windows.py."""
    if _ui_mode() == "qt":
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        from desktop.app import MyraWindow

        app = QApplication([sys.argv[0]])
        window = MyraWindow()
        window.show()
        QTimer.singleShot(250, window.close)
        QTimer.singleShot(500, app.quit)
        return app.exec()
    from desktop.web_shell import self_test

    return self_test()


def main():
    if "--self-test" in sys.argv:
        return _self_test()
    if "--backend" in sys.argv:
        backend_dir = SOURCE_ROOT / "backend"
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))
        os.environ.setdefault("MYRA_HOST", "127.0.0.1")
        os.environ.setdefault("MYRA_PORT", "8765")
        import server

        server.main()
        return 0

    def run_web():
        from desktop.web_shell import main as web_main

        return web_main()

    def run_qt():
        from desktop.app import main as qt_main

        return qt_main()

    bootstrap_attempted = False

    def try_bootstrap():
        nonlocal bootstrap_attempted
        if bootstrap_attempted:
            return False
        bootstrap_attempted = True
        if getattr(sys, "frozen", False) or os.environ.get("MYRA_BOOTSTRAPPED") == "1":
            return False
        try:
            from desktop.bootstrap import bootstrap_and_launch

            return bool(bootstrap_and_launch(SOURCE_ROOT))
        except Exception:
            return False

    mode = _ui_mode()
    runners = {"web": run_web, "qt": run_qt}
    fallback_mode = "qt" if mode == "web" else "web"
    try:
        return runners[mode]()
    except ModuleNotFoundError as exc:
        missing = exc.name or ""
        installable = missing.startswith(("webview", "PySide6", "clr", "bottle", "proxy_tools"))
        if installable and try_bootstrap():
            return 0
        # If one shell's package is unavailable, the other shell is a
        # better owner experience than an error dialog.
        try:
            return runners[fallback_mode]()
        except ModuleNotFoundError:
            if try_bootstrap():
                return 0
            _show_error(
                "MYRA's desktop packages are not installed for this Python environment.\n\n"
                "For the easiest route, use the packaged MYRA.exe. For a source run, open MYRA.pyw "
                "with Python so the setup window can create MYRA's environment."
            )
            return 2
    except Exception as exc:
        # A missing/broken WebView2 runtime should not leave the owner
        # with no MYRA at all: fall back to the other shell once.
        if mode == "web":
            try:
                return run_qt()
            except Exception:
                pass
        _show_error(f"MYRA could not start its desktop window.\n\n{exc.__class__.__name__}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
