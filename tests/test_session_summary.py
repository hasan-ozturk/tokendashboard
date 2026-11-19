import json
import os
import tempfile
import unittest

from token_dashboard.session_summary import summarize, to_markdown


def _user(ts, content, **extra):
    return {"type": "user", "uuid": "u" + ts, "sessionId": "s1", "timestamp": ts,
            "message": {"role": "user", "content": content}, **extra}


def _reply(ts, mid, tool=None, out=10, cache_read=100):
    content = [{"type": "tool_use", "id": "t" + ts, "name": tool, "input": {}}] if tool else [{"type": "text", "text": "ok"}]
    return {"type": "assistant", "uuid": "a" + ts, "sessionId": "s1", "timestamp": ts,
            "message": {"id": mid, "model": "claude-opus-5-5", "content": content,
                        "usage": {"input_tokens": 1, "output_tokens": out, "cache_read_input_tokens": cache_read}}}


def _att(ts, attachment):
    return {"type": "attachment", "uuid": "x" + ts, "sessionId": "s1", "timestamp": ts, "attachment": attachment}


class SessionSummaryTests(unittest.TestCase):
    def _summarize(self, records):
        tmp = tempfile.mkdtemp()
        proj = os.path.join(tmp, "p")
        os.makedirs(proj)
        with open(os.path.join(proj, "s1.jsonl"), "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        return summarize(tmp, "s1")

    def test_replies_grouped_under_the_prompt_that_started_them(self):
        s = self._summarize([
            _att("2026-11-19T07:00:00Z", {"type": "instructions", "files": [{"path": "CLAUDE.md", "type": "Project", "content": "x" * 400}]}),
            _user("2026-11-19T07:00:01Z", "first task"),
            _reply("2026-11-19T07:00:02Z", "m1", tool="Read"),
            _reply("2026-11-19T07:00:03Z", "m1", tool="Grep"),  # second snapshot of the same reply
            _user("2026-11-19T07:00:04Z", [{"type": "tool_result", "tool_use_id": "t1", "content": "r"}]),
            _user("2026-11-19T07:00:05Z", "<task-notification>done</task-notification>"),
            _reply("2026-11-19T07:00:06Z", "m2"),
            _att("2026-11-19T07:00:07Z", {"type": "queued_command", "origin": {"kind": "human"},
                                          "timestamp": "2026-11-19T07:00:07Z", "prompt": [{"type": "text", "text": "second"}]}),
            _user("2026-11-19T07:00:08Z", "second"),  # same queued prompt written again
            _reply("2026-11-19T07:00:09Z", "m3", out=50, cache_read=300),
        ])
        self.assertEqual([st["prompt"] for st in s["steps"]], ["first task", "second"])
        first, second = s["steps"]
        self.assertEqual(first["turns"], 2)
        self.assertEqual(first["tools"], {"Read": 1, "Grep": 1})
        self.assertEqual(second["models"]["claude-opus-5-5"]["output_tokens"], 50)
        self.assertEqual([c["tokens"] for c in s["context"]], [101, 101, 301])
        self.assertEqual(s["loaded"][0], {"kind": "instructions (Project)", "name": "CLAUDE.md",
                                          "loads": 1, "tokens": 100, "total_tokens": 100})

    def test_slash_command_is_a_prompt(self):
        s = self._summarize([_user("2026-11-19T07:00:00Z",
                                   "<command-message>review</command-message><command-name>/review</command-name><command-args>all</command-args>")])
        self.assertEqual(s["steps"][0]["prompt"], "/review all")

    def test_markdown_has_steps_and_escapes_pipes(self):
        s = self._summarize([_user("2026-11-19T07:00:00Z", "a | b"), _reply("2026-11-19T07:00:01Z", "m1")])
        for st in s["steps"]:
            st.pop("models")
            st["cost_usd"] = 0.5
        s.update(models=[], title="T", cost_usd=0.5)
        md = to_markdown(s, "s1")
        self.assertIn("# T", md)
        self.assertIn("a \\| b", md)
        self.assertIn("$0.50", md)


if __name__ == "__main__":
    unittest.main()
