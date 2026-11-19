import json
import os
import tempfile
import unittest

from token_dashboard.db import init_db, session_title
from token_dashboard.scanner import scan_dir


class SessionTitleTests(unittest.TestCase):
    def _scan(self, lines):
        tmp = tempfile.mkdtemp()
        proj = os.path.join(tmp, "projects", "p")
        os.makedirs(proj)
        with open(os.path.join(proj, "s1.jsonl"), "w", encoding="utf-8") as f:
            for rec in lines:
                f.write(json.dumps(rec) + "\n")
        db = os.path.join(tmp, "t.db")
        init_db(db)
        scan_dir(os.path.join(tmp, "projects"), db)
        return session_title(db, "s1")

    def _user(self, text):
        return {"type": "user", "uuid": "u-" + text, "sessionId": "s1", "timestamp": "2026-11-19T07:00:00Z",
                "isSidechain": False, "message": {"role": "user", "content": text}}

    def test_falls_back_to_first_prompt(self):
        self.assertEqual(self._scan([self._user("fix the bug")]), "fix the bug")

    def test_ai_title_then_custom_wins(self):
        title = self._scan([
            self._user("fix the bug"),
            {"type": "custom-title", "customTitle": "My name", "sessionId": "s1"},
            {"type": "ai-title", "aiTitle": "Later AI title", "sessionId": "s1"},
        ])
        self.assertEqual(title, "My name")

    def test_ai_title_used(self):
        title = self._scan([self._user("x"), {"type": "ai-title", "aiTitle": "Bug fix", "sessionId": "s1"}])
        self.assertEqual(title, "Bug fix")


if __name__ == "__main__":
    unittest.main()
