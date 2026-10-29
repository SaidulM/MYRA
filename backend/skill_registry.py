"""MYRA skill registry and safe built-in skills.

A skill is a typed, permission-checked tool.  The model may *request* a
skill, but this registry validates the skill id, enabled state and every
argument before the handler runs.  Built-in file skills are deliberately
limited to MYRA's own workspace until the owner grants a selected folder
in a later, explicitly designed permission flow.
"""
from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import paths


class SkillError(Exception):
    def __init__(self, message, code="skill_error"):
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass
class SkillContext:
    memory: object = None
    task_id: str | None = None
    workspace: Path = field(default_factory=lambda: paths.workspace_dir())


@dataclass
class SkillDefinition:
    id: str
    name: str
    description: str
    version: str
    category: str
    parameters: dict
    permissions: list
    handler: Callable
    risk: str = "low"  # low | medium | high
    requires_confirmation: bool = False
    timeout_seconds: int = 15
    enabled_default: bool = True
    error_strategy: str = "stop"

    def manifest(self, enabled=True):
        data = asdict(self)
        data.pop("handler", None)
        data["enabled"] = bool(enabled)
        data["result_format"] = "json"
        return data


_ID_RE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")


def _type_ok(expected, value):
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True


def validate_arguments(schema, arguments):
    """Validate the small JSON-Schema subset used by MYRA skills."""
    if not isinstance(arguments, dict):
        raise SkillError("Skill arguments must be a JSON object.", "invalid_arguments")
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise SkillError("Skill schema is invalid.", "invalid_skill_schema")
    properties = schema.get("properties") or {}
    required = schema.get("required") or []
    for key in required:
        if key not in arguments:
            raise SkillError(f"Missing required skill argument: {key}", "invalid_arguments")
    if schema.get("additionalProperties") is False:
        unknown = sorted(set(arguments) - set(properties))
        if unknown:
            raise SkillError(
                "Unknown skill argument(s): " + ", ".join(unknown), "invalid_arguments"
            )
    for key, value in arguments.items():
        rule = properties.get(key) or {}
        expected = rule.get("type")
        if expected and not _type_ok(expected, value):
            raise SkillError(f"Argument '{key}' must be {expected}.", "invalid_arguments")
        if "enum" in rule and value not in rule["enum"]:
            raise SkillError(f"Argument '{key}' has an unsupported value.", "invalid_arguments")
        if isinstance(value, str):
            if len(value) > int(rule.get("maxLength", 30000)):
                raise SkillError(f"Argument '{key}' is too long.", "invalid_arguments")
            if len(value) < int(rule.get("minLength", 0)):
                raise SkillError(f"Argument '{key}' is too short.", "invalid_arguments")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in rule and value < rule["minimum"]:
                raise SkillError(f"Argument '{key}' is below its minimum.", "invalid_arguments")
            if "maximum" in rule and value > rule["maximum"]:
                raise SkillError(f"Argument '{key}' exceeds its maximum.", "invalid_arguments")
        if isinstance(value, list) and len(value) > int(rule.get("maxItems", 100)):
            raise SkillError(f"Argument '{key}' has too many items.", "invalid_arguments")
    return arguments


class SkillRegistry:
    def __init__(self, memory_store=None):
        self.memory_store = memory_store
        self._skills = {}
        self._enabled_overrides = {}

    def register(self, definition):
        if not _ID_RE.match(definition.id):
            raise ValueError(f"invalid skill id: {definition.id}")
        if definition.id in self._skills:
            raise ValueError(f"duplicate skill id: {definition.id}")
        if not callable(definition.handler):
            raise ValueError(f"skill {definition.id} has no callable handler")
        if not isinstance(definition.parameters, dict):
            raise ValueError(f"skill {definition.id} parameters must be a schema object")
        self._skills[definition.id] = definition
        return definition

    def get(self, skill_id):
        return self._skills.get(skill_id)

    def is_enabled(self, skill_id):
        definition = self.get(skill_id)
        if not definition:
            return False
        if self.memory_store is not None:
            return self.memory_store.skill_enabled(skill_id, definition.enabled_default)
        return self._enabled_overrides.get(skill_id, definition.enabled_default)

    def set_enabled(self, skill_id, enabled):
        if not self.get(skill_id):
            raise KeyError("skill not found")
        if self.memory_store is not None:
            self.memory_store.set_skill_enabled(skill_id, enabled)
        else:
            self._enabled_overrides[skill_id] = bool(enabled)
        return bool(enabled)

    def list(self, enabled_only=False):
        out = []
        for definition in sorted(self._skills.values(), key=lambda item: item.id):
            enabled = self.is_enabled(definition.id)
            if enabled_only and not enabled:
                continue
            out.append(definition.manifest(enabled=enabled))
        return out

    def definitions(self, enabled_only=True):
        return [
            definition
            for definition in sorted(self._skills.values(), key=lambda item: item.id)
            if not enabled_only or self.is_enabled(definition.id)
        ]

    def execute(self, skill_id, arguments=None, context=None):
        started = time.monotonic()
        definition = self.get(skill_id)
        if not definition:
            raise SkillError(f"Unknown skill: {skill_id}", "unknown_skill")
        if not self.is_enabled(skill_id):
            raise SkillError(f"Skill is disabled: {skill_id}", "skill_disabled")
        arguments = validate_arguments(definition.parameters, arguments or {})
        context = context or SkillContext(memory=self.memory_store)
        if context.memory is None:
            context.memory = self.memory_store

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="myra-skill")
        try:
            future = executor.submit(definition.handler, arguments, context)
            result = future.result(timeout=max(1, definition.timeout_seconds))
        except FutureTimeout:
            # Python cannot safely kill the thread; built-in handlers are
            # bounded and the task is reported as timed out to the planner.
            raise SkillError(
                f"Skill {skill_id} exceeded its {definition.timeout_seconds}s timeout.",
                "skill_timeout",
            ) from None
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        if not isinstance(result, dict):
            result = {"value": result}
        return {
            "ok": True,
            "skill_id": skill_id,
            "result": result,
            "verified": bool(result.get("verified", True)),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }


# ----------------------------------------------------------------------
# Safe built-in handlers
# ----------------------------------------------------------------------

def _empty_schema():
    return {"type": "object", "properties": {}, "additionalProperties": False}


def _workspace_path(context, relative="."):
    workspace = Path(context.workspace).resolve()
    raw = Path(relative or ".")
    if raw.is_absolute():
        raise SkillError("Built-in file skills only accept paths inside MYRA's workspace.", "path_not_allowed")
    candidate = (workspace / raw).resolve()
    if candidate != workspace and workspace not in candidate.parents:
        raise SkillError("That path is outside MYRA's workspace.", "path_not_allowed")
    return candidate


def _relative(context, path):
    try:
        return str(Path(path).resolve().relative_to(Path(context.workspace).resolve()))
    except ValueError:
        return str(path)


def _system_info(args, context):
    usage = shutil.disk_usage(paths.data_dir())
    return {
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(),
        "data_directory": str(paths.data_dir()),
        "workspace": str(context.workspace),
        "disk_free_gb": round(usage.free / (1024**3), 2),
        "verified": True,
    }


def _time_now(args, context):
    from datetime import datetime

    now = datetime.now().astimezone()
    return {
        "iso": now.isoformat(timespec="seconds"),
        "date": now.strftime("%A, %d %B %Y"),
        "time": now.strftime("%H:%M:%S"),
        "timezone": str(now.tzinfo),
        "verified": True,
    }


def _workspace_list(args, context):
    root = _workspace_path(context, args.get("path", "."))
    if not root.exists() or not root.is_dir():
        raise SkillError("Workspace folder was not found.", "not_found")
    entries = []
    for item in sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:200]:
        try:
            size = item.stat().st_size if item.is_file() else None
        except OSError:
            size = None
        entries.append(
            {
                "name": item.name,
                "path": _relative(context, item),
                "type": "folder" if item.is_dir() else "file",
                "size": size,
            }
        )
    return {"path": _relative(context, root), "entries": entries, "count": len(entries), "verified": True}


def _workspace_read(args, context):
    path = _workspace_path(context, args["path"])
    if not path.is_file():
        raise SkillError("Workspace file was not found.", "not_found")
    if path.stat().st_size > 1_000_000:
        raise SkillError("File is too large for this safe text reader (1 MB limit).", "file_too_large")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise SkillError("That file is not UTF-8 text.", "unsupported_file") from None
    max_chars = int(args.get("max_chars", 8000))
    return {
        "path": _relative(context, path),
        "content": text[:max_chars],
        "truncated": len(text) > max_chars,
        "characters": len(text),
        "verified": True,
    }


def _workspace_write(args, context):
    path = _workspace_path(context, args["path"])
    content = args["content"]
    overwrite = bool(args.get("overwrite", False))
    backup = bool(args.get("create_backup", True))
    existed_before = path.exists()
    if existed_before and not overwrite:
        raise SkillError("File already exists; overwrite was not approved in the arguments.", "already_exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = path.with_suffix(path.suffix + ".bak")
    backup_created = False
    if existed_before and backup:
        shutil.copy2(path, backup_path)
        backup_created = backup_path.exists()
    path.write_text(content, encoding="utf-8")
    written = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(written.encode("utf-8")).hexdigest()
    return {
        "path": _relative(context, path),
        "characters": len(written),
        "sha256": digest,
        "backup_created": backup_created,
        "verified": written == content,
    }


def _safe_destination(destination):
    if not destination.exists():
        return destination
    stem, suffix = destination.stem, destination.suffix
    for index in range(1, 1000):
        candidate = destination.with_name(f"{stem} ({index}){suffix}")
        if not candidate.exists():
            return candidate
    raise SkillError("Could not find a free destination filename.", "already_exists")


def _workspace_organize(args, context):
    root = _workspace_path(context, args.get("path", "."))
    dry_run = bool(args.get("dry_run", True))
    if not root.is_dir():
        raise SkillError("Workspace folder was not found.", "not_found")
    moves = []
    for item in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not item.is_file():
            continue
        ext = item.suffix.lower().lstrip(".")
        ext = re.sub(r"[^a-z0-9_-]", "", ext)[:24] or "no_extension"
        destination_dir = root / ext
        destination = _safe_destination(destination_dir / item.name)
        moves.append(
            {
                "from": _relative(context, item),
                "to": _relative(context, destination),
            }
        )
        if not dry_run:
            destination_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(item), str(destination))
    verified = True
    if not dry_run:
        verified = all((Path(context.workspace) / move["to"]).exists() for move in moves)
    return {"dry_run": dry_run, "moves": moves, "count": len(moves), "verified": verified}


def _require_memory(context):
    if context.memory is None:
        raise SkillError("Memory store is not available.", "memory_unavailable")
    return context.memory


def _memory_remember(args, context):
    memory = _require_memory(context).add_memory(
        args["text"], category=args.get("category", "general"), source="agent"
    )
    return {"memory": memory, "verified": memory is not None}


def _memory_search(args, context):
    results = _require_memory(context).search_memories(args["query"], limit=args.get("limit", 8))
    return {"results": results, "count": len(results), "verified": True}


def _notes_create(args, context):
    note = _require_memory(context).create_note(args["title"], args.get("body", ""))
    return {"note": note, "verified": note is not None}


def _notes_list(args, context):
    notes = _require_memory(context).list_notes(query=args.get("query", ""), limit=args.get("limit", 50))
    return {"notes": notes, "count": len(notes), "verified": True}


def _app_launch(args, context):
    if os.name != "nt":
        raise SkillError("Allowlisted app launch is currently implemented for Windows only.", "unsupported_platform")
    commands = {
        "notepad": ["notepad.exe"],
        "calculator": ["calc.exe"],
        "explorer": ["explorer.exe"],
    }
    app = args["app"]
    process = subprocess.Popen(commands[app], close_fds=True)
    return {"app": app, "pid": process.pid, "verified": process.poll() is None or app == "explorer"}


def _web_open(args, context):
    url = args["url"].strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SkillError("Only complete http/https URLs may be opened.", "invalid_url")
    opened = webbrowser.open(url)
    if not opened:
        raise SkillError("The operating system could not open a browser.", "browser_unavailable")
    return {"url": url, "opened": True, "verified": True}


def build_default_registry(memory_store=None):
    registry = SkillRegistry(memory_store=memory_store)
    add = registry.register

    add(SkillDefinition(
        "system.info", "System information", "Read basic OS, Python, CPU and free-disk information.",
        "1.0.0", "system", _empty_schema(), ["read:system"], _system_info,
    ))
    add(SkillDefinition(
        "time.now", "Current time", "Return the laptop's current local date and time.",
        "1.0.0", "system", _empty_schema(), [], _time_now,
    ))
    add(SkillDefinition(
        "workspace.list", "List workspace", "List files inside MYRA's safe workspace folder.",
        "1.0.0", "files",
        {"type": "object", "properties": {"path": {"type": "string", "maxLength": 300}}, "additionalProperties": False},
        ["read:workspace"], _workspace_list,
    ))
    add(SkillDefinition(
        "workspace.read_text", "Read workspace text", "Read a UTF-8 text file from MYRA's workspace.",
        "1.0.0", "files",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1, "maxLength": 300},
                "max_chars": {"type": "integer", "minimum": 100, "maximum": 20000},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        ["read:workspace"], _workspace_read,
    ))
    add(SkillDefinition(
        "workspace.write_text", "Write workspace text", "Create or explicitly overwrite a UTF-8 text file in MYRA's workspace, with a backup by default.",
        "1.0.0", "files",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1, "maxLength": 300},
                "content": {"type": "string", "maxLength": 30000},
                "overwrite": {"type": "boolean"},
                "create_backup": {"type": "boolean"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        ["write:workspace"], _workspace_write,
        risk="medium", requires_confirmation=True,
    ))
    add(SkillDefinition(
        "workspace.organize_by_extension", "Organize workspace by extension",
        "Preview or perform organizing top-level workspace files into folders named by file extension. Never overwrites.",
        "1.0.0", "files",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "maxLength": 300},
                "dry_run": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        ["read:workspace", "write:workspace"], _workspace_organize,
        risk="medium", requires_confirmation=True,
    ))
    add(SkillDefinition(
        "memory.remember", "Remember approved fact", "Save one explicit, user-approved memory in local SQLite.",
        "1.0.0", "memory",
        {
            "type": "object",
            "properties": {
                "text": {"type": "string", "minLength": 1, "maxLength": 2000},
                "category": {"type": "string", "maxLength": 60},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
        ["write:memory"], _memory_remember,
        risk="medium", requires_confirmation=True,
    ))
    add(SkillDefinition(
        "memory.search", "Search memories", "Search user-approved local memories by keyword.",
        "1.0.0", "memory",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 300},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        ["read:memory"], _memory_search,
    ))
    add(SkillDefinition(
        "notes.create", "Create note", "Create a local note in MYRA's SQLite database.",
        "1.0.0", "productivity",
        {
            "type": "object",
            "properties": {
                "title": {"type": "string", "minLength": 1, "maxLength": 160},
                "body": {"type": "string", "maxLength": 30000},
            },
            "required": ["title"],
            "additionalProperties": False,
        },
        ["write:notes"], _notes_create,
        risk="medium", requires_confirmation=True,
    ))
    add(SkillDefinition(
        "notes.list", "List notes", "List or search local notes.",
        "1.0.0", "productivity",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "maxLength": 300},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "additionalProperties": False,
        },
        ["read:notes"], _notes_list,
    ))
    add(SkillDefinition(
        "app.launch_allowlisted", "Launch allowlisted Windows app",
        "Launch one allowlisted Windows app: notepad, calculator, or explorer. No arbitrary programs or shell commands.",
        "1.0.0", "desktop",
        {
            "type": "object",
            "properties": {"app": {"type": "string", "enum": ["notepad", "calculator", "explorer"]}},
            "required": ["app"],
            "additionalProperties": False,
        },
        ["launch:app"], _app_launch,
        risk="medium", requires_confirmation=True,
    ))
    add(SkillDefinition(
        "web.open_url", "Open URL for the user",
        "Open one complete http/https URL in the user's default browser. This does not automate or read the page.",
        "1.0.0", "web",
        {
            "type": "object",
            "properties": {"url": {"type": "string", "minLength": 8, "maxLength": 2000}},
            "required": ["url"],
            "additionalProperties": False,
        },
        ["open:browser"], _web_open,
        risk="medium", requires_confirmation=True,
    ))
    return registry
