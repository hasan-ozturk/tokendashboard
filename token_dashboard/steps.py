"""Cost per step across sessions.

A step is one prompt the user typed plus every reply (subagents too) until the
next typed prompt in the same session. Built from the messages table, so the
page does not re-read transcripts.
"""
from __future__ import annotations

from .db import _range_clause, best_project_name, connect, session_title
from .pricing import cost_for
from .session_summary import prompt_label

KEYS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_create_5m_tokens", "cache_create_1h_tokens")
# One turn that writes this much cache re-caches the whole context: the cache expired
# (idle > 1h) or the model changed. A fresh session writes ~40K on its first turn.
REBUILD_TOKENS = 100_000


def _step_cost(models: dict, pricing: dict) -> dict:
    parts = {"input": 0.0, "output": 0.0, "cache read": 0.0, "cache write": 0.0}
    for model, u in models.items():
        bd = cost_for(model, u, pricing)["breakdown"]
        parts["input"] += bd.get("input", 0)
        parts["output"] += bd.get("output", 0)
        parts["cache read"] += bd.get("cache_read", 0)
        parts["cache write"] += bd.get("cache_create_5m", 0) + bd.get("cache_create_1h", 0)
    return parts


def expensive_steps(db_path, pricing: dict, since=None, until=None, project=None, model=None,
                    sort: str = "cost", limit: int = 100) -> dict:
    rng, args = _range_clause(since, until)
    if project:
        rng += " AND project_slug = ?"
        args = [*args, project]
    sql = f"""
      SELECT session_id, project_slug, type, timestamp, model, prompt_text, {", ".join(KEYS)}
        FROM messages
       WHERE (type = 'assistant' OR (type = 'user' AND is_sidechain = 0 AND prompt_text IS NOT NULL)) {rng}
       ORDER BY session_id, timestamp
    """
    steps, cur, sid = [], None, None
    with connect(db_path) as c:
        for r in c.execute(sql, args):
            if r["session_id"] != sid:
                sid, cur = r["session_id"], None
            if r["type"] == "user":
                label = prompt_label(r["prompt_text"])
                if label:
                    cur = {"session_id": sid, "project_slug": r["project_slug"], "ts": r["timestamp"],
                           "prompt": label[:500], "turns": 0, "models": {}, "rebuild": {}, "rebuild_tokens": 0}
                    steps.append(cur)
                continue
            if cur is None or not r["model"] or r["model"] == "<synthetic>":
                continue
            cur["turns"] += 1
            agg = cur["models"].setdefault(r["model"], dict.fromkeys(KEYS, 0))
            for k in KEYS:
                agg[k] += r[k] or 0
            write = (r["cache_create_5m_tokens"] or 0) + (r["cache_create_1h_tokens"] or 0)
            if write >= REBUILD_TOKENS:
                reb = cur["rebuild"].setdefault(r["model"], dict.fromkeys(KEYS, 0))
                reb["cache_create_5m_tokens"] += r["cache_create_5m_tokens"] or 0
                reb["cache_create_1h_tokens"] += r["cache_create_1h_tokens"] or 0
                cur["rebuild_tokens"] += write

        steps = [s for s in steps if s["turns"] and (not model or model in s["models"])]
        models_seen = set()
        for s in steps:
            parts = _step_cost(s["models"], pricing)
            s["cost_usd"] = round(sum(parts.values()), 4)
            s["why"] = max(parts, key=parts.get)
            s["rebuild_usd"] = round(sum(_step_cost(s["rebuild"], pricing).values()), 4)
            s["model"] = max(s["models"], key=lambda m: sum(s["models"][m].values()))
            models_seen.update(s["models"])
            del s["models"], s["rebuild"]

        total = sum(s["cost_usd"] for s in steps)
        by_cost = sorted(steps, key=lambda s: s["cost_usd"], reverse=True)
        rebuilds = [s for s in steps if s["rebuild_tokens"]]
        rows = by_cost if sort == "cost" else sorted(steps, key=lambda s: s["ts"], reverse=True)
        rows = rows[:limit]

        names = {}
        for s in rows:
            slug = s["project_slug"]
            if slug not in names:
                cwds = [x["cwd"] for x in c.execute(
                    "SELECT DISTINCT cwd FROM messages WHERE project_slug=? AND cwd IS NOT NULL", (slug,))]
                names[slug] = best_project_name(cwds, slug)
            s["project_name"] = names[slug]
    titles = {}
    for s in rows:
        if s["session_id"] not in titles:
            titles[s["session_id"]] = session_title(db_path, s["session_id"])
        s["title"] = titles[s["session_id"]]

    return {
        "summary": {
            "steps": len(steps),
            "total_usd": round(total, 4),
            "top10_usd": round(sum(s["cost_usd"] for s in by_cost[:10]), 4),
            "rebuilds": len(rebuilds),
            "rebuild_usd": round(sum(s["rebuild_usd"] for s in rebuilds), 4),
            "models": sorted(models_seen),
        },
        "rows": rows,
    }
