"""MYRA service layer used by the web API, API v1 and native desktop UI.

Keeping this layer independent from HTTP/Qt objects means the same chat,
memory, skills and agent behaviour can later sit behind FastAPI or another
client without rewriting business logic.
"""
from __future__ import annotations

import base64
import binascii

import chat
import config
import paths
import providers
from core_agent import AgentEngine
from core_memory import MemoryStore
from skill_registry import SkillContext, SkillError, build_default_registry
from voice import VoiceModelManager


APP_VERSION = "2.0-foundation"
MAX_IMAGE_BYTES = 6 * 1024 * 1024
ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}


class MyraService:
    def __init__(self, memory_store=None, registry=None, planner=None):
        self.memory = memory_store or MemoryStore()
        self.registry = registry or build_default_registry(self.memory)
        self.agent = AgentEngine(self.memory, self.registry, planner=planner)
        self.voice = VoiceModelManager(paths.data_dir())

    # --------------------------------------------------------------
    def health(self):
        return {
            "ok": True,
            "app": "MYRA",
            "version": APP_VERSION,
            "core_stage": 3,
            "core_label": "Core 2.0 foundation",
            "providers": self.providers(),
            "memory": self.memory.stats(),
            "skills": len(self.registry.list()),
            "data_directory": str(paths.data_dir()),
            "workspace": str(paths.workspace_dir()),
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
        chat_payload = {
            "messages": history,
            "assistant_name": payload.get("assistant_name", "MYRA"),
            "owner_name": payload.get("owner_name", "Boss"),
            "character": character,
            "personality": payload.get("personality", "Balanced"),
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
                context=SkillContext(memory=self.memory),
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
        return {**result, "source": source, "frame_mode": "single_explicit_frame"}


_SERVICE = None


def get_service():
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = MyraService()
    return _SERVICE
