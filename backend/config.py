"""MYRA — local settings & API keys.

Secrets prefer the operating-system credential store when the optional
``keyring`` package is available (Windows Credential Manager on Windows).
The existing private ``.env`` file remains a no-dependency fallback for
the current lightweight install. Security rules:

* Real key values are used by the backend only.
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
    """Read a non-secret setting: real environment first, then .env."""
    if os.environ.get(name):
        return os.environ[name]
    return load_env().get(name, default)


SECRET_SERVICE = "MYRA"
_SECRET_ENV_NAMES = {GEMINI, GROQ}


def _keyring_module():
    """Return keyring only when it has a usable (non-fail) backend."""
    if os.environ.get("MYRA_SECRET_STORE", "").strip().lower() == "env":
        return None
    try:
        import keyring

        backend = keyring.get_keyring()
        backend_name = f"{backend.__class__.__module__}.{backend.__class__.__name__}".lower()
        if "fail" in backend_name or "null" in backend_name:
            return None
        return keyring
    except Exception:
        return None


def secret_backend():
    return "os-credential-store" if _keyring_module() else "local-.env"


def _keyring_get(name):
    keyring = _keyring_module()
    if not keyring:
        return ""
    try:
        return keyring.get_password(SECRET_SERVICE, name) or ""
    except Exception:
        return ""


def _keyring_set(name, value):
    keyring = _keyring_module()
    if not keyring:
        return False
    try:
        if value:
            keyring.set_password(SECRET_SERVICE, name, value)
        else:
            try:
                keyring.delete_password(SECRET_SERVICE, name)
            except Exception:
                pass
        return True
    except Exception:
        return False


def secret_source(name):
    if name not in _SECRET_ENV_NAMES:
        return "setting"
    if os.environ.get(name):
        return "environment"
    if _keyring_get(name):
        return "os-credential-store"
    if load_env().get(name):
        return "local-.env"
    return "not-set"


def effective_secret(name):
    """Read an API secret without ever exposing it to the UI layer."""
    if os.environ.get(name):
        return os.environ[name]
    value = _keyring_get(name)
    if value:
        return value
    return load_env().get(name, "")


def _mask(value):
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return "••••" + value[-4:]


def key_status():
    """What the settings UI is allowed to know — never the full keys."""
    gemini = effective_secret(GEMINI)
    groq = effective_secret(GROQ)
    return {
        "gemini": {
            "set": bool(gemini),
            "masked": _mask(gemini),
            "storage": secret_source(GEMINI),
        },
        "groq": {
            "set": bool(groq),
            "masked": _mask(groq),
            "storage": secret_source(GROQ),
        },
        "secret_backend": secret_backend(),
    }


def _save_env_values(updates):
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


def save_keys(gemini=None, groq=None):
    """Save/remove API keys and return masked status.

    ``None`` leaves a key untouched; ``""`` removes it everywhere.  When
    an OS credential store is available, new non-empty keys are stored
    there and any old plaintext copy is blanked from ``.env``.
    """
    updates = {}
    if gemini is not None:
        updates[GEMINI] = gemini.strip()
    if groq is not None:
        updates[GROQ] = groq.strip()

    env_updates = {}
    use_keyring = _keyring_module() is not None
    for name, value in updates.items():
        if not value:
            if use_keyring:
                _keyring_set(name, "")
            env_updates[name] = ""
        elif use_keyring and _keyring_set(name, value):
            # Remove a previous plaintext copy after the secure save works.
            env_updates[name] = ""
        else:
            env_updates[name] = value

    if env_updates:
        _save_env_values(env_updates)
    return key_status()


# Used by the backend brain from Stage 3 onwards.
def gemini_key():
    return effective_secret(GEMINI)


def groq_key():
    return effective_secret(GROQ)
