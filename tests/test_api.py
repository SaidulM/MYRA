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

import config  # noqa: E402
import server  # noqa: E402
import service as service_module  # noqa: E402
from memory import MemoryStore  # noqa: E402
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

        self.old_get_service = server.get_service
        self.old_host = server.HOST
        self.old_env_path = config.ENV_PATH
        self.old_env_example = config.ENV_EXAMPLE
        server.get_service = lambda: self.service
        server.HOST = "127.0.0.1"
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
        server.get_service = self.old_get_service
        server.HOST = self.old_host
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

    def test_vision_refuses_without_explicit_consent(self):
        status, data = self.call(
            "POST",
            "/api/v1/vision/analyze",
            {"image_base64": "aGVsbG8=", "mime_type": "image/jpeg", "consent": False},
        )
        self.assertEqual(status, 403)
        self.assertIn("explicit consent", data["error"])


if __name__ == "__main__":
    unittest.main()
