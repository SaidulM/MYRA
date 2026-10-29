"""MYRA native desktop entry point.

Run normally:
    python run_desktop.py

The desktop app starts/uses the same local backend.  ``--backend`` is an
internal mode used by the desktop process (and a future frozen EXE) to run
only the backend.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    if "--backend" in sys.argv:
        backend_dir = ROOT / "backend"
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
            print("PySide6 is not installed. Run: pip install -r requirements-desktop.txt")
            return 2
        raise
    return desktop_main()


if __name__ == "__main__":
    raise SystemExit(main())
