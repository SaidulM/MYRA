"""MYRA runtime files, default UI settings and readiness checks.

The visual UI has many options.  This module is the one place that makes
sure the local files/folders those options need actually exist on the
owner's PC, and reports (without secrets) what is ready or still needs a
one-time action such as saving an API key or downloading the voice model.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import config
import paths
from core_memory import MemoryStore
from voice import VoiceModelManager


DEFAULT_UI_SETTINGS = {
    "assistant_name": "MYRA",
    "owner_name": "Saidul",
    "character": "female",
    "theme": "stonic",
    "brain_provider": "auto",
    "personality": "Warm & friendly",
    # Owner rule: short answers by default; detailed only when asked.
    "response_style": "auto",
    "awareness": False,
    "voice_style": "gentle",
    "voice_pitch": 1.0,
    "voice_rate": 1.0,
    "voice_uri": "auto",
    "voice_muted": False,
    "speech_language": "bn-BD",
    "custom_persona_name": "",
    "custom_persona_prompt": "",
    "office_animation": True,
    "globe_auto_spin": True,
    "right_panel_collapsed": False,
    "news_region": "all",
    "onboarded": False,
}

_BOOL_KEYS = {
    "awareness",
    "voice_muted",
    "office_animation",
    "globe_auto_spin",
    "right_panel_collapsed",
    "onboarded",
}
_RUNTIME_DIRS = (
    "workspace",
    "models",
    "models/faster-whisper",
    "voice_cache",
    "voice-temp",
    "backups",
    "logs",
    "webview-profile",
    "attachments",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _data_dir(data_dir=None) -> Path:
    return Path(data_dir).expanduser() if data_dir else paths.data_dir()


def _env_path(env_path=None) -> Path:
    return Path(env_path).expanduser() if env_path else config.ENV_PATH


def _store_for(data: Path, store=None) -> MemoryStore:
    return store or MemoryStore(data / "myra.db")


def _clean_ui_settings(partial) -> dict:
    if not isinstance(partial, dict):
        raise ValueError("UI settings must be an object")

    clean = {}
    text_limits = {
        "assistant_name": 40,
        "owner_name": 60,
        "personality": 80,
        "voice_uri": 240,
        "speech_language": 16,
        "custom_persona_name": 80,
        "custom_persona_prompt": 2000,
        "news_region": 32,
    }
    choices = {
        "character": {"core", "male", "female", "custom"},
        "theme": {"stonic", "normal", "friendly", "hacker"},
        "brain_provider": {
            "auto", "gemini", "groq", "openrouter", "openai", "anthropic",
            "deepseek", "mistral", "ollama",
        },
        "response_style": {"auto", "short", "detailed"},
        "voice_style": {"gentle", "whisper", "chat", "jarvis"},
    }

    for key, value in partial.items():
        if key not in DEFAULT_UI_SETTINGS:
            continue
        if key in _BOOL_KEYS:
            if isinstance(value, bool):
                clean[key] = value
            elif isinstance(value, str):
                clean[key] = value.strip().lower() in {"1", "true", "yes", "on"}
            elif isinstance(value, (int, float)):
                clean[key] = bool(value)
            continue
        if key in {"voice_pitch", "voice_rate"}:
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            clean[key] = max(0.5, min(2.0, number))
            continue
        text = " ".join(str(value or "").split()) if key != "custom_persona_prompt" else str(value or "").strip()
        if key in choices:
            text = text.lower()
            if text not in choices[key]:
                continue
        clean[key] = text[: text_limits.get(key, 120)]
    return clean


def get_ui_settings(data_dir=None, store=None) -> dict:
    """Return merged UI settings plus the raw stored subset.

    ``stored_settings`` lets the web UI migrate safely: values already in
    the owner's WebView local storage win on first sync; backend values are
    used to restore a setting when local storage is missing it.
    """
    data = _data_dir(data_dir)
    raw = {}
    if store is not None:
        value = store.get_preference("ui_settings", {})
        if isinstance(value, dict):
            raw = _clean_ui_settings(value)
    elif (data / "myra.db").exists():
        value = _store_for(data).get_preference("ui_settings", {})
        if isinstance(value, dict):
            raw = _clean_ui_settings(value)
    merged = dict(DEFAULT_UI_SETTINGS)
    merged.update(raw)
    return {"settings": merged, "stored_settings": raw}


def save_ui_settings(partial, data_dir=None, store=None) -> dict:
    data = _data_dir(data_dir)
    data.mkdir(parents=True, exist_ok=True)
    active_store = _store_for(data, store)
    current = get_ui_settings(data, active_store)["settings"]
    current.update(_clean_ui_settings(partial))
    active_store.set_preference("ui_settings", current)
    return current


def _atomic_write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _db_tables(db_path: Path) -> set[str]:
    if not db_path.exists():
        return set()
    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
            ).fetchall()
        finally:
            conn.close()
        return {str(row[0]) for row in rows}
    except sqlite3.Error:
        return set()


def ensure_runtime_files(data_dir=None, env_path=None, create_env=True) -> dict:
    """Create every local folder/file/default needed by the UI options."""
    data = _data_dir(data_dir)
    data.mkdir(parents=True, exist_ok=True)
    for relative in _RUNTIME_DIRS:
        (data / relative).mkdir(parents=True, exist_ok=True)

    store = _store_for(data)
    if not isinstance(store.get_preference("ui_settings", None), dict):
        store.set_preference("ui_settings", dict(DEFAULT_UI_SETTINGS))
    if store.get_preference("provider_models", None) is None:
        store.set_preference("provider_models", {})

    # World Monitor offline cache (backend copy; the web UI also keeps a
    # browser-profile cache for instant Start).
    news_cache = data / "news_cache.json"
    valid_news = False
    if news_cache.exists():
        try:
            parsed = json.loads(news_cache.read_text(encoding="utf-8"))
            valid_news = isinstance(parsed, dict) and isinstance(parsed.get("items"), list)
        except (OSError, ValueError):
            valid_news = False
    if not valid_news:
        _atomic_write_json(news_cache, {"items": [], "updated_at": 0})

    # Voice model registry file.  Creating the registry never downloads a
    # model; downloads still require the owner's explicit confirmation.
    voice_manager = VoiceModelManager(data)
    if not voice_manager.state_path.exists():
        _atomic_write_json(voice_manager.state_path, {"installed": []})

    feedback_path = data / "feedback.jsonl"
    if not feedback_path.exists():
        feedback_path.touch()

    env_created = False
    if create_env:
        try:
            env_created = config.ensure_env_file(_env_path(env_path))
        except OSError:
            # A read-only install folder must not prevent MYRA from
            # starting.  Readiness will honestly report the missing .env;
            # keys can still use the OS credential store when available.
            env_created = False

    try:
        _atomic_write_json(
            data / "runtime-status.json",
            {
                "initialized_at": _now(),
                "database": "myra.db",
                "env_created": env_created,
                "directories": list(_RUNTIME_DIRS),
            },
        )
    except OSError:
        pass

    return runtime_status(data_dir=data, env_path=env_path, store=store)


def append_feedback(text, source="web-ui", data_dir=None) -> dict:
    clean = str(text or "").strip()[:4000]
    if not clean:
        raise ValueError("Feedback text is required")
    data = _data_dir(data_dir)
    data.mkdir(parents=True, exist_ok=True)
    record = {
        "created_at": _now(),
        "source": str(source or "web-ui")[:40],
        "text": clean,
    }
    with open(data / "feedback.jsonl", "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def runtime_status(data_dir=None, env_path=None, host="127.0.0.1", scheme="http", store=None) -> dict:
    """Non-secret readiness checklist for every major UI option."""
    data = _data_dir(data_dir)
    env_file = _env_path(env_path)
    db_path = data / "myra.db"
    tables = _db_tables(db_path)
    required_tables = {
        "conversations", "messages", "memories", "notes", "reminders",
        "preferences", "skill_settings", "agent_tasks",
    }

    key_status = config.key_status()
    configured_brains = [
        name for name in ("gemini", "groq", "openrouter", "openai", "anthropic", "deepseek", "mistral")
        if (key_status.get(name) or {}).get("set")
    ]
    if (key_status.get("ollama") or {}).get("model"):
        configured_brains.append("ollama")

    voice_status = VoiceModelManager(data).status()
    engines = voice_status.get("engines") or {}
    ui = get_ui_settings(data, store)
    host_text = str(host or "127.0.0.1")
    loopback = host_text in {"127.0.0.1", "localhost", "::1"}
    scheme_text = str(scheme or "http").lower()

    checks = []

    def add(check_id, label, status, detail):
        checks.append({
            "id": check_id,
            "label": label,
            "status": status,
            "ok": status == "ready",
            "ready": status == "ready",
            "detail": detail,
        })

    add(
        "database",
        "Memory · Notes · Reminders · History database",
        "ready" if db_path.exists() and required_tables.issubset(tables) else "action_needed",
        "myra.db and its tables are ready." if required_tables.issubset(tables) else "Tap CREATE / REPAIR FILES to create myra.db.",
    )
    add(
        "env_file",
        "Brain keys & model settings file",
        "ready" if env_file.exists() else "action_needed",
        "Private .env exists on this laptop (values are never shown here)." if env_file.exists() else "Tap CREATE / REPAIR FILES; then save a free Gemini/Groq key above.",
    )
    add(
        "brain",
        "AI Brain connection",
        "ready" if configured_brains else "action_needed",
        ("Configured: " + ", ".join(configured_brains) + ".") if configured_brains else "No API key or Ollama model saved yet.",
    )
    add(
        "ui_settings",
        "UI preferences backup",
        "ready" if ui["stored_settings"] else "action_needed",
        "Theme, character, brain, voice, awareness and answer-length defaults are stored in myra.db." if ui["stored_settings"] else "Tap CREATE / REPAIR FILES to create the default UI settings.",
    )
    add(
        "workspace",
        "Agent workspace & downloads",
        "ready" if (data / "workspace").is_dir() else "action_needed",
        "workspace folder is ready for approved Agent file work." if (data / "workspace").is_dir() else "workspace folder is missing.",
    )
    add(
        "skills",
        "Skills & Agent settings",
        "ready" if "skill_settings" in tables and Path(__file__).with_name("skill_registry.py").exists() else "action_needed",
        "Built-in skill registry and on/off settings table are ready." if "skill_settings" in tables else "Skill settings table is missing.",
    )
    add(
        "voice_hearing",
        "Live voice hearing (microphone → text)",
        "ready" if engines.get("faster_whisper_python_package") and engines.get("faster_whisper_model_installed") else "action_needed",
        "faster-whisper package and a downloaded speech model are ready." if engines.get("faster_whisper_python_package") and engines.get("faster_whisper_model_installed") else "Needs the one-time confirmed speech-model download in CHARACTER → VOICE STUDIO.",
    )
    add(
        "voice_speaking",
        "Voice speaking (MYRA reply → sound)",
        "ready" if engines.get("edge_tts_python_package") else "optional",
        "Edge Neural voice package is ready; browser speech is the fallback." if engines.get("edge_tts_python_package") else "Edge voice package is missing; MYRA will try the Windows/browser voice.",
    )
    add(
        "voice_files",
        "Voice cache & temporary audio folders",
        "ready" if (data / "voice_cache").is_dir() and (data / "voice-temp").is_dir() and (data / "voice-models.json").exists() else "action_needed",
        "voice_cache, voice-temp and voice-models.json are ready." if (data / "voice_cache").is_dir() and (data / "voice-temp").is_dir() and (data / "voice-models.json").exists() else "Voice cache/temp folders or voice-models.json are missing.",
    )
    add(
        "news_cache",
        "World Monitor offline headlines",
        "ready" if (data / "news_cache.json").exists() else "action_needed",
        "news_cache.json exists; online refresh fills it over HTTPS." if (data / "news_cache.json").exists() else "Offline news cache file is missing.",
    )
    add(
        "feedback",
        "Feedback storage",
        "ready" if (data / "feedback.jsonl").exists() else "action_needed",
        "feedback.jsonl is ready on this laptop." if (data / "feedback.jsonl").exists() else "Feedback file is missing.",
    )
    add(
        "updates",
        "GitHub auto-update",
        "ready" if (Path(__file__).resolve().parent.parent / "launcher.py").exists() else "action_needed",
        "launcher.py checks GitHub main over HTTPS; the update popup is always dismissible.",
    )
    if scheme_text == "https":
        add("local_connection", "MYRA window ↔ local backend", "ready", "Local backend is served over HTTPS with your configured certificate.")
    elif loopback:
        add("local_connection", "MYRA window ↔ local backend", "ready", "HTTP on 127.0.0.1 only — this stays inside your own laptop, so no internet HTTPS certificate is needed.")
    else:
        add("local_connection", "MYRA window ↔ local backend", "warning", "Backend is exposed beyond loopback over HTTP. Use only trusted home Wi-Fi and prefer HTTPS. MYRA_API_TOKEN gates Core API calls from other devices; it is not a password for the whole page.")
    add(
        "external_https",
        "Internet connections (AI · GitHub · news · models)",
        "ready",
        "Cloud AI, GitHub updates, RSS and confirmed model downloads use verified HTTPS. Ollama stays local on this PC.",
    )
    if loopback:
        add("phone_link", "Phone Link (QR)", "optional", "OFF in safe local-only mode. The QR option will say so honestly instead of pretending the phone can connect.")
    elif scheme_text == "https":
        add("phone_link", "Phone Link (QR)", "ready", "LAN mode with HTTPS is configured. Use only your trusted Wi-Fi — the page itself has no password lock.")
    else:
        add("phone_link", "Phone Link (QR)", "warning", "LAN mode is on over HTTP (not HTTPS) and the page has no password lock. Use only trusted home Wi-Fi.")

    ready = sum(1 for item in checks if item["status"] == "ready")
    return {
        "ok": True,
        "ready": ready,
        "total": len(checks),
        "all_core_ready": all(item["status"] != "action_needed" for item in checks),
        "backend": {
            "host": host_text,
            "scheme": scheme_text,
            "mode": (
                "Local HTTPS" if scheme_text == "https"
                else "Safe local-only mode" if loopback
                else "LAN HTTP mode (trusted Wi-Fi only — no page password)"
            ),
            "lan_enabled": not loopback,
        },
        "data_folder": "MYRA app data",
        "database_file": "myra.db",
        "settings_file": ".env (private, in the MYRA install folder)",
        "ui_settings": ui["settings"],
        "checks": checks,
    }
