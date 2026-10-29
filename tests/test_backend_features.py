import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import agent
import memory
import news
import notes
import skills_manager


class BackendFeaturesTests(unittest.TestCase):
    def setUp(self):
        memory.init_db()
        notes.init_db()
        memory.clear_memories()
        notes.clear_notes()

    def test_memory_crud(self):
        mem_id = memory.add_memory("I like green tea", category="preferences")
        self.assertIsNotNone(mem_id)

        mems = memory.list_memories()
        self.assertEqual(len(mems), 1)
        self.assertEqual(mems[0]["text"], "I like green tea")
        self.assertEqual(mems[0]["category"], "preferences")

        ctx = memory.get_memory_context()
        self.assertIn("I like green tea", ctx)

        deleted = memory.delete_memory(mem_id)
        self.assertTrue(deleted)
        self.assertEqual(len(memory.list_memories()), 0)

    def test_notes_crud(self):
        created = notes.add_note("Project plan for MYRA", title="Plan")
        self.assertIsNotNone(created)
        note_id = created["id"]

        all_notes = notes.get_notes()
        self.assertEqual(len(all_notes), 1)
        self.assertEqual(all_notes[0]["title"], "Plan")
        self.assertEqual(all_notes[0]["content"], "Project plan for MYRA")

        updated = notes.update_note(note_id, "Updated plan", title="New Plan")
        self.assertTrue(updated)
        updated_notes = notes.get_notes()
        self.assertEqual(updated_notes[0]["title"], "New Plan")

        deleted = notes.delete_note(note_id)
        self.assertTrue(deleted)
        self.assertEqual(len(notes.get_notes()), 0)

    def test_skills_calculator(self):
        res = skills_manager.safe_calculate("2 + 3 * 4")
        self.assertEqual(res, "14")

        res_sqrt = skills_manager.safe_calculate("sqrt(16)")
        self.assertEqual(res_sqrt, "4")

    def test_skills_system_info(self):
        info = skills_manager.get_system_info()
        self.assertIn("os", info)
        self.assertIn("python", info)

    def test_agent_task(self):
        result = agent.run_agent_task("calculate 25 * 4")
        self.assertTrue(result["ok"])
        self.assertTrue(len(result["logs"]) > 0)
        self.assertIn("Autonomous Agent Report", result["report"])

    def test_config_groq_model_and_key_status(self):
        import config
        status = config.save_keys(gemini="AIzaTest123", groq="gsk_Test456", gemini_model="gemini-1.5-pro", groq_model="llama-3.3-70b-versatile")
        self.assertTrue(status["gemini"]["set"])
        self.assertTrue(status["groq"]["set"])
        self.assertEqual(status["gemini"]["model"], "gemini-1.5-pro")
        self.assertEqual(status["groq"]["model"], "llama-3.3-70b-versatile")

        # Clean up
        config.save_keys(gemini="", groq="", gemini_model="auto", groq_model="auto")

    def test_agent_local_intents_zero_tokens(self):
        # Music intent
        music_res = agent.parse_and_execute_local_intent("play song Arijit Singh")
        self.assertIsNotNone(music_res)
        self.assertTrue(music_res["ok"])
        self.assertEqual(music_res["action"], "play_music")
        self.assertEqual(music_res["tokens_used"], 0)

        # Bengali music intent
        bn_music = agent.parse_and_execute_local_intent("তুমি গান চালাও রবীন্দ্র সংগীত")
        self.assertIsNotNone(bn_music)
        self.assertEqual(bn_music["action"], "play_music")
        self.assertEqual(bn_music["tokens_used"], 0)

        # Camera intent
        cam_res = agent.parse_and_execute_local_intent("open camera")
        self.assertIsNotNone(cam_res)
        self.assertEqual(cam_res["action"], "open_camera")
        self.assertTrue(cam_res["client_trigger"])

        # System telemetry intent
        sys_res = agent.parse_and_execute_local_intent("system status")
        self.assertIsNotNone(sys_res)
        self.assertEqual(sys_res["action"], "system_status")

    def test_reminders_crud_and_due(self):
        import reminders
        reminders.init_db()
        # Add reminder
        res = reminders.add_reminder("Review project code", minutes=0)
        self.assertTrue(res["ok"])
        rem_id = res["id"]

        rems = reminders.list_reminders()
        self.assertTrue(any(r["id"] == rem_id for r in rems))

        # Check due
        due = reminders.check_due_reminders()
        self.assertTrue(any(d["id"] == rem_id for d in due))

        # Clean up
        reminders.delete_reminder(rem_id)

    def test_voice_studio_pick_voice_and_status(self):
        import voice_studio
        # Bengali voice pick
        bn_v = voice_studio.pick_voice("হ্যালো! আমি মায়রা।", character="female")
        self.assertEqual(bn_v, "bn-BD-NabanitaNeural")

        bn_v_male = voice_studio.pick_voice("হ্যালো! আমি মায়রা।", character="male")
        self.assertEqual(bn_v_male, "bn-BD-PradeepNeural")

        # English voice pick
        en_v = voice_studio.pick_voice("Hello world", character="female")
        self.assertEqual(en_v, "en-US-JennyNeural")

        en_v_male = voice_studio.pick_voice("Hello world", character="male")
        self.assertEqual(en_v_male, "en-US-GuyNeural")

        status = voice_studio.get_voice_status()
        self.assertTrue(status["ok"])
        self.assertIn("bn-BD-NabanitaNeural", status["supported_voices"])

    def test_auto_learn_and_memory_recall(self):
        # Auto-learn name from user speech
        learned = memory.auto_learn_from_text("আমার নাম সাইদুল")
        self.assertIsNotNone(learned)
        self.assertIn("সাইদুল", learned)

        # Zero-token query resolution in Bengali
        answer_bn = memory.resolve_memory_query("আমার নাম কি?")
        self.assertIsNotNone(answer_bn)
        self.assertIn("সাইদুল", answer_bn)

        # Zero-token query resolution in English
        answer_en = memory.resolve_memory_query("What is my name?")
        self.assertIsNotNone(answer_en)
        self.assertIn("সাইদুল", answer_en)

    def test_agent_shutdown_search_and_whatsapp(self):
        # Shutdown intent
        shut = agent.parse_and_execute_local_intent("তুমি বন্ধ হয়ে যাও")
        self.assertIsNotNone(shut)
        self.assertEqual(shut["action"], "shutdown_app")
        self.assertTrue(shut["client_trigger"])

        # File search intent
        fsearch = agent.parse_and_execute_local_intent("search file run.py")
        self.assertIsNotNone(fsearch)
        self.assertEqual(fsearch["action"], "search_files")
        self.assertEqual(fsearch["tokens_used"], 0)

        # WhatsApp intent
        wa = agent.parse_and_execute_local_intent("send whatsapp to 01711223344 hello friend")
        self.assertIsNotNone(wa)
        self.assertEqual(wa["action"], "send_whatsapp")
        self.assertIn("web.whatsapp.com", wa["url"])
        self.assertEqual(wa["tokens_used"], 0)

    def test_voice_ssml_and_whisper_style(self):
        import voice_studio
        ssml = voice_studio.build_ssml("Secret message", "en-US-AvaNeural", style="whisper")
        self.assertIn("whispering", ssml)
        self.assertIn("Secret message", ssml)

        whisper_v = voice_studio.pick_voice("Secret", character="female", style="whisper")
        self.assertEqual(whisper_v, "en-US-AvaNeural")


if __name__ == "__main__":
    unittest.main()
