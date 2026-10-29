"""MYRA — local settings & API keys (Stage 2 + Extended Multi-Brain Provider).

Reads and writes the `.env` file at the repo root using only the
Python standard library. Security rules:

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

# Provider Key Names
GEMINI = "GEMINI_API_KEY"
GROQ = "GROQ_API_KEY"
OPENROUTER = "OPENROUTER_API_KEY"
OPENAI = "OPENAI_API_KEY"
ANTHROPIC = "ANTHROPIC_API_KEY"
DEEPSEEK = "DEEPSEEK_API_KEY"
MISTRAL = "MISTRAL_API_KEY"
OLLAMA_URL = "OLLAMA_URL"


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
    openrouter = env.get(OPENROUTER, "")
    openai = env.get(OPENAI, "")
    anthropic = env.get(ANTHROPIC, "")
    deepseek = env.get(DEEPSEEK, "")
    mistral = env.get(MISTRAL, "")
    ollama_url = env.get(OLLAMA_URL, "http://127.0.0.1:11434")

    return {
        "gemini": {"set": bool(gemini), "masked": _mask(gemini), "model": env.get("GEMINI_MODEL", "auto")},
        "groq": {"set": bool(groq), "masked": _mask(groq), "model": env.get("GROQ_MODEL", "auto")},
        "openrouter": {"set": bool(openrouter), "masked": _mask(openrouter), "model": env.get("OPENROUTER_MODEL", "auto")},
        "openai": {"set": bool(openai), "masked": _mask(openai), "model": env.get("OPENAI_MODEL", "gpt-4o-mini")},
        "anthropic": {"set": bool(anthropic), "masked": _mask(anthropic), "model": env.get("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")},
        "deepseek": {"set": bool(deepseek), "masked": _mask(deepseek), "model": env.get("DEEPSEEK_MODEL", "deepseek-chat")},
        "mistral": {"set": bool(mistral), "masked": _mask(mistral), "model": env.get("MISTRAL_MODEL", "mistral-small-latest")},
        "ollama": {"set": bool(env.get("OLLAMA_MODEL")), "url": ollama_url, "model": env.get("OLLAMA_MODEL", "")},
    }


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
    """Update .env in place with any supported provider keys."""
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


# Accessors used across backend
def gemini_key(): return get(GEMINI)
def groq_key(): return get(GROQ)
def openrouter_key(): return get(OPENROUTER)
def openai_key(): return get(OPENAI)
def anthropic_key(): return get(ANTHROPIC)
def deepseek_key(): return get(DEEPSEEK)
def mistral_key(): return get(MISTRAL)
def ollama_url(): return get(OLLAMA_URL, "http://127.0.0.1:11434")
def ollama_model(): return get("OLLAMA_MODEL", "")
