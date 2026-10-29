"""Legacy notes API backed by MYRA's unified Core SQLite store."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import paths
from core_memory import MemoryStore

ROOT = Path(__file__).resolve().parent.parent
LEGACY_DB_PATH = ROOT / "data" / "myra.db"
DATA_DIR = paths.data_dir(create=False)
DB_PATH = paths.database_path(create=False)

_LOCK = threading.Lock()
_STORE = None
_STORE_PATH = None


def _store() -> MemoryStore:
    global _STORE, _STORE_PATH, DATA_DIR
    DATA_DIR = Path(DB_PATH).parent
    if _STORE is None or _STORE_PATH != Path(DB_PATH):
        _STORE = MemoryStore(DB_PATH)
        _STORE_PATH = Path(DB_PATH)
        try:
            if Path(DB_PATH) == paths.database_path(create=False):
                _STORE.import_legacy_database(LEGACY_DB_PATH)
        except Exception:
            pass
    return _STORE


def _legacy(note):
    if not note:
        return note
    return {
        "id": note["id"],
        "title": note.get("title") or "",
        "content": note.get("body") or "",
        "body": note.get("body") or "",
        "created_at": note.get("created_at"),
        "updated_at": note.get("updated_at"),
    }


def init_db() -> None:
    _store()


def get_notes(limit: int = 100) -> List[Dict[str, Any]]:
    with _LOCK:
        notes = sorted(_store().list_notes(limit=5000), key=lambda item: item["id"], reverse=True)
    return [_legacy(note) for note in notes[: max(1, min(int(limit or 100), 500))]]


def add_note(content: str, title: str = "") -> Optional[Dict[str, Any]]:
    cleaned = str(content).strip()
    if not cleaned:
        return None
    clean_title = " ".join(str(title).split()).strip()[:100] or "Untitled note"
    with _LOCK:
        return _legacy(_store().create_note(clean_title, cleaned[:10000]))


def update_note(note_id: int, content: str, title: str = "") -> bool:
    cleaned = str(content).strip()
    if not cleaned:
        return False
    clean_title = " ".join(str(title).split()).strip()[:100] or "Untitled note"
    with _LOCK:
        try:
            _store().update_note(int(note_id), title=clean_title, body=cleaned[:10000])
            return True
        except (KeyError, TypeError, ValueError):
            return False


def delete_note(note_id: int) -> bool:
    with _LOCK:
        try:
            return bool(_store().delete_note(int(note_id)))
        except (KeyError, TypeError, ValueError):
            return False


def clear_notes() -> bool:
    with _LOCK:
        return bool(_store().clear_notes())
