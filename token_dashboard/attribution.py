"""Cost by project + git branch (with the commits made meanwhile) and cost by subagent."""
from __future__ import annotations

import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from .db import _range_clause, best_project_name, connect, session_title
from .git_outcomes import commits_for
from .pricing import cost_for

KEYS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_create_5m_tokens", "cache_create_1h_tokens")
_SUMS = ", ".join(f"COALESCE(SUM({k}), 0) AS {k}" for k in KEYS)


def _usd(model: str, row, pricing: dict) -> float:
    return cost_for(model, {k: row[k] for k in KEYS}, pricing)["usd"] or 0.0


def _names(c, slugs) -> dict:
    out = {}
    for slug in slugs:
        cwds = [r["cwd"] for r in c.execute(
            "SELECT DISTINCT cwd FROM messages WHERE project_slug=? AND cwd IS NOT NULL", (slug,))]
        out[slug] = best_project_name(cwds, slug)
    return out


def branch_costs(db_path, pricing: dict, since=None, until=None, project=None,
                 with_commits: bool = True, limit: int = 50) -> list:
    rng, args = _range_clause(since, until)
    if project:
        rng += " AND project_slug = ?"
        args = [*args, project]
    rows = {}
    with connect(db_path) as c:
        for r in c.execute(f"""
            SELECT project_slug, COALESCE(git_branch, '') AS branch, model, COUNT(*) AS turns, {_SUMS}
              FROM messages WHERE type='assistant' AND model IS NOT NULL AND model != '<synthetic>' {rng}
             GROUP BY project_slug, branch, model""", args):
            row = rows.setdefault((r["project_slug"], r["branch"]), {
                "project_slug": r["project_slug"], "branch": r["branch"], "turns": 0, "cost_usd": 0.0,
                "output_tokens": 0, "sessions": []})
            row["turns"] += r["turns"]
            row["output_tokens"] += r["output_tokens"]
            row["cost_usd"] += _usd(r["model"], r, pricing)
        # One window per session on that branch; the most used cwd locates the git repo.
        cwd_use = defaultdict(lambda: defaultdict(int))
        for r in c.execute(f"""
            SELECT project_slug, COALESCE(git_branch, '') AS branch, session_id, cwd,
                   MIN(timestamp) AS started, MAX(timestamp) AS ended, COUNT(*) AS n
              FROM messages WHERE type='assistant' {rng}
             GROUP BY project_slug, branch, session_id, cwd""", args):
            row = rows.get((r["project_slug"], r["branch"]))
            if row is None:
                continue
            row["sessions"].append((r["session_id"], r["started"], r["ended"]))
            if r["cwd"]:
                cwd_use[(r["project_slug"], r["branch"])][r["cwd"]] += r["n"]
        out = sorted(rows.values(), key=lambda x: x["cost_usd"], reverse=True)[:limit]
        names = _names(c, {x["project_slug"] for x in out})

    for x in out:
        x["project_name"] = names[x["project_slug"]]
        x["cost_usd"] = round(x["cost_usd"], 4)
        sessions = x.pop("sessions")
        windows = [(s, e) for _, s, e in sessions]
        x["first"] = min((s for s, _ in windows), default=None)
        x["last"] = max((e for _, e in windows), default=None)
        x["session_count"] = len({sid for sid, _, _ in sessions})
        cwds = cwd_use.get((x["project_slug"], x["branch"]))
        x["cwd"] = max(cwds, key=cwds.get) if cwds else None
        x["_windows"] = windows
    if with_commits:
        with ThreadPoolExecutor(max_workers=8) as pool:  # git calls wait on disk, not CPU
            gits = list(pool.map(lambda x: commits_for(x["cwd"], x["branch"], x["_windows"]), out))
        _assign_commits(out, gits)
    for x in out:
        del x["_windows"]
        cm = (x.get("git") or {}).get("commits")
        if cm is not None:
            x["commits"] = len(cm)
            x["added"] = sum(c["added"] for c in cm)
            x["deleted"] = sum(c["deleted"] for c in cm)
            x["usd_per_commit"] = round(x["cost_usd"] / len(cm), 4) if cm else None
    return out


def _assign_commits(rows: list, gits: list) -> None:
    """Give each commit to one branch row of its repo.

    After a merge a commit is reachable from several branches, and sessions on
    different branches can overlap in time. The session that started last before
    the commit is the one whose branch was checked out when it was made.
    """
    owner = {}  # (repo root, hash) -> (latest session start before the commit, row index)
    for i, (x, g) in enumerate(zip(rows, gits)):
        for c in (g or {}).get("commits", []):
            made = _dt(c["date"])
            starts = [_dt(s) for s, _ in x["_windows"] if _dt(s) <= made]
            score = (max(starts) if starts else _EPOCH, -i)
            key = (g["root"].lower(), c["hash"])
            if key not in owner or score > owner[key][0]:
                owner[key] = (score, i)
    for i, (x, g) in enumerate(zip(rows, gits)):
        if g is None:
            x["git"] = None
            continue
        x["git"] = {**g, "commits": [c for c in g["commits"] if owner[(g["root"].lower(), c["hash"])][1] == i]}


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def _agent_meta(projects_dir) -> dict:
    """agent id -> {type, description} from Claude Code's subagents/agent-<id>.meta.json files."""
    meta = {}
    for p in Path(projects_dir).glob("*/*/subagents/**/agent-*.meta.json"):  # workflows nest one level deeper
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        meta[p.name[len("agent-"):-len(".meta.json")]] = {
            "type": m.get("agentType") or "unknown", "description": m.get("description") or ""}
    return meta


def subagent_costs(db_path, projects_dir, pricing: dict, since=None, until=None, session_id=None) -> dict:
    rng, args = _range_clause(since, until)
    if session_id:
        rng += " AND session_id = ?"
        args = [*args, session_id]
    meta = _agent_meta(projects_dir)
    runs = {}
    with connect(db_path) as c:
        for r in c.execute(f"""
            SELECT session_id, agent_id, model, COUNT(*) AS turns, MIN(timestamp) AS started, {_SUMS}
              FROM messages
             WHERE type='assistant' AND is_sidechain=1 AND agent_id IS NOT NULL
               AND model IS NOT NULL AND model != '<synthetic>' {rng}
             GROUP BY session_id, agent_id, model""", args):
            m = meta.get(r["agent_id"], {"type": "unknown", "description": ""})
            run = runs.setdefault((r["session_id"], r["agent_id"]), {
                "session_id": r["session_id"], "agent_id": r["agent_id"], "type": m["type"],
                "description": m["description"], "started": r["started"], "turns": 0,
                "tokens": 0, "cost_usd": 0.0, "models": []})
            run["turns"] += r["turns"]
            run["tokens"] += sum(r[k] for k in KEYS)
            run["cost_usd"] += _usd(r["model"], r, pricing)
            run["models"].append(r["model"])
            run["started"] = min(run["started"], r["started"])
        total_rows = c.execute(f"""
            SELECT model, {_SUMS} FROM messages
             WHERE type='assistant' AND model IS NOT NULL AND model != '<synthetic>' {rng} GROUP BY model""", args)
        total = sum(_usd(r["model"], r, pricing) for r in total_rows)

    by_type = {}
    for run in runs.values():
        run["cost_usd"] = round(run["cost_usd"], 4)
        t = by_type.setdefault(run["type"], {"type": run["type"], "dispatches": 0, "turns": 0, "tokens": 0, "cost_usd": 0.0})
        t["dispatches"] += 1
        t["turns"] += run["turns"]
        t["tokens"] += run["tokens"]
        t["cost_usd"] += run["cost_usd"]
    for t in by_type.values():
        t["cost_usd"] = round(t["cost_usd"], 4)
        t["avg_usd"] = round(t["cost_usd"] / t["dispatches"], 4)
    top = sorted(runs.values(), key=lambda r: r["cost_usd"], reverse=True)[:25 if not session_id else None]
    titles = {}
    for run in top:
        if run["session_id"] not in titles:
            titles[run["session_id"]] = session_title(db_path, run["session_id"])
        run["title"] = titles[run["session_id"]]
    sub_total = sum(t["cost_usd"] for t in by_type.values())
    return {
        "total_usd": round(total, 4),
        "subagent_usd": round(sub_total, 4),
        "share": round(sub_total / total, 4) if total else 0,
        "dispatches": len(runs),
        "by_type": sorted(by_type.values(), key=lambda t: t["cost_usd"], reverse=True),
        "top": top,
    }
