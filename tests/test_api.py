import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import api_v1  # noqa: E402
import config  # noqa: E402
import server  # noqa: E402
import service as service_module  # noqa: E402
from core_memory import MemoryStore  # noqa: E402
from service import MyraService  # noqa: E402
from skill_registry import build_default_registry  # noqa: E402


class ApiIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env_patch = mock.patch.dict(
            os.environ,
            {"MYRA_DATA_DIR": str(self.root / "data"), "MYRA_SECRET_STORE": "env"},
            clear=False,
        )
        self.env_patch.start()
        self.old_gemini_env = os.environ.pop("GEMINI_API_KEY", None)
        self.old_groq_env = os.environ.pop("GROQ_API_KEY", None)

        memory = MemoryStore(self.root / "data" / "api.db")
        registry = build_default_registry(memory)
        self.service = MyraService(memory_store=memory, registry=registry)

        self.old_get_service = api_v1.get_service
        self.old_env_path = config.ENV_PATH
        self.old_env_example = config.ENV_EXAMPLE
        api_v1.get_service = lambda: self.service
        config.ENV_PATH = self.root / ".env"
        config.ENV_EXAMPLE = self.root / "missing.env.example"

        self.http = ThreadingHTTPServer(
            ("127.0.0.1", 0), partial(server.MyraHandler, directory=str(ROOT / "ui"))
        )
        self.port = self.http.server_address[1]
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=3)
        api_v1.get_service = self.old_get_service
        config.ENV_PATH = self.old_env_path
        config.ENV_EXAMPLE = self.old_env_example
        if self.old_gemini_env is not None:
            os.environ["GEMINI_API_KEY"] = self.old_gemini_env
        if self.old_groq_env is not None:
            os.environ["GROQ_API_KEY"] = self.old_groq_env
        self.env_patch.stop()
        self.tmp.cleanup()

    def call(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    def test_old_settings_field_names_are_accepted_and_confirmed(self):
        status, data = self.call(
            "POST", "/api/settings/keys", {"gemini_key": "AIzaFakeIntegration1234"}
        )
        self.assertEqual(status, 200)
        self.assertTrue(data["keys"]["gemini"]["set"])
        self.assertEqual(data["keys"]["gemini"]["masked"], "••••1234")
        self.assertNotIn("AIzaFakeIntegration", json.dumps(data))

        status, data = self.call("GET", "/api/settings/keys")
        self.assertEqual(status, 200)
        self.assertTrue(data["gemini"]["set"])

        status, data = self.call("POST", "/api/settings/remove", {"which": "gemini"})
        self.assertEqual(status, 200)
        self.assertFalse(data["keys"]["gemini"]["set"])

    def test_api_v1_memory_note_skill_confirmation_and_chat(self):
        status, data = self.call(
            "POST", "/api/v1/memories", {"text": "Owner uses an 8 GB laptop", "category": "device"}
        )
        self.assertEqual(status, 201)
        self.assertEqual(data["memory"]["category"], "device")

        status, data = self.call("POST", "/api/v1/notes", {"title": "API note", "body": "Saved"})
        self.assertEqual(status, 201)
        self.assertEqual(data["note"]["body"], "Saved")

        status, data = self.call(
            "POST",
            "/api/v1/skills/workspace.write_text/run",
            {"arguments": {"path": "api.txt", "content": "hello"}, "confirmed": False},
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "confirmation_required")

        with mock.patch.object(service_module.chat, "get_reply") as reply:
            reply.return_value = {
                "ok": True,
                "reply": "Hello from fake provider",
                "provider": "fake",
                "provider_label": "Fake",
                "model": "fake-1",
            }
            status, data = self.call("POST", "/api/v1/chat", {"message": "Hello MYRA"})
        self.assertEqual(status, 200)
        self.assertEqual(data["reply"], "Hello from fake provider")
        status, data = self.call("GET", f"/api/v1/conversations/{data['conversation_id']}")
        self.assertEqual(len(data["conversation"]["messages"]), 2)

    def test_runtime_settings_readiness_feedback_and_network_endpoints(self):
        status, data = self.call(
            "POST",
            "/api/settings/ui",
            {"settings": {"theme": "friendly", "response_style": "short", "voice_pitch": 1.2}},
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["settings"]["theme"], "friendly")
        self.assertEqual(data["settings"]["response_style"], "short")

        status, data = self.call("GET", "/api/settings/ui")
        self.assertEqual(status, 200)
        self.assertEqual(data["stored_settings"]["theme"], "friendly")

        status, data = self.call(
            "POST", "/api/settings/keys", {"mistral_key": "mistral-fake-secret-1234"}
        )
        self.assertEqual(status, 200)
        self.assertTrue(data["keys"]["mistral"]["set"])
        self.assertNotIn("mistral-fake-secret", json.dumps(data))

        status, data = self.call("POST", "/api/system/readiness/ensure", {})
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        check_ids = {item["id"] for item in data["checks"]}
        self.assertTrue({"database", "ui_settings", "workspace", "feedback", "external_https"}.issubset(check_ids))
        self.assertNotIn("mistral-fake-secret", json.dumps(data))
        data_dir = self.root / "data"
        self.assertTrue((data_dir / "myra.db").exists())
        self.assertTrue((data_dir / "workspace").is_dir())
        self.assertTrue((data_dir / "voice_cache").is_dir())
        self.assertTrue((data_dir / "feedback.jsonl").exists())

        status, data = self.call(
            "POST", "/api/feedback", {"text": "Readiness endpoint works", "source": "test"}
        )
        self.assertEqual(status, 201)
        self.assertEqual(data["feedback"]["text"], "Readiness endpoint works")
        self.assertIn("Readiness endpoint works", (data_dir / "feedback.jsonl").read_text(encoding="utf-8"))

        status, data = self.call("GET", "/api/system/network-info")
        self.assertEqual(status, 200)
        self.assertFalse(data["lan_enabled"])
        self.assertEqual(data["mobile_url"], "")
        self.assertEqual(data["scheme"], "http")

        status, data = self.call("POST", "/api/v1/voice/warmup", {})
        self.assertEqual(status, 200)
        self.assertIn("warmup", data)
        self.assertFalse(data["warmup"]["started"])

        with mock.patch.object(
            server.chat,
            "verify_key_connection",
            return_value={"gemini": {"ok": True, "model": "gemini-fake"}},
        ):
            status, data = self.call(
                "POST", "/api/settings/verify", {"gemini_key": "fake-key-for-test"}
            )
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["results"]["gemini"]["model"], "gemini-fake")

        with mock.patch.object(server.chat, "verify_key_connection", return_value={}):
            status, data = self.call("POST", "/api/settings/verify", {})
        self.assertEqual(status, 503)
        self.assertFalse(data["ok"])
        self.assertEqual(data["results"], {})

    def test_vision_refuses_without_explicit_consent(self):
        status, data = self.call(
            "POST",
            "/api/v1/vision/analyze",
            {"image_base64": "aGVsbG8=", "mime_type": "image/jpeg", "consent": False},
        )
        self.assertEqual(status, 403)
        self.assertIn("explicit consent", data["error"])


class ApiTokenScopeTests(unittest.TestCase):
    """MYRA_API_TOKEN gates other devices, never MYRA's own local screen."""

    def _handler(self, client_host, bind_host="0.0.0.0", token_header=""):
        handler = object.__new__(api_v1.CoreApiMixin)
        handler.client_address = (client_host, 51234)
        handler.headers = {"X-MYRA-Token": token_header} if token_header else {}

        class _Server:
            server_address = (bind_host, 8765)

        handler.server = _Server()
        return handler

    def test_loopback_client_allowed_even_with_token_set(self):
        handler = self._handler("127.0.0.1")
        with mock.patch.object(
            api_v1.config, "get", side_effect=lambda name, default="": "s3cret" if name == "MYRA_API_TOKEN" else default
        ):
            self.assertTrue(handler._api_v1_authorized("POST", "/api/v1/chat"))
            self.assertTrue(handler._api_v1_full_access())

    def test_lan_client_needs_token_header_for_actions(self):
        handler = self._handler("192.168.1.40")
        with mock.patch.object(
            api_v1.config, "get", side_effect=lambda name, default="": "s3cret" if name == "MYRA_API_TOKEN" else default
        ):
            self.assertFalse(handler._api_v1_authorized("POST", "/api/v1/chat"))
            self.assertFalse(handler._api_v1_full_access())
        with_token = self._handler("192.168.1.40", token_header="s3cret")
        with mock.patch.object(
            api_v1.config, "get", side_effect=lambda name, default="": "s3cret" if name == "MYRA_API_TOKEN" else default
        ):
            self.assertTrue(with_token._api_v1_authorized("POST", "/api/v1/chat"))

    def test_lan_client_without_token_configured_gets_only_public_gets(self):
        handler = self._handler("192.168.1.40")
        with mock.patch.object(api_v1.config, "get", side_effect=lambda name, default="": default):
            self.assertTrue(handler._api_v1_authorized("GET", "/api/v1/health"))
            self.assertFalse(handler._api_v1_authorized("POST", "/api/v1/chat"))


if __name__ == "__main__":
    unittest.main()
