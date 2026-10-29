"""MYRA persistent local memory (SQLite).

Stores conversations, user-approved memories, notes, preferences, skill
settings and agent-task state on the owner's computer.  The database is
provider-independent: changing Gemini/Groq/model never changes the data.

Only user-approved memory records are treated as long-term memory.  Normal
conversation history is stored because the user is using the chat history
feature, but MYRA does not silently extract sensitive facts into the
separate memories table.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import paths


SCHEMA_VERSION = 2
_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _tokens(text):
    return {token.casefold() for token in _TOKEN_RE.findall(text or "") if len(token) > 1}


def _score(query_tokens, text):
    if not query_tokens:
        return 0
    text_tokens = _tokens(text)
    return len(query_tokens & text_tokens)


def _clean_text(value, max_len, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()[:max_len]


class MemoryStore:
    def __init__(self, db_path=None):
        self.db_path = Path(db_path) if db_path else paths.database_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @staticmethod
    def _table_columns(conn, table):
        try:
            return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        except sqlite3.Error:
            return set()

    def _migrate_existing_tables(self, conn):
        """Upgrade an old combined MYRA DB without losing legacy rows."""
        notes_columns = self._table_columns(conn, "notes")
        if notes_columns and "content" in notes_columns and "body" not in notes_columns:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS notes_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                INSERT OR IGNORE INTO notes_v2(id,title,body,created_at,updated_at)
                SELECT id,
                       COALESCE(NULLIF(title,''), 'Untitled note'),
                       COALESCE(content, ''),
                       COALESCE(NULLIF(created_at,''), CURRENT_TIMESTAMP),
                       COALESCE(NULLIF(updated_at,''), COALESCE(NULLIF(created_at,''), CURRENT_TIMESTAMP))
                FROM notes;
                DROP TABLE notes;
                ALTER TABLE notes_v2 RENAME TO notes;
                """
            )

        memory_columns = self._table_columns(conn, "memories")
        if memory_columns:
            if "source" not in memory_columns:
                conn.execute("ALTER TABLE memories ADD COLUMN source TEXT NOT NULL DEFAULT 'legacy'")
            if "pinned" not in memory_columns:
                conn.execute("ALTER TABLE memories ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")

        reminder_columns = self._table_columns(conn, "reminders")
        if reminder_columns:
            if "due_at" not in reminder_columns:
                conn.execute("ALTER TABLE reminders ADD COLUMN due_at TEXT NOT NULL DEFAULT ''")
            if "notified" not in reminder_columns:
                conn.execute("ALTER TABLE reminders ADD COLUMN notified INTEGER NOT NULL DEFAULT 0")

    def _initialise(self):
        with self._connect() as conn:
            self._migrate_existing_tables(conn)
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT 'New conversation',
                    character TEXT NOT NULL DEFAULT 'core',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant','system','tool')),
                    content TEXT NOT NULL,
                    provider TEXT,
                    model TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON messages(conversation_id, id);
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'general',
                    source TEXT NOT NULL DEFAULT 'user',
                    pinned INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS skill_settings (
                    skill_id TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_tasks (
                    id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    status TEXT NOT NULL,
                    transcript_json TEXT NOT NULL DEFAULT '[]',
                    steps_json TEXT NOT NULL DEFAULT '[]',
                    pending_json TEXT,
                    approved_json TEXT NOT NULL DEFAULT '[]',
                    approval_mode TEXT NOT NULL DEFAULT 'ask',
                    max_steps INTEGER NOT NULL DEFAULT 6,
                    final_summary TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    due_timestamp REAL NOT NULL,
                    due_str TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0,
                    notified INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_reminders_due
                    ON reminders(completed, due_timestamp);
                CREATE TABLE IF NOT EXISTS legacy_id_map (
                    source_key TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    legacy_id TEXT NOT NULL,
                    core_id TEXT NOT NULL,
                    imported_at TEXT NOT NULL,
                    PRIMARY KEY(source_key, kind, legacy_id)
                );
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    # ------------------------------------------------------------------
    # Conversations
    # ------------------------------------------------------------------
    def create_conversation(self, title="New conversation", character="core"):
        now = _now()
        conversation_id = uuid.uuid4().hex
        title = (title or "New conversation").strip()[:120] or "New conversation"
        character = character if character in {"core", "male", "female"} else "core"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversations(id,title,character,created_at,updated_at) VALUES(?,?,?,?,?)",
                (conversation_id, title, character, now, now),
            )
        return self.get_conversation(conversation_id)

    def get_conversation(self, conversation_id):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_conversations(self, limit=50, include_archived=False):
        limit = max(1, min(int(limit or 50), 200))
        query = "SELECT * FROM conversations"
        if not include_archived:
            query += " WHERE archived = 0"
        query += " ORDER BY updated_at DESC LIMIT ?"
        with self._connect() as conn:
            rows = conn.execute(query, (limit,)).fetchall()
        return [dict(row) for row in rows]

    def rename_conversation(self, conversation_id, title):
        title = _clean_text(title, 120, "title")
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE conversations SET title=?, updated_at=? WHERE id=?",
                (title, _now(), conversation_id),
            )
            if cur.rowcount == 0:
                raise KeyError("conversation not found")
        return self.get_conversation(conversation_id)

    def delete_conversation(self, conversation_id):
        with self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
            cur = conn.execute("DELETE FROM conversations WHERE id=?", (conversation_id,))
            if cur.rowcount == 0:
                raise KeyError("conversation not found")
        return True

    def add_message(self, conversation_id, role, content, provider=None, model=None):
        if role not in {"user", "assistant", "system", "tool"}:
            raise ValueError("invalid message role")
        content = _clean_text(content, 30000, "content")
        if not self.get_conversation(conversation_id):
            raise KeyError("conversation not found")
        now = _now()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO messages(conversation_id,role,content,provider,model,created_at)
                   VALUES(?,?,?,?,?,?)""",
                (conversation_id, role, content, provider, model, now),
            )
            message_id = cur.lastrowid
            if role == "user":
                row = conn.execute(
                    "SELECT title FROM conversations WHERE id=?", (conversation_id,)
                ).fetchone()
                if row and row["title"] == "New conversation":
                    title = " ".join(content.split())[:64]
                    conn.execute(
                        "UPDATE conversations SET title=? WHERE id=?", (title, conversation_id)
                    )
            conn.execute(
                "UPDATE conversations SET updated_at=? WHERE id=?", (now, conversation_id)
            )
        return {
            "id": message_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "provider": provider,
            "model": model,
            "created_at": now,
        }

    def list_messages(self, conversation_id, limit=200):
        limit = max(1, min(int(limit or 200), 1000))
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT * FROM messages WHERE conversation_id=?
                   ORDER BY id DESC LIMIT ?""",
                (conversation_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def recent_messages_for_provider(self, conversation_id, limit=14):
        messages = self.list_messages(conversation_id, limit=limit)
        return [
            {"role": row["role"], "text": row["content"]}
            for row in messages
            if row["role"] in {"user", "assistant"}
        ]

    def search_conversations(self, query, limit=20):
        query = (query or "").strip()
        if not query:
            return []
        like = f"%{query}%"
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT m.*, c.title AS conversation_title
                   FROM messages m JOIN conversations c ON c.id=m.conversation_id
                   WHERE m.content LIKE ? COLLATE NOCASE
                   ORDER BY m.id DESC LIMIT ?""",
                (like, max(1, min(int(limit or 20), 100))),
            ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # User-approved memories
    # ------------------------------------------------------------------
    def add_memory(self, text, category="general", source="user", pinned=False):
        text = _clean_text(text, 2000, "memory text")
        category = _clean_text(category or "general", 60, "category")
        now = _now()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO memories(text,category,source,pinned,created_at,updated_at)
                   VALUES(?,?,?,?,?,?)""",
                (text, category, (source or "user")[:40], int(bool(pinned)), now, now),
            )
            memory_id = cur.lastrowid
        return self.get_memory(memory_id)

    def get_memory(self, memory_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memories WHERE id=?", (memory_id,)).fetchone()
        return dict(row) if row else None

    def list_memories(self, limit=200):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memories ORDER BY pinned DESC, updated_at DESC LIMIT ?",
                (max(1, min(int(limit or 200), 1000)),),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_memory(self, memory_id, text=None, category=None, pinned=None):
        current = self.get_memory(memory_id)
        if not current:
            raise KeyError("memory not found")
        if text is not None:
            current["text"] = _clean_text(text, 2000, "memory text")
        if category is not None:
            current["category"] = _clean_text(category, 60, "category")
        if pinned is not None:
            current["pinned"] = int(bool(pinned))
        current["updated_at"] = _now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE memories SET text=?,category=?,pinned=?,updated_at=? WHERE id=?",
                (current["text"], current["category"], current["pinned"], current["updated_at"], memory_id),
            )
        return self.get_memory(memory_id)

    def delete_memory(self, memory_id):
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
            if cur.rowcount == 0:
                raise KeyError("memory not found")
        return True

    def search_memories(self, query, limit=8):
        memories = self.list_memories(limit=1000)
        if not (query or "").strip():
            return [m for m in memories if m["pinned"]][:limit]
        q_tokens = _tokens(query)
        scored = []
        for memory in memories:
            score = _score(q_tokens, memory["text"] + " " + memory["category"])
            if memory["pinned"]:
                score += 2
            if score:
                scored.append((score, memory["updated_at"], memory))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in scored[: max(1, min(int(limit or 8), 50))]]

    def relevant_context(self, query, limit=6):
        """Return small, bounded local context for a provider request."""
        items = []
        for memory in self.search_memories(query, limit=limit):
            items.append(
                {
                    "type": "memory",
                    "id": memory["id"],
                    "text": memory["text"][:700],
                    "category": memory["category"],
                }
            )
        if len(items) < limit and (query or "").strip():
            for row in self.search_conversations(query, limit=limit):
                items.append(
                    {
                        "type": "past_message",
                        "conversation_id": row["conversation_id"],
                        "text": row["content"][:500],
                        "role": row["role"],
                    }
                )
                if len(items) >= limit:
                    break
        return items

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------
    def create_note(self, title, body=""):
        title = _clean_text(title, 160, "note title")
        body = body if isinstance(body, str) else ""
        now = _now()
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO notes(title,body,created_at,updated_at) VALUES(?,?,?,?)",
                (title, body[:30000], now, now),
            )
            note_id = cur.lastrowid
        return self.get_note(note_id)

    def get_note(self, note_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
        return dict(row) if row else None

    def list_notes(self, query="", limit=200):
        query = (query or "").strip()
        with self._connect() as conn:
            if query:
                like = f"%{query}%"
                rows = conn.execute(
                    """SELECT * FROM notes WHERE title LIKE ? COLLATE NOCASE
                       OR body LIKE ? COLLATE NOCASE ORDER BY updated_at DESC LIMIT ?""",
                    (like, like, max(1, min(int(limit or 200), 1000))),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM notes ORDER BY updated_at DESC LIMIT ?",
                    (max(1, min(int(limit or 200), 1000)),),
                ).fetchall()
        return [dict(row) for row in rows]

    def update_note(self, note_id, title=None, body=None):
        current = self.get_note(note_id)
        if not current:
            raise KeyError("note not found")
        if title is not None:
            current["title"] = _clean_text(title, 160, "note title")
        if body is not None:
            if not isinstance(body, str):
                raise ValueError("note body must be text")
            current["body"] = body[:30000]
        current["updated_at"] = _now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE notes SET title=?,body=?,updated_at=? WHERE id=?",
                (current["title"], current["body"], current["updated_at"], note_id),
            )
        return self.get_note(note_id)

    def delete_note(self, note_id):
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
            if cur.rowcount == 0:
                raise KeyError("note not found")
        return True

    def clear_memories(self):
        with self._connect() as conn:
            conn.execute("DELETE FROM memories")
        return True

    def clear_notes(self):
        with self._connect() as conn:
            conn.execute("DELETE FROM notes")
        return True

    # ------------------------------------------------------------------
    # Reminders (canonical replacement for the old separate legacy table)
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_due(due_at=None, minutes=None):
        now = datetime.now().astimezone()
        if due_at:
            if isinstance(due_at, (int, float)):
                due = datetime.fromtimestamp(float(due_at)).astimezone()
            else:
                raw = str(due_at).strip().replace("Z", "+00:00")
                try:
                    due = datetime.fromisoformat(raw)
                except ValueError as exc:
                    raise ValueError("due_at must be an ISO date/time") from exc
                if due.tzinfo is None:
                    due = due.replace(tzinfo=now.tzinfo)
                due = due.astimezone()
        elif minutes is not None:
            due = now + timedelta(minutes=float(minutes))
        else:
            due = now + timedelta(minutes=10)
        return due

    def create_reminder(self, text, due_at=None, minutes=None):
        text = _clean_text(text, 1000, "reminder text")
        due = self._parse_due(due_at=due_at, minutes=minutes)
        now = _now()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO reminders(text,due_at,due_timestamp,due_str,created_at,completed,notified)
                   VALUES(?,?,?,?,?,0,0)""",
                (
                    text,
                    due.astimezone(timezone.utc).isoformat(timespec="seconds"),
                    due.timestamp(),
                    due.strftime("%Y-%m-%d %I:%M %p"),
                    now,
                ),
            )
            reminder_id = cur.lastrowid
        return self.get_reminder(reminder_id)

    def get_reminder(self, reminder_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM reminders WHERE id=?", (reminder_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["completed"] = bool(item.get("completed"))
        item["notified"] = bool(item.get("notified"))
        item["ok"] = True
        return item

    def list_reminders(self, active_only=True, limit=200):
        query = "SELECT * FROM reminders"
        if active_only:
            query += " WHERE completed=0"
        query += " ORDER BY due_timestamp ASC LIMIT ?"
        with self._connect() as conn:
            rows = conn.execute(query, (max(1, min(int(limit or 200), 1000)),)).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["completed"] = bool(item.get("completed"))
            item["notified"] = bool(item.get("notified"))
            out.append(item)
        return out

    def complete_reminder(self, reminder_id, completed=True):
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE reminders SET completed=? WHERE id=?",
                (int(bool(completed)), reminder_id),
            )
            if cur.rowcount == 0:
                raise KeyError("reminder not found")
        return self.get_reminder(reminder_id)

    def delete_reminder(self, reminder_id):
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM reminders WHERE id=?", (reminder_id,))
            if cur.rowcount == 0:
                raise KeyError("reminder not found")
        return True

    def due_reminders(self, mark_completed=True):
        now_ts = datetime.now().timestamp()
        due = [
            item for item in self.list_reminders(active_only=True, limit=1000)
            if float(item.get("due_timestamp") or 0) <= now_ts
        ]
        if mark_completed and due:
            with self._connect() as conn:
                conn.executemany(
                    "UPDATE reminders SET completed=1, notified=1 WHERE id=?",
                    [(item["id"],) for item in due],
                )
            for item in due:
                item["completed"] = True
                item["notified"] = True
        return due

    # ------------------------------------------------------------------
    # Legacy database import / unification
    # ------------------------------------------------------------------
    def import_legacy_database(self, legacy_path):
        """Import legacy repo ``data/myra.db`` into this canonical DB.

        The operation is idempotent: it de-duplicates by content and keeps
        a source/id map, so it is safe to run on every desktop start.
        """
        legacy_path = Path(legacy_path).expanduser()
        result = {
            "ok": True,
            "source": str(legacy_path),
            "skipped": False,
            "memories_imported": 0,
            "notes_imported": 0,
            "reminders_imported": 0,
        }
        if not legacy_path.exists():
            result.update({"ok": False, "skipped": True, "reason": "legacy database not found"})
            return result
        try:
            if legacy_path.resolve() == self.db_path.resolve():
                result.update({"skipped": True, "reason": "already the canonical database"})
                return result
        except OSError:
            pass

        source_key = hashlib.sha256(str(legacy_path).encode("utf-8")).hexdigest()[:24]
        source = sqlite3.connect(f"file:{legacy_path}?mode=ro", uri=True)
        source.row_factory = sqlite3.Row
        try:
            tables = {
                row[0] for row in source.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            existing_memories = {
                " ".join((m.get("text") or "").split()).casefold() for m in self.list_memories(limit=5000)
            }
            existing_notes = {
                ((n.get("title") or ""), (n.get("body") or "")) for n in self.list_notes(limit=5000)
            }
            existing_reminders = {
                ((r.get("text") or ""), round(float(r.get("due_timestamp") or 0), 3))
                for r in self.list_reminders(active_only=False, limit=5000)
            }

            if "memories" in tables:
                for row in source.execute("SELECT * FROM memories"):
                    data = dict(row)
                    text = " ".join(str(data.get("text") or "").split()).strip()
                    if not text or text.casefold() in existing_memories:
                        continue
                    created = data.get("created_at") or _now()
                    updated = data.get("updated_at") or created
                    with self._connect() as conn:
                        cur = conn.execute(
                            "INSERT INTO memories(text,category,source,pinned,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                            (text[:2000], str(data.get("category") or "general")[:60],
                             str(data.get("source") or "legacy-import")[:40],
                             int(bool(data.get("pinned", 0))), str(created), str(updated)),
                        )
                        core_id = cur.lastrowid
                        conn.execute(
                            "INSERT OR IGNORE INTO legacy_id_map(source_key,kind,legacy_id,core_id,imported_at) VALUES(?,?,?,?,?)",
                            (source_key, "memory", str(data.get("id", "")), str(core_id), _now()),
                        )
                    existing_memories.add(text.casefold())
                    result["memories_imported"] += 1

            if "notes" in tables:
                for row in source.execute("SELECT * FROM notes"):
                    data = dict(row)
                    title = (str(data.get("title") or "").strip() or "Untitled note")[:160]
                    body = str(data.get("body") if data.get("body") is not None else data.get("content") or "")[:30000]
                    key = (title, body)
                    if key in existing_notes:
                        continue
                    created = data.get("created_at") or _now()
                    updated = data.get("updated_at") or created
                    with self._connect() as conn:
                        cur = conn.execute(
                            "INSERT INTO notes(title,body,created_at,updated_at) VALUES(?,?,?,?)",
                            (title, body, str(created), str(updated)),
                        )
                        core_id = cur.lastrowid
                        conn.execute(
                            "INSERT OR IGNORE INTO legacy_id_map(source_key,kind,legacy_id,core_id,imported_at) VALUES(?,?,?,?,?)",
                            (source_key, "note", str(data.get("id", "")), str(core_id), _now()),
                        )
                    existing_notes.add(key)
                    result["notes_imported"] += 1

            if "reminders" in tables:
                for row in source.execute("SELECT * FROM reminders"):
                    data = dict(row)
                    text = str(data.get("text") or "").strip()
                    if not text:
                        continue
                    due_ts = float(data.get("due_timestamp") or 0)
                    if not due_ts and data.get("due_at"):
                        try:
                            due_ts = self._parse_due(due_at=data.get("due_at")).timestamp()
                        except ValueError:
                            continue
                    key = (text, round(due_ts, 3))
                    if key in existing_reminders:
                        continue
                    due_local = datetime.fromtimestamp(due_ts).astimezone() if due_ts else datetime.now().astimezone()
                    with self._connect() as conn:
                        cur = conn.execute(
                            "INSERT INTO reminders(text,due_at,due_timestamp,due_str,created_at,completed,notified) VALUES(?,?,?,?,?,?,?)",
                            (
                                text[:1000],
                                str(data.get("due_at") or due_local.astimezone(timezone.utc).isoformat(timespec="seconds")),
                                due_ts,
                                str(data.get("due_str") or due_local.strftime("%Y-%m-%d %I:%M %p")),
                                str(data.get("created_at") or _now()),
                                int(bool(data.get("completed", 0))),
                                int(bool(data.get("notified", data.get("completed", 0)))),
                            ),
                        )
                        core_id = cur.lastrowid
                        conn.execute(
                            "INSERT OR IGNORE INTO legacy_id_map(source_key,kind,legacy_id,core_id,imported_at) VALUES(?,?,?,?,?)",
                            (source_key, "reminder", str(data.get("id", "")), str(core_id), _now()),
                        )
                    existing_reminders.add(key)
                    result["reminders_imported"] += 1
        finally:
            source.close()

        self.set_preference("last_legacy_import", result)
        return result

    # ------------------------------------------------------------------
    # Preferences and skill settings
    # ------------------------------------------------------------------
    def get_preference(self, key, default=None):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value_json FROM preferences WHERE key=?", (key,)
            ).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value_json"])
        except ValueError:
            return default

    def set_preference(self, key, value):
        key = _clean_text(key, 80, "preference key")
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO preferences(key,value_json,updated_at) VALUES(?,?,?)",
                (key, json.dumps(value, ensure_ascii=False), _now()),
            )
        return value

    def all_preferences(self):
        with self._connect() as conn:
            rows = conn.execute("SELECT key,value_json FROM preferences ORDER BY key").fetchall()
        out = {}
        for row in rows:
            try:
                out[row["key"]] = json.loads(row["value_json"])
            except ValueError:
                pass
        return out

    def skill_enabled(self, skill_id, default=True):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT enabled FROM skill_settings WHERE skill_id=?", (skill_id,)
            ).fetchone()
        return bool(row["enabled"]) if row else bool(default)

    def set_skill_enabled(self, skill_id, enabled):
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO skill_settings(skill_id,enabled,updated_at) VALUES(?,?,?)",
                (skill_id, int(bool(enabled)), _now()),
            )
        return bool(enabled)

    # ------------------------------------------------------------------
    # Agent tasks
    # ------------------------------------------------------------------
    def create_task(self, goal, max_steps=6, approval_mode="ask", approved_skill_ids=None):
        goal = _clean_text(goal, 4000, "agent goal")
        now = _now()
        task_id = uuid.uuid4().hex
        transcript = [{"type": "user", "text": goal}]
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO agent_tasks
                   (id,goal,status,transcript_json,steps_json,approved_json,approval_mode,
                    max_steps,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    task_id,
                    goal,
                    "queued",
                    json.dumps(transcript, ensure_ascii=False),
                    "[]",
                    json.dumps(list(approved_skill_ids or [])),
                    approval_mode if approval_mode in {"ask", "allow_all"} else "ask",
                    max(1, min(int(max_steps or 6), 12)),
                    now,
                    now,
                ),
            )
        return self.get_task(task_id)

    def _task_from_row(self, row):
        if not row:
            return None
        task = dict(row)
        for source, target in (
            ("transcript_json", "transcript"),
            ("steps_json", "steps"),
            ("pending_json", "pending"),
            ("approved_json", "approved_skill_ids"),
        ):
            raw = task.pop(source, None)
            try:
                task[target] = json.loads(raw) if raw else ([] if target != "pending" else None)
            except ValueError:
                task[target] = [] if target != "pending" else None
        return task

    def get_task(self, task_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
        return self._task_from_row(row)

    def list_tasks(self, limit=50):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM agent_tasks ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(int(limit or 50), 200)),),
            ).fetchall()
        return [self._task_from_row(row) for row in rows]

    def update_task(self, task_id, **fields):
        allowed = {}
        mapping = {
            "status": "status",
            "transcript": "transcript_json",
            "steps": "steps_json",
            "pending": "pending_json",
            "approved_skill_ids": "approved_json",
            "final_summary": "final_summary",
            "error": "error",
        }
        for key, value in fields.items():
            if key not in mapping:
                continue
            column = mapping[key]
            if column.endswith("_json"):
                value = None if value is None else json.dumps(value, ensure_ascii=False)
            allowed[column] = value
        if not allowed:
            return self.get_task(task_id)
        allowed["updated_at"] = _now()
        sql = "UPDATE agent_tasks SET " + ", ".join(f"{k}=?" for k in allowed) + " WHERE id=?"
        with self._connect() as conn:
            cur = conn.execute(sql, (*allowed.values(), task_id))
            if cur.rowcount == 0:
                raise KeyError("agent task not found")
        return self.get_task(task_id)

    def mark_interrupted_tasks(self):
        with self._connect() as conn:
            conn.execute(
                """UPDATE agent_tasks SET status='interrupted',
                   error='MYRA restarted while this task was running.', updated_at=?
                   WHERE status IN ('running','queued','paused')""",
                (_now(),),
            )

    # ------------------------------------------------------------------
    # Export / backup / stats
    # ------------------------------------------------------------------
    def export_data(self):
        return {
            "exported_at": _now(),
            "schema_version": SCHEMA_VERSION,
            "conversations": [
                {
                    **conv,
                    "messages": self.list_messages(conv["id"], limit=1000),
                }
                for conv in self.list_conversations(limit=200, include_archived=True)
            ],
            "memories": self.list_memories(limit=1000),
            "notes": self.list_notes(limit=1000),
            "reminders": self.list_reminders(active_only=False, limit=1000),
            "preferences": self.all_preferences(),
        }

    def backup(self, destination=None):
        if destination is None:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            destination = paths.data_dir() / "backups" / f"myra-backup-{stamp}.db"
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as source:
            target = sqlite3.connect(destination)
            try:
                source.backup(target)
            finally:
                target.close()
        return str(destination)

    def stats(self):
        with self._connect() as conn:
            counts = {}
            for table in ("conversations", "messages", "memories", "notes", "reminders", "agent_tasks"):
                counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return {"database": str(self.db_path), "schema_version": SCHEMA_VERSION, **counts}
