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

    def test_gemini_auto_model_discovery(self):
        def fake_discovery_opener(request, timeout):
            if "models" in request.full_url:
                return FakeResponse({
                    "models": [
                        {"name": "models/gemini-pro", "supportedGenerationMethods": ["generateContent"]},
                        {"name": "models/gemini-1.5-pro", "supportedGenerationMethods": ["generateContent"]},
                        {"name": "models/gemini-1.5-flash", "supportedGenerationMethods": ["generateContent"]},
                        {"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]},
                    ]
                })
            return FakeResponse({})

        models = chat.discover_gemini_models("test-key-123", opener=fake_discovery_opener)
        self.assertIn("gemini-1.5-flash", models)
        self.assertIn("gemini-1.5-pro", models)
        self.assertNotIn("embedding-001", models)
        # Verify 1.5-flash is prioritized first
        self.assertEqual(models[0], "gemini-1.5-flash")

    def test_gemini_fallback_on_model_unavailable(self):
        attempts = []

        def fallback_opener(request, timeout):
            attempts.append(request.full_url)
            if "gemini-1.5-flash" in request.full_url:
                # Simulate 404 model not found
                import urllib.error
                raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)
            if "gemini-1.5-pro" in request.full_url:
                return FakeResponse({
                    "candidates": [{"content": {"parts": [{"text": "Hello from Gemini 1.5 Pro!"}]}}]
                })
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

        with patch.object(chat, "_models_for", return_value=("gemini-1.5-flash", "gemini-1.5-pro")), patch.object(
            chat.config, "gemini_key", return_value="fake-gemini-key"
        ), patch.object(chat.config, "groq_key", return_value=""):
            result = chat.get_reply(self.payload(), opener=fallback_opener)

        self.assertTrue(result["ok"])
        self.assertEqual(result["model"], "gemini-1.5-pro")
        self.assertEqual(result["reply"], "Hello from Gemini 1.5 Pro!")
        self.assertEqual(len(attempts), 2)

    def test_groq_auto_model_discovery(self):
        def fake_groq_opener(request, timeout):
            if "openai/v1/models" in request.full_url:
                return FakeResponse({
                    "data": [
                        {"id": "whisper-large-v3"},
                        {"id": "gemma2-9b-it"},
                        {"id": "llama-3.1-8b-instant"},
                        {"id": "llama-3.3-70b-versatile"},
                        {"id": "distil-whisper"},
                    ]
                })
            return FakeResponse({})

        models = chat.discover_groq_models("fake-groq-key-discovery", opener=fake_groq_opener)
        self.assertIn("llama-3.3-70b-versatile", models)
        self.assertIn("llama-3.1-8b-instant", models)
        self.assertIn("gemma2-9b-it", models)
        self.assertNotIn("whisper-large-v3", models)
        self.assertNotIn("distil-whisper", models)
        # Verify llama-3.3-70b-versatile is prioritized first
        self.assertEqual(models[0], "llama-3.3-70b-versatile")

    def test_gemini_fallback_on_provider_busy(self):
        attempts = []

        def fallback_opener(request, timeout):
            attempts.append(request.full_url)
            import urllib.error
            if "gemini-1.5-flash" in request.full_url:
                # 503 Provider Busy / overloaded
                raise urllib.error.HTTPError(request.full_url, 503, "Service Unavailable", {}, None)
            if "gemini-1.5-pro" in request.full_url:
                return FakeResponse({
                    "candidates": [{"content": {"parts": [{"text": "Hello from Gemini 1.5 Pro!"}]}}]
                })
            raise urllib.error.HTTPError(request.full_url, 503, "Service Unavailable", {}, None)

        with patch.object(chat, "_models_for", return_value=("gemini-1.5-flash", "gemini-1.5-pro")), patch.object(
            chat.config, "gemini_key", return_value="fake-gemini-key"
        ), patch.object(chat.config, "groq_key", return_value=""):
            result = chat.get_reply(self.payload(), opener=fallback_opener)

        self.assertTrue(result["ok"])
        self.assertEqual(result["model"], "gemini-1.5-pro")
        self.assertEqual(result["reply"], "Hello from Gemini 1.5 Pro!")
        self.assertEqual(len(attempts), 2)

    def test_seamless_failover_gemini_to_groq_on_503(self):
        calls = []

        def opener(request, timeout):
            calls.append(request.full_url)
            import urllib.error
            if "generativelanguage.googleapis.com" in request.full_url:
                # All Gemini models overloaded
                raise urllib.error.HTTPError(request.full_url, 503, "Service Unavailable", {}, None)
            if "api.groq.com" in request.full_url:
                return FakeResponse({
                    "choices": [{"message": {"content": "Groq took over seamlessly."}}]
                })
            raise urllib.error.HTTPError(request.full_url, 500, "Internal Server Error", {}, None)

        with patch.object(chat, "_models_for", side_effect=lambda p, *args, **kw: ("gemini-1.5-flash",) if p == "gemini" else ("llama-3.3-70b-versatile",)), patch.object(
            chat.config, "gemini_key", return_value="fake-gemini-key"
        ), patch.object(chat.config, "groq_key", return_value="fake-groq-key"):
            result = chat.get_reply(self.payload(), opener=opener)

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "groq")
        self.assertTrue(result["fallback"])
        self.assertEqual(result["reply"], "Groq took over seamlessly.")
        self.assertIn("temporarily unavailable", result.get("notice", ""))

    def explicit_payload(self, provider):
        payload = self.payload()
        payload.update({
            "provider": provider,
            "allow_local_intent": False,
            "auto_learn": False,
        })
        return payload

    def test_explicit_ollama_missing_model_never_falls_back_to_gemini(self):
        with patch.object(chat.config, "gemini_key", return_value="fake-gemini-key"), patch.object(
            chat.config, "groq_key", return_value=""
        ), patch.object(chat.config, "openrouter_key", return_value=""), patch.object(
            chat.config, "openai_key", return_value=""
        ), patch.object(chat.config, "deepseek_key", return_value=""), patch.object(
            chat.config, "mistral_key", return_value=""
        ), patch.object(chat.config, "ollama_model", return_value=""), patch.object(
            chat, "_call_gemini", side_effect=AssertionError("Gemini must not be called")
        ):
            with self.assertRaises(chat.ChatError) as caught:
                chat.get_reply(self.explicit_payload("ollama"))
        self.assertEqual(caught.exception.code, "provider_not_configured")
        self.assertEqual(caught.exception.provider, "ollama")
        self.assertIn("will not silently switch to Gemini", caught.exception.message)

    def test_explicit_ollama_unreachable_is_reported_as_ollama(self):
        with patch.object(chat.config, "gemini_key", return_value="fake-gemini-key"), patch.object(
            chat.config, "groq_key", return_value=""
        ), patch.object(chat.config, "openrouter_key", return_value=""), patch.object(
            chat.config, "openai_key", return_value=""
        ), patch.object(chat.config, "deepseek_key", return_value=""), patch.object(
            chat.config, "mistral_key", return_value=""
        ), patch.object(chat.config, "ollama_model", return_value="llama3.2"), patch.object(
            chat.config, "ollama_url", return_value="http://127.0.0.1:11434"
        ), patch.object(
            chat,
            "_call_openai_compatible",
            side_effect=chat.ChatError("network", "Could not reach ollama", provider="ollama", status=503),
        ), patch.object(chat, "_call_gemini", side_effect=AssertionError("Gemini must not be called")):
            with self.assertRaises(chat.ChatError) as caught:
                chat.get_reply(self.explicit_payload("ollama"))
        self.assertEqual(caught.exception.code, "provider_unreachable")
        self.assertEqual(caught.exception.provider, "ollama")
        self.assertIn("Start the Ollama app", caught.exception.message)

    def test_explicit_ollama_success_is_labeled_ollama(self):
        with patch.object(chat.config, "gemini_key", return_value="fake-gemini-key"), patch.object(
            chat.config, "groq_key", return_value=""
        ), patch.object(chat.config, "openrouter_key", return_value=""), patch.object(
            chat.config, "openai_key", return_value=""
        ), patch.object(chat.config, "deepseek_key", return_value=""), patch.object(
            chat.config, "mistral_key", return_value=""
        ), patch.object(chat.config, "ollama_model", return_value="llama3.2"), patch.object(
            chat.config, "ollama_url", return_value="http://127.0.0.1:11434"
        ), patch.object(
            chat, "_call_openai_compatible", return_value=("Local brain reply", "llama3.2")
        ), patch.object(chat, "_call_gemini", side_effect=AssertionError("Gemini must not be called")):
            result = chat.get_reply(self.explicit_payload("ollama"))
        self.assertEqual(result["provider"], "ollama")
        self.assertEqual(result["provider_label"], "Ollama Local AI")
        self.assertEqual(result["reply"], "Local brain reply")

    def test_explicit_ollama_receives_attached_image(self):
        captured = {}

        def fake_compatible(messages, system_prompt, api_key, endpoint_url, models, provider, opener, image=None, max_output_tokens=None):
            captured["provider"] = provider
            captured["image"] = image
            captured["endpoint"] = endpoint_url
            return ("I can see the frame.", models[0])

        payload = self.explicit_payload("ollama")
        payload["image"] = "data:image/jpeg;base64,QUJD"
        with patch.object(chat.config, "gemini_key", return_value="fake-gemini-key"), patch.object(
            chat.config, "groq_key", return_value=""
        ), patch.object(chat.config, "openrouter_key", return_value=""), patch.object(
            chat.config, "openai_key", return_value=""
        ), patch.object(chat.config, "deepseek_key", return_value=""), patch.object(
            chat.config, "mistral_key", return_value=""
        ), patch.object(chat.config, "ollama_model", return_value="llava"), patch.object(
            chat.config, "ollama_url", return_value="http://127.0.0.1:11434"
        ), patch.object(chat, "_call_openai_compatible", side_effect=fake_compatible), patch.object(
            chat, "_call_gemini", side_effect=AssertionError("Gemini must not be called")
        ):
            result = chat.get_reply(payload)
        self.assertEqual(result["provider"], "ollama")
        self.assertEqual(captured["provider"], "ollama")
        self.assertEqual(captured["image"], "data:image/jpeg;base64,QUJD")
        self.assertTrue(captured["endpoint"].endswith("/v1/chat/completions"))

    def test_response_style_short_by_default_and_detailed_only_when_asked(self):
        cases = [
            ("আজকের আবহাওয়া কেমন?", "auto", "short"),
            ("বেশি করে বলো", "auto", "detailed"),
            ("একটু বড় করে বলো", "short", "detailed"),
            ("ভালো করে বুঝিয়ে বলো", "auto", "detailed"),
            ("Please explain in detail", "auto", "detailed"),
            ("সংক্ষেপে বলো", "detailed", "short"),
            ("Tell me about Dhaka", "detailed", "detailed"),
            ("Tell me about Dhaka", "short", "short"),
        ]
        for text, saved_style, expected in cases:
            with self.subTest(text=text, saved_style=saved_style):
                payload = {
                    "messages": [{"role": "user", "text": text}],
                    "response_style": saved_style,
                }
                self.assertEqual(chat.response_style_for_payload(payload), expected)
        self.assertEqual(chat.output_token_budget("short"), 220)
        self.assertEqual(chat.output_token_budget("detailed"), 1200)

    def test_gemini_request_uses_short_or_detailed_token_budget(self):
        seen_budgets = []

        def opener(request, timeout):
            body = json.loads(request.data.decode("utf-8"))
            seen_budgets.append(body["generationConfig"]["maxOutputTokens"])
            return FakeResponse(
                {"candidates": [{"content": {"parts": [{"text": "Short main answer."}]}}]}
            )

        for text, expected_style, expected_budget in [
            ("Hello MYRA", "short", 220),
            ("ভালো করে বুঝিয়ে বলো", "detailed", 1200),
        ]:
            payload = self.payload()
            payload["messages"] = [{"role": "user", "text": text}]
            payload.update({
                "response_style": "auto",
                "allow_local_intent": False,
                "auto_learn": False,
            })
            with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-test"}), patch.object(
                chat.config, "gemini_key", return_value="fake-gemini-key"
            ), patch.object(chat.config, "groq_key", return_value=""):
                result = chat.get_reply(payload, opener=opener)
            self.assertEqual(result["response_style"], expected_style)
            self.assertEqual(seen_budgets[-1], expected_budget)


if __name__ == "__main__":
    unittest.main()
