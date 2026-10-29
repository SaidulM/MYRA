import hashlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import config  # noqa: E402
import providers  # noqa: E402
import service as service_module  # noqa: E402
from core_agent import AgentEngine  # noqa: E402
from core_memory import MemoryStore  # noqa: E402
from providers import PlannerDecision, ToolCall  # noqa: E402
from service import MyraService  # noqa: E402
from skill_registry import SkillContext, SkillError, build_default_registry  # noqa: E402
from voice import VoiceModelError, VoiceModelManager  # noqa: E402


class CoreTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_data_dir = os.environ.get("MYRA_DATA_DIR")
        os.environ["MYRA_DATA_DIR"] = str(self.root / "data")
        self.memory = MemoryStore(self.root / "data" / "test.db")
        self.registry = build_default_registry(self.memory)
        self.workspace = self.root / "data" / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.context = SkillContext(memory=self.memory, workspace=self.workspace)

    def tearDown(self):
        if self.old_data_dir is None:
            os.environ.pop("MYRA_DATA_DIR", None)
        else:
            os.environ["MYRA_DATA_DIR"] = self.old_data_dir
        self.tmp.cleanup()


class MemoryTests(CoreTestCase):
    def test_conversation_memory_and_note_persist(self):
        conversation = self.memory.create_conversation()
        self.memory.add_message(conversation["id"], "user", "My laptop question")
        self.memory.add_memory("Owner laptop has 8 GB RAM", category="device")
        note = self.memory.create_note("Shopping", "Buy rice")

        reopened = MemoryStore(self.root / "data" / "test.db")
        self.assertEqual(reopened.list_messages(conversation["id"])[0]["content"], "My laptop question")
        self.assertEqual(reopened.search_memories("laptop RAM")[0]["category"], "device")
        self.assertEqual(reopened.get_note(note["id"])["body"], "Buy rice")
        self.assertEqual(reopened.relevant_context("laptop")[0]["type"], "memory")


class SkillTests(CoreTestCase):
    def test_workspace_write_read_and_path_escape_blocked(self):
        result = self.registry.execute(
            "workspace.write_text",
            {"path": "hello.txt", "content": "hello MYRA"},
            context=self.context,
        )
        self.assertTrue(result["verified"])
        read = self.registry.execute(
            "workspace.read_text", {"path": "hello.txt"}, context=self.context
        )
        self.assertEqual(read["result"]["content"], "hello MYRA")
        with self.assertRaises(SkillError):
            self.registry.execute(
                "workspace.read_text", {"path": "../secret.txt"}, context=self.context
            )

    def test_unknown_argument_is_rejected(self):
        with self.assertRaises(SkillError):
            self.registry.execute("time.now", {"surprise": True}, context=self.context)

    def test_organize_dry_run_does_not_move(self):
        (self.workspace / "a.txt").write_text("a", encoding="utf-8")
        result = self.registry.execute(
            "workspace.organize_by_extension", {"dry_run": True}, context=self.context
        )
        self.assertEqual(result["result"]["count"], 1)
        self.assertTrue((self.workspace / "a.txt").exists())
        self.assertFalse((self.workspace / "txt" / "a.txt").exists())


class AgentTests(CoreTestCase):
    def test_confirmation_then_verified_completion(self):
        def fake_planner(task, definitions):
            if not any(event.get("type") == "tool_result" for event in task["transcript"]):
                return PlannerDecision(
                    kind="tool_call",
                    tool_call=ToolCall(
                        "call-1",
                        "workspace.write_text",
                        {"path": "agent.txt", "content": "agent verified"},
                    ),
                    provider="fake",
                    model="fake-planner",
                )
            return PlannerDecision(
                kind="final", text="Finished after verification.", provider="fake", model="fake"
            )

        engine = AgentEngine(self.memory, self.registry, planner=fake_planner)
        task = engine.create_task("Create a verified text file")
        engine.start_task(task["id"], background=False)
        waiting = engine.get_task(task["id"])
        self.assertEqual(waiting["status"], "awaiting_confirmation")
        self.assertFalse((self.workspace / "agent.txt").exists())

        engine.approve_pending(task["id"])
        for _ in range(50):
            current = engine.get_task(task["id"])
            if current["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.05)
        self.assertEqual(current["status"], "completed")
        self.assertEqual((self.workspace / "agent.txt").read_text(encoding="utf-8"), "agent verified")
        self.assertTrue(current["steps"][0]["result"]["verified"])


class ProviderAndServiceTests(CoreTestCase):
    def test_tool_schema_conversion(self):
        definitions = self.registry.definitions(enabled_only=True)
        gemini_tools = providers.tool_schemas(definitions, "gemini")
        groq_tools = providers.tool_schemas(definitions, "groq")
        self.assertIn("workspace_write_text", {tool["name"] for tool in gemini_tools})
        self.assertIn(
            "workspace_write_text",
            {tool["function"]["name"] for tool in groq_tools},
        )
        write_tool = next(tool for tool in gemini_tools if tool["name"] == "workspace_write_text")
        self.assertEqual(write_tool["parameters"]["type"], "OBJECT")

    def test_service_chat_persists_and_vision_requires_consent(self):
        service = MyraService(memory_store=self.memory, registry=self.registry)
        with mock.patch.object(service_module.chat, "get_reply") as fake_reply:
            fake_reply.return_value = {
                "ok": True,
                "reply": "Hello Boss",
                "provider": "fake",
                "model": "fake-model",
                "used_fallback": False,
            }
            result = service.chat({"message": "Hello"})
        self.assertEqual(result["reply"], "Hello Boss")
        messages = self.memory.list_messages(result["conversation_id"])
        self.assertEqual([m["role"] for m in messages], ["user", "assistant"])

        with self.assertRaises(PermissionError):
            service.analyze_image(
                {"image_base64": "aGVsbG8=", "mime_type": "image/jpeg", "consent": False}
            )
        with self.assertRaises(ValueError):
            service.analyze_image(
                {"image_base64": "not base64!", "mime_type": "image/jpeg", "consent": True}
            )


class VoiceModelManagerTests(CoreTestCase):
    def test_download_requires_confirmation_and_verifies_checksum(self):
        manager = VoiceModelManager(self.root / "data")
        self.assertFalse(manager.status()["realtime_voice_ready"])
        payload = b"fake voice model for checksum test"
        manifest = {
            "engine": "test-engine",
            "model_id": "tiny",
            "url": "https://example.invalid/tiny.bin",
            "filename": "tiny.bin",
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        with self.assertRaises(VoiceModelError):
            manager.download_model(manifest, confirmed=False)
        record = manager.download_model(
            manifest,
            confirmed=True,
            opener=lambda url, timeout=60: io.BytesIO(payload),
        )
        self.assertTrue(Path(record["path"]).exists())
        self.assertEqual(manager.status()["installed"][0]["model_id"], "tiny")
        removed = manager.remove_model_record("test-engine", "tiny", delete_file=True)
        self.assertFalse(Path(removed["path"]).exists())


class ConfigTests(unittest.TestCase):
    def test_env_secret_fallback_never_returns_full_key_in_status(self):
        with tempfile.TemporaryDirectory() as folder:
            env_path = Path(folder) / ".env"
            with mock.patch.object(config, "ENV_PATH", env_path), mock.patch.object(
                config, "ENV_EXAMPLE", Path(folder) / "missing"
            ), mock.patch.dict(os.environ, {"MYRA_SECRET_STORE": "env"}, clear=True):
                status = config.save_keys(gemini="fake-gemini-key-1234")
                self.assertTrue(status["gemini"]["set"])
                self.assertEqual(status["gemini"]["masked"], "••••1234")
                self.assertNotIn("fake-gemini-key", json.dumps(status))
                self.assertEqual(config.gemini_key(), "fake-gemini-key-1234")


if __name__ == "__main__":
    unittest.main()
