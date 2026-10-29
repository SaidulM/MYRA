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


if __name__ == "__main__":
    unittest.main()
