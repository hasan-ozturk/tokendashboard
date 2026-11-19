"""Per-session summary: what was read, which tools/MCP servers were called,
and how many tokens each tool result brought into context.

Read straight from the session's JSONL files (main + subagents), because the
tool_calls table does not link a tool_use to its result.
"""
from __future__ import annotations

import bisect
import json
import re
from pathlib import Path
from typing import Iterable, Optional

# Input field that best names what a tool touched.
_TARGET = {
    "Read": "file_path", "Edit": "file_path", "Write": "file_path", "NotebookEdit": "notebook_path",
    "Glob": "pattern", "Grep": "pattern", "Bash": "command", "PowerShell": "command",
    "WebFetch": "url", "WebSearch": "query", "Skill": "skill", "Agent": "description", "Task": "description",
}
_FILE_TOOLS = {"Read", "Edit", "Write", "NotebookEdit"}


def session_files(projects_dir: str, session_id: str) -> list:
    root = Path(projects_dir)
    files = list(root.glob(f"*/{session_id}.jsonl"))
    files += list(root.glob(f"*/{session_id}/subagents/*.jsonl"))
    return files


def _records(files: Iterable[Path]):
    for f in files:
        with open(f, "rb") as fh:
            for raw in fh:
                try:
                    yield json.loads(raw)
                except ValueError:
                    continue  # partial line at EOF while the session is still writing


def _result_chars(body) -> int:
    if isinstance(body, str):
        return len(body)
    if isinstance(body, list):
        return sum(len(p.get("text", "")) for p in body if isinstance(p, dict))
    return 0


def _target(name: str, inp: dict) -> Optional[str]:
    v = inp.get(_TARGET.get(name, ""))
    return v[:300] if isinstance(v, str) else None


# Attachment kinds that are bookkeeping, not text the model sees.
_NOT_CONTEXT = {"hook_cancelled", "hook_success", "command_permissions", "credential_org",
                "remote_session_change", "thinking_drop", "queued_command", "compact_file_reference"}
_ATT_TEXT_KEYS = ("content", "text", "systemPrompt", "snippet", "addedLines", "addedBlocks",
                  "entries", "prompt", "context", "snapshot", "skills")


def _as_text(v) -> str:
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def _attachment_items(a: dict):
    """Yield (kind, name, chars) for text an attachment put into the context."""
    kind = a.get("type") or "unknown"
    if kind in _NOT_CONTEXT:
        return
    if kind == "instructions":  # CLAUDE.md, rules, memory files
        for f in a.get("files") or []:
            yield f"instructions ({f.get('type') or 'file'})", f.get("path"), len(f.get("content") or "")
    elif kind == "invoked_skills":
        for s in a.get("skills") or []:
            yield "skill", s.get("name"), len(s.get("content") or "")
    elif kind == "mcp_instructions_delta":
        for name, block in zip(a.get("addedNames") or [], a.get("addedBlocks") or []):
            yield "mcp instructions", name, len(block or "")
    else:
        if kind.startswith("hook_"):
            name = f"{a.get('hookEvent')}:{a.get('hookName')}"
        else:
            name = a.get("filename") or a.get("displayPath") or kind
        text = next((_as_text(a[k]) for k in _ATT_TEXT_KEYS if k in a), "")
        yield kind, name, len(text)


def _prompt_text(rec: dict) -> Optional[str]:
    """Text of a prompt the user typed, or None for tool results, notices and meta records."""
    if rec.get("type") != "user" or rec.get("isSidechain") or rec.get("isMeta") or rec.get("isCompactSummary"):
        return None
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, list):
        content = "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return prompt_label(content) if isinstance(content, str) else None


# Text Claude Code writes into user records that the user did not type. The DB has no
# isMeta flag, so these prefixes are how the cross-session Prompts page drops them.
_NOT_TYPED = ("<", "[Request interrupted", "[Image", "Base directory for this skill",
              "This session is being continued", "The coordinator sent a message",
              "Another Claude session sent a message", "Caveat:")


def prompt_label(text: Optional[str]) -> Optional[str]:
    """Prompt text as the user typed it, a slash command as '/name args', or None for system text."""
    # IDE context and pastes wrap real prompts; drop the IDE part, shorten the paste.
    text = re.sub(r"<(ide_selection|ide_opened_file)>.*?</\1>", "", text or "", flags=re.S)
    text = re.sub(r"<pasted_content[^>]*>.*?</pasted_content>", "[pasted text]", text, flags=re.S).strip()
    if not text:
        return None
    if text.startswith("<command-message>") or text.startswith("<command-name>"):
        m = re.search(r"<command-name>(.*?)</command-name>.*?(?:<command-args>(.*?)</command-args>)?", text, re.S)
        return " ".join(p for p in (m.groups() if m else (text,)) if p).strip()
    if text.startswith(_NOT_TYPED):
        return None  # task notifications, interrupts, agent messages: part of the previous step
    return text


def _usage_row(u: dict) -> dict:
    cc = u.get("cache_creation") or {}
    return {
        "input_tokens": u.get("input_tokens") or 0,
        "output_tokens": u.get("output_tokens") or 0,
        "cache_read_tokens": u.get("cache_read_input_tokens") or 0,
        "cache_create_5m_tokens": cc.get("ephemeral_5m_input_tokens") or 0,
        "cache_create_1h_tokens": cc.get("ephemeral_1h_input_tokens") or 0,
    }


def summarize(projects_dir: str, session_id: str) -> dict:
    uses = {}      # tool_use_id -> {name, target, sidechain}
    results = {}   # tool_use_id -> (tokens, is_error)
    prompts = []   # (timestamp, text)
    replies = {}   # message.id -> (timestamp, model, sidechain, usage, [tool names]); last snapshot wins
    loaded = {}    # (kind, name) -> {kind, name, loads, tokens, total_tokens}
    for rec in _records(session_files(projects_dir, session_id)):
        ts = rec.get("timestamp") or ""
        att = rec.get("attachment")
        if rec.get("type") == "attachment" and isinstance(att, dict):
            if att.get("type") == "queued_command" and (att.get("origin") or {}).get("kind") == "human":
                text = _as_text(att.get("prompt")) if not isinstance(att.get("prompt"), list) else \
                    "".join(b.get("text", "") for b in att["prompt"] if isinstance(b, dict))
                prompts.append((att.get("timestamp") or ts, text.strip()))
            if not rec.get("isSidechain"):
                for kind, name, chars in _attachment_items(att):
                    row = loaded.setdefault((kind, name), {"kind": kind, "name": name, "loads": 0,
                                                           "tokens": 0, "total_tokens": 0})
                    row["loads"] += 1
                    row["tokens"] = max(row["tokens"], chars // 4)
                    row["total_tokens"] += chars // 4
            continue
        text = _prompt_text(rec)
        if text:
            prompts.append((ts, text))
        msg = rec.get("message") or {}
        if rec.get("type") == "assistant" and msg.get("usage") and msg.get("model") != "<synthetic>":
            key = msg.get("id") or rec.get("uuid")
            # Each snapshot of one reply holds a different content block, so keep all tool names.
            names = (replies[key][4] if key in replies else []) + [
                b.get("name") for b in msg.get("content") or [] if isinstance(b, dict) and b.get("type") == "tool_use"]
            replies[key] = (ts, msg.get("model"), bool(rec.get("isSidechain")), _usage_row(msg["usage"]), names)
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use":
                name = b.get("name") or "unknown"
                uses[b.get("id")] = {
                    "name": name,
                    "target": _target(name, b.get("input") or {}),
                    "sidechain": bool(rec.get("isSidechain")),
                }
            elif b.get("type") == "tool_result":
                # shortcut: chars/4 token estimate, same as the scanner; use count_tokens if exact numbers matter
                results[b.get("tool_use_id")] = (_result_chars(b.get("content")) // 4, bool(b.get("is_error")))

    tools, mcp, files, urls, calls = {}, {}, {}, {}, []
    for uid, u in uses.items():
        tokens, err = results.get(uid, (0, False))
        name, target = u["name"], u["target"]
        t = tools.setdefault(name, {"name": name, "calls": 0, "result_tokens": 0, "errors": 0})
        t["calls"] += 1
        t["result_tokens"] += tokens
        t["errors"] += int(err)
        if name.startswith("mcp__"):
            server, _, tool = name[5:].partition("__")
            m = mcp.setdefault(server, {"server": server, "calls": 0, "result_tokens": 0, "tools": set()})
            m["calls"] += 1
            m["result_tokens"] += tokens
            m["tools"].add(tool)
        if name in _FILE_TOOLS and target:
            f = files.setdefault(target, {"path": target, "reads": 0, "writes": 0, "result_tokens": 0})
            f["reads" if name == "Read" else "writes"] += 1
            f["result_tokens"] += tokens
        if name == "WebFetch" and target:
            w = urls.setdefault(target, {"url": target, "calls": 0, "result_tokens": 0})
            w["calls"] += 1
            w["result_tokens"] += tokens
        calls.append({"tool": name, "target": target, "result_tokens": tokens,
                      "is_error": err, "subagent": u["sidechain"]})

    for m in mcp.values():
        m["tools"] = sorted(m["tools"])
    by_tokens = lambda rows: sorted(rows, key=lambda r: r["result_tokens"], reverse=True)

    # Steps: each typed prompt owns every reply (subagents too) until the next prompt.
    steps, starts = [], []
    for ts, text in sorted(prompts):
        if steps and steps[-1]["prompt"] == text:
            continue  # a queued prompt is also written as a user record
        steps.append({"ts": ts, "prompt": text[:300], "turns": 0, "models": {}, "tools": {}})
        starts.append(ts)
    context = []
    for ts, model, side, usage, names in sorted(replies.values(), key=lambda r: r[0]):
        i = bisect.bisect_right(starts, ts) - 1
        if i < 0:
            steps.insert(0, {"ts": ts, "prompt": "(before first prompt)", "turns": 0, "models": {}, "tools": {}})
            starts.insert(0, ts)
            i = 0
        s = steps[i]
        s["turns"] += 1
        m = s["models"].setdefault(model, dict.fromkeys(usage, 0))
        for k, v in usage.items():
            m[k] += v
        for n in names:
            s["tools"][n] = s["tools"].get(n, 0) + 1
        if not side:
            context.append({"ts": ts, "model": model, "tokens": usage["input_tokens"] + usage["cache_read_tokens"]
                            + usage["cache_create_5m_tokens"] + usage["cache_create_1h_tokens"]})

    return {
        "steps": steps,
        "context": context,
        "loaded": sorted(loaded.values(), key=lambda r: r["total_tokens"], reverse=True),
        "tool_calls": len(uses),
        "result_tokens": sum(c["result_tokens"] for c in calls),
        "subagent_calls": sum(c["subagent"] for c in calls),
        "tools": by_tokens(tools.values()),
        "mcp": by_tokens(mcp.values()),
        "files": by_tokens(files.values()),
        "urls": by_tokens(urls.values()),
        "top_results": by_tokens(calls)[:10],
    }


def _md_cell(v) -> str:
    return str(v if v is not None else "").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _md_table(head: list, rows: list) -> str:
    if not rows:
        return "_none_\n"
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(_md_cell(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def to_markdown(s: dict, session_id: str) -> str:
    """Session overview as Markdown, for pasting into project docs."""
    usd = lambda v: f"${v:,.2f}" if v is not None else "?"
    tok = lambda v: f"{v:,}"
    tot = lambda k: sum(m.get(k) or 0 for m in s["models"])
    parts = [
        f"# {s.get('title') or 'Session ' + session_id}\n",
        f"- Session: `{session_id}`",
        f"- Time: {s['models'][0]['started'] if s['models'] else ''} to {s['models'][0]['ended'] if s['models'] else ''}",
        f"- Estimated API cost: **{usd(s['cost_usd'])}**",
        f"- Tokens: {tok(tot('input_tokens'))} input, {tok(tot('output_tokens'))} output, "
        f"{tok(tot('cache_read_tokens'))} cache read, "
        f"{tok(tot('cache_create_5m_tokens') + tot('cache_create_1h_tokens'))} cache write",
        f"- Tool calls: {s['tool_calls']} ({s['subagent_calls']} in subagents), "
        f"about {tok(s['result_tokens'])} tokens of tool results\n",
        "## Cost by model\n",
        _md_table(["Model", "Turns", "Cost"], [[m["model"], m["turns"], usd(m["cost_usd"])] for m in s["models"]]),
        "## Steps (cost per prompt)\n",
        _md_table(["Time", "Prompt", "Turns", "Tools", "Cost"],
                  [[st["ts"][11:19], st["prompt"][:120], st["turns"],
                    ", ".join(f"{k} {v}" for k, v in sorted(st["tools"].items(), key=lambda x: -x[1])[:4]),
                    usd(st.get("cost_usd"))] for st in s["steps"]]),
        "## Loaded into context automatically\n",
        _md_table(["Kind", "Name", "Loads", "Tokens each", "Tokens total"],
                  [[r["kind"], r["name"], r["loads"], tok(r["tokens"]), tok(r["total_tokens"])] for r in s["loaded"]]
                  + ([["**Total**", "", sum(r["loads"] for r in s["loaded"]), "",
                       f"**{tok(sum(r['total_tokens'] for r in s['loaded']))}**"]] if s["loaded"] else [])),
        "## Files read or written\n",
        _md_table(["Path", "Reads", "Writes", "Tokens"],
                  [[f["path"], f["reads"], f["writes"], tok(f["result_tokens"])] for f in s["files"]]),
        "## MCP servers and web\n",
        _md_table(["Source", "Calls", "Tokens"],
                  [["MCP " + m["server"], m["calls"], tok(m["result_tokens"])] for m in s["mcp"]]
                  + [[u["url"], u["calls"], tok(u["result_tokens"])] for u in s["urls"]]),
        "## Tools\n",
        _md_table(["Tool", "Calls", "Non-zero exit / errors", "Result tokens"],
                  [[t["name"], t["calls"], t["errors"], tok(t["result_tokens"])] for t in s["tools"]]),
        "_Tool and context token counts are estimates (characters / 4). Costs use API list prices._\n",
    ]
    return "\n".join(parts)
