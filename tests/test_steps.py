import os
import tempfile
import unittest
from pathlib import Path

from token_dashboard.db import connect, init_db
from token_dashboard.pricing import load_pricing
from token_dashboard.session_summary import prompt_label
from token_dashboard.steps import expensive_steps

PRICING = load_pricing(Path(__file__).resolve().parent.parent / "pricing.json")


class StepsTests(unittest.TestCase):
    def setUp(self):
        self.db = os.path.join(tempfile.mkdtemp(), "s.db")
        init_db(self.db)
        rows = [
            # uuid, session, type, ts, model, prompt, out, cache_read, write_1h, sidechain
            ("u1", "s1", "user", "2026-11-01T10:00:00Z", None, "build it", 0, 0, 0, 0),
            ("a1", "s1", "assistant", "2026-11-01T10:00:01Z", "claude-opus-5-5", None, 1000, 0, 0, 0),
            ("t1", "s1", "user", "2026-11-01T10:00:02Z", None, "<task-notification>x</task-notification>", 0, 0, 0, 0),
            ("a2", "s1", "assistant", "2026-11-01T10:00:03Z", "claude-opus-5-5", None, 0, 1_000_000, 0, 0),
            ("x1", "s1", "assistant", "2026-11-01T10:00:04Z", "claude-haiku-5-5", None, 10, 0, 0, 1),
            ("u2", "s1", "user", "2026-11-01T12:00:00Z", None, "continue", 0, 0, 0, 0),
            ("a3", "s1", "assistant", "2026-11-01T12:00:01Z", "claude-opus-5-5", None, 0, 0, 200_000, 0),
        ]
        with connect(self.db) as c:
            c.executemany(
                """INSERT INTO messages (uuid, session_id, project_slug, type, timestamp, model, prompt_text,
                     input_tokens, output_tokens, cache_read_tokens, cache_create_5m_tokens, cache_create_1h_tokens, is_sidechain)
                   VALUES (?, ?, 'p', ?, ?, ?, ?, 0, ?, ?, 0, ?, ?)""", rows)
            c.commit()

    def test_steps_group_replies_and_flag_rebuilds(self):
        out = expensive_steps(self.db, PRICING, sort="recent")
        first, second = out["rows"][1], out["rows"][0]
        self.assertEqual((first["prompt"], first["turns"]), ("build it", 3))  # notification and subagent turn included
        # opus 5.5: 1000 out * $20/M + 1M cache read * $0.20/M; haiku 5.5: 10 out * $0.50/M
        self.assertAlmostEqual(first["cost_usd"], 0.02 + 0.2 + 0.000005, places=4)
        self.assertEqual(first["why"], "cache read")
        self.assertEqual(first["rebuild_tokens"], 0)
        self.assertEqual((second["prompt"], second["rebuild_tokens"], second["why"]), ("continue", 200_000, "cache write"))
        self.assertAlmostEqual(second["rebuild_usd"], 1.6, places=4)  # 200K * $8/M (1h write)
        self.assertEqual(out["summary"]["rebuilds"], 1)
        self.assertEqual(out["summary"]["steps"], 2)

    def test_model_filter_and_sort_by_cost(self):
        out = expensive_steps(self.db, PRICING, model="claude-haiku-5-5")
        self.assertEqual([r["prompt"] for r in out["rows"]], ["build it"])
        out = expensive_steps(self.db, PRICING)
        self.assertEqual(out["rows"][0]["prompt"], "continue")

    def test_prompt_label(self):
        self.assertEqual(prompt_label("<ide_selection>code</ide_selection>fix this"), "fix this")
        self.assertEqual(prompt_label('look <pasted_content id="1">long log</pasted_content>'), "look [pasted text]")
        self.assertIsNone(prompt_label("The coordinator sent a message while you were working: x"))
        self.assertIsNone(prompt_label("[Image: original 100x100]"))


if __name__ == "__main__":
    unittest.main()
