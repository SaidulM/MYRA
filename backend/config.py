"""MYRA — local settings & API keys (Stage 2).

Reads and writes the `.env` file at the repo root using only the
Python standard library. Security rules:

* Real key values are used by the backend only (Stages 3+).
* The UI never receives a full key back — `key_status()` returns
  only "is it set?" plus a masked tail like ``••••a1b2``.
* `.env` stays out of Git (see .gitignore).
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"

GEMINI = "GEMINI_API_KEY"
GROQ = "GROQ_API_KEY"


def load_env():
    """Parse the .env file into a dict (missing file -> empty dict)."""
    values = {}
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return values


def get(name, default=""):
    """Real environment variables win (used by launchers), then .env."""
    if os.environ.get(name):
        return os.environ[name]
    return load_env().get(name, default)


def _mask(value):
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return "••••" + value[-4:]


def key_status():
    """What the settings UI is allowed to know — never the full keys."""
    env = load_env()
    gemini = env.get(GEMINI, "")
    groq = env.get(GROQ, "")
    return {
        "gemini": {"set": bool(gemini), "masked": _mask(gemini)},
        "groq": {"set": bool(groq), "masked": _mask(groq)},
    }


def save_keys(gemini=None, groq=None):
    """Update .env in place.

    ``None`` = leave that key untouched, ``""`` = remove it,
    any other string = store it. Existing comments/other lines are
    preserved. Returns the new masked status.
    """
    updates = {}
    if gemini is not None:
        updates[GEMINI] = gemini.strip()
    if groq is not None:
        updates[GROQ] = groq.strip()

    lines = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    elif ENV_EXAMPLE.exists():
        lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()

    out, seen = [], set()
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")

    tmp = ENV_PATH.with_suffix(".tmp")
    tmp.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    os.replace(tmp, ENV_PATH)
    return key_status()


# Used by the backend brain from Stage 3 onwards.
def gemini_key():
    return get(GEMINI)


def groq_key():
    return get(GROQ)
