"""Provider capability registry and tool/vision adapters.

The current production chat path remains in ``chat.py``.  This module adds
the provider-independent pieces needed by Agent Mode and explicit vision:

* normalized transcript events;
* conversion from MYRA skill schemas to Gemini/Groq tool formats;
* one bounded planner decision at a time;
* one explicit image analysis call.

No capability is advertised unless the adapter in *this build* implements
it.  In particular, streaming tokens and realtime voice are still false.
"""
from __future__ import annotations

import copy
import inspect
import json
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


def provider_infos(model_overrides=None):
    model_overrides = model_overrides or {}
    return [
        {
            "id": "gemini",
            "label": "Google Gemini",
            "implemented": True,
            "configured": bool(config.gemini_key().strip()),
            "default_models": list(chat.DEFAULT_GEMINI_MODELS),
            "selected_model": model_overrides.get("gemini") or config.get("GEMINI_MODEL") or chat.DEFAULT_GEMINI_MODELS[0],
            "capabilities": {
                "text": True,
                "streaming": False,
                "tools": True,
                "structured_output": False,
                "vision": True,
                "audio_input": False,
                "audio_output": False,
                "realtime_session": False,
            },
            "notes": "Current MYRA adapter uses non-streaming generateContent calls.",
        },
        {
            "id": "groq",
            "label": "Groq",
            "implemented": True,
            "configured": bool(config.groq_key().strip()),
            "default_models": list(chat.DEFAULT_GROQ_MODELS),
            "selected_model": model_overrides.get("groq") or config.get("GROQ_MODEL") or chat.DEFAULT_GROQ_MODELS[0],
            "capabilities": {
                "text": True,
                "streaming": False,
                "tools": True,
                "structured_output": False,
                "vision": False,
                "audio_input": False,
                "audio_output": False,
                "realtime_session": False,
            },
            "notes": "Vision is not enabled for MYRA's configured text-first Groq defaults.",
        },
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


def _groq_next(events, system_prompt, definitions, api_key, opener, model_override=None):
    last_error = None
    for model in _provider_models("groq", api_key, opener, model_override):
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
            response = chat._post_json(
                "https://api.groq.com/openai/v1/chat/completions",
                payload,
                {"Authorization": f"Bearer {api_key}"},
                "groq",
                opener,
            )
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
                        id=first.get("id") or "groq-call",
                        name=_skill_id_from_function(raw_name, definitions),
                        arguments=_parse_tool_arguments(function.get("arguments")),
                    ),
                    provider="groq",
                    model=model,
                )
            text = _extract_groq_text(response)
            if text:
                return PlannerDecision(kind="final", text=text, provider="groq", model=model)
            raise _chat_error("invalid_response", "Groq sent an empty planner response.", provider="groq", status=502)
        except chat.ChatError as exc:
            last_error = exc
            if exc.code != "model_unavailable":
                break
    raise last_error


def next_action(events, system_prompt, definitions, opener=None, model_overrides=None):
    """Ask Gemini first, then Groq, for one planner decision."""
    opener = opener or _default_opener()
    model_overrides = model_overrides or {}
    gemini_key = config.gemini_key().strip()
    groq_key = config.groq_key().strip()
    if not gemini_key and not groq_key:
        raise _chat_error(
            "missing_keys",
            "No API key is saved. Open Settings and add a Gemini or Groq key first.",
            status=503,
        )

    errors = []
    if gemini_key:
        try:
            return _gemini_next(
                events,
                system_prompt,
                definitions,
                gemini_key,
                opener,
                model_overrides.get("gemini"),
            )
        except chat.ChatError as exc:
            errors.append(exc)
    if groq_key:
        try:
            return _groq_next(
                events,
                system_prompt,
                definitions,
                groq_key,
                opener,
                model_overrides.get("groq"),
            )
        except chat.ChatError as exc:
            errors.append(exc)
    if errors:
        last = errors[-1]
        if len(errors) > 1:
            raise _chat_error(
                "all_providers_failed",
                "Gemini and Groq both failed. " + errors[0].message + " " + last.message,
                status=502,
            )
        raise last
    raise _chat_error("missing_keys", "No usable API provider is configured.", status=503)


def analyze_image(image_base64, mime_type, prompt, opener=None, model_override=None):
    """Analyze one explicitly supplied image with Gemini.

    Groq vision is intentionally not claimed for MYRA's current default
    text models.
    """
    api_key = config.gemini_key().strip()
    if not api_key:
        raise _chat_error(
            "vision_provider_missing",
            "Image analysis currently requires a saved Gemini key.",
            provider="gemini",
            status=503,
        )
    opener = opener or _default_opener()
    prompt = (prompt or "Describe this image and help with what is visible.").strip()[:2000]
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
