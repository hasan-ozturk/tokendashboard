import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from token_dashboard.attribution import _assign_commits, branch_costs, subagent_costs
from token_dashboard.db import connect, init_db
from token_dashboard.git_outcomes import parse_log
from token_dashboard.pricing import load_pricing

PRICING = load_pricing(Path(__file__).resolve().parent.parent / "pricing.json")
INSERT = """INSERT INTO messages (uuid, session_id, project_slug, type, timestamp, model, cwd, git_branch,
              is_sidechain, agent_id, input_tokens, output_tokens, cache_read_tokens, cache_create_5m_tokens, cache_create_1h_tokens)
            VALUES (?, ?, 'p', 'assistant', ?, 'claude-opus-5-5', ?, ?, ?, ?, 0, ?, 0, 0, 0)"""


class ParseLogTests(unittest.TestCase):
    def test_parse_log_reads_hash_date_subject_and_shortstat(self):
        text = ("\x1eabc\x1f2026-11-01T10:00:00+03:00\x1ffix bug\n\n 2 files changed, 10 insertions(+), 3 deletions(-)\n"
                "\x1edef\x1f2026-11-01T11:00:00+03:00\x1fdocs\n\n 1 file changed, 1 deletion(-)\n")
        self.assertEqual(parse_log(text), [
            {"hash": "abc", "date": "2026-11-01T10:00:00+03:00", "subject": "fix bug", "added": 10, "deleted": 3},
            {"hash": "def", "date": "2026-11-01T11:00:00+03:00", "subject": "docs", "added": 0, "deleted": 1},
        ])

    def test_merged_commit_goes_to_branch_whose_session_was_active(self):
        commit = {"hash": "h1", "date": "2026-11-01T12:30:00+00:00", "added": 1, "deleted": 0}
        rows = [{"_windows": [("2026-11-01T09:00:00Z", "2026-11-01T13:00:00Z")]},   # main, long session
                {"_windows": [("2026-11-01T12:00:00Z", "2026-11-01T12:45:00Z")]}]   # feature, started later
        gits = [{"root": "C:/r", "commits": [commit]}, {"root": "c:/R", "commits": [commit]}]
        _assign_commits(rows, gits)
        self.assertEqual([len(r["git"]["commits"]) for r in rows], [0, 1])


@unittest.skipUnless(shutil.which("git"), "git not installed")
class BranchCostTests(unittest.TestCase):
    def test_branch_cost_and_commits_inside_session_window(self):
        tmp = tempfile.mkdtemp()
        repo = os.path.join(tmp, "repo")
        os.makedirs(repo)
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
        git = lambda *a, **kw: subprocess.run(["git", "-C", repo, *a], check=True, capture_output=True, env={**env, **kw})
        git("init", "-q", "-b", "feat")
        git("config", "user.email", "t@x")
        for name, when in (("in.txt", "2026-11-01T10:30:00+00:00"), ("late.txt", "2026-11-01T15:00:00+00:00")):
            Path(repo, name).write_text("a\nb\n")
            git("add", name)
            git("commit", "-q", "-m", name, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
        db = os.path.join(tmp, "t.db")
        init_db(db)
        with connect(db) as c:
            c.executemany(INSERT, [
                ("a1", "s1", "2026-11-01T10:00:00Z", repo, "feat", 0, None, 1_000_000),
                ("a2", "s1", "2026-11-01T10:20:00Z", repo, "feat", 0, None, 0),
                ("a3", "s2", "2026-11-01T10:05:00Z", os.path.join(tmp, "nogit"), "HEAD", 0, None, 0),
            ])
            c.commit()
        rows = {r["branch"]: r for r in branch_costs(db, PRICING)}
        feat = rows["feat"]
        self.assertAlmostEqual(feat["cost_usd"], 20.0)  # 1M output tokens * $20/M (Opus 5.5)
        self.assertEqual(feat["session_count"], 1)
        # in.txt lands inside the session + 1h grace; late.txt (15:00) does not.
        self.assertEqual([c["subject"] for c in feat["git"]["commits"]], ["in.txt"])
        self.assertEqual((feat["commits"], feat["added"], feat["usd_per_commit"]), (1, 2, 20.0))
        self.assertIsNone(rows["HEAD"]["git"])


class SubagentCostTests(unittest.TestCase):
    def test_runs_grouped_by_agent_with_type_from_meta_file(self):
        tmp = tempfile.mkdtemp()
        sub = Path(tmp, "projects", "p", "s1", "subagents", "workflows", "wf1")
        sub.mkdir(parents=True)
        (sub / "agent-ag1.meta.json").write_text(json.dumps({"agentType": "Explore", "description": "find callers"}))
        db = os.path.join(tmp, "t.db")
        init_db(db)
        with connect(db) as c:
            c.executemany(INSERT, [
                ("m1", "s1", "2026-11-01T10:00:00Z", None, None, 0, None, 1_000_000),
                ("x1", "s1", "2026-11-01T10:01:00Z", None, None, 1, "ag1", 500_000),
                ("x2", "s1", "2026-11-01T10:02:00Z", None, None, 1, "ag1", 0),
                ("x3", "s1", "2026-11-01T10:03:00Z", None, None, 1, "ag2", 0),
            ])
            c.commit()
        out = subagent_costs(db, os.path.join(tmp, "projects"), PRICING)
        self.assertEqual(out["dispatches"], 2)
        self.assertAlmostEqual(out["total_usd"], 30.0)
        self.assertAlmostEqual(out["subagent_usd"], 10.0)
        top = out["top"][0]
        self.assertEqual((top["type"], top["description"], top["turns"]), ("Explore", "find callers", 2))
        self.assertEqual({t["type"] for t in out["by_type"]}, {"Explore", "unknown"})


if __name__ == "__main__":
    unittest.main()
