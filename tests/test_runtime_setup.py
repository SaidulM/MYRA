import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import config  # noqa: E402
import runtime_setup  # noqa: E402
import voice_studio  # noqa: E402
from voice_engine import VoiceEngine  # noqa: E402


EMPTY_KEY_STATUS = {
    name: {"set": False, "masked": "", "model": "auto", "storage": "not-set"}
    for name in ("gemini", "groq", "openrouter", "openai", "anthropic", "deepseek", "mistral")
}
EMPTY_KEY_STATUS["ollama"] = {
    "set": False,
    "url": "http://127.0.0.1:11434",
    "model": "",
    "running": False,
    "model_installed": False,
}
EMPTY_KEY_STATUS["secret_backend"] = "local-.env"


class FakeOllamaResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(
            {"models": [{"name": "llama3.2:latest"}, {"name": "qwen2.5:3b"}]}
        ).encode("utf-8")


class RuntimeSetupTests(unittest.TestCase):
    def test_ensure_runtime_files_creates_everything_and_persists_ui_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data_dir = root / "data"
            env_path = root / "install" / ".env"
            with mock.patch.object(
                runtime_setup.config, "key_status", return_value=dict(EMPTY_KEY_STATUS)
            ):
                status = runtime_setup.ensure_runtime_files(
                    data_dir=data_dir, env_path=env_path, create_env=True
                )

            self.assertTrue(status["ok"])
            self.assertTrue((data_dir / "myra.db").exists())
            self.assertTrue(env_path.exists())
            for relative in (
                "workspace",
                "models/faster-whisper",
                "voice_cache",
                "voice-temp",
                "backups",
                "logs",
                "webview-profile",
                "attachments",
            ):
                self.assertTrue((data_dir / relative).is_dir(), relative)
            self.assertTrue((data_dir / "news_cache.json").exists())
            self.assertTrue((data_dir / "feedback.jsonl").exists())
            self.assertTrue((data_dir / "runtime-status.json").exists())

            settings = runtime_setup.get_ui_settings(data_dir=data_dir)
            self.assertEqual(settings["settings"]["response_style"], "auto")
            self.assertEqual(settings["stored_settings"]["assistant_name"], "MYRA")

            saved = runtime_setup.save_ui_settings(
                {
                    "theme": "hacker",
                    "response_style": "detailed",
                    "voice_pitch": 99,
                    "brain_provider": "not-a-provider",
                    "unknown_setting": "ignored",
                },
                data_dir=data_dir,
            )
            self.assertEqual(saved["theme"], "hacker")
            self.assertEqual(saved["response_style"], "detailed")
            self.assertEqual(saved["voice_pitch"], 2.0)
            self.assertEqual(saved["brain_provider"], "auto")
            self.assertNotIn("unknown_setting", saved)

            record = runtime_setup.append_feedback(
                "  MYRA feels faster now  ", source="test", data_dir=data_dir
            )
            self.assertEqual(record["text"], "MYRA feels faster now")
            lines = (data_dir / "feedback.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(json.loads(lines[-1])["source"], "test")

    def test_runtime_status_reports_loopback_and_https_modes_honestly(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data_dir = root / "data"
            env_path = root / ".env"
            with mock.patch.object(
                runtime_setup.config, "key_status", return_value=dict(EMPTY_KEY_STATUS)
            ):
                runtime_setup.ensure_runtime_files(
                    data_dir=data_dir, env_path=env_path, create_env=False
                )
                local = runtime_setup.runtime_status(
                    data_dir=data_dir, env_path=env_path, host="127.0.0.1", scheme="http"
                )
                lan = runtime_setup.runtime_status(
                    data_dir=data_dir, env_path=env_path, host="0.0.0.0", scheme="https"
                )

            local_checks = {item["id"]: item for item in local["checks"]}
            self.assertEqual(local_checks["local_connection"]["status"], "ready")
            self.assertEqual(local_checks["phone_link"]["status"], "optional")
            self.assertEqual(local["backend"]["mode"], "Safe local-only mode")

            lan_checks = {item["id"]: item for item in lan["checks"]}
            self.assertEqual(lan_checks["local_connection"]["status"], "ready")
            self.assertEqual(lan_checks["phone_link"]["status"], "ready")
            self.assertTrue(lan["backend"]["lan_enabled"])

    def test_ollama_status_checks_tags_and_saved_model(self):
        config._OLLAMA_STATUS_CACHE.update({"key": None, "at": 0.0, "value": None})

        def fake_get(name, default=""):
            return {
                "OLLAMA_MODEL": "llama3.2",
                config.OLLAMA_URL: "http://127.0.0.1:11434",
            }.get(name, default)

        def fake_opener(request, timeout):
            self.assertEqual(timeout, 0.35)
            self.assertTrue(request.full_url.endswith("/api/tags"))
            return FakeOllamaResponse()

        with mock.patch.object(config, "get", side_effect=fake_get):
            status = config.ollama_status(opener=fake_opener)
        self.assertTrue(status["set"])
        self.assertTrue(status["running"])
        self.assertTrue(status["model_installed"])
        self.assertIn("qwen2.5:3b", status["installed_models"])


class VoiceSpeedTests(unittest.TestCase):
    def test_spoken_text_is_short_by_default_and_longer_when_detailed(self):
        reply = (
            "Sure. The main answer is ready. This is the second sentence. "
            "Third sentence should wait. Fourth sentence. Fifth sentence. "
            "Sources: this appendix must not be read aloud."
        )
        short = voice_studio.speech_text_for_reply(reply)
        detailed = voice_studio.speech_text_for_reply(reply, detailed=True)
        self.assertEqual(short, "The main answer is ready. This is the second sentence.")
        self.assertIn("Fifth sentence.", detailed)
        self.assertNotIn("appendix", detailed)

    def test_voice_warmup_loads_existing_model_in_background_without_download(self):
        loaded = threading.Event()

        class FakeTranscriber:
            _model = None

            def _load(self):
                self._model = object()
                loaded.set()
                return self._model

        class FakeManager:
            def find_installed(self, engine="faster-whisper"):
                return []

            def status(self):
                return {"pipeline_ready": False}

        fake = FakeTranscriber()
        engine = VoiceEngine(model_manager=FakeManager(), transcriber=fake)
        result = engine.warmup()
        self.assertTrue(result["ok"])
        self.assertTrue(result["started"])
        self.assertTrue(loaded.wait(timeout=2))
        engine._warmup_thread.join(timeout=2)
        self.assertTrue(engine.status()["transcriber_loaded"])


class UiWiringTests(unittest.TestCase):
    def test_new_ui_controls_have_backend_and_js_wiring(self):
        html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
        for element_id in (
            "responseLengthSelect",
            "mistralKey",
            "mistralKeyStatus",
            "removeMistral",
            "ollamaKeyStatus",
            "refreshReadiness",
            "repairReadiness",
            "readinessSummary",
            "readinessList",
            "skillLibraryStatus",
            "refreshSkillLibrary",
            "mobileLinkNote",
        ):
            self.assertIn(f'id="{element_id}"', html)
            self.assertIn(element_id, js)
        self.assertIn("/api/settings/ui", js)
        self.assertIn("/api/system/readiness", js)
        self.assertIn("/api/feedback", js)
        self.assertIn("/api/v1/voice/warmup", js)
        self.assertIn("response_style: localStorage.getItem('myra_response_style')", js)
        self.assertIn("{ image }", js)
        self.assertNotIn("Add New Skill", html)
        self.assertNotIn("Real vision arrives in Stage 9", js)


if __name__ == "__main__":
    unittest.main()
