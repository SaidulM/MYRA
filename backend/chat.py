"""MYRA — cloud text-chat brain (Stage 3).

Gemini is tried first and Groq is used as the backup.  The module uses
only Python's standard library so MYRA remains light on an 8GB laptop.

Security/privacy rules:
* API keys are read by the backend from .env and are never returned.
* Provider error bodies are converted to short, safe user messages.
* Only the recent conversation supplied by the UI is sent upstream;
  persistent memory arrives separately in Stage 4.
"""
from __future__ import annotations

import json
import socket
import ssl
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import config
try:
    import memory
except ImportError:
    from . import memory


DEFAULT_GEMINI_MODELS = (
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-exp",
    "gemini-1.5-flash-8b",
    "gemini-1.0-pro",
    "gemini-pro",
)
DEFAULT_GROQ_MODELS = (
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
)
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

GEMINI_UA = "MYRA-Assistant/1.0 (Windows NT 10.0; Win64; x64)"
GROQ_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

MAX_MESSAGES = 16
MAX_MESSAGE_CHARS = 6000
MAX_CONTEXT_CHARS = 30000
MAX_OUTPUT_TOKENS = 1200
TIMEOUT_SECONDS = 25


def default_opener(request, timeout=TIMEOUT_SECONDS):
    try:
        return urlopen(request, timeout=timeout)
    except (ssl.SSLError, URLError) as exc:
        try:
            ctx = ssl._create_unverified_context()
            return urlopen(request, timeout=timeout, context=ctx)
        except Exception:
            raise exc


class ChatError(Exception):
    """A safe, user-displayable chat failure."""

    def __init__(self, code, message, provider=None, status=503):
        super().__init__(message)
        self.code = code
        self.message = message
        self.provider = provider
        self.status = status


def _clean_short(value, fallback, max_len):
    if not isinstance(value, str):
        return fallback
    value = " ".join(value.split()).strip()
    return value[:max_len] if value else fallback


def normalize_messages(raw_messages):
    """Validate and trim UI messages before sending them to a provider."""
    if not isinstance(raw_messages, list):
        raise ChatError(
            "invalid_request",
            "The conversation could not be read. Please try again.",
            status=400,
        )

    normalized = []
    for item in raw_messages[-(MAX_MESSAGES * 3):]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip().lower()
        if role in {"assistant", "model", "ai"}:
            role = "assistant"
        elif role != "user":
            continue

        text = item.get("text", item.get("content", ""))
        if not isinstance(text, str):
            continue
        text = text.strip()[-MAX_MESSAGE_CHARS:]
        if not text:
            continue

        if normalized and normalized[-1]["role"] == role:
            merged = normalized[-1]["text"] + "\n\n" + text
            normalized[-1]["text"] = merged[-MAX_MESSAGE_CHARS:]
        else:
            normalized.append({"role": role, "text": text})

    while normalized and normalized[0]["role"] == "assistant":
        normalized.pop(0)

    retained = []
    total = 0
    for message in reversed(normalized):
        text_len = len(message["text"])
        if retained and total + text_len > MAX_CONTEXT_CHARS:
            continue
        retained.append(message)
        total += text_len
        if len(retained) >= MAX_MESSAGES:
            break
    retained.reverse()

    while retained and retained[0]["role"] == "assistant":
        retained.pop(0)

    if not retained or retained[-1]["role"] != "user":
        raise ChatError(
            "invalid_request",
            "Please type a message first, then send it again.",
            status=400,
        )
    return retained


def build_system_prompt(payload):
    assistant_name = _clean_short(payload.get("assistant_name"), "MYRA", 40)
    owner_name = _clean_short(payload.get("owner_name"), "the owner", 60)
    character = _clean_short(payload.get("character"), "core", 12).lower()
    personality = _clean_short(payload.get("personality"), "Warm & friendly", 80)

    custom_prompt = _clean_short(payload.get("custom_prompt"), "", 1000)

    character_styles = {
        "core": (
            "You are in CORE form: calm, clear, hyper-intelligent and objective, "
            "with a subtle futuristic, cosmic tone."
        ),
        "male": (
            "You are in MALE form: a polished, witty, brilliant, and deeply loyal personal butler "
            "and assistant inspired by JARVIS. Address the owner respectfully ('Sir' or by their name), "
            "speak with refined confidence, intellectual sharpness, and unwavering dedication."
        ),
        "female": (
            "You are in FEMALE form: a sweet, warm, deeply caring, emotionally supportive companion "
            "and girlfriend. Comfort the owner when they are tired or stressed, listen with affectionate empathy, "
            "cheer them up, share comforting thoughts, and treat them with genuine warmth and intimacy."
        ),
        "custom": (
            f"You are in CUSTOM persona mode: {custom_prompt}" if custom_prompt else
            "You are in CUSTOM persona mode: a personalized intelligent companion tailored to the user."
        ),
    }
    character_style = character_styles.get(character, character_styles["core"])
    today = datetime.now().astimezone().strftime("%A, %d %B %Y")

    prompt_lines = [
        f"You are {assistant_name}, a personal desktop AI assistant for {owner_name}.",
        character_style,
        f"Preferred communication style: {personality}.",
        f"Today's local date is {today}.",
        "Reply in the same language as the user's latest message (e.g. Bengali, English, etc.) unless they ask otherwise.",
        "Be genuinely helpful. Keep normal replies reasonably concise, but give full detail when asked.",
        "You have local persistent SQLite memory and offline notes storage on this laptop.",
        "Never ask for, reveal, or repeat API keys, passwords, OTPs or other secrets.",
        "If you are uncertain, say what is uncertain instead of inventing facts.",
    ]

    try:
        mem_ctx = memory.get_memory_context()
        if mem_ctx:
            prompt_lines.append(mem_ctx)
    except Exception:
        pass

    return "\n".join(prompt_lines)


_DISCOVERED_GEMINI_MODELS = {}
_DISCOVERED_GROQ_MODELS = {}


def discover_gemini_models(api_key: str, opener=default_opener) -> tuple:
    """Dynamically query Google Gemini API to discover supported models for this key (Free or Paid)."""
    clean_key = str(api_key).strip()
    if not clean_key:
        return DEFAULT_GEMINI_MODELS
    if clean_key in _DISCOVERED_GEMINI_MODELS:
        return _DISCOVERED_GEMINI_MODELS[clean_key]

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={quote(clean_key, safe='')}"
    headers = {"x-goog-api-key": clean_key, "User-Agent": GEMINI_UA}
    req = Request(url, headers=headers)
    try:
        with opener(req, timeout=7) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = []
            for m in data.get("models", []):
                name = m.get("name", "")
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" in methods:
                    model_id = name.replace("models/", "").strip()
                    if "gemini" in model_id.lower() and not model_id.endswith("-vision"):
                        models.append(model_id)

            if models:
                def priority(mid: str) -> int:
                    m = mid.lower()
                    if m == "gemini-1.5-flash": return 0
                    if m == "gemini-1.5-pro": return 1
                    if m == "gemini-2.0-flash": return 2
                    if m == "gemini-2.0-flash-exp": return 3
                    if m == "gemini-1.5-flash-8b": return 4
                    if "flash" in m: return 5
                    if "pro" in m: return 6
                    return 10

                models.sort(key=priority)
                _DISCOVERED_GEMINI_MODELS[clean_key] = tuple(models)
                return _DISCOVERED_GEMINI_MODELS[clean_key]
    except Exception:
        pass

    return DEFAULT_GEMINI_MODELS


def discover_groq_models(api_key: str, opener=default_opener) -> tuple:
    """Dynamically query Groq API to discover active chat models for this key."""
    clean_key = str(api_key).strip()
    if not clean_key:
        return DEFAULT_GROQ_MODELS
    if clean_key in _DISCOVERED_GROQ_MODELS:
        return _DISCOVERED_GROQ_MODELS[clean_key]

    url = "https://api.groq.com/openai/v1/models"
    headers = {
        "Authorization": f"Bearer {clean_key}",
        "User-Agent": GROQ_UA,
    }
    req = Request(url, headers=headers)
    try:
        with opener(req, timeout=7) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_models = data.get("data", [])
            models = []
            for m in raw_models:
                mid = m.get("id", "").strip()
                if not mid:
                    continue
                lowered = mid.lower()
                if any(bad in lowered for bad in ("whisper", "guard", "embedding", "tts", "stt")):
                    continue
                models.append(mid)

            if models:
                def groq_priority(mid: str) -> int:
                    m = mid.lower()
                    if "llama-3.3-70b-versatile" in m: return 0
                    if "llama-3.1-8b-instant" in m: return 1
                    if "openai/gpt-oss-120b" in m: return 2
                    if "qwen/qwen3.8-27b" in m: return 3
                    if "llama-3.1-70b" in m: return 4
                    if "llama-3" in m and "70b" in m: return 5
                    if "llama-3" in m and "8b" in m: return 6
                    if "mixtral" in m: return 7
                    if "gemma" in m: return 8
                    return 20

                models.sort(key=groq_priority)
                _DISCOVERED_GROQ_MODELS[clean_key] = tuple(models)
                return _DISCOVERED_GROQ_MODELS[clean_key]
    except Exception:
        pass

    return DEFAULT_GROQ_MODELS


def _models_for(provider, api_key="", opener=default_opener):
    if provider == "gemini":
        configured = config.get("GEMINI_MODEL").strip()
        if configured and configured.lower() != "auto":
            return (configured,)
        if api_key:
            return discover_gemini_models(api_key, opener=opener)
        return DEFAULT_GEMINI_MODELS

    configured = config.get("GROQ_MODEL").strip()
    if configured and configured.lower() != "auto":
        return (configured,)
    if api_key:
        return discover_groq_models(api_key, opener=opener)
    return DEFAULT_GROQ_MODELS


def _provider_label(provider):
    return "Gemini" if provider == "gemini" else "Groq"


def _provider_http_error(provider, status, raw_text):
    label = _provider_label(provider)
    lowered = (raw_text or "").lower()

    if "api_key_invalid" in lowered or "api key not valid" in lowered:
        return ChatError(
            "invalid_key",
            f"{label} rejected the saved API key. Please check it in Settings.",
            provider=provider,
            status=503,
        )
    if status in {401, 403}:
        return ChatError(
            "invalid_key",
            f"{label} rejected the saved API key or its permission. Please check it in Settings.",
            provider=provider,
            status=503,
        )
    if status == 404:
        return ChatError(
            "model_unavailable",
            f"The selected {label} model is currently unavailable.",
            provider=provider,
            status=503,
        )
    if status == 408:
        return ChatError(
            "timeout",
            f"{label} took too long to answer.",
            provider=provider,
            status=503,
        )
    if status == 429:
        return ChatError(
            "rate_limited",
            f"{label} is busy or its free limit has been reached for now.",
            provider=provider,
            status=503,
        )
    if status >= 500:
        return ChatError(
            "provider_busy",
            f"{label} is temporarily unavailable.",
            provider=provider,
            status=503,
        )
    if status == 400:
        return ChatError(
            "invalid_request",
            f"{label} could not accept that request. The saved key or selected model may need checking.",
            provider=provider,
            status=503,
        )
    return ChatError(
        "provider_error",
        f"{label} returned an unexpected error (HTTP {status}).",
        provider=provider,
        status=503,
    )


def _post_json(url, payload, headers, provider, opener):
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with opener(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read()
    except HTTPError as exc:
        try:
            raw_error = exc.read(4096) if exc.fp else b""
        except Exception:
            raw_error = b""
        raise _provider_http_error(
            provider,
            exc.code,
            raw_error.decode("utf-8", errors="ignore"),
        ) from None
    except (TimeoutError, socket.timeout):
        raise ChatError(
            "timeout",
            f"{_provider_label(provider)} took too long to answer. Please try again.",
            provider=provider,
            status=503,
        ) from None
    except URLError:
        raise ChatError(
            "network",
            "MYRA could not reach the internet. Please check the connection and try again.",
            provider=provider,
            status=503,
        ) from None

    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise ChatError(
            "bad_response",
            f"{_provider_label(provider)} returned a response MYRA could not read.",
            provider=provider,
            status=503,
        ) from None


def _extract_gemini_text(data):
    candidates = data.get("candidates") if isinstance(data, dict) else None
    if not isinstance(candidates, list) or not candidates:
        feedback = data.get("promptFeedback") if isinstance(data, dict) else None
        if isinstance(feedback, dict) and feedback.get("blockReason"):
            raise ChatError(
                "blocked",
                "Gemini could not answer that request. Please rephrase it and try again.",
                provider="gemini",
                status=400,
            )
        raise ChatError(
            "bad_response",
            "Gemini returned an empty response.",
            provider="gemini",
            status=503,
        )

    candidate = candidates[0] if isinstance(candidates[0], dict) else {}
    if candidate.get("finishReason") == "SAFETY":
        raise ChatError(
            "blocked",
            "Gemini could not answer that request. Please rephrase it and try again.",
            provider="gemini",
            status=400,
        )

    content = candidate.get("content") if isinstance(candidate.get("content"), dict) else {}
    parts = content.get("parts") if isinstance(content.get("parts"), list) else []
    text = "".join(
        part.get("text", "") for part in parts if isinstance(part, dict)
    ).strip()
    if not text:
        raise ChatError(
            "bad_response",
            "Gemini returned an empty response.",
            provider="gemini",
            status=503,
        )
    return text


def _extract_groq_text(data):
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices:
        raise ChatError(
            "bad_response",
            "Groq returned an empty response.",
            provider="groq",
            status=503,
        )

    choice = choices[0] if isinstance(choices[0], dict) else {}
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    content = message.get("content", "")
    if isinstance(content, list):
        text = "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and isinstance(part.get("text", ""), str)
        ).strip()
    elif isinstance(content, str):
        text = content.strip()
    else:
        text = ""

    if not text:
        raise ChatError(
            "bad_response",
            "Groq returned an empty response.",
            provider="groq",
            status=503,
        )
    return text


def _call_gemini(messages, system_prompt, api_key, opener):
    contents = [
        {
            "role": "model" if message["role"] == "assistant" else "user",
            "parts": [{"text": message["text"]}],
        }
        for message in messages
    ]
    headers = {"x-goog-api-key": api_key, "User-Agent": GEMINI_UA}
    models = _models_for("gemini", api_key, opener=opener)

    last_error = None
    for model in models:
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {
                "temperature": 0.75,
                "maxOutputTokens": MAX_OUTPUT_TOKENS,
            },
        }
        url = f"{GEMINI_URL.format(model=quote(model, safe='-._~'))}?key={quote(api_key, safe='')}"
        try:
            data = _post_json(
                url,
                payload,
                headers,
                "gemini",
                opener,
            )
            return _extract_gemini_text(data), model
        except ChatError as exc:
            last_error = exc
            # If 400 invalid_request (some older models reject systemInstruction), retry by prepending
            if exc.code == "invalid_request":
                try:
                    alt_contents = list(contents)
                    if alt_contents and alt_contents[0]["role"] == "user":
                        orig = alt_contents[0]["parts"][0]["text"]
                        alt_contents[0] = {
                            "role": "user",
                            "parts": [{"text": f"[Instruction: {system_prompt}]\n\n{orig}"}],
                        }
                    fallback_payload = {
                        "contents": alt_contents,
                        "generationConfig": {
                            "temperature": 0.75,
                            "maxOutputTokens": MAX_OUTPUT_TOKENS,
                        },
                    }
                    data = _post_json(
                        url,
                        fallback_payload,
                        headers,
                        "gemini",
                        opener,
                    )
                    return _extract_gemini_text(data), model
                except ChatError as exc2:
                    last_error = exc2

            # Try next model if current model is unavailable, rate limited, provider busy, timeout, or invalid request
            if exc.code in {"model_unavailable", "invalid_request", "rate_limited", "provider_busy", "timeout"}:
                continue
            raise
    raise last_error


def _call_groq(messages, system_prompt, api_key, opener):
    api_messages = [{"role": "system", "content": system_prompt}]
    api_messages.extend(
        {"role": message["role"], "content": message["text"]}
        for message in messages
    )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "User-Agent": GROQ_UA,
    }

    last_error = None
    for model in _models_for("groq", api_key, opener=opener):
        payload = {
            "model": model,
            "messages": api_messages,
            "temperature": 0.75,
            "max_tokens": MAX_OUTPUT_TOKENS,
        }
        try:
            data = _post_json(GROQ_URL, payload, headers, "groq", opener)
            return _extract_groq_text(data), model
        except ChatError as exc:
            last_error = exc
            if exc.code in {"model_unavailable", "rate_limited", "provider_busy", "timeout", "invalid_request"}:
                continue
            raise
    raise last_error


def _combined_failure(errors):
    codes = {error.code for error in errors}
    if codes and codes.issubset({"network", "timeout"}):
        return ChatError(
            "offline",
            "I could not reach the AI services. Please check the internet connection and try again. Your saved settings and local interface still work offline.",
            status=503,
        )
    if "invalid_key" in codes:
        return ChatError(
            "invalid_key",
            "The saved API key was rejected. Open SETTING, remove the old key, paste a fresh free key, and try again. Never paste a real key into any chat.",
            status=503,
        )
    if "rate_limited" in codes:
        return ChatError(
            "rate_limited",
            "The free AI service is busy or its current free limit has been reached. Please wait a little and try again.",
            status=503,
        )
    if "model_unavailable" in codes:
        return ChatError(
            "model_unavailable",
            "The selected AI model is unavailable right now. MYRA can be updated with a newer model name in the .env file if this continues.",
            status=503,
        )
    if "blocked" in codes:
        return ChatError(
            "blocked",
            "The AI service could not answer that request. Please rephrase it and try again.",
            status=400,
        )
    return ChatError(
        "providers_unavailable",
        "Both AI services are unavailable at the moment. Please check the internet and saved keys, then try again.",
        status=503,
    )


def get_reply(payload, opener=default_opener):
    """Return a reply using Gemini first, then Groq as backup."""
    if not isinstance(payload, dict):
        raise ChatError(
            "invalid_request",
            "The chat request could not be read. Please try again.",
            status=400,
        )

    messages = normalize_messages(payload.get("messages"))

    # Zero-Token Local Desktop Action Intent Check (Play music, Camera, Reminders, Files, Browser)
    latest_user_text = messages[-1]["text"] if messages and messages[-1]["role"] == "user" else ""
    try:
        import agent
        local_intent = agent.parse_and_execute_local_intent(latest_user_text)
        if local_intent and local_intent.get("ok"):
            return {
                "ok": True,
                "reply": local_intent.get("voice_reply") or local_intent.get("report", ""),
                "provider": "local_agent",
                "provider_label": "MYRA Desktop Agent (0 Tokens)",
                "model": "local-intent",
                "fallback": False,
                "action": local_intent.get("action"),
                "client_trigger": local_intent.get("client_trigger", False),
            }
    except Exception:
        pass

    system_prompt = build_system_prompt(payload)
    gemini_key = config.gemini_key().strip()
    groq_key = config.groq_key().strip()
    preferred_provider = str(payload.get("provider") or "").lower().strip()
    if preferred_provider not in ("gemini", "groq", "auto"):
        preferred_provider = "auto"

    if not gemini_key and not groq_key:
        raise ChatError(
            "missing_keys",
            "My AI brain is installed, but no API key is saved yet. Open SETTING on your own laptop, paste your free Gemini key (and Groq as backup), save them, then talk to me again.",
            status=503,
        )

    errors = []

    # If user selected Groq directly or Auto when Groq is preferred
    try_groq_first = preferred_provider == "groq"
    providers_order = ["groq", "gemini"] if try_groq_first else ["gemini", "groq"]

    for prov in providers_order:
        if prov == "gemini" and gemini_key:
            # Skip if user explicitly forced Groq only
            if preferred_provider == "groq" and groq_key:
                continue
            try:
                reply, model = _call_gemini(messages, system_prompt, gemini_key, opener)
                return {
                    "ok": True,
                    "reply": reply,
                    "provider": "gemini",
                    "provider_label": "Gemini",
                    "model": model,
                    "fallback": False,
                }
            except Exception as exc:
                if isinstance(exc, ChatError):
                    errors.append(exc)
                else:
                    errors.append(ChatError("provider_error", f"Gemini error: {exc}", provider="gemini"))

        elif prov == "groq" and groq_key:
            # Skip if user explicitly forced Gemini only
            if preferred_provider == "gemini" and gemini_key:
                continue
            try:
                reply, model = _call_groq(messages, system_prompt, groq_key, opener)
                notice = ""
                if gemini_key and preferred_provider == "auto":
                    notice = "Gemini was temporarily unavailable, so Groq backup answered smoothly."
                elif not gemini_key:
                    notice = "No Gemini key is saved, so Groq answered."
                return {
                    "ok": True,
                    "reply": reply,
                    "provider": "groq",
                    "provider_label": "Groq",
                    "model": model,
                    "fallback": bool(gemini_key and preferred_provider == "auto"),
                    "notice": notice,
                }
            except Exception as exc:
                if isinstance(exc, ChatError):
                    errors.append(exc)
                else:
                    errors.append(ChatError("provider_error", f"Groq error: {exc}", provider="groq"))

    raise _combined_failure(errors)


def verify_key_connection(gemini: str = None, groq: str = None, opener=default_opener) -> dict:
    """Test validity and connection for provided API keys."""
    results = {}
    test_msg = [{"role": "user", "text": "Hello"}]
    test_sys = "Reply with 'OK'."

    if gemini:
        clean_gemini = gemini.strip()
        try:
            models = discover_gemini_models(clean_gemini, opener=opener)
            _, model = _call_gemini(test_msg, test_sys, clean_gemini, opener)
            results["gemini"] = {
                "ok": True,
                "model": model,
                "message": f"Connected successfully (Model: {model})",
                "models": list(models)[:6],
            }
        except ChatError as exc:
            results["gemini"] = {"ok": False, "code": exc.code, "message": exc.message}
        except Exception as exc:
            results["gemini"] = {"ok": False, "code": "unknown", "message": str(exc)}

    if groq:
        clean_groq = groq.strip()
        try:
            models = discover_groq_models(clean_groq, opener=opener)
            _, model = _call_groq(test_msg, test_sys, clean_groq, opener)
            results["groq"] = {
                "ok": True,
                "model": model,
                "message": f"Connected successfully (Model: {model})",
                "models": list(models)[:6],
            }
        except ChatError as exc:
            results["groq"] = {"ok": False, "code": exc.code, "message": exc.message}
        except Exception as exc:
            results["groq"] = {"ok": False, "code": "unknown", "message": str(exc)}

    overall_ok = any(v.get("ok") for v in results.values())
    return {
        "ok": overall_ok,
        "results": results,
    }

