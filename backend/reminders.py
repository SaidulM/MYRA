"""Legacy reminders API backed by MYRA's unified Core SQLite store."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import paths
from core_memory import MemoryStore

ROOT = Path(__file__).resolve().parent.parent
LEGACY_DB_PATH = ROOT / "data" / "myra.db"
DB_DIR = paths.data_dir(create=False)
DB_PATH = paths.database_path(create=False)

_LOCK = threading.Lock()
_STORE = None
_STORE_PATH = None


def _store() -> MemoryStore:
    global _STORE, _STORE_PATH, DB_DIR
    DB_DIR = Path(DB_PATH).parent
    if _STORE is None or _STORE_PATH != Path(DB_PATH):
        _STORE = MemoryStore(DB_PATH)
        _STORE_PATH = Path(DB_PATH)
        try:
            if Path(DB_PATH) == paths.database_path(create=False):
                _STORE.import_legacy_database(LEGACY_DB_PATH)
        except Exception:
            pass
    return _STORE


def get_conn():
    """Compatibility helper for older imports; returns a SQLite connection."""
    return _store()._connect()


def init_db():
    _store()


def add_reminder(text: str, due_str: str = "", minutes: Optional[int] = None) -> Dict[str, Any]:
    clean = str(text).strip()
    if not clean:
        return {"ok": False, "error": "Reminder text cannot be empty"}
    with _LOCK:
        # The legacy API used minutes=0 as an already-due test reminder.
        reminder = _store().create_reminder(clean, due_at=due_str or None, minutes=minutes)
    return reminder


def list_reminders(active_only: bool = True) -> List[Dict[str, Any]]:
    with _LOCK:
        return _store().list_reminders(active_only=active_only, limit=50 if not active_only else 200)


def check_due_reminders() -> List[Dict[str, Any]]:
    with _LOCK:
        return _store().due_reminders(mark_completed=True)


def delete_reminder(rem_id: int) -> bool:
    with _LOCK:
        try:
            return bool(_store().delete_reminder(int(rem_id)))
        except (KeyError, TypeError, ValueError):
            return False
