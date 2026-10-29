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
    service: object = None


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


def _workspace_search_text(args, context):
    root = _workspace_path(context, args.get("path", "."))
    if not root.is_dir():
        raise SkillError("Workspace folder was not found.", "not_found")
    query = args["query"].casefold()
    limit = int(args.get("limit", 50))
    matches = []
    for path in sorted(root.rglob("*")):
        if len(matches) >= limit:
            break
        if not path.is_file() or path.stat().st_size > 1_000_000:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(lines, 1):
            if query in line.casefold():
                matches.append({"path": _relative(context, path), "line": number, "text": line[:300]})
                if len(matches) >= limit:
                    break
    return {"query": args["query"], "matches": matches, "count": len(matches), "verified": True}


def _python_syntax_check(args, context):
    path = _workspace_path(context, args["path"])
    if not path.is_file():
        raise SkillError("Workspace Python file was not found.", "not_found")
    if path.suffix.lower() != ".py":
        raise SkillError("Python syntax check only accepts .py files.", "unsupported_file")
    try:
        source = path.read_text(encoding="utf-8")
        compile(source, str(path), "exec")
    except SyntaxError as exc:
        raise SkillError(f"Syntax error at line {exc.lineno}: {exc.msg}", "syntax_error") from exc
    except UnicodeDecodeError:
        raise SkillError("That file is not UTF-8 text.", "unsupported_file") from None
    return {"path": _relative(context, path), "syntax_ok": True, "verified": True}


def _multimodal_analyze_workspace_image(args, context):
    if context.service is None:
        raise SkillError("Vision service is not available in this execution context.", "vision_unavailable")
    path = _workspace_path(context, args["path"])
    if not path.is_file():
        raise SkillError("Workspace image was not found.", "not_found")
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(path.suffix.lower())
    if not mime:
        raise SkillError("Only JPEG, PNG or WebP workspace images can be analyzed.", "unsupported_file")
    raw = path.read_bytes()
    if len(raw) > 6 * 1024 * 1024:
        raise SkillError("Workspace image exceeds the 6 MB vision limit.", "file_too_large")
    import base64
    result = context.service.analyze_image({
        "image_base64": base64.b64encode(raw).decode("ascii"),
        "mime_type": mime,
        "prompt": args.get("prompt") or "Describe this workspace image and help with what is visible.",
        "consent": True,
        "source": "upload",
    })
    return {"path": _relative(context, path), **result, "verified": bool(result.get("text"))}


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
    process = subprocess.Popen(
        commands[app],
        close_fds=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
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


def _reminders_create(args, context):
    reminder = _require_memory(context).create_reminder(
        args["text"], due_at=args.get("due_at"), minutes=args.get("minutes")
    )
    return {"reminder": reminder, "verified": reminder is not None}


def _reminders_list(args, context):
    reminders = _require_memory(context).list_reminders(
        active_only=bool(args.get("active_only", True)), limit=args.get("limit", 50)
    )
    return {"reminders": reminders, "count": len(reminders), "verified": True}


def _reminders_complete(args, context):
    reminder = _require_memory(context).complete_reminder(args["id"], completed=True)
    return {"reminder": reminder, "verified": bool(reminder and reminder.get("completed"))}


def _reminders_delete(args, context):
    deleted = _require_memory(context).delete_reminder(args["id"])
    return {"deleted": args["id"], "verified": bool(deleted)}


def _data_migrate_legacy(args, context):
    legacy = Path(__file__).resolve().parent.parent / "data" / "myra.db"
    return _require_memory(context).import_legacy_database(legacy)


def _web_research(args, context):
    payload = {"query": args["query"], "max_sources": args.get("max_sources", 5)}
    try:
        if context.service is not None:
            return context.service.research(payload)
        import research as research_module
        return research_module.research(payload["query"], max_sources=payload["max_sources"])
    except Exception as exc:
        raise SkillError(str(exc), "research_failed") from exc


def _web_fetch_text(args, context):
    try:
        import research as research_module
        page = research_module.fetch_page(args["url"])
        page["text"] = page.get("text", "")[: int(args.get("max_chars", 10000))]
        return {**page, "verified": True}
    except Exception as exc:
        raise SkillError(str(exc), "web_fetch_failed") from exc


def _world_news(args, context):
    try:
        import news
        result = news.get_news(region=args.get("region", "all"), force_refresh=bool(args.get("force_refresh", False)))
        result["verified"] = bool(result.get("articles"))
        return result
    except Exception as exc:
        raise SkillError(str(exc), "news_failed") from exc


def _browser_call(method, *call_args, **call_kwargs):
    try:
        from browser_control import get_browser_controller
        return getattr(get_browser_controller(), method)(*call_args, **call_kwargs)
    except Exception as exc:
        raise SkillError(str(exc), "browser_failed") from exc


def _browser_status(args, context):
    from browser_control import browser_status
    return {**browser_status(), "verified": True}


def _browser_snapshot(args, context):
    return _browser_call("snapshot", args["url"])


def _browser_screenshot(args, context):
    return _browser_call("screenshot", args["url"], args.get("filename", "browser.png"))


def _browser_click(args, context):
    return _browser_call("click", args["url"], selector=args.get("selector", ""), text=args.get("text", ""))


def _browser_fill(args, context):
    return _browser_call(
        "fill", args["url"], args["selector"], args["value"], submit=bool(args.get("submit", False))
    )


def _windows_call(method, *call_args, **call_kwargs):
    try:
        from windows_control import get_windows_controller
        return getattr(get_windows_controller(), method)(*call_args, **call_kwargs)
    except Exception as exc:
        raise SkillError(str(exc), "windows_control_failed") from exc


def _windows_status(args, context):
    return {**_windows_call("status"), "verified": True}


def _windows_list(args, context):
    return _windows_call("list_windows")


def _windows_observe(args, context):
    return _windows_call("observe", window_title=args.get("window_title", ""), max_controls=args.get("max_controls", 160))


def _windows_focus(args, context):
    return _windows_call("focus_window", args["window_title"])


def _windows_query(args):
    return {
        "window_title": args.get("window_title", ""),
        "name": args.get("name", ""),
        "automation_id": args.get("automation_id", ""),
        "control_type": args.get("control_type", ""),
        "class_name": args.get("class_name", ""),
        "index": args.get("index", 0),
    }


def _windows_invoke(args, context):
    return _windows_call("invoke_control", **_windows_query(args))


def _windows_set_text(args, context):
    return _windows_call("set_text", args["text"], **_windows_query(args))


def _windows_send_keys(args, context):
    return _windows_call("send_keys", args["keys"], window_title=args.get("window_title", ""))


def _windows_click_point(args, context):
    return _windows_call(
        "click_point", args["x"], args["y"], button=args.get("button", "left"), double=bool(args.get("double", False))
    )


def _windows_type_text(args, context):
    return _windows_call("type_text", args["text"], interval_seconds=args.get("interval_seconds", 0.01))


def _windows_hotkey(args, context):
    return _windows_call("hotkey", args["keys"])


def _windows_emergency_stop(args, context):
    return {**_windows_call("emergency_stop"), "verified": True}


def _windows_reset_stop(args, context):
    return {**_windows_call("reset_emergency_stop"), "verified": True}


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
        "workspace.search_text", "Search workspace text", "Search UTF-8 text inside MYRA's safe workspace and return bounded line matches.",
        "1.0.0", "development",
        {"type": "object", "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 300},
            "path": {"type": "string", "maxLength": 300},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        }, "required": ["query"], "additionalProperties": False},
        ["read:workspace"], _workspace_search_text,
    ))
    add(SkillDefinition(
        "development.python_syntax_check", "Check Python syntax", "Compile-check one .py file in MYRA's workspace without executing it.",
        "1.0.0", "development",
        {"type": "object", "properties": {"path": {"type": "string", "minLength": 1, "maxLength": 300}}, "required": ["path"], "additionalProperties": False},
        ["read:workspace"], _python_syntax_check,
    ))
    add(SkillDefinition(
        "multimodal.analyze_workspace_image", "Analyze workspace image", "Send one explicitly selected JPEG/PNG/WebP image from MYRA's workspace to the configured vision provider.",
        "1.0.0", "multimodal",
        {"type": "object", "properties": {
            "path": {"type": "string", "minLength": 1, "maxLength": 300},
            "prompt": {"type": "string", "maxLength": 2000},
        }, "required": ["path"], "additionalProperties": False},
        ["read:workspace", "network:vision"], _multimodal_analyze_workspace_image,
        risk="medium", requires_confirmation=True, timeout_seconds=90,
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

    # Unified productivity/data skills
    add(SkillDefinition(
        "reminders.create", "Create reminder", "Create a local reminder in MYRA's unified SQLite database.",
        "1.0.0", "productivity",
        {"type": "object", "properties": {
            "text": {"type": "string", "minLength": 1, "maxLength": 1000},
            "due_at": {"type": "string", "maxLength": 80},
            "minutes": {"type": "number", "minimum": 0, "maximum": 525600},
        }, "required": ["text"], "additionalProperties": False},
        ["write:reminders"], _reminders_create, risk="medium", requires_confirmation=True,
    ))
    add(SkillDefinition(
        "reminders.list", "List reminders", "List local reminders from the unified database.",
        "1.0.0", "productivity",
        {"type": "object", "properties": {
            "active_only": {"type": "boolean"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
        }, "additionalProperties": False},
        ["read:reminders"], _reminders_list,
    ))
    add(SkillDefinition(
        "reminders.complete", "Complete reminder", "Mark one local reminder completed.",
        "1.0.0", "productivity",
        {"type": "object", "properties": {"id": {"type": "integer", "minimum": 1}}, "required": ["id"], "additionalProperties": False},
        ["write:reminders"], _reminders_complete, risk="medium", requires_confirmation=True,
    ))
    add(SkillDefinition(
        "reminders.delete", "Delete reminder", "Delete one local reminder.",
        "1.0.0", "productivity",
        {"type": "object", "properties": {"id": {"type": "integer", "minimum": 1}}, "required": ["id"], "additionalProperties": False},
        ["write:reminders"], _reminders_delete, risk="medium", requires_confirmation=True,
    ))
    add(SkillDefinition(
        "data.migrate_legacy", "Import legacy MYRA data", "Idempotently import the old repository data/myra.db into the unified app-data database.",
        "1.0.0", "system", _empty_schema(), ["write:database"], _data_migrate_legacy,
        risk="medium", requires_confirmation=True, timeout_seconds=60,
    ))

    # Public web research and world headlines
    add(SkillDefinition(
        "web.research", "Research the web", "Search public web sources, fetch bounded pages and return a cited synthesis or transparent source excerpts.",
        "1.0.0", "web",
        {"type": "object", "properties": {
            "query": {"type": "string", "minLength": 2, "maxLength": 300},
            "max_sources": {"type": "integer", "minimum": 1, "maximum": 8},
        }, "required": ["query"], "additionalProperties": False},
        ["network:public-web"], _web_research, timeout_seconds=90,
    ))
    add(SkillDefinition(
        "web.fetch_text", "Fetch public page text", "Fetch and extract readable text from one public http/https page. Private/local URLs are refused.",
        "1.0.0", "web",
        {"type": "object", "properties": {
            "url": {"type": "string", "minLength": 8, "maxLength": 2000},
            "max_chars": {"type": "integer", "minimum": 500, "maximum": 20000},
        }, "required": ["url"], "additionalProperties": False},
        ["network:public-web"], _web_fetch_text, timeout_seconds=30,
    ))
    add(SkillDefinition(
        "world.news", "World headlines", "Read MYRA's RSS World Monitor headlines, with offline cache fallback in the backend.",
        "1.0.0", "web",
        {"type": "object", "properties": {
            "region": {"type": "string", "enum": ["all", "global", "mideast", "tech", "asia"]},
            "force_refresh": {"type": "boolean"},
        }, "additionalProperties": False},
        ["network:public-web"], _world_news, timeout_seconds=35,
    ))

    # Optional visible Playwright automation
    add(SkillDefinition(
        "browser.status", "Browser automation status", "Report whether optional Playwright browser automation is installed.",
        "1.0.0", "web", _empty_schema(), ["read:browser"], _browser_status,
    ))
    add(SkillDefinition(
        "browser.snapshot", "Browser page snapshot", "Open a page in a visible Playwright browser and return title, text, links and controls. Refuses CAPTCHA/MFA pages.",
        "1.0.0", "web",
        {"type": "object", "properties": {"url": {"type": "string", "minLength": 8, "maxLength": 2000}}, "required": ["url"], "additionalProperties": False},
        ["read:browser", "network:public-web"], _browser_snapshot, timeout_seconds=60,
    ))
    add(SkillDefinition(
        "browser.screenshot", "Browser screenshot", "Open a page visibly with Playwright and save a screenshot into MYRA's workspace.",
        "1.0.0", "web",
        {"type": "object", "properties": {
            "url": {"type": "string", "minLength": 8, "maxLength": 2000},
            "filename": {"type": "string", "maxLength": 120},
        }, "required": ["url"], "additionalProperties": False},
        ["read:browser", "write:workspace"], _browser_screenshot,
        risk="medium", requires_confirmation=True, timeout_seconds=60,
    ))
    add(SkillDefinition(
        "browser.click", "Browser click", "Click one selector or visible text in a visible Playwright browser, then return the after-state snapshot.",
        "1.0.0", "web",
        {"type": "object", "properties": {
            "url": {"type": "string", "minLength": 8, "maxLength": 2000},
            "selector": {"type": "string", "maxLength": 500},
            "text": {"type": "string", "maxLength": 200},
        }, "required": ["url"], "additionalProperties": False},
        ["control:browser"], _browser_click, risk="high", requires_confirmation=True, timeout_seconds=60,
    ))
    add(SkillDefinition(
        "browser.fill", "Browser fill field", "Fill one non-secret browser field by CSS selector and optionally submit with Enter. Password/OTP fields are refused.",
        "1.0.0", "web",
        {"type": "object", "properties": {
            "url": {"type": "string", "minLength": 8, "maxLength": 2000},
            "selector": {"type": "string", "minLength": 1, "maxLength": 500},
            "value": {"type": "string", "maxLength": 5000},
            "submit": {"type": "boolean"},
        }, "required": ["url", "selector", "value"], "additionalProperties": False},
        ["control:browser"], _browser_fill, risk="high", requires_confirmation=True, timeout_seconds=60,
    ))

    # Semantic/coordinate Windows control.  Action skills are OFF until
    # the owner explicitly enables them in Skills; Agent confirmation is
    # still required for every write/control action.
    control_query = {
        "window_title": {"type": "string", "maxLength": 250},
        "name": {"type": "string", "maxLength": 250},
        "automation_id": {"type": "string", "maxLength": 250},
        "control_type": {"type": "string", "maxLength": 100},
        "class_name": {"type": "string", "maxLength": 250},
        "index": {"type": "integer", "minimum": 0, "maximum": 100},
    }
    add(SkillDefinition(
        "windows.status", "Windows control status", "Report semantic/coordinate Windows-control availability and emergency-stop state.",
        "1.0.0", "desktop", _empty_schema(), ["read:system"], _windows_status,
    ))
    add(SkillDefinition(
        "windows.list_windows", "List Windows windows", "List visible top-level Windows windows using UI Automation.",
        "1.0.0", "desktop", _empty_schema(), ["observe:windows"], _windows_list, enabled_default=False,
    ))
    add(SkillDefinition(
        "windows.observe", "Observe Windows window", "Observe a Windows window's semantic controls. Password values are redacted/refused.",
        "1.0.0", "desktop",
        {"type": "object", "properties": {
            "window_title": {"type": "string", "maxLength": 250},
            "max_controls": {"type": "integer", "minimum": 1, "maximum": 500},
        }, "additionalProperties": False},
        ["observe:windows"], _windows_observe, enabled_default=False, timeout_seconds=30,
    ))
    add(SkillDefinition(
        "windows.focus", "Focus Windows window", "Bring one named Windows window to focus.",
        "1.0.0", "desktop",
        {"type": "object", "properties": {"window_title": {"type": "string", "minLength": 1, "maxLength": 250}}, "required": ["window_title"], "additionalProperties": False},
        ["control:windows"], _windows_focus, risk="medium", requires_confirmation=True, enabled_default=False,
    ))
    add(SkillDefinition(
        "windows.invoke_control", "Invoke Windows control", "Invoke/click one semantic Windows control found by name, automation id, type or class.",
        "1.0.0", "desktop",
        {"type": "object", "properties": control_query, "additionalProperties": False},
        ["control:windows"], _windows_invoke, risk="high", requires_confirmation=True, enabled_default=False,
    ))
    add(SkillDefinition(
        "windows.set_text", "Set Windows control text", "Set text in one non-password semantic Windows control and verify where possible.",
        "1.0.0", "desktop",
        {"type": "object", "properties": {**control_query, "text": {"type": "string", "maxLength": 10000}}, "required": ["text"], "additionalProperties": False},
        ["control:windows"], _windows_set_text, risk="high", requires_confirmation=True, enabled_default=False,
    ))
    add(SkillDefinition(
        "windows.send_keys", "Send Windows keys", "Send pywinauto keyboard syntax to a focused/named Windows window.",
        "1.0.0", "desktop",
        {"type": "object", "properties": {
            "keys": {"type": "string", "minLength": 1, "maxLength": 1000},
            "window_title": {"type": "string", "maxLength": 250},
        }, "required": ["keys"], "additionalProperties": False},
        ["control:windows"], _windows_send_keys, risk="high", requires_confirmation=True, enabled_default=False,
    ))
    add(SkillDefinition(
        "windows.click_point", "Click screen point", "Coordinate fallback: click one on-screen point with PyAutoGUI failsafe enabled.",
        "1.0.0", "desktop",
        {"type": "object", "properties": {
            "x": {"type": "integer", "minimum": 0, "maximum": 20000},
            "y": {"type": "integer", "minimum": 0, "maximum": 20000},
            "button": {"type": "string", "enum": ["left", "right", "middle"]},
            "double": {"type": "boolean"},
        }, "required": ["x", "y"], "additionalProperties": False},
        ["control:windows"], _windows_click_point, risk="high", requires_confirmation=True, enabled_default=False,
    ))
    add(SkillDefinition(
        "windows.type_text", "Type text at focus", "Coordinate fallback: type text into the currently focused control. Never use for passwords/OTPs.",
        "1.0.0", "desktop",
        {"type": "object", "properties": {
            "text": {"type": "string", "minLength": 1, "maxLength": 5000},
            "interval_seconds": {"type": "number", "minimum": 0, "maximum": 0.2},
        }, "required": ["text"], "additionalProperties": False},
        ["control:windows"], _windows_type_text, risk="high", requires_confirmation=True, enabled_default=False, timeout_seconds=60,
    ))
    add(SkillDefinition(
        "windows.hotkey", "Press Windows hotkey", "Coordinate fallback: press a bounded key combination with PyAutoGUI.",
        "1.0.0", "desktop",
        {"type": "object", "properties": {
            "keys": {"type": "array", "maxItems": 5},
        }, "required": ["keys"], "additionalProperties": False},
        ["control:windows"], _windows_hotkey, risk="high", requires_confirmation=True, enabled_default=False,
    ))
    add(SkillDefinition(
        "windows.emergency_stop", "Emergency-stop Windows control", "Immediately block further MYRA Windows-control actions until manually reset in the UI.",
        "1.0.0", "desktop", _empty_schema(), ["control:windows"], _windows_emergency_stop,
    ))
    add(SkillDefinition(
        "windows.reset_emergency_stop", "Reset Windows emergency stop", "Allow Windows-control actions again after an emergency stop. Owner confirmation required.",
        "1.0.0", "desktop", _empty_schema(), ["control:windows"], _windows_reset_stop,
        risk="high", requires_confirmation=True,
    ))
    return registry
