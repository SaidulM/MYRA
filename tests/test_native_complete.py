import array
import base64
import json
import math
import os
import sqlite3
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

import api_v1  # noqa: E402
import memory as legacy_memory  # noqa: E402
import notes as legacy_notes  # noqa: E402
import reminders as legacy_reminders  # noqa: E402
import providers  # noqa: E402
import research  # noqa: E402
import server  # noqa: E402
import service as service_module  # noqa: E402
from browser_control import BrowserController, detect_blocking_challenge  # noqa: E402
from core_memory import MemoryStore  # noqa: E402
from desktop.hologram_geometry import build_point_clouds, interpolate  # noqa: E402
from desktop.voice_tools import VoiceActivitySegmenter as DesktopSegmenter  # noqa: E402
from desktop.voice_tools import wav_bytes as desktop_wav_bytes  # noqa: E402
from live_vision import LiveVisionError, LiveVisionManager  # noqa: E402
from service import MyraService  # noqa: E402
from skill_registry import build_default_registry  # noqa: E402
from voice_engine import RealtimeVoiceSession, VoiceActivitySegmenter, wav_bytes  # noqa: E402
from windows_control import WindowsControlError, WindowsController  # noqa: E402


class UnifiedDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_paths = (legacy_memory.DB_PATH, legacy_notes.DB_PATH, legacy_reminders.DB_PATH)

    def tearDown(self):
        legacy_memory.DB_PATH, legacy_notes.DB_PATH, legacy_reminders.DB_PATH = self.old_paths
        self.tmp.cleanup()

    def test_legacy_import_is_idempotent_and_wrappers_share_core_db(self):
        legacy_db = self.root / "legacy.db"
        with sqlite3.connect(legacy_db) as conn:
            conn.executescript(
                """
                CREATE TABLE memories(id INTEGER PRIMARY KEY, text TEXT, category TEXT, created_at TEXT, updated_at TEXT);
                CREATE TABLE notes(id INTEGER PRIMARY KEY, title TEXT, content TEXT, created_at TEXT, updated_at TEXT);
                CREATE TABLE reminders(id INTEGER PRIMARY KEY, text TEXT, due_timestamp REAL, due_str TEXT, created_at TEXT, completed INTEGER);
                """
            )
            conn.execute("INSERT INTO memories VALUES(1,'Owner lives in Kolkata','location','2026-01-01','2026-01-01')")
            conn.execute("INSERT INTO notes VALUES(1,'Old note','Legacy body','2026-01-01','2026-01-01')")
            conn.execute("INSERT INTO reminders VALUES(1,'Old reminder',1893456000,'2030-01-01 09:00 AM','2026-01-01',0)")

        core_db = self.root / "core.db"
        store = MemoryStore(core_db)
        first = store.import_legacy_database(legacy_db)
        second = store.import_legacy_database(legacy_db)
        self.assertEqual((first["memories_imported"], first["notes_imported"], first["reminders_imported"]), (1, 1, 1))
        self.assertEqual((second["memories_imported"], second["notes_imported"], second["reminders_imported"]), (0, 0, 0))

        legacy_memory.DB_PATH = core_db
        legacy_notes.DB_PATH = core_db
        legacy_reminders.DB_PATH = core_db
        legacy_id = legacy_memory.add_memory("Shared fact", category="test")
        self.assertIsNotNone(legacy_id)
        self.assertTrue(any(item["text"] == "Shared fact" for item in store.list_memories()))
        note = legacy_notes.add_note("Shared body", title="Shared title")
        self.assertEqual(store.get_note(note["id"])["body"], "Shared body")
        reminder = legacy_reminders.add_reminder("Shared reminder", minutes=30)
        self.assertEqual(store.get_reminder(reminder["id"])["text"], "Shared reminder")

    def test_reminder_skills_and_confirmation_gate(self):
        store = MemoryStore(self.root / "core2.db")
        registry = build_default_registry(store)
        service = MyraService(memory_store=store, registry=registry)
        blocked = service.execute_skill("reminders.create", {"text": "Call Boss", "minutes": 5}, confirmed=False)
        self.assertEqual(blocked["status"], "confirmation_required")
        done = service.execute_skill("reminders.create", {"text": "Call Boss", "minutes": 5}, confirmed=True)
        self.assertTrue(done["ok"])
        self.assertEqual(len(store.list_reminders()), 1)


class HologramGeometryTests(unittest.TestCase):
    def test_three_forms_are_finite_busts_and_morphable(self):
        clouds, samples = build_point_clouds(count=900)
        self.assertEqual(set(clouds), {"core", "male", "female"})
        for points in clouds.values():
            self.assertEqual(len(points), 900)
            self.assertTrue(all(all(math.isfinite(value) for value in point) for point in points))
        male_width = max(abs(point[0]) for point in clouds["male"])
        female_width = max(abs(point[0]) for point in clouds["female"])
        self.assertGreater(male_width, female_width)
        bust_top = max(point[1] for point in clouds["male"])
        bust_bottom = min(point[1] for point in clouds["male"])
        self.assertGreater(bust_top, 0.8)
        self.assertLess(bust_bottom, -0.8)
        midpoint = interpolate(clouds["core"][0], clouds["female"][0], 0.5)
        self.assertEqual(len(midpoint), 3)
        self.assertEqual(len(samples), 900)


class FakeHttpResponse:
    def __init__(self, text, url, content_type="text/html"):
        self._body = text.encode("utf-8")
        self.url = url
        self.headers = self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit=None):
        return self._body[:limit] if limit else self._body

    def get_content_type(self):
        return "text/html"

    def get_content_charset(self):
        return "utf-8"

    def get(self, _name, default=""):
        return default


class ResearchTests(unittest.TestCase):
    def test_search_fetch_and_cited_synthesis_with_fake_opener(self):
        def opener(request, timeout=10):
            url = request.full_url
            if "duckduckgo" in url:
                html = """
                <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fmyra">MYRA Research</a>
                <a class="result__snippet" href="#">A useful result</a>
                """
                return FakeHttpResponse(html, url)
            if "example.com/myra" in url:
                html = "<html><title>Example Article</title><p>MYRA is a lightweight personal desktop assistant for Windows laptops.</p></html>"
                return FakeHttpResponse(html, url)
            raise AssertionError(url)

        result = research.research(
            "What is MYRA?",
            max_sources=1,
            opener=opener,
            summarizer=lambda _q, sources: f"MYRA summary from {sources[0]['title']} [1]",
            resolve_dns=False,
        )
        self.assertTrue(result["synthesized_by_ai"])
        self.assertIn("MYRA summary", result["report"])
        self.assertEqual(result["citations"][0]["url"], "https://example.com/myra")
        with self.assertRaises(research.ResearchError):
            research.validate_public_url("http://127.0.0.1/secret")

    def test_browser_challenge_detection(self):
        self.assertEqual(detect_blocking_challenge("Please verify you are human"), "verify you are human")
        controller = BrowserController()
        self.assertTrue(hasattr(controller, "snapshot"))


class FakeSemanticBackend:
    def list_windows(self):
        return [{"name": "Notepad"}]

    def observe(self, window_title="", max_controls=160):
        return {"window": {"name": window_title or "Notepad"}, "controls": [], "verified": True}

    def focus_window(self, window_title):
        return {"window": {"name": window_title}, "verified": True}

    def invoke(self, **query):
        return {"control": query, "verified": True}

    def set_text(self, text, **query):
        return {"text": text, "control": query, "verified": True}

    def send_keys(self, keys, window_title=""):
        return {"keys": keys, "verified": True}


class FakeGui:
    def __init__(self):
        self.calls = []

    def size(self):
        return (1000, 800)

    def click(self, **kwargs):
        self.calls.append(("click", kwargs))

    def doubleClick(self, **kwargs):
        self.calls.append(("double", kwargs))

    def typewrite(self, text, interval=0):
        self.calls.append(("type", text, interval))

    def hotkey(self, *keys):
        self.calls.append(("hotkey", keys))


class WindowsControlTests(unittest.TestCase):
    def test_fake_semantic_coordinate_and_emergency_stop(self):
        gui = FakeGui()
        controller = WindowsController(backend=FakeSemanticBackend(), coordinate_backend=gui)
        self.assertEqual(controller.list_windows()["count"], 1)
        self.assertTrue(controller.invoke_control(name="OK")["verified"])
        self.assertTrue(controller.click_point(10, 20)["verified"])
        controller.type_text("hello")
        controller.hotkey(["ctrl", "s"])
        self.assertEqual(len(gui.calls), 3)
        controller.emergency_stop()
        with self.assertRaises(WindowsControlError):
            controller.list_windows()
        controller.reset_emergency_stop()
        self.assertEqual(controller.list_windows()["count"], 1)


class LiveVisionTests(unittest.TestCase):
    def test_consent_duplicate_budget_and_stop(self):
        calls = []
        manager = LiveVisionManager(lambda payload: calls.append(payload) or {"provider": "fake", "model": "m", "text": "seen"})
        with self.assertRaises(PermissionError):
            manager.start_session("screen", consent=False)
        session = manager.start_session("screen", consent=True, analysis_interval_seconds=1)
        first = manager.submit_frame(session["id"], "aGVsbG8=", analyze_now=True)
        self.assertTrue(first["analyzed"])
        duplicate = manager.submit_frame(session["id"], "aGVsbG8=", analyze_now=False)
        self.assertEqual(duplicate["reason"], "duplicate_frame")
        self.assertEqual(len(calls), 1)
        manager.stop_session(session["id"])
        with self.assertRaises(LiveVisionError):
            manager.submit_frame(session["id"], "bmV3", analyze_now=True)


class VoiceTests(unittest.TestCase):
    @staticmethod
    def pcm(value, seconds, sample_rate=16000):
        return array.array("h", [value] * int(sample_rate * seconds)).tobytes()

    def test_vad_segments_and_realtime_session(self):
        for segmenter_class in (VoiceActivitySegmenter, DesktopSegmenter):
            segmenter = segmenter_class(threshold=1000, min_speech_ms=100, silence_ms=300)
            self.assertIsNone(segmenter.feed(self.pcm(8000, 0.2)))
            utterance = segmenter.feed(self.pcm(0, 0.35))
            self.assertIsNotNone(utterance)
            self.assertTrue(wav_bytes(utterance).startswith(b"RIFF"))
            self.assertTrue(desktop_wav_bytes(utterance).startswith(b"RIFF"))

        spoken = []
        stopped = []
        session = RealtimeVoiceSession(
            transcribe=lambda _audio, _lang: {"text": "hello"},
            chat=lambda text: {"reply": f"reply to {text}"},
            speak=spoken.append,
        )
        session.register_speech_stopper(lambda: stopped.append(True))
        result = session.process_utterance(b"wav")
        self.assertEqual(result["reply"], "reply to hello")
        self.assertEqual(spoken, ["reply to hello"])
        self.assertTrue(stopped)


class FakeJsonResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, _limit=None):
        return self._body


class FakeStreamResponse:
    def __init__(self, lines):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        return iter(self._lines)


class ProviderStreamingStructuredTests(unittest.TestCase):
    def test_gemini_structured_output_is_validated(self):
        opener = lambda _req, timeout=30: FakeJsonResponse({
            "candidates": [{"content": {"parts": [{"text": '{"answer": "yes", "confidence": 0.9}'}]}}]
        })
        schema = {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["answer", "confidence"],
        }
        with mock.patch.object(providers.config, "gemini_key", return_value="fake"), mock.patch.object(
            providers.config, "groq_key", return_value=""
        ):
            result = providers.generate_structured(
                "Answer", schema, provider="gemini", opener=opener, model_overrides={"gemini": "gemini-test"}
            )
        self.assertEqual(result["data"]["answer"], "yes")

    def test_gemini_stream_and_service_persistence(self):
        lines = [
            b'data: {"candidates":[{"content":{"parts":[{"text":"Hel"}]}}]}',
            b'data: {"candidates":[{"content":{"parts":[{"text":"lo"}]}}]}',
            b"data: [DONE]",
        ]
        with mock.patch.object(providers.config, "gemini_key", return_value="fake"), mock.patch.object(
            providers.config, "groq_key", return_value=""
        ):
            events = list(providers.stream_text(
                [{"role": "user", "text": "hi"}], "system", provider="gemini",
                opener=lambda _req, timeout=90: FakeStreamResponse(lines),
                model_overrides={"gemini": "gemini-test"},
            ))
        self.assertEqual("".join(event["text"] for event in events), "Hello")

        with tempfile.TemporaryDirectory() as folder:
            store = MemoryStore(Path(folder) / "db.sqlite")
            service = MyraService(memory_store=store)

            def fake_stream(*_args, **_kwargs):
                yield {"type": "delta", "text": "Saved ", "provider": "fake", "model": "m"}
                yield {"type": "delta", "text": "reply", "provider": "fake", "model": "m"}

            with mock.patch.object(service_module.providers, "stream_text", fake_stream):
                events = list(service.chat_stream({"message": "hello"}))
            self.assertEqual(events[-1]["reply"], "Saved reply")
            messages = store.list_messages(events[-1]["conversation_id"])
            self.assertEqual([message["content"] for message in messages], ["hello", "Saved reply"])


class NativeApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.old_env = os.environ.get("MYRA_DATA_DIR")
        os.environ["MYRA_DATA_DIR"] = str(root)
        self.store = MemoryStore(root / "api.db")
        self.service = MyraService(memory_store=self.store)
        self.service.live_vision = LiveVisionManager(lambda _payload: {"provider": "fake", "model": "m", "text": "frame seen"})
        self.service.research = lambda payload: {"ok": True, "query": payload["query"], "report": "fake", "citations": []}
        self.old_get_service = api_v1.get_service
        api_v1.get_service = lambda: self.service
        self.httpd = server.create_server("127.0.0.1", 0)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        api_v1.get_service = self.old_get_service
        if self.old_env is None:
            os.environ.pop("MYRA_DATA_DIR", None)
        else:
            os.environ["MYRA_DATA_DIR"] = self.old_env
        self.tmp.cleanup()

    def request(self, method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode("utf-8"))

    def test_reminders_live_windows_and_research_routes(self):
        status, created = self.request("POST", "/api/v1/reminders", {"text": "Due now", "minutes": 0})
        self.assertEqual(status, 201)
        reminder_id = created["reminder"]["id"]
        status, listed = self.request("GET", "/api/v1/reminders?active=0")
        self.assertTrue(any(item["id"] == reminder_id for item in listed["reminders"]))

        status, denied = self.request("POST", "/api/v1/live-vision/sessions", {"source": "camera", "consent": False})
        self.assertEqual(status, 403)
        status, started = self.request("POST", "/api/v1/live-vision/sessions", {"source": "screen", "consent": True})
        self.assertEqual(status, 201)
        session_id = started["session"]["id"]
        status, framed = self.request(
            "POST", f"/api/v1/live-vision/sessions/{session_id}/frame",
            {"image_base64": base64.b64encode(b"fake").decode(), "analyze_now": True},
        )
        self.assertEqual(status, 200)
        self.assertTrue(framed["analyzed"])

        status, research_result = self.request("POST", "/api/v1/research", {"query": "MYRA"})
        self.assertEqual(status, 200)
        self.assertEqual(research_result["report"], "fake")

        status, blocked = self.request(
            "POST", "/api/v1/windows/action",
            {"action": "focus", "arguments": {"window_title": "Notepad"}, "confirmed": False},
        )
        self.assertEqual(status, 409)
        self.assertEqual(blocked["status"], "confirmation_required")


class PurePythonLaunchTests(unittest.TestCase):
    def test_no_console_entrypoints_and_embedded_backend(self):
        spec = (ROOT / "packaging" / "MYRA.spec").read_text(encoding="utf-8")
        app = (ROOT / "desktop" / "app.py").read_text(encoding="utf-8")
        self.assertIn("console=False", spec)
        self.assertTrue((ROOT / "MYRA.pyw").exists())
        self.assertTrue((ROOT / "packaging" / "build_windows.py").exists())
        self.assertIn("EmbeddedBackend", app)
        self.assertNotIn("subprocess.Popen", app)
        self.assertNotIn("backend_process", app)

    def test_workers_kept_alive_and_launcher_prefers_desktop(self):
        # Regression guard (found by offscreen Qt smoke test): PySide6 does
        # not keep a Python reference to a QRunnable after
        # QThreadPool.start(), so every worker must go through
        # _start_worker(), which keeps it in self._workers until it
        # reports.  Without this the GUI never receives any API result.
        app = (ROOT / "desktop" / "app.py").read_text(encoding="utf-8")
        self.assertIn("self._workers = set()", app)
        self.assertIn("def _start_worker(self, worker):", app)
        # Exactly one direct pool.start remains: inside _start_worker.
        self.assertEqual(app.count("self.pool.start(worker)"), 1)
        self.assertGreaterEqual(app.count("self._start_worker(worker)"), 9)
        # The auto-update launcher must open the native desktop app.
        launcher = (ROOT / "launcher.py").read_text(encoding="utf-8")
        self.assertIn("MYRA.pyw", launcher)
        self.assertIn("pythonw.exe", launcher)
        self.assertNotIn("_create_unverified_context", launcher)


if __name__ == "__main__":
    unittest.main()
