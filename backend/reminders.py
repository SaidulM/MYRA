"""MYRA — Local Reminders & Alarm Engine (SQLite).

Stores reminders safely on the laptop and notifies the user via UI and Voice.
Runs 100% offline with zero cloud tokens.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
DB_DIR = ROOT / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "myra.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                due_timestamp REAL NOT NULL,
                due_str TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed INTEGER DEFAULT 0
            )
            """
        )
        conn.commit()


def add_reminder(text: str, due_str: str = "", minutes: Optional[int] = None) -> Dict[str, Any]:
    init_db()
    clean_text = str(text).strip()
    if not clean_text:
        return {"ok": False, "error": "Reminder text cannot be empty"}

    now = datetime.now()
    if minutes is not None and minutes == 0:
        due_dt = now - timedelta(seconds=1)
    elif minutes is not None and minutes > 0:
        due_dt = now + timedelta(minutes=minutes)
    else:
        due_dt = now + timedelta(minutes=10)

    due_ts = due_dt.timestamp()
    formatted_due = due_dt.strftime("%Y-%m-%d %I:%M %p")
    created = now.strftime("%Y-%m-%d %H:%M:%S")

    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO reminders (text, due_timestamp, due_str, created_at, completed) VALUES (?, ?, ?, ?, 0)",
            (clean_text, due_ts, formatted_due, created),
        )
        conn.commit()
        rem_id = cur.lastrowid

    return {
        "ok": True,
        "id": rem_id,
        "text": clean_text,
        "due_str": formatted_due,
        "due_timestamp": due_ts,
    }


def list_reminders(active_only: bool = True) -> List[Dict[str, Any]]:
    init_db()
    with get_conn() as conn:
        if active_only:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE completed = 0 ORDER BY due_timestamp ASC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM reminders ORDER BY due_timestamp DESC LIMIT 50"
            ).fetchall()

    return [
        {
            "id": r["id"],
            "text": r["text"],
            "due_str": r["due_str"],
            "due_timestamp": r["due_timestamp"],
            "created_at": r["created_at"],
            "completed": bool(r["completed"]),
        }
        for r in rows
    ]


def check_due_reminders() -> List[Dict[str, Any]]:
    """Return all reminders whose due time has passed and mark them as alerted."""
    init_db()
    now_ts = datetime.now().timestamp()
    due = []
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM reminders WHERE completed = 0 AND due_timestamp <= ?",
            (now_ts,),
        ).fetchall()
        for r in rows:
            due.append(dict(r))
            conn.execute("UPDATE reminders SET completed = 1 WHERE id = ?", (r["id"],))
        conn.commit()

    return due


def delete_reminder(rem_id: int) -> bool:
    init_db()
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM reminders WHERE id = ?", (rem_id,))
        conn.commit()
        return cur.rowcount > 0
