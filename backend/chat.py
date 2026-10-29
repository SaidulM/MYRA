"""MYRA — Multi-Brain AI Orchestration Engine.

Supports Free & Paid Providers with Dynamic Model Discovery:
1. Google Gemini (Free & Paid, dynamic discovery, Multimodal Vision)
2. Groq (Free fast inference)
3. OpenRouter (Free tier models + Paid models, OpenAI format)
4. OpenAI (GPT-4o, GPT-4o-mini, Vision)
5. Anthropic Claude (Claude 3.5 Sonnet, Claude 3.5 Haiku)
6. DeepSeek (deepseek-chat, deepseek-reasoner)
7. Mistral AI (mistral-small, mistral-large)
8. Ollama / Local AI (Zero API keys, 100% private localhost)

Security/privacy rules:
* API keys are read by the backend from .env and are never returned.
* Only the recent conversation supplied by the UI is sent upstream.
* Persistent SQLite memory is preserved locally on this PC.
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
DEFAULT_OPENROUTER_MODELS = (
    "meta-llama/llama-3.2-3b-instruct:free",
    "google/gemini-2.0-flash-exp:free",
    "deepseek/deepseek-r1:free",
    "mistralai/mistral-7b-instruct:free",
    "meta-llama/llama-3.3-70b-instruct",
    "openai/gpt-4o-mini",
)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

UA_STRING = "MYRA-Assistant/1.0 (Windows NT 10.0; Win64; x64)"

MAX_MESSAGES = 16
MAX_MESSAGE_CHARS = 6000
MAX_CONTEXT_CHARS = 30000
MAX_OUTPUT_TOKENS = 1200
TIMEOUT_SECONDS = 25


def default_opener(request, timeout=TIMEOUT_SECONDS):
    try:
        return urlopen(request, timeout=timeout)
    except (ssl.SSLError, URLError):
        ctx = ssl._create_unverified_context()
        return urlopen(request, timeout=timeout, context=ctx)


class ChatError(Exception):
    def __init__(self, code, message, provider=None, status=500):
        super().__init__(message)
        self.code = code
        self.message = message
        self.provider = provider
        self.status = status

    def to_dict(self):
        body = {"ok": False, "error": self.code, "message": self.message}
        if self.provider:
            body["provider"] = self.provider
        return body


def _clean_short(value, default, max_len=60):
    if not isinstance(value, str):
        return default
    cleaned = " ".join(value.split()).strip()
    return cleaned[:max_len] if cleaned else default


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
    owner_name = _clean_short(payload.get("owner_name"), "Saidul", 60)
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
        "Be genuinely helpful, intelligent and empathetic. Keep normal speech replies natural and concise.",
        "When an image or webcam/screen frame is attached, inspect it carefully and answer questions about what is seen (objects in hand, text, screens).",
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
    clean_key = str(api_key).strip()
    if not clean_key:
        return DEFAULT_GEMINI_MODELS
    if clean_key in _DISCOVERED_GEMINI_MODELS:
        return _DISCOVERED_GEMINI_MODELS[clean_key]

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={quote(clean_key, safe='')}"
    headers = {"x-goog-api-key": clean_key, "User-Agent": UA_STRING}
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
                    if m == "gemini-2.0-flash": return 1
                    if m == "gemini-1.5-pro": return 2
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
    clean_key = str(api_key).strip()
    if not clean_key:
        return DEFAULT_GROQ_MODELS
    if clean_key in _DISCOVERED_GROQ_MODELS:
        return _DISCOVERED_GROQ_MODELS[clean_key]

    url = "https://api.groq.com/openai/v1/models"
    headers = {"Authorization": f"Bearer {clean_key}", "User-Agent": UA_STRING}
    req = Request(url, headers=headers)
    try:
        with opener(req, timeout=7) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw_models = data.get("data", [])
            models = []
            for m in raw_models:
                mid = m.get("id", "").strip()
                if not mid: continue
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
    labels = {
        "gemini": "Google Gemini",
        "groq": "Groq",
        "openrouter": "OpenRouter",
        "openai": "OpenAI",
        "anthropic": "Anthropic Claude",
        "deepseek": "DeepSeek",
        "mistral": "Mistral AI",
        "ollama": "Ollama Local",
    }
    return labels.get(provider, provider.capitalize())


def _provider_http_error(provider, status, raw_text):
    label = _provider_label(provider)
    lowered = (raw_text or "").lower()

    if "api_key_invalid" in lowered or "api key not valid" in lowered:
        return ChatError("invalid_key", f"{label} rejected the saved API key. Please check it in Settings.", provider=provider, status=503)
    if status in {401, 403}:
        return ChatError("invalid_key", f"{label} rejected the saved API key or authentication. Check key in Settings.", provider=provider, status=503)
    if status == 404:
        return ChatError("model_unavailable", f"The selected {label} model is unavailable.", provider=provider, status=503)
    if status == 408:
        return ChatError("timeout", f"{label} took too long to answer.", provider=provider, status=503)
    if status == 429:
        return ChatError("rate_limited", f"{label} is busy or rate limit reached. Please wait a moment.", provider=provider, status=503)
    if status >= 500:
        return ChatError("provider_busy", f"{label} service is temporarily unavailable.", provider=provider, status=503)
    if status == 400:
        return ChatError("invalid_request", f"{label} request error: {lowered[:120]}", provider=provider, status=503)
    return ChatError("provider_error", f"{label} error (HTTP {status}).", provider=provider, status=503)


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
        raise _provider_http_error(provider, exc.code, raw_error.decode("utf-8", errors="ignore")) from None
    except (TimeoutError, socket.timeout):
        raise ChatError("timeout", f"{_provider_label(provider)} took too long to answer.", provider=provider, status=503) from None
    except URLError:
        raise ChatError("network", f"Could not reach {provider}. Check internet connection.", provider=provider, status=503) from None

    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise ChatError("bad_response", f"{_provider_label(provider)} returned invalid response.", provider=provider, status=503) from None


def _extract_gemini_text(data):
    candidates = data.get("candidates") if isinstance(data, dict) else None
    if not isinstance(candidates, list) or not candidates:
        feedback = data.get("promptFeedback") if isinstance(data, dict) else None
        if isinstance(feedback, dict) and feedback.get("blockReason"):
            raise ChatError("blocked", "Gemini filtered that request.", provider="gemini", status=400)
        raise ChatError("bad_response", "Gemini returned an empty response.", provider="gemini", status=503)

    candidate = candidates[0] if isinstance(candidates[0], dict) else {}
    if candidate.get("finishReason") == "SAFETY":
        raise ChatError("blocked", "Gemini filtered that request for safety.", provider="gemini", status=400)

    content = candidate.get("content") if isinstance(candidate.get("content"), dict) else {}
    parts = content.get("parts") if isinstance(content.get("parts"), list) else []
    text = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
    if not text:
        raise ChatError("bad_response", "Gemini returned an empty response.", provider="gemini", status=503)
    return text


def _extract_openai_text(data, provider="openai"):
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices:
        raise ChatError("bad_response", f"{_provider_label(provider)} returned empty response.", provider=provider, status=503)

    choice = choices[0] if isinstance(choices[0], dict) else {}
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    content = message.get("content", "")
    if isinstance(content, list):
        text = "".join(p.get("text", "") for p in content if isinstance(p, dict) and isinstance(p.get("text"), str)).strip()
    elif isinstance(content, str):
        text = content.strip()
    else:
        text = ""

    if not text:
        raise ChatError("bad_response", f"{_provider_label(provider)} returned empty response.", provider=provider, status=503)
    return text


def _call_gemini(messages, system_prompt, api_key, opener, image=None):
    contents = []
    for i, msg in enumerate(messages):
        is_user = msg["role"] == "user"
        parts = [{"text": msg["text"]}]

        # Multimodal Vision injection into the latest user message
        if is_user and i == len(messages) - 1 and image:
            clean_b64 = image.split(",")[-1] if "," in image else image
            parts.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": clean_b64.strip(),
                }
            })

        contents.append({
            "role": "user" if is_user else "model",
            "parts": parts,
        })

    headers = {"x-goog-api-key": api_key, "User-Agent": UA_STRING}
    models = _models_for("gemini", api_key, opener=opener)

    last_error = None
    for model in models:
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.75, "maxOutputTokens": MAX_OUTPUT_TOKENS},
        }
        url = f"{GEMINI_URL.format(model=quote(model, safe='-._~'))}?key={quote(api_key, safe='')}"
        try:
            data = _post_json(url, payload, headers, "gemini", opener)
            return _extract_gemini_text(data), model
        except ChatError as exc:
            last_error = exc
            if exc.code == "invalid_request":
                # Fallback for older model syntax
                try:
                    alt_contents = list(contents)
                    if alt_contents and alt_contents[0]["role"] == "user":
                        orig = alt_contents[0]["parts"][0].get("text", "")
                        alt_contents[0]["parts"][0]["text"] = f"[Instruction: {system_prompt}]\n\n{orig}"
                    data = _post_json(url, {"contents": alt_contents, "generationConfig": {"temperature": 0.75}}, headers, "gemini", opener)
                    return _extract_gemini_text(data), model
                except Exception:
                    pass
            if exc.code in {"model_unavailable", "invalid_request", "rate_limited", "provider_busy", "timeout"}:
                continue
            raise
    raise last_error


def _call_openai_compatible(messages, system_prompt, api_key, endpoint_url, models, provider, opener, image=None):
    headers = {"User-Agent": UA_STRING}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://github.com/SaidulM/MYRA"
        headers["X-Title"] = "MYRA Desktop Assistant"

    api_messages = [{"role": "system", "content": system_prompt}]
    for i, msg in enumerate(messages):
        is_user = msg["role"] == "user"
        if is_user and i == len(messages) - 1 and image:
            clean_b64 = image if image.startswith("data:") else f"data:image/jpeg;base64,{image}"
            api_messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": msg["text"]},
                    {"type": "image_url", "image_url": {"url": clean_b64}},
                ],
            })
        else:
            api_messages.append({"role": msg["role"], "content": msg["text"]})

    last_error = None
    for model in models:
        payload = {
            "model": model,
            "messages": api_messages,
            "temperature": 0.75,
            "max_tokens": MAX_OUTPUT_TOKENS,
        }
        try:
            data = _post_json(endpoint_url, payload, headers, provider, opener)
            return _extract_openai_text(data, provider=provider), model
        except ChatError as exc:
            last_error = exc
            if exc.code in {"model_unavailable", "rate_limited", "provider_busy", "timeout", "invalid_request"}:
                continue
            raise
    raise last_error or ChatError("provider_error", f"Could not connect to {provider}", provider=provider)


def _combined_failure(errors):
    codes = {error.code for error in errors if isinstance(error, ChatError)}
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
    """Orchestrate multi-brain intelligence with vision, memory auto-learning, and zero-token local execution."""
    if not isinstance(payload, dict):
        raise ChatError("invalid_request", "The chat request could not be read. Please try again.", status=400)

    messages = normalize_messages(payload.get("messages"))
    image = payload.get("image")  # base64 webcam / screen snapshot if active

    # Zero-Token Local Desktop Action Intent Check (Play music, Gold rate, Shopping, Camera, Reminders, Files, Browser)
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

    # Automatic Persistent Memory Extraction from chat
    learned_fact = None
    try:
        learned_fact = memory.auto_learn_from_text(latest_user_text)
    except Exception:
        pass

    system_prompt = build_system_prompt(payload)

    # Load provider keys
    gemini_k = config.gemini_key().strip()
    groq_k = config.groq_key().strip()
    openrouter_k = config.openrouter_key().strip()
    openai_k = config.openai_key().strip()
    deepseek_k = config.deepseek_key().strip()
    mistral_k = config.mistral_key().strip()
    ollama_m = config.ollama_model().strip()

    preferred_provider = str(payload.get("provider") or "auto").lower().strip()

    # Determine order of provider execution
    providers = []
    if preferred_provider != "auto":
        providers.append(preferred_provider)
    # Default priority waterfall
    for p in ["gemini", "groq", "openrouter", "openai", "deepseek", "mistral", "ollama"]:
        if p not in providers:
            providers.append(p)

    has_any_key = bool(gemini_k or groq_k or openrouter_k or openai_k or deepseek_k or mistral_k or ollama_m)
    if not has_any_key:
        raise ChatError(
            "missing_keys",
            "My AI brain is installed, but no API key is saved yet. Open SETTING on your laptop, paste your free Gemini or Groq or OpenRouter key, save them, then talk to me again.",
            status=503,
        )

    errors = []

    for prov in providers:
        if prov == "gemini" and gemini_k:
            try:
                reply, model = _call_gemini(messages, system_prompt, gemini_k, opener, image=image)
                return {
                    "ok": True,
                    "reply": reply,
                    "provider": "gemini",
                    "provider_label": "Google Gemini",
                    "model": model,
                    "fallback": False,
                    "memory_learned": learned_fact,
                }
            except Exception as exc:
                errors.append(exc if isinstance(exc, ChatError) else ChatError("provider_error", str(exc), provider="gemini"))

        elif prov == "groq" and groq_k:
            try:
                models = _models_for("groq", groq_k, opener=opener)
                reply, model = _call_openai_compatible(messages, system_prompt, groq_k, GROQ_URL, models, "groq", opener, image=image)
                notice = ""
                if gemini_k and preferred_provider == "auto":
                    notice = "Gemini was temporarily unavailable, so Groq backup answered smoothly."
                elif not gemini_k:
                    notice = "No Gemini key is saved, so Groq answered."
                return {
                    "ok": True,
                    "reply": reply,
                    "provider": "groq",
                    "provider_label": "Groq",
                    "model": model,
                    "fallback": bool(gemini_k and preferred_provider == "auto"),
                    "notice": notice,
                    "memory_learned": learned_fact,
                }
            except Exception as exc:
                errors.append(exc if isinstance(exc, ChatError) else ChatError("provider_error", str(exc), provider="groq"))

        elif prov == "openrouter" and openrouter_k:
            try:
                conf_model = config.get("OPENROUTER_MODEL", "auto").strip()
                models = (conf_model,) if conf_model and conf_model != "auto" else DEFAULT_OPENROUTER_MODELS
                reply, model = _call_openai_compatible(messages, system_prompt, openrouter_k, OPENROUTER_URL, models, "openrouter", opener, image=image)
                return {
                    "ok": True,
                    "reply": reply,
                    "provider": "openrouter",
                    "provider_label": "OpenRouter",
                    "model": model,
                    "fallback": False,
                    "memory_learned": learned_fact,
                }
            except Exception as exc:
                errors.append(exc if isinstance(exc, ChatError) else ChatError("provider_error", str(exc), provider="openrouter"))

        elif prov == "openai" and openai_k:
            try:
                conf_model = config.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
                reply, model = _call_openai_compatible(messages, system_prompt, openai_k, OPENAI_URL, (conf_model,), "openai", opener, image=image)
                return {
                    "ok": True,
                    "reply": reply,
                    "provider": "openai",
                    "provider_label": "OpenAI ChatGPT",
                    "model": model,
                    "fallback": False,
                    "memory_learned": learned_fact,
                }
            except Exception as exc:
                errors.append(exc if isinstance(exc, ChatError) else ChatError("provider_error", str(exc), provider="openai"))

        elif prov == "deepseek" and deepseek_k:
            try:
                conf_model = config.get("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat"
                reply, model = _call_openai_compatible(messages, system_prompt, deepseek_k, DEEPSEEK_URL, (conf_model,), "deepseek", opener)
                return {
                    "ok": True,
                    "reply": reply,
                    "provider": "deepseek",
                    "provider_label": "DeepSeek",
                    "model": model,
                    "fallback": False,
                    "memory_learned": learned_fact,
                }
            except Exception as exc:
                errors.append(exc if isinstance(exc, ChatError) else ChatError("provider_error", str(exc), provider="deepseek"))

        elif prov == "mistral" and mistral_k:
            try:
                conf_model = config.get("MISTRAL_MODEL", "mistral-small-latest").strip() or "mistral-small-latest"
                reply, model = _call_openai_compatible(messages, system_prompt, mistral_k, MISTRAL_URL, (conf_model,), "mistral", opener)
                return {
                    "ok": True,
                    "reply": reply,
                    "provider": "mistral",
                    "provider_label": "Mistral AI",
                    "model": model,
                    "fallback": False,
                    "memory_learned": learned_fact,
                }
            except Exception as exc:
                errors.append(exc if isinstance(exc, ChatError) else ChatError("provider_error", str(exc), provider="mistral"))

        elif prov == "ollama" and ollama_m:
            try:
                ollama_base = config.ollama_url()
                endpoint = f"{ollama_base.rstrip('/')}/v1/chat/completions"
                reply, model = _call_openai_compatible(messages, system_prompt, "", endpoint, (ollama_m,), "ollama", opener)
                return {
                    "ok": True,
                    "reply": reply,
                    "provider": "ollama",
                    "provider_label": "Ollama Local AI",
                    "model": model,
                    "fallback": False,
                    "memory_learned": learned_fact,
                }
            except Exception as exc:
                errors.append(exc if isinstance(exc, ChatError) else ChatError("provider_error", str(exc), provider="ollama"))

    raise _combined_failure(errors)


def verify_key_connection(gemini: str = None, groq: str = None, opener=default_opener) -> dict:
    results = {}
    test_msg = [{"role": "user", "text": "Hello"}]
    test_sys = "Reply with 'OK'."

    if gemini:
        try:
            _, model = _call_gemini(test_msg, test_sys, gemini.strip(), opener)
            results["gemini"] = {"ok": True, "model": model}
        except Exception as e:
            results["gemini"] = {"ok": False, "error": str(e)}

    if groq:
        try:
            _, model = _call_openai_compatible(test_msg, test_sys, groq.strip(), GROQ_URL, DEFAULT_GROQ_MODELS, "groq", opener)
            results["groq"] = {"ok": True, "model": model}
        except Exception as e:
            results["groq"] = {"ok": False, "error": str(e)}

    return results
