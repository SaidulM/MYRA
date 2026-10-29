"""MYRA service layer used by the web API, API v1 and native desktop UI.

Keeping this layer independent from HTTP/Qt objects means the same chat,
memory, skills and agent behaviour can later sit behind FastAPI or another
client without rewriting business logic.
"""
from __future__ import annotations

import base64
import binascii

from pathlib import Path

import chat
import config
import paths
import providers
import research as research_module
from core_agent import AgentEngine
from core_memory import MemoryStore
from live_vision import LiveVisionManager
from skill_registry import SkillContext, SkillError, build_default_registry
from voice import VoiceModelManager
from voice_engine import VoiceEngine


APP_VERSION = "3.0-python-native"
MAX_IMAGE_BYTES = 6 * 1024 * 1024
ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}


class MyraService:
    def __init__(self, memory_store=None, registry=None, planner=None):
        using_default_store = memory_store is None
        self.memory = memory_store or MemoryStore()
        self.registry = registry or build_default_registry(self.memory)
        self.agent = AgentEngine(self.memory, self.registry, planner=planner)
        self.agent.service = self
        self.voice = VoiceModelManager(paths.data_dir())
        self.voice_engine = VoiceEngine(self.voice)
        self.live_vision = LiveVisionManager(self.analyze_image)
        self.legacy_import_result = None
        if using_default_store:
            try:
                legacy_db = Path(__file__).resolve().parent.parent / "data" / "myra.db"
                self.legacy_import_result = self.memory.import_legacy_database(legacy_db)
            except Exception as exc:
                self.legacy_import_result = {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}

    # --------------------------------------------------------------
    def health(self):
        from browser_control import browser_status
        from windows_control import get_windows_controller

        return {
            "ok": True,
            "app": "MYRA",
            "version": APP_VERSION,
            "core_stage": 4,
            "core_label": "Unified Python Native",
            "providers": self.providers(),
            "memory": self.memory.stats(),
            "skills": len(self.registry.list()),
            "data_directory": str(paths.data_dir()),
            "workspace": str(paths.workspace_dir()),
            "database_unified": True,
            "legacy_import": self.legacy_import_result,
            "capabilities": {
                "voice": self.voice_engine.status(),
                "live_vision_sessions": len(self.live_vision.list_sessions()),
                "browser": browser_status(),
                "windows": get_windows_controller().status(),
            },
            "secret_backend": config.secret_backend(),
        }

    def providers(self):
        return providers.provider_infos(self.memory.get_preference("provider_models", {}) or {})

    # --------------------------------------------------------------
    # Chat + conversations
    # --------------------------------------------------------------
    def create_conversation(self, title="New conversation", character="core"):
        return self.memory.create_conversation(title=title, character=character)

    def chat(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("chat payload must be an object")
        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            raise chat.ChatError("invalid_request", "Message text is required.", status=400)
        character = payload.get("character") or "core"
        conversation_id = payload.get("conversation_id")
        if conversation_id:
            conversation = self.memory.get_conversation(conversation_id)
            if not conversation:
                raise KeyError("conversation not found")
        else:
            conversation = self.memory.create_conversation(character=character)
            conversation_id = conversation["id"]

        self.memory.add_message(conversation_id, "user", message.strip())
        history = self.memory.recent_messages_for_provider(conversation_id, limit=14)
        memory_context = self.memory.relevant_context(message, limit=6)
        provider = str(payload.get("provider") or "auto").lower().strip()
        if provider not in {"auto", "gemini", "groq", "openrouter", "openai", "anthropic", "deepseek", "mistral", "ollama"}:
            provider = "auto"
        image = payload.get("image")
        if image is not None:
            if not isinstance(image, str) or len(image) > 9_000_000:
                raise ValueError("chat image must be a base64/data URL string under 9 MB")
            if image.startswith("data:") and image[5:].split(";")[0].lower() not in ALLOWED_IMAGE_MIME:
                raise ValueError("Only JPEG, PNG or WebP chat images are supported.")
        chat_payload = {
            "messages": history,
            "assistant_name": payload.get("assistant_name", "MYRA"),
            "owner_name": payload.get("owner_name", "Boss"),
            "character": character,
            "personality": payload.get("personality", "Balanced"),
            "provider": provider,
            "image": image,
            "memory_context": memory_context,
            "models": self.memory.get_preference("provider_models", {}) or {},
            # Core Chat is conversation only. Legacy local-intent execution
            # and silent memory extraction stay off here; computer work is
            # routed through the confirmable Core Agent instead.
            "allow_local_intent": False,
            "auto_learn": False,
            "include_legacy_memory": False,
        }
        result = chat.get_reply(chat_payload)
        assistant_message = self.memory.add_message(
            conversation_id,
            "assistant",
            result["reply"],
            provider=result.get("provider"),
            model=result.get("model"),
        )
        return {
            **result,
            "conversation_id": conversation_id,
            "message": assistant_message,
            "memory_context_used": len(memory_context),
            "mode": "chat",
        }

    def chat_stream(self, payload):
        """Yield persistent-chat streaming events: delta*, then final."""
        if not isinstance(payload, dict):
            raise ValueError("chat payload must be an object")
        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            raise chat.ChatError("invalid_request", "Message text is required.", status=400)
        character = payload.get("character") or "core"
        conversation_id = payload.get("conversation_id")
        if conversation_id:
            if not self.memory.get_conversation(conversation_id):
                raise KeyError("conversation not found")
        else:
            conversation_id = self.memory.create_conversation(character=character)["id"]

        self.memory.add_message(conversation_id, "user", message.strip())
        history = self.memory.recent_messages_for_provider(conversation_id, limit=14)
        memory_context = self.memory.relevant_context(message, limit=6)
        provider = str(payload.get("provider") or "auto").lower().strip()
        if provider not in {"auto", "gemini", "groq", "openrouter", "openai", "anthropic", "deepseek", "mistral", "ollama"}:
            provider = "auto"
        chat_payload = {
            "messages": history,
            "assistant_name": payload.get("assistant_name", "MYRA"),
            "owner_name": payload.get("owner_name", "Boss"),
            "character": character,
            "personality": payload.get("personality", "Balanced"),
            "provider": provider,
            "image": payload.get("image"),
            "memory_context": memory_context,
            "models": self.memory.get_preference("provider_models", {}) or {},
            "allow_local_intent": False,
            "auto_learn": False,
            "include_legacy_memory": False,
        }
        yield {"type": "start", "conversation_id": conversation_id, "provider": provider}

        # The streaming adapters are text-only; images use the established
        # non-streaming multimodal chat path and arrive as one delta.
        if payload.get("image") or provider == "ollama":
            result = chat.get_reply(chat_payload)
            text = result.get("reply", "")
            saved = self.memory.add_message(conversation_id, "assistant", text, provider=result.get("provider"), model=result.get("model"))
            yield {"type": "delta", "text": text, "provider": result.get("provider"), "model": result.get("model")}
            yield {"type": "final", **result, "conversation_id": conversation_id, "message": saved, "mode": "chat", "streamed": False}
            return

        system_prompt = chat.build_system_prompt(chat_payload)
        text_parts, used_provider, used_model = [], provider, ""
        try:
            for event in providers.stream_text(
                history,
                system_prompt,
                provider=provider,
                model_overrides=chat_payload["models"],
            ):
                if event.get("type") == "delta" and event.get("text"):
                    text_parts.append(event["text"])
                    used_provider = event.get("provider") or used_provider
                    used_model = event.get("model") or used_model
                    yield event
        except Exception:
            if text_parts:
                raise
            result = chat.get_reply(chat_payload)
            text = result.get("reply", "")
            saved = self.memory.add_message(conversation_id, "assistant", text, provider=result.get("provider"), model=result.get("model"))
            yield {"type": "delta", "text": text, "provider": result.get("provider"), "model": result.get("model")}
            yield {"type": "final", **result, "conversation_id": conversation_id, "message": saved, "mode": "chat", "streamed": False, "fallback_from_stream": True}
            return

        full_text = "".join(text_parts).strip()
        if not full_text:
            raise chat.ChatError("invalid_response", "The streaming provider sent an empty reply.", provider=used_provider, status=502)
        saved = self.memory.add_message(conversation_id, "assistant", full_text, provider=used_provider, model=used_model)
        yield {
            "type": "final",
            "ok": True,
            "reply": full_text,
            "provider": used_provider,
            "model": used_model,
            "conversation_id": conversation_id,
            "message": saved,
            "mode": "chat",
            "streamed": True,
        }

    def structured(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("structured payload must be an object")
        return providers.generate_structured(
            payload.get("prompt", ""),
            payload.get("schema") or {},
            provider=payload.get("provider", "auto"),
            model_overrides=self.memory.get_preference("provider_models", {}) or {},
        )

    # --------------------------------------------------------------
    # Skills
    # --------------------------------------------------------------
    def execute_skill(self, skill_id, arguments=None, confirmed=False):
        definition = self.registry.get(skill_id)
        if not definition:
            raise KeyError("skill not found")
        if definition.requires_confirmation and not confirmed:
            return {
                "ok": False,
                "status": "confirmation_required",
                "skill_id": skill_id,
                "permissions": definition.permissions,
                "risk": definition.risk,
                "message": "This skill requires explicit confirmation before MYRA runs it.",
            }
        try:
            result = self.registry.execute(
                skill_id,
                arguments or {},
                context=SkillContext(memory=self.memory, service=self),
            )
            return {"status": "completed", **result}
        except SkillError as exc:
            return {
                "ok": False,
                "status": "error",
                "skill_id": skill_id,
                "error": exc.message,
                "code": exc.code,
                "verified": False,
            }

    # --------------------------------------------------------------
    # Unified data, web research and realtime voice
    # --------------------------------------------------------------
    def migrate_legacy(self, legacy_path=None):
        path = Path(legacy_path).expanduser() if legacy_path else Path(__file__).resolve().parent.parent / "data" / "myra.db"
        self.legacy_import_result = self.memory.import_legacy_database(path)
        return self.legacy_import_result

    def _research_summarizer(self, query, sources):
        excerpts = []
        total = 0
        for index, source in enumerate(sources, 1):
            excerpt = str(source.get("text") or source.get("snippet") or "")[:2200]
            total += len(excerpt)
            if total > 14000:
                break
            excerpts.append(f"[{index}] {source.get('title')}\nURL: {source.get('url')}\n{excerpt}")
        result = chat.get_reply({
            "messages": [{
                "role": "user",
                "text": (
                    "Write a concise, source-grounded research report for this question. "
                    "Use only the sources below, cite claims like [1], distinguish facts from uncertainty, "
                    "and include a short conclusion.\n\nQuestion: " + query + "\n\n" + "\n\n".join(excerpts)
                ),
            }],
            "assistant_name": "MYRA",
            "owner_name": "Boss",
            "character": "core",
            "personality": "Professional",
            "models": self.memory.get_preference("provider_models", {}) or {},
            "allow_local_intent": False,
            "auto_learn": False,
            "include_legacy_memory": False,
            "memory_context": [],
        })
        return result.get("reply", "")

    def research(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("research payload must be an object")
        return research_module.research(
            payload.get("query", ""),
            max_sources=payload.get("max_sources", 5),
            summarizer=self._research_summarizer,
        )

    def voice_status(self):
        return self.voice_engine.status()

    def transcribe_voice(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("voice transcription payload must be an object")
        return self.voice_engine.transcribe_base64(
            payload.get("audio_base64", ""),
            language=payload.get("language", "auto"),
            model=payload.get("model", ""),
        )

    def synthesize_voice(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("voice synthesis payload must be an object")
        return self.voice_engine.synthesize(
            payload.get("text", ""),
            character=payload.get("character", "core"),
            voice=payload.get("voice"),
            style=payload.get("style", "gentle"),
        )

    def voice_turn(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("voice turn payload must be an object")
        transcript = self.transcribe_voice(payload)
        text = str(transcript.get("text") or "").strip()
        if not text:
            return {"ok": True, "transcript": transcript, "reply": "", "audio": None}
        chat_result = self.chat({
            "message": text,
            "conversation_id": payload.get("conversation_id"),
            "character": payload.get("character", "core"),
            "assistant_name": payload.get("assistant_name", "MYRA"),
            "owner_name": payload.get("owner_name", "Boss"),
            "personality": payload.get("personality", "Balanced"),
            "provider": payload.get("provider", "auto"),
        })
        audio, tts_error = None, ""
        if payload.get("speak", True):
            try:
                audio = self.synthesize_voice({
                    "text": chat_result.get("reply", ""),
                    "character": payload.get("character", "core"),
                    "voice": payload.get("voice"),
                    "style": payload.get("style", "gentle"),
                })
            except Exception as exc:
                tts_error = f"{exc.__class__.__name__}: {exc}"[:400]
        return {
            "ok": True,
            "transcript": transcript,
            "chat": chat_result,
            "reply": chat_result.get("reply", ""),
            "conversation_id": chat_result.get("conversation_id"),
            "audio": audio,
            "tts_error": tts_error,
        }

    def install_voice_model(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("voice model payload must be an object")
        return self.voice.install_faster_whisper_model(
            model_id=payload.get("model_id", "base"),
            confirmed=payload.get("confirmed") is True,
        )

    def shutdown(self):
        try:
            self.live_vision.stop_all()
        except Exception:
            pass
        try:
            from windows_control import get_windows_controller
            get_windows_controller().emergency_stop()
        except Exception:
            pass

    # --------------------------------------------------------------
    # Explicit one-frame vision
    # --------------------------------------------------------------
    def analyze_image(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("vision payload must be an object")
        if payload.get("consent") is not True:
            raise PermissionError("Image analysis requires explicit consent for this frame.")
        source = payload.get("source") or "upload"
        if source not in {"screen", "camera", "upload"}:
            raise ValueError("source must be screen, camera or upload")
        raw = payload.get("image_base64") or ""
        mime = (payload.get("mime_type") or "image/jpeg").split(";")[0].strip().lower()
        if isinstance(raw, str) and raw.startswith("data:"):
            header, raw = raw.split(",", 1)
            if header.startswith("data:"):
                mime = header[5:].split(";")[0] or mime
        if mime not in ALLOWED_IMAGE_MIME:
            raise ValueError("Only JPEG, PNG or WebP images are supported.")
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("image_base64 is required")
        try:
            decoded = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("image_base64 is not valid base64") from exc
        if len(decoded) > MAX_IMAGE_BYTES:
            raise ValueError("Image is too large (6 MB limit for one frame).")
        # Send the original validated base64 upstream; never store it by
        # default and never treat this as continuous screen/camera sharing.
        model_overrides = self.memory.get_preference("provider_models", {}) or {}
        result = providers.analyze_image(
            raw,
            mime,
            payload.get("prompt") or "Describe this image and help with what is visible.",
            model_override=model_overrides.get("gemini"),
        )
        requested_mode = payload.get("frame_mode")
        frame_mode = requested_mode if requested_mode in {"single_explicit_frame", "live_sampled_frame"} else "single_explicit_frame"
        return {**result, "source": source, "frame_mode": frame_mode}


_SERVICE = None


def get_service():
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = MyraService()
    return _SERVICE
