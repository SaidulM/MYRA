"""MYRA pure-Python native desktop entry point.

Preferred source launch on Windows: ``MYRA.pyw`` (uses pythonw, so no
console window appears).  In the packaged build this module is the
PyInstaller entry point for ``MYRA.exe`` with ``console=False``.

The Qt window embeds MYRA's backend in a thread inside this same GUI
process.  ``--backend`` remains only as a manual diagnostic mode; the
desktop UI never starts it as a child process.
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


def _self_test():
    """Headless packaged-build smoke test used by build_windows.py."""
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

    try:
        from desktop.app import main as desktop_main
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("PySide6"):
            if not getattr(sys, "frozen", False) and os.environ.get("MYRA_BOOTSTRAPPED") != "1":
                try:
                    from desktop.bootstrap import bootstrap_and_launch

                    if bootstrap_and_launch(SOURCE_ROOT):
                        return 0
                except Exception:
                    pass
            _show_error(
                "PySide6 is not installed for this Python environment.\n\n"
                "For the easiest route, use the packaged MYRA.exe. For a source run, open MYRA.pyw "
                "with Python so the pure-Python GUI setup can create MYRA's environment."
            )
            return 2
        raise
    return desktop_main()


if __name__ == "__main__":
    raise SystemExit(main())
