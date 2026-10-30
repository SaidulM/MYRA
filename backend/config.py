"""MYRA — local settings & API keys (multi-provider).

Secrets prefer the operating-system credential store when the optional
``keyring`` package is available (Windows Credential Manager on Windows).
The private ``.env`` file remains the no-dependency fallback and also stores
non-secret model choices. Security rules:

* Real key values are used by the backend only.
* The UI never receives a full key back — ``key_status()`` returns only
  "is it set?" plus a masked tail like ``••••a1b2``.
* ``.env`` stays out of Git (see .gitignore).
"""
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"

# Provider key names
GEMINI = "GEMINI_API_KEY"
GROQ = "GROQ_API_KEY"
OPENROUTER = "OPENROUTER_API_KEY"
OPENAI = "OPENAI_API_KEY"
ANTHROPIC = "ANTHROPIC_API_KEY"
DEEPSEEK = "DEEPSEEK_API_KEY"
MISTRAL = "MISTRAL_API_KEY"
OLLAMA_URL = "OLLAMA_URL"

_SECRET_ENV_NAMES = {
    GEMINI,
    GROQ,
    OPENROUTER,
    OPENAI,
    ANTHROPIC,
    DEEPSEEK,
    MISTRAL,
}
SECRET_SERVICE = "MYRA"


def load_env():
    """Parse the .env file into a dict (missing file -> empty dict)."""
    values = {}
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as handle:
            for line in handle:
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


def ensure_env_file(path=None):
    """Create the private .env starter file if it does not exist.

    Existing files are never overwritten.  The starter contains setting
    names only; the owner still pastes their own keys inside MYRA.
    Returns True only when a new file was created.
    """
    target = Path(path).expanduser() if path else ENV_PATH
    if target.exists():
        return False
    text = ENV_EXAMPLE.read_text(encoding="utf-8") if ENV_EXAMPLE.exists() else "# MYRA private settings\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(text.rstrip() + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return True


def _keyring_module():
    """Return keyring only when it has a usable (non-fail) backend."""
    if get("MYRA_SECRET_STORE", "").strip().lower() == "env":
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


def _secret_status(name, model):
    value = effective_secret(name)
    return {
        "set": bool(value),
        "masked": _mask(value),
        "model": model,
        "storage": secret_source(name),
    }


_OLLAMA_STATUS_CACHE = {"key": None, "at": 0.0, "value": None}


def ollama_status(opener=None):
    """Return saved Ollama settings plus a short, cached reachability check.

    The settings UI previously guessed "offline" from a missing field.
    This performs one tiny local ``/api/tags`` request (cached for a few
    seconds) so the badge can honestly say whether the Ollama app is
    reachable and whether the saved model is installed.
    """
    model = get("OLLAMA_MODEL", "").strip()
    base_url = (get(OLLAMA_URL, "http://127.0.0.1:11434") or "http://127.0.0.1:11434").rstrip("/")
    cache_key = (base_url, model)
    now = time.monotonic()
    if (
        _OLLAMA_STATUS_CACHE["key"] == cache_key
        and _OLLAMA_STATUS_CACHE["value"] is not None
        and now - _OLLAMA_STATUS_CACHE["at"] < 3.0
    ):
        return dict(_OLLAMA_STATUS_CACHE["value"])

    running = False
    installed_models = []
    open_url = opener or urllib.request.urlopen
    try:
        request = urllib.request.Request(
            f"{base_url}/api/tags", headers={"Accept": "application/json"}
        )
        with open_url(request, timeout=0.35) as response:
            running = int(getattr(response, "status", 200) or 200) == 200
            payload = json.loads(response.read().decode("utf-8") or "{}")
        for item in payload.get("models", []) if isinstance(payload, dict) else []:
            if isinstance(item, dict):
                name = str(item.get("name") or item.get("model") or "").strip()
                if name:
                    installed_models.append(name)
    except (OSError, ValueError, urllib.error.URLError):
        running = False

    wanted = model.lower()
    model_installed = bool(
        wanted
        and any(
            name.lower() == wanted or name.lower().startswith(wanted + ":")
            for name in installed_models
        )
    )
    value = {
        "set": bool(model),
        "url": base_url,
        "model": model,
        "running": running,
        "model_installed": model_installed,
        "installed_models": installed_models[:20],
    }
    _OLLAMA_STATUS_CACHE.update({"key": cache_key, "at": now, "value": value})
    return dict(value)


def key_status():
    """What the settings UI is allowed to know — never the full keys."""
    return {
        "gemini": _secret_status(GEMINI, get("GEMINI_MODEL", "auto") or "auto"),
        "groq": _secret_status(GROQ, get("GROQ_MODEL", "auto") or "auto"),
        "openrouter": _secret_status(OPENROUTER, get("OPENROUTER_MODEL", "auto") or "auto"),
        "openai": _secret_status(OPENAI, get("OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini"),
        "anthropic": _secret_status(
            ANTHROPIC, get("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022") or "claude-3-5-haiku-20241022"
        ),
        "deepseek": _secret_status(DEEPSEEK, get("DEEPSEEK_MODEL", "deepseek-chat") or "deepseek-chat"),
        "mistral": _secret_status(
            MISTRAL, get("MISTRAL_MODEL", "mistral-small-latest") or "mistral-small-latest"
        ),
        "ollama": ollama_status(),
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


def save_keys(
    gemini=None,
    groq=None,
    gemini_model=None,
    groq_model=None,
    openrouter=None,
    openrouter_model=None,
    openai=None,
    openai_model=None,
    anthropic=None,
    anthropic_model=None,
    deepseek=None,
    deepseek_model=None,
    mistral=None,
    mistral_model=None,
    ollama_url=None,
    ollama_model=None,
):
    """Update provider secrets/settings and return masked status."""
    updates = {}
    if gemini is not None: updates[GEMINI] = gemini.strip()
    if groq is not None: updates[GROQ] = groq.strip()
    if gemini_model is not None: updates["GEMINI_MODEL"] = gemini_model.strip()
    if groq_model is not None: updates["GROQ_MODEL"] = groq_model.strip()

    if openrouter is not None: updates[OPENROUTER] = openrouter.strip()
    if openrouter_model is not None: updates["OPENROUTER_MODEL"] = openrouter_model.strip()

    if openai is not None: updates[OPENAI] = openai.strip()
    if openai_model is not None: updates["OPENAI_MODEL"] = openai_model.strip()

    if anthropic is not None: updates[ANTHROPIC] = anthropic.strip()
    if anthropic_model is not None: updates["ANTHROPIC_MODEL"] = anthropic_model.strip()

    if deepseek is not None: updates[DEEPSEEK] = deepseek.strip()
    if deepseek_model is not None: updates["DEEPSEEK_MODEL"] = deepseek_model.strip()

    if mistral is not None: updates[MISTRAL] = mistral.strip()
    if mistral_model is not None: updates["MISTRAL_MODEL"] = mistral_model.strip()

    if ollama_url is not None: updates[OLLAMA_URL] = ollama_url.strip()
    if ollama_model is not None: updates["OLLAMA_MODEL"] = ollama_model.strip()

    env_updates = {}
    use_keyring = _keyring_module() is not None
    for name, value in updates.items():
        if name not in _SECRET_ENV_NAMES:
            env_updates[name] = value
        elif not value:
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


# Accessors used across the backend. Secrets use environment ->
# OS credential store -> private .env; model/URL settings use get().
def gemini_key(): return effective_secret(GEMINI)
def groq_key(): return effective_secret(GROQ)
def openrouter_key(): return effective_secret(OPENROUTER)
def openai_key(): return effective_secret(OPENAI)
def anthropic_key(): return effective_secret(ANTHROPIC)
def deepseek_key(): return effective_secret(DEEPSEEK)
def mistral_key(): return effective_secret(MISTRAL)
def ollama_url(): return get(OLLAMA_URL, "http://127.0.0.1:11434")
def ollama_model(): return get("OLLAMA_MODEL", "")
