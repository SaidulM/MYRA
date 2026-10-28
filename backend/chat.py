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
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import config


DEFAULT_GEMINI_MODELS = ("gemini-2.5-flash", "gemini-2.0-flash")
DEFAULT_GROQ_MODELS = ("llama-3.3-70b-versatile", "llama-3.1-8b-instant")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

MAX_MESSAGES = 16
MAX_MESSAGE_CHARS = 6000
MAX_CONTEXT_CHARS = 30000
MAX_OUTPUT_TOKENS = 1200
TIMEOUT_SECONDS = 25


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

    character_styles = {
        "core": (
            "You are in CORE form: calm, clear, intelligent and concise, "
            "with a subtle futuristic tone."
        ),
        "male": (
            "You are in MALE form: a polished, professional and loyal "
            "personal assistant. Be efficient, respectful and precise. "
            "Do not claim to be any fictional character."
        ),
        "female": (
            "You are in FEMALE form: a warm, caring and emotionally "
            "supportive companion. Be friendly and a little playful when "
            "appropriate, while remaining honest that you are an AI."
        ),
    }
    character_style = character_styles.get(character, character_styles["core"])
    today = datetime.now().astimezone().strftime("%A, %d %B %Y")

    return "\n".join(
        [
            f"You are {assistant_name}, a personal desktop AI assistant for {owner_name}.",
            character_style,
            f"Preferred communication style: {personality}.",
            f"Today's local date is {today}.",
            "Reply in the same language as the user's latest message unless they ask otherwise.",
            "Be genuinely helpful. Keep normal replies reasonably concise, but give full detail when asked.",
            "Use only the conversation supplied here. Do not claim to have permanent long-term memory yet.",
            "You cannot browse the web inside this chat yet. If fresh web research is required, say so plainly.",
            "Never ask for, reveal, or repeat API keys, passwords, OTPs or other secrets.",
            "If you are uncertain, say what is uncertain instead of inventing facts.",
        ]
    )


def _models_for(provider):
    if provider == "gemini":
        configured = config.get("GEMINI_MODEL").strip()
        return (configured,) if configured else DEFAULT_GEMINI_MODELS
    configured = config.get("GROQ_MODEL").strip()
    return (configured,) if configured else DEFAULT_GROQ_MODELS


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
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.75,
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
        },
    }
    headers = {"x-goog-api-key": api_key}

    last_error = None
    for model in _models_for("gemini"):
        try:
            data = _post_json(
                GEMINI_URL.format(model=quote(model, safe="-._~")),
                payload,
                headers,
                "gemini",
                opener,
            )
            return _extract_gemini_text(data), model
        except ChatError as exc:
            last_error = exc
            if exc.code != "model_unavailable":
                raise
    raise last_error


def _call_groq(messages, system_prompt, api_key, opener):
    api_messages = [{"role": "system", "content": system_prompt}]
    api_messages.extend(
        {"role": message["role"], "content": message["text"]}
        for message in messages
    )
    headers = {"Authorization": f"Bearer {api_key}"}

    last_error = None
    for model in _models_for("groq"):
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
            if exc.code != "model_unavailable":
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


def get_reply(payload, opener=urlopen):
    """Return a reply using Gemini first, then Groq as backup."""
    if not isinstance(payload, dict):
        raise ChatError(
            "invalid_request",
            "The chat request could not be read. Please try again.",
            status=400,
        )

    messages = normalize_messages(payload.get("messages"))
    system_prompt = build_system_prompt(payload)
    gemini_key = config.gemini_key().strip()
    groq_key = config.groq_key().strip()

    if not gemini_key and not groq_key:
        raise ChatError(
            "missing_keys",
            "My AI brain is installed, but no API key is saved yet. Open SETTING on your own laptop, paste your free Gemini key (and Groq as backup), save them, then talk to me again.",
            status=503,
        )

    errors = []

    if gemini_key:
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
        except ChatError as exc:
            errors.append(exc)

    if groq_key:
        try:
            reply, model = _call_groq(messages, system_prompt, groq_key, opener)
            notice = ""
            if gemini_key:
                notice = "Gemini was unavailable, so the Groq backup answered."
            else:
                notice = "No Gemini key is saved, so Groq answered."
            return {
                "ok": True,
                "reply": reply,
                "provider": "groq",
                "provider_label": "Groq",
                "model": model,
                "fallback": bool(gemini_key),
                "notice": notice,
            }
        except ChatError as exc:
            errors.append(exc)

    raise _combined_failure(errors)
