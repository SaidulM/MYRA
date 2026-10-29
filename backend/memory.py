"""MYRA — Local Memory Engine (Stage 4).

Uses Python's built-in sqlite3 database stored in data/myra.db.
Everything remains 100% local on the user's laptop and is never
uploaded to the cloud.
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
    """Initialize SQLite tables for memory and settings."""
    with _LOCK:
        conn = _get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        text TEXT NOT NULL,
                        category TEXT DEFAULT 'general',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_memories_created 
                    ON memories(created_at DESC)
                    """
                )
        finally:
            conn.close()


def add_memory(text: str, category: str = "general") -> Optional[int]:
    """Add a new memory fact."""
    cleaned = " ".join(str(text).split()).strip()
    if not cleaned:
        return None

    init_db()
    with _LOCK:
        conn = _get_connection()
        try:
            with conn:
                cur = conn.execute(
                    "INSERT INTO memories (text, category, updated_at) VALUES (?, ?, ?)",
                    (cleaned[:1000], category[:50], datetime.utcnow().isoformat()),
                )
                return cur.lastrowid
        finally:
            conn.close()


def list_memories(limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieve memories, newest first."""
    init_db()
    with _LOCK:
        conn = _get_connection()
        try:
            cur = conn.execute(
                "SELECT id, text, category, created_at FROM memories ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            )
            rows = cur.fetchall()
            return [
                {
                    "id": r["id"],
                    "text": r["text"],
                    "category": r["category"],
                    "created_at": r["created_at"],
                }
                for r in rows
            ]
        finally:
            conn.close()


def delete_memory(mem_id: int) -> bool:
    """Delete a memory by id."""
    init_db()
    with _LOCK:
        conn = _get_connection()
        try:
            with conn:
                cur = conn.execute("DELETE FROM memories WHERE id = ?", (mem_id,))
                return cur.rowcount > 0
        finally:
            conn.close()


def clear_memories() -> bool:
    """Delete all memories."""
    init_db()
    with _LOCK:
        conn = _get_connection()
        try:
            with conn:
                conn.execute("DELETE FROM memories")
                return True
        finally:
            conn.close()


def get_memory_context(limit: int = 15) -> str:
    """Return a formatted string of memories for injection into AI system prompt."""
    mems = list_memories(limit=limit)
    if not mems:
        return ""
    lines = ["Saved personal memories and facts about the user (stored locally):"]
    for m in reversed(mems):
        lines.append(f"- {m['text']}")
    return "\n".join(lines)
