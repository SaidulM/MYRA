import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import chat  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class ChatTests(unittest.TestCase):
    def payload(self):
        return {
            "messages": [{"role": "user", "text": "Hello MYRA"}],
            "character": "female",
            "personality": "Warm & friendly",
            "assistant_name": "MYRA",
            "owner_name": "Saidul",
        }

    def test_normalize_messages_merges_and_drops_leading_assistant(self):
        messages = chat.normalize_messages(
            [
                {"role": "assistant", "text": "old greeting"},
                {"role": "user", "text": "Hello"},
                {"role": "user", "text": "How are you?"},
            ]
        )
        self.assertEqual(
            messages,
            [{"role": "user", "text": "Hello\n\nHow are you?"}],
        )

    def test_missing_keys_returns_safe_error(self):
        with patch.object(chat.config, "gemini_key", return_value=""), patch.object(
            chat.config, "groq_key", return_value=""
        ):
            with self.assertRaises(chat.ChatError) as caught:
                chat.get_reply(self.payload())
        self.assertEqual(caught.exception.code, "missing_keys")
        self.assertIn("no API key is saved yet", caught.exception.message)

    def test_gemini_success(self):
        def opener(request, timeout):
            self.assertIn("generativelanguage.googleapis.com", request.full_url)
            return FakeResponse(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [{"text": "Hello! I am ready."}],
                            }
                        }
                    ]
                }
            )

        with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-test"}), patch.object(
            chat.config, "gemini_key", return_value="fake-gemini-key"
        ), patch.object(chat.config, "groq_key", return_value=""):
            result = chat.get_reply(self.payload(), opener=opener)

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "gemini")
        self.assertEqual(result["model"], "gemini-test")
        self.assertEqual(result["reply"], "Hello! I am ready.")

    def test_groq_fallback_when_gemini_network_fails(self):
        calls = []

        def opener(request, timeout):
            calls.append(request.full_url)
            if "generativelanguage.googleapis.com" in request.full_url:
                raise URLError("simulated offline")
            self.assertIn("api.groq.com", request.full_url)
            return FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "Backup brain is here.",
                            }
                        }
                    ]
                }
            )

        with patch.dict(
            os.environ,
            {"GEMINI_MODEL": "gemini-test", "GROQ_MODEL": "groq-test"},
        ), patch.object(
            chat.config, "gemini_key", return_value="fake-gemini-key"
        ), patch.object(
            chat.config, "groq_key", return_value="fake-groq-key"
        ):
            result = chat.get_reply(self.payload(), opener=opener)

        self.assertEqual(len(calls), 2)
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "groq")
        self.assertTrue(result["fallback"])
        self.assertEqual(result["reply"], "Backup brain is here.")


if __name__ == "__main__":
    unittest.main()
