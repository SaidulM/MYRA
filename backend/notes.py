"""MYRA — Local Notes Storage Engine (Stage 7).

Stores personal notes locally in data/myra.db using SQLite.
Completely offline, private, and persistent.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "myra.db"

_LOCK = threading.Lock()


def _get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize SQLite tables for notes."""
    with _LOCK:
        conn = _get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS notes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT DEFAULT '',
                        content TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_notes_updated 
                    ON notes(updated_at DESC)
                    """
                )
        finally:
            conn.close()


def get_notes(limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieve all notes, newest first."""
    init_db()
    with _LOCK:
        conn = _get_connection()
        try:
            cur = conn.execute(
                "SELECT id, title, content, created_at, updated_at FROM notes ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            )
            rows = cur.fetchall()
            return [
                {
                    "id": r["id"],
                    "title": r["title"] or "",
                    "content": r["content"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                }
                for r in rows
            ]
        finally:
            conn.close()


def add_note(content: str, title: str = "") -> Optional[Dict[str, Any]]:
    """Create a new note."""
    cleaned = str(content).strip()
    if not cleaned:
        return None

    clean_title = " ".join(str(title).split()).strip()[:100]
    now = datetime.utcnow().isoformat()

    init_db()
    with _LOCK:
        conn = _get_connection()
        try:
            with conn:
                cur = conn.execute(
                    "INSERT INTO notes (title, content, updated_at) VALUES (?, ?, ?)",
                    (clean_title, cleaned[:10000], now),
                )
                note_id = cur.lastrowid
                return {
                    "id": note_id,
                    "title": clean_title,
                    "content": cleaned,
                    "created_at": now,
                    "updated_at": now,
                }
        finally:
            conn.close()


def update_note(note_id: int, content: str, title: str = "") -> bool:
    """Update an existing note."""
    cleaned = str(content).strip()
    if not cleaned:
        return False

    clean_title = " ".join(str(title).split()).strip()[:100]
    now = datetime.utcnow().isoformat()

    init_db()
    with _LOCK:
        conn = _get_connection()
        try:
            with conn:
                cur = conn.execute(
                    "UPDATE notes SET title = ?, content = ?, updated_at = ? WHERE id = ?",
                    (clean_title, cleaned[:10000], now, note_id),
                )
                return cur.rowcount > 0
        finally:
            conn.close()


def delete_note(note_id: int) -> bool:
    """Delete a note by ID."""
    init_db()
    with _LOCK:
        conn = _get_connection()
        try:
            with conn:
                cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
                return cur.rowcount > 0
        finally:
            conn.close()


def clear_notes() -> bool:
    """Delete all notes."""
    init_db()
    with _LOCK:
        conn = _get_connection()
        try:
            with conn:
                conn.execute("DELETE FROM notes")
                return True
        finally:
            conn.close()
