"""MYRA legacy memory API backed by the unified Core SQLite store.

The old web routes keep their familiar function names, but there is now
only one canonical database: ``paths.database_path()`` (Windows:
``%LOCALAPPDATA%\MYRA\myra.db``).  Existing repository ``data/myra.db``
rows are imported idempotently by :class:`core_memory.MemoryStore``.
"""
from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import paths
from core_memory import MemoryStore

ROOT = Path(__file__).resolve().parent.parent
LEGACY_DATA_DIR = ROOT / "data"
LEGACY_DB_PATH = LEGACY_DATA_DIR / "myra.db"
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
        # Only auto-import for the real configured database.  Tests that
        # patch DB_PATH get a clean isolated store instead.
        try:
            if Path(DB_PATH) == paths.database_path(create=False):
                _STORE.import_legacy_database(LEGACY_DB_PATH)
        except Exception:
            # Import can be retried from Diagnostics; memory CRUD must not
            # fail just because an old side database is damaged.
            pass
    return _STORE


def init_db() -> None:
    """Initialize/upgrade the unified SQLite database."""
    _store()


def add_memory(text: str, category: str = "general") -> Optional[int]:
    cleaned = " ".join(str(text).split()).strip()
    if not cleaned:
        return None
    with _LOCK:
        store = _store()
        for memory in store.list_memories(limit=5000):
            if " ".join(memory.get("text", "").split()).casefold() == cleaned[:1000].casefold():
                return int(memory["id"])
        return int(store.add_memory(cleaned[:1000], category=category[:50], source="legacy")["id"])


def list_memories(limit: int = 150) -> List[Dict[str, Any]]:
    with _LOCK:
        memories = sorted(_store().list_memories(limit=5000), key=lambda item: item["id"], reverse=True)
    return [
        {
            "id": m["id"],
            "text": m["text"],
            "category": m.get("category") or "general",
            "created_at": m.get("created_at"),
            "updated_at": m.get("updated_at"),
            "source": m.get("source"),
            "pinned": bool(m.get("pinned")),
        }
        for m in memories[: max(1, min(int(limit or 150), 500))]
    ]


def delete_memory(mem_id: int) -> bool:
    with _LOCK:
        try:
            return bool(_store().delete_memory(int(mem_id)))
        except (KeyError, TypeError, ValueError):
            return False


def clear_memories() -> bool:
    with _LOCK:
        return bool(_store().clear_memories())


def get_memory_context(limit: int = 20) -> str:
    mems = list_memories(limit=limit)
    if not mems:
        return ""
    lines = ["Saved personal memories and facts about the user (stored locally in MYRA's unified SQLite database):"]
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
