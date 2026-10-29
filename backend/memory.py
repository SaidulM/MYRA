"""MYRA — Local Memory Engine (Stage 4 + Extended Multi-Pattern Recall).

Uses Python's built-in sqlite3 database stored in data/myra.db.
Everything remains 100% local on the user's laptop and is never
uploaded to the cloud.
"""
from __future__ import annotations

import re
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
                # Check for duplicate
                existing = conn.execute(
                    "SELECT id FROM memories WHERE text = ? LIMIT 1", (cleaned[:1000],)
                ).fetchone()
                if existing:
                    return existing["id"]

                cur = conn.execute(
                    "INSERT INTO memories (text, category, updated_at) VALUES (?, ?, ?)",
                    (cleaned[:1000], category[:50], datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                )
                return cur.lastrowid
        finally:
            conn.close()


def list_memories(limit: int = 150) -> List[Dict[str, Any]]:
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


def get_memory_context(limit: int = 20) -> str:
    """Return a formatted string of memories for injection into AI system prompt."""
    mems = list_memories(limit=limit)
    if not mems:
        return ""
    lines = ["Saved personal memories and facts about the user (stored locally in data/myra.db):"]
    for m in reversed(mems):
        lines.append(f"- [{m.get('category', 'fact')}] {m['text']}")
    return "\n".join(lines)


def auto_learn_from_text(text: str) -> Optional[str]:
    """Inspect user message to automatically extract and remember personal facts in SQLite."""
    raw = str(text).strip()
    if not raw or len(raw) < 3:
        return None

    # Skip general queries unless they contain remember directive
    lowered = raw.lower()
    is_question = any(q in lowered for q in ("what is", "who is", "where is", "how to", "কি", "কেমন", "কোথায়", "কোনটা")) or "?" in raw

    # 1. Explicit remember: "Remember that X", "মনে রেখো X", "মনে রাখো X", "নোট রাখো X"
    m_exp = re.search(r"(?:remember\s+(?:that\s+)?|note\s+that\s+|মনে\s*রেখো\s+|মনে\s*রাখো\s+|মনে\s*রেখ\s+)(.+)", raw, re.IGNORECASE)
    if m_exp:
        fact = m_exp.group(1).strip()
        add_memory(fact, category="user_note")
        return fact

    if is_question:
        return None

    # 2. Name patterns: "my name is X", "আমার নাম X", "আমি X"
    m = re.search(r"(?:my name is|আমার নাম|amr nam)\s+([A-Za-z\u0980-\u09FF\s]{2,30})", raw, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        fact = f"User's name is {name}"
        add_memory(fact, category="identity")
        return fact

    # 3. Favorite patterns: "my favorite X is Y", "আমার প্রিয় X হলো/হচ্ছে Y"
    m = re.search(r"(?:my favorite|আমার প্রিয়)\s+([a-zA-Z\u0980-\u09FF\s]+?)\s+(?:is|হলো|হচ্ছে|হল)\s+(.+)", raw, re.IGNORECASE)
    if m:
        item = m.group(1).strip()
        val = m.group(2).strip()
        fact = f"User's favorite {item} is {val}"
        add_memory(fact, category="preference")
        return fact

    # 4. Likes & Dislikes: "I like X", "আমার X পছন্দ", "আমি X পছন্দ করি", "আমার X ভালো লাগে"
    m = re.search(r"(?:i like|i love)\s+([a-zA-Z0-9\s,]{3,40})", raw, re.IGNORECASE)
    if m and not any(w in lowered for w in ("to be", "it if", "you")):
        val = m.group(1).strip()
        fact = f"User likes {val}"
        add_memory(fact, category="preference")
        return fact

    m_bn = re.search(r"আমি\s+(.+?)\s+(?:পছন্দ\s*করি|ভালোবাসি)", raw)
    if m_bn:
        val = m_bn.group(1).strip()
        fact = f"ব্যবহারকারী {val} পছন্দ করেন"
        add_memory(fact, category="preference")
        return fact

    m_bn2 = re.search(r"আমার\s+(.+?)\s+(?:ভালো\s*লাগে|পছন্দ)", raw)
    if m_bn2:
        val = m_bn2.group(1).strip()
        fact = f"ব্যবহারকারীর {val} পছন্দ"
        add_memory(fact, category="preference")
        return fact

    # 5. Location: "I live in X", "আমার বাসা X এ", "আমি X থাকি"
    m = re.search(r"(?:i live in|আমার বাসা|আমি)\s+([A-Za-z\u0980-\u09FF\s]{2,25})\s*(?:তে থাকি|এ থাকি|থাকি)", raw, re.IGNORECASE)
    if m:
        loc = m.group(1).strip()
        fact = f"User lives in {loc}"
        add_memory(fact, category="location")
        return fact

    # 6. Profession: "I am a/an X", "আমি একজন X"
    m = re.search(r"(?:i am a|i am an|আমি একজন)\s+([a-zA-Z\u0980-\u09FF\s]{3,30})", raw, re.IGNORECASE)
    if m and not any(w in lowered for w in ("feeling", "thinking", "student of nature", "free")):
        prof = m.group(1).strip()
        fact = f"User is a {prof}"
        add_memory(fact, category="profession")
        return fact

    # 7. Age: "I am X years old", "আমার বয়স X"
    m = re.search(r"(?:my age is|i am)\s+(\d{1,2})\s*(?:years old)?|আমার বয়স\s*(\d{1,2})", raw, re.IGNORECASE)
    if m:
        age = m.group(1) or m.group(2)
        fact = f"User is {age} years old"
        add_memory(fact, category="identity")
        return fact

    return None


def resolve_memory_query(text: str) -> Optional[str]:
    """Answer questions about stored user facts directly from SQLite without using cloud tokens."""
    raw = str(text).strip()
    lowered = raw.lower()
    is_bn = bool(re.search(r"[\u0980-\u09FF]", raw))

    mems = list_memories(limit=100)

    # 1. Name question
    if any(q in lowered for q in ("what is my name", "what's my name", "who am i", "আমার নাম কি", "আমি কে")):
        if mems:
            for m in mems:
                t = m["text"]
                match = re.search(r"(?:name is|নাম)\s+([A-Za-z\u0980-\u09FF\s]+)", t, re.IGNORECASE)
                if match:
                    name = match.group(1).strip()
                    return f"আপনার নাম {name}।" if is_bn else f"Your name is {name}."
        return "আমি এখনো আপনার নাম মনে রাখতে পারিনি। আপনার নাম কি বলবেন?" if is_bn else "I don't have your name in my memory yet. What is your name?"

    if not mems:
        return None

    # 2. Favorite item
    if "favorite" in lowered or "প্রিয়" in raw or "প্রিয়" in raw or "পছন্দ" in raw:
        for m in mems:
            t = m["text"]
            for keyword in ("food", "খাবার", "color", "রং", "song", "গান", "movie", "সিনেমা", "place", "জায়গা", "game", "খেলা"):
                if (keyword in lowered or keyword in raw) and (keyword in t.lower() or keyword in t):
                    return f"আপনার মেমোরি অনুযায়ী: {t}।" if is_bn else f"According to your memory: {t}."

    # 3. Location question
    if any(q in lowered for q in ("where do i live", "where is my home", "আমি কোথায় থাকি", "আমার বাসা কোথায়")):
        for m in mems:
            t = m["text"]
            if "live" in t.lower() or "বাসা" in t or "থাকি" in t:
                return f"আপনার মেমোরি অনুযায়ী: {t}।" if is_bn else f"According to your memory: {t}."

    # 4. General recall: "what do you remember about me", "তুমি আমার সম্পর্কে কি জানো"
    if any(q in lowered for q in ("what do you remember", "what do you know about me", "তুমি আমার সম্পর্কে কি জানো", "আমার কি কি মনে আছে")):
        fact_lines = [f"• [{m.get('category', 'তথ্য')}] {m['text']}" for m in mems[:10]]
        if is_bn:
            return "আপনার সম্পর্কে আমার লোকাল মেমোরিতে যা জমা আছে:\n" + "\n".join(fact_lines)
        return "Here is what I have saved about you in local memory:\n" + "\n".join(fact_lines)

    return None
