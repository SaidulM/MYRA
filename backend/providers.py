"""Provider capability registry and tool/vision adapters.

The current production chat path remains in ``chat.py``.  This module adds
the provider-independent pieces needed by Agent Mode and explicit vision:

* normalized transcript events;
* conversion from MYRA skill schemas to Gemini/Groq tool formats;
* one bounded planner decision at a time;
* one explicit image analysis call.

No capability is advertised unless the adapter in *this build* implements
it.  Provider-native realtime audio sessions remain false; MYRA's realtime
voice is the separate microphone -> STT -> chat -> TTS pipeline.
"""
from __future__ import annotations

import copy
import inspect
import json
import urllib.error
import urllib.request
from dataclasses import dataclass

import chat
import config


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class PlannerDecision:
    kind: str  # final | tool_call
    text: str = ""
    tool_call: ToolCall | None = None
    provider: str = ""
    model: str = ""


def _chat_error(code, message, provider=None, status=502):
    return chat.ChatError(code, message, provider=provider, status=status)


def _default_opener():
    return getattr(chat, "default_opener", urllib.request.urlopen)


def _provider_models(provider, api_key, opener, override=None):
    """Support both MYRA chat generations without passing a key as a model."""
    if isinstance(override, str) and override.strip() and override.strip().lower() != "auto":
        return (override.strip(),)
    models_for = chat._models_for
    try:
        params = inspect.signature(models_for).parameters
    except (TypeError, ValueError):
        params = {}
    if "api_key" in params:
        return models_for(provider, api_key, opener=opener)
    if "override" in params:
        return models_for(provider, None)
    return models_for(provider)


def _extract_groq_text(data):
    extractor = getattr(chat, "_extract_groq_text", None)
    if extractor is not None:
        return extractor(data)
    return chat._extract_openai_text(data, provider="groq")


def _selected_model(provider, defaults, model_overrides):
    configured = (model_overrides.get(provider) or config.get(f"{provider.upper()}_MODEL") or "").strip()
    if configured and configured.lower() != "auto":
        return configured
    return defaults[0] if defaults else ""


def provider_infos(model_overrides=None):
    if not isinstance(model_overrides, dict):
        model_overrides = {}

    def entry(provider, label, configured, defaults, capabilities, notes):
        defaults = tuple(defaults or ())
        return {
            "id": provider,
            "label": label,
            "implemented": True,
            "configured": bool(configured),
            "default_models": list(defaults),
            "selected_model": _selected_model(provider, defaults, model_overrides),
            "capabilities": capabilities,
            "notes": notes,
        }

    openai_model = config.get("OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini"
    anthropic_model = config.get("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022") or "claude-3-5-haiku-20241022"
    deepseek_model = config.get("DEEPSEEK_MODEL", "deepseek-chat") or "deepseek-chat"
    mistral_model = config.get("MISTRAL_MODEL", "mistral-small-latest") or "mistral-small-latest"
    ollama_model = config.ollama_model()
    return [
        entry("gemini", "Google Gemini", config.gemini_key().strip(), chat.DEFAULT_GEMINI_MODELS,
              {"text": True, "streaming": True, "tools": True, "structured_output": True, "vision": True, "audio_input": False, "audio_output": False, "realtime_session": False},
              "Gemini generateContent/streamGenerateContent, function calling, JSON schema output and vision adapters are implemented."),
        entry("groq", "Groq", config.groq_key().strip(), chat.DEFAULT_GROQ_MODELS,
              {"text": True, "streaming": True, "tools": True, "structured_output": True, "vision": False, "audio_input": False, "audio_output": False, "realtime_session": False},
              "Groq OpenAI-compatible streaming, tools and validated JSON output are implemented for MYRA's text models."),
        entry("openrouter", "OpenRouter", config.openrouter_key().strip(), getattr(chat, "DEFAULT_OPENROUTER_MODELS", ()),
              {"text": True, "streaming": True, "tools": True, "structured_output": True, "vision": True, "audio_input": False, "audio_output": False, "realtime_session": False},
              "Tool/vision support depends on the selected OpenRouter model; MYRA reports provider errors instead of faking success."),
        entry("openai", "OpenAI", config.openai_key().strip(), (openai_model,),
              {"text": True, "streaming": True, "tools": True, "structured_output": True, "vision": True, "audio_input": False, "audio_output": False, "realtime_session": False},
              "OpenAI Chat Completions streaming/tools/JSON/vision adapters are implemented."),
        entry("mistral", "Mistral", config.mistral_key().strip(), (mistral_model,),
              {"text": True, "streaming": True, "tools": True, "structured_output": True, "vision": False, "audio_input": False, "audio_output": False, "realtime_session": False},
              "Mistral OpenAI-compatible streaming/tools/JSON adapters are implemented; vision is model-specific and not advertised."),
        entry("deepseek", "DeepSeek", config.deepseek_key().strip(), (deepseek_model,),
              {"text": True, "streaming": True, "tools": True, "structured_output": True, "vision": False, "audio_input": False, "audio_output": False, "realtime_session": False},
              "DeepSeek OpenAI-compatible streaming/tools/JSON adapters are implemented."),
        entry("anthropic", "Anthropic", config.anthropic_key().strip(), (anthropic_model,),
              {"text": True, "streaming": True, "tools": False, "structured_output": False, "vision": False, "audio_input": False, "audio_output": False, "realtime_session": False},
              "Anthropic text/streaming is available through the shared chat layer; Core Agent tool calling uses Gemini/Groq/OpenAI-compatible providers."),
        entry("ollama", "Ollama (optional local endpoint)", ollama_model, (ollama_model,) if ollama_model else (),
              {"text": True, "streaming": False, "tools": False, "structured_output": False, "vision": False, "audio_input": False, "audio_output": False, "realtime_session": False},
              "Optional endpoint only; it is not MYRA's primary cloud intelligence path."),
    ]


def _gemini_schema(schema):
    if not isinstance(schema, dict):
        return {"type": "OBJECT", "properties": {}}
    result = {}
    if "type" in schema:
        result["type"] = str(schema["type"]).upper()
    if "description" in schema:
        result["description"] = schema["description"]
    if "enum" in schema:
        result["enum"] = schema["enum"]
    if "properties" in schema:
        result["properties"] = {
            key: _gemini_schema(value) for key, value in (schema["properties"] or {}).items()
        }
    if "required" in schema:
        result["required"] = schema["required"]
    if "items" in schema:
        result["items"] = _gemini_schema(schema["items"])
    return result


def tool_schemas(definitions, provider):
    tools = []
    for definition in definitions:
        manifest = definition.manifest() if hasattr(definition, "manifest") else definition
        function_name = manifest["id"].replace(".", "_")
        if provider == "gemini":
            tools.append(
                {
                    "name": function_name,
                    "description": manifest["description"],
                    "parameters": _gemini_schema(manifest["parameters"]),
                }
            )
        else:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": function_name,
                        "description": manifest["description"],
                        "parameters": copy.deepcopy(manifest["parameters"]),
                    },
                }
            )
    return tools


def _skill_id_from_function(name, definitions):
    for definition in definitions:
        manifest_id = definition.id if hasattr(definition, "id") else definition["id"]
        if manifest_id.replace(".", "_") == name or manifest_id == name:
            return manifest_id
    return name


def _json_text(value):
    return json.dumps(value, ensure_ascii=False)[:12000]


def _gemini_contents(events):
    contents = []
    for event in events:
        kind = event.get("type")
        if kind == "user":
            contents.append({"role": "user", "parts": [{"text": event.get("text", "")}]})
        elif kind == "assistant":
            contents.append({"role": "model", "parts": [{"text": event.get("text", "")}]})
        elif kind == "tool_call":
            call = event.get("tool_call") or {}
            contents.append(
                {
                    "role": "model",
                    "parts": [
                        {
                            "functionCall": {
                                "name": str(call.get("name", "")).replace(".", "_"),
                                "args": call.get("arguments") or {},
                            }
                        }
                    ],
                }
            )
        elif kind == "tool_result":
            result = event.get("result")
            if not isinstance(result, dict):
                result = {"result": result}
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": str(event.get("name", "tool")).replace(".", "_"),
                                "response": result,
                            }
                        }
                    ],
                }
            )
    return contents


def _groq_messages(events, system_prompt):
    messages = [{"role": "system", "content": system_prompt}]
    for event in events:
        kind = event.get("type")
        if kind == "user":
            messages.append({"role": "user", "content": event.get("text", "")})
        elif kind == "assistant":
            messages.append({"role": "assistant", "content": event.get("text", "")})
        elif kind == "tool_call":
            call = event.get("tool_call") or {}
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call.get("id") or "call_1",
                            "type": "function",
                            "function": {
                                "name": str(call.get("name", "")).replace(".", "_"),
                                "arguments": _json_text(call.get("arguments") or {}),
                            },
                        }
                    ],
                }
            )
        elif kind == "tool_result":
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": event.get("tool_call_id") or "call_1",
                    "name": str(event.get("name", "tool")).replace(".", "_"),
                    "content": _json_text(event.get("result")),
                }
            )
    return messages


def _gemini_next(events, system_prompt, definitions, api_key, opener, model_override=None):
    payload_base = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": _gemini_contents(events),
        "tools": [{"functionDeclarations": tool_schemas(definitions, "gemini")}],
        "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}},
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1200},
    }
    last_error = None
    for model in _provider_models("gemini", api_key, opener, model_override):
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        try:
            response = chat._post_json(
                url,
                payload_base,
                {"x-goog-api-key": api_key},
                "gemini",
                opener,
            )
            candidates = response.get("candidates") or []
            parts = []
            if candidates:
                parts = ((candidates[0].get("content") or {}).get("parts") or [])
            for part in parts:
                function_call = part.get("functionCall") if isinstance(part, dict) else None
                if function_call:
                    raw_name = function_call.get("name", "")
                    return PlannerDecision(
                        kind="tool_call",
                        tool_call=ToolCall(
                            id="gemini-call",
                            name=_skill_id_from_function(raw_name, definitions),
                            arguments=function_call.get("args") or {},
                        ),
                        provider="gemini",
                        model=model,
                    )
            text = chat._extract_gemini_text(response)
            if text:
                return PlannerDecision(kind="final", text=text, provider="gemini", model=model)
            raise _chat_error(
                "invalid_response", "Gemini sent an empty planner response.", provider="gemini", status=502
            )
        except chat.ChatError as exc:
            last_error = exc
            if exc.code != "model_unavailable":
                break
    raise last_error


def _parse_tool_arguments(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}


_OPENAI_COMPATIBLE = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", lambda: config.groq_key(), lambda: chat.DEFAULT_GROQ_MODELS),
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions", lambda: config.openrouter_key(), lambda: getattr(chat, "DEFAULT_OPENROUTER_MODELS", ())),
    "openai": ("https://api.openai.com/v1/chat/completions", lambda: config.openai_key(), lambda: ((config.get("OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini"),)),
    "mistral": ("https://api.mistral.ai/v1/chat/completions", lambda: config.mistral_key(), lambda: ((config.get("MISTRAL_MODEL", "mistral-small-latest") or "mistral-small-latest"),)),
    "deepseek": ("https://api.deepseek.com/chat/completions", lambda: config.deepseek_key(), lambda: ((config.get("DEEPSEEK_MODEL", "deepseek-chat") or "deepseek-chat"),)),
}


def _compatible_models(provider, api_key, opener, override=None):
    if provider == "groq":
        return _provider_models(provider, api_key, opener, override)
    if isinstance(override, str) and override.strip() and override.strip().lower() != "auto":
        return (override.strip(),)
    configured = config.get(f"{provider.upper()}_MODEL", "").strip()
    if configured and configured.lower() != "auto":
        return (configured,)
    defaults = _OPENAI_COMPATIBLE[provider][2]()
    return tuple(defaults)


def _openai_compatible_next(provider, events, system_prompt, definitions, api_key, opener, model_override=None):
    endpoint = _OPENAI_COMPATIBLE[provider][0]
    last_error = None
    for model in _compatible_models(provider, api_key, opener, model_override):
        payload = {
            "model": model,
            "messages": _groq_messages(events, system_prompt),
            "tools": tool_schemas(definitions, "groq"),
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "temperature": 0.2,
            "max_tokens": 1200,
        }
        try:
            response = chat._post_json(endpoint, payload, {"Authorization": f"Bearer {api_key}"}, provider, opener)
            choices = response.get("choices") or []
            message = (choices[0].get("message") or {}) if choices else {}
            tool_calls = message.get("tool_calls") or []
            if tool_calls:
                first = tool_calls[0]
                function = first.get("function") or {}
                raw_name = function.get("name", "")
                return PlannerDecision(
                    kind="tool_call",
                    tool_call=ToolCall(
                        id=first.get("id") or f"{provider}-call",
                        name=_skill_id_from_function(raw_name, definitions),
                        arguments=_parse_tool_arguments(function.get("arguments")),
                    ),
                    provider=provider,
                    model=model,
                )
            text = _extract_groq_text(response)
            if text:
                return PlannerDecision(kind="final", text=text, provider=provider, model=model)
            raise _chat_error("invalid_response", f"{provider.title()} sent an empty planner response.", provider=provider, status=502)
        except chat.ChatError as exc:
            last_error = exc
            if exc.code != "model_unavailable":
                break
    raise last_error


def _groq_next(events, system_prompt, definitions, api_key, opener, model_override=None):
    return _openai_compatible_next("groq", events, system_prompt, definitions, api_key, opener, model_override)


def next_action(events, system_prompt, definitions, opener=None, model_overrides=None):
    """Ask configured tool-capable providers for one planner decision."""
    opener = opener or _default_opener()
    model_overrides = model_overrides or {}
    gemini_key = config.gemini_key().strip()
    compatible_keys = {
        provider: key_getter().strip()
        for provider, (_endpoint, key_getter, _defaults) in _OPENAI_COMPATIBLE.items()
    }
    if not gemini_key and not any(compatible_keys.values()):
        raise _chat_error(
            "missing_keys",
            "No tool-capable API key is saved. Open Settings and add a Gemini, Groq, OpenRouter, OpenAI, Mistral or DeepSeek key first.",
            status=503,
        )

    errors = []
    if gemini_key:
        try:
            return _gemini_next(events, system_prompt, definitions, gemini_key, opener, model_overrides.get("gemini"))
        except chat.ChatError as exc:
            errors.append(exc)
    for provider in ("groq", "openrouter", "openai", "mistral", "deepseek"):
        api_key = compatible_keys.get(provider, "")
        if not api_key:
            continue
        try:
            return _openai_compatible_next(provider, events, system_prompt, definitions, api_key, opener, model_overrides.get(provider))
        except chat.ChatError as exc:
            errors.append(exc)
    if errors:
        last = errors[-1]
        if len(errors) > 1:
            raise _chat_error("all_providers_failed", "All configured tool providers failed. " + errors[0].message + " " + last.message, status=502)
        raise last
    raise _chat_error("missing_keys", "No usable API provider is configured.", status=503)


def analyze_image(image_base64, mime_type, prompt, opener=None, model_override=None):
    """Analyze one explicitly supplied image.

    Gemini is preferred; OpenAI/OpenRouter vision models are used as a
    fallback when configured.  Groq vision is not claimed for MYRA's
    current default text models.
    """
    opener = opener or _default_opener()
    prompt = (prompt or "Describe this image and help with what is visible.").strip()[:2000]
    api_key = config.gemini_key().strip()
    if not api_key:
        return _analyze_image_openai_compatible(image_base64, mime_type, prompt, opener=opener)
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"inlineData": {"mimeType": mime_type, "data": image_base64}},
                ],
            }
        ],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1200},
    }
    last_error = None
    for model in _provider_models("gemini", api_key, opener, model_override):
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        try:
            response = chat._post_json(
                url,
                payload,
                {"x-goog-api-key": api_key},
                "gemini",
                opener,
            )
            text = chat._extract_gemini_text(response)
            if not text:
                raise _chat_error(
                    "invalid_response", "Gemini sent an empty image response.", provider="gemini", status=502
                )
            return {"provider": "gemini", "model": model, "text": text}
        except chat.ChatError as exc:
            last_error = exc
            if exc.code != "model_unavailable":
                break
    raise last_error


def _analyze_image_openai_compatible(image_base64, mime_type, prompt, opener=None):
    """Vision fallback for OpenAI/OpenRouter models that accept image URLs."""
    opener = opener or _default_opener()
    candidates = []
    if config.openai_key().strip():
        candidates.append(("openai", config.openai_key().strip(), "https://api.openai.com/v1/chat/completions", (config.get("OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini"),))
    if config.openrouter_key().strip():
        models = _compatible_models("openrouter", config.openrouter_key(), opener)
        candidates.append(("openrouter", config.openrouter_key().strip(), "https://openrouter.ai/api/v1/chat/completions", models[:1]))
    last_error = None
    for provider, api_key, endpoint, models in candidates:
        for model in models:
            payload = {
                "model": model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_base64}"}},
                    ],
                }],
                "temperature": 0.3,
                "max_tokens": 1200,
            }
            try:
                response = chat._post_json(endpoint, payload, {"Authorization": f"Bearer {api_key}"}, provider, opener)
                text = _extract_groq_text(response)
                if text:
                    return {"provider": provider, "model": model, "text": text}
                raise _chat_error("invalid_response", f"{provider.title()} sent an empty image response.", provider=provider, status=502)
            except chat.ChatError as exc:
                last_error = exc
                break
    if last_error:
        raise last_error
    raise _chat_error(
        "vision_provider_missing",
        "Image analysis requires a saved Gemini, OpenAI or OpenRouter vision-capable key/model.",
        provider="gemini",
        status=503,
    )


def _validate_structured(value, schema, path="$"):
    if not isinstance(schema, dict):
        return
    expected = schema.get("type")
    types = {
        "object": dict,
        "array": list,
        "string": str,
        "boolean": bool,
        "integer": int,
        "number": (int, float),
        "null": type(None),
    }
    if expected in types:
        valid = isinstance(value, types[expected])
        if expected in {"integer", "number"} and isinstance(value, bool):
            valid = False
        if expected == "integer" and isinstance(value, float):
            valid = False
        if not valid:
            raise _chat_error("invalid_structured_output", f"Structured output at {path} must be {expected}.", status=502)
    if "enum" in schema and value not in schema["enum"]:
        raise _chat_error("invalid_structured_output", f"Structured output at {path} is not an allowed value.", status=502)
    if isinstance(value, dict):
        for key in schema.get("required") or []:
            if key not in value:
                raise _chat_error("invalid_structured_output", f"Structured output is missing {path}.{key}.", status=502)
        for key, subschema in (schema.get("properties") or {}).items():
            if key in value:
                _validate_structured(value[key], subschema, f"{path}.{key}")
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            _validate_structured(item, schema["items"], f"{path}[{index}]")
    if isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)) or len(value) > int(schema.get("maxLength", 1000000)):
            raise _chat_error("invalid_structured_output", f"Structured output string at {path} has an invalid length.", status=502)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise _chat_error("invalid_structured_output", f"Structured output at {path} is below its minimum.", status=502)
        if "maximum" in schema and value > schema["maximum"]:
            raise _chat_error("invalid_structured_output", f"Structured output at {path} exceeds its maximum.", status=502)


def _parse_structured_text(text, schema, provider, model):
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        value = json.loads(cleaned)
    except ValueError as exc:
        raise _chat_error("invalid_structured_output", f"{provider.title()} did not return valid JSON.", provider=provider, status=502) from exc
    _validate_structured(value, schema)
    return {"provider": provider, "model": model, "data": value}


def generate_structured(prompt, schema, provider="auto", opener=None, model_overrides=None):
    """Generate and validate JSON output against MYRA's JSON-schema subset."""
    if not isinstance(schema, dict) or not schema:
        raise _chat_error("invalid_request", "A JSON schema object is required for structured output.", status=400)
    prompt = str(prompt or "").strip()[:12000]
    if not prompt:
        raise _chat_error("invalid_request", "A prompt is required for structured output.", status=400)
    opener = opener or _default_opener()
    model_overrides = model_overrides or {}
    requested = str(provider or "auto").lower()
    errors = []

    def try_gemini():
        api_key = config.gemini_key().strip()
        if not api_key:
            return None
        model = _provider_models("gemini", api_key, opener, model_overrides.get("gemini"))[0]
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1800,
                "responseMimeType": "application/json",
                "responseSchema": _gemini_schema(schema),
            },
        }
        response = chat._post_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            payload, {"x-goog-api-key": api_key}, "gemini", opener,
        )
        return _parse_structured_text(chat._extract_gemini_text(response), schema, "gemini", model)

    def try_compatible(name):
        endpoint, key_getter, _defaults = _OPENAI_COMPATIBLE[name]
        api_key = key_getter().strip()
        if not api_key:
            return None
        model = _compatible_models(name, api_key, opener, model_overrides.get(name))[0]
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Return only valid JSON matching this schema: " + json.dumps(schema, ensure_ascii=False)},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
            "max_tokens": 1800,
        }
        response = chat._post_json(endpoint, payload, {"Authorization": f"Bearer {api_key}"}, name, opener)
        return _parse_structured_text(_extract_groq_text(response), schema, name, model)

    order = ["gemini", "groq", "openrouter", "openai", "mistral", "deepseek"]
    if requested != "auto":
        if requested not in order:
            raise _chat_error("unsupported_provider", f"Structured output is not implemented for {requested}.", status=400)
        order = [requested]
    for name in order:
        try:
            result = try_gemini() if name == "gemini" else try_compatible(name)
            if result:
                return result
        except chat.ChatError as exc:
            errors.append(exc)
            if requested != "auto":
                raise
    if errors:
        raise errors[-1]
    raise _chat_error("missing_keys", "No structured-output provider key is saved.", status=503)


def _stream_lines(url, payload, headers, provider, opener):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream", **headers},
        method="POST",
    )
    try:
        try:
            response = opener(request, timeout=90)
        except TypeError:
            response = opener(request)
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read(4096) if exc.fp else b""
        except Exception:
            raw = b""
        text = raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else str(raw or "")
        error_factory = getattr(chat, "_provider_http_error", None)
        if error_factory:
            raise error_factory(provider, exc.code, text) from None
        raise _chat_error("provider_error", f"{provider.title()} streaming failed with HTTP {exc.code}.", provider=provider, status=exc.code) from None
    with response:
        for raw in response:
            yield raw.decode("utf-8", errors="replace").strip() if isinstance(raw, bytes) else str(raw).strip()


def _sse_data(line):
    if not line.startswith("data:"):
        return None
    value = line[5:].strip()
    if not value or value == "[DONE]":
        return None
    try:
        return json.loads(value)
    except ValueError:
        return None


def _stream_gemini(messages, system_prompt, api_key, opener, override=None):
    model = _provider_models("gemini", api_key, opener, override)[0]
    contents = []
    for message in messages:
        contents.append({
            "role": "model" if message.get("role") == "assistant" else "user",
            "parts": [{"text": str(message.get("text") or message.get("content") or "")}],
        })
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.5, "maxOutputTokens": 1800},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse"
    for line in _stream_lines(url, payload, {"x-goog-api-key": api_key}, "gemini", opener):
        data = _sse_data(line)
        if not data:
            continue
        for candidate in data.get("candidates") or []:
            for part in ((candidate.get("content") or {}).get("parts") or []):
                text = part.get("text") if isinstance(part, dict) else ""
                if text:
                    yield {"type": "delta", "text": text, "provider": "gemini", "model": model}


def _stream_compatible(provider, messages, system_prompt, api_key, opener, override=None):
    endpoint = _OPENAI_COMPATIBLE[provider][0]
    model = _compatible_models(provider, api_key, opener, override)[0]
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}] + [
            {"role": message.get("role", "user"), "content": str(message.get("text") or message.get("content") or "")}
            for message in messages
        ],
        "stream": True,
        "temperature": 0.5,
        "max_tokens": 1800,
    }
    for line in _stream_lines(endpoint, payload, {"Authorization": f"Bearer {api_key}"}, provider, opener):
        data = _sse_data(line)
        if not data:
            continue
        for choice in data.get("choices") or []:
            text = ((choice.get("delta") or {}).get("content") or "")
            if text:
                yield {"type": "delta", "text": text, "provider": provider, "model": data.get("model") or model}


def _stream_anthropic(messages, system_prompt, api_key, opener, override=None):
    model = override or config.get("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022") or "claude-3-5-haiku-20241022"
    payload = {
        "model": model,
        "system": system_prompt,
        "messages": [
            {"role": message.get("role", "user"), "content": str(message.get("text") or message.get("content") or "")}
            for message in messages if message.get("role") in {"user", "assistant"}
        ],
        "max_tokens": 1800,
        "stream": True,
    }
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    for line in _stream_lines("https://api.anthropic.com/v1/messages", payload, headers, "anthropic", opener):
        data = _sse_data(line)
        if not data or data.get("type") != "content_block_delta":
            continue
        text = ((data.get("delta") or {}).get("text") or "")
        if text:
            yield {"type": "delta", "text": text, "provider": "anthropic", "model": model}


def stream_text(messages, system_prompt, provider="auto", opener=None, model_overrides=None):
    """Yield text deltas from the first configured streaming provider.

    If a provider fails before emitting anything, the next configured
    provider is tried.  Once text has been emitted, errors propagate so
    MYRA never silently splices two different answers together.
    """
    opener = opener or _default_opener()
    model_overrides = model_overrides or {}
    requested = str(provider or "auto").lower()
    candidates = []
    if requested in {"auto", "gemini"} and config.gemini_key().strip():
        candidates.append(("gemini", lambda: _stream_gemini(messages, system_prompt, config.gemini_key().strip(), opener, model_overrides.get("gemini"))))
    for name in ("groq", "openrouter", "openai", "mistral", "deepseek"):
        if requested not in {"auto", name}:
            continue
        api_key = _OPENAI_COMPATIBLE[name][1]().strip()
        if api_key:
            candidates.append((name, lambda n=name, k=api_key: _stream_compatible(n, messages, system_prompt, k, opener, model_overrides.get(n))))
    if requested in {"auto", "anthropic"} and config.anthropic_key().strip():
        candidates.append(("anthropic", lambda: _stream_anthropic(messages, system_prompt, config.anthropic_key().strip(), opener, model_overrides.get("anthropic"))))
    if not candidates:
        raise _chat_error("missing_keys", "No streaming provider key is saved.", status=503)

    last_error = None
    for _name, factory in candidates:
        emitted = False
        try:
            for event in factory():
                emitted = True
                yield event
            if emitted:
                return
            raise _chat_error("invalid_response", "Streaming provider sent no text.", status=502)
        except Exception as exc:
            last_error = exc
            if emitted or requested != "auto":
                raise
    if last_error:
        raise last_error
