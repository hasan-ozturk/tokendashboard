"""Commits made while Claude Code sessions were running, read from the local git repo.

Attribution is by time: a commit counts for a branch when it is on that branch,
written by the repo's configured git user, and its author date falls inside a
session on that branch (or up to GRACE after it ends). This is an estimate: it
cannot tell a commit Claude helped with from one made by hand in the same window.
"""
from __future__ import annotations

import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

GRACE = timedelta(hours=1)  # commits shortly after a session usually finish its work
_STAT = re.compile(r"(\d+) insertion|(\d+) deletion")


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)


def _git(cwd: str, *args: str) -> Optional[str]:
    try:
        out = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None  # git missing, folder gone, or too slow
    return out.stdout if out.returncode == 0 else None


def _merge(windows: List[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
    merged = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def parse_log(text: str) -> list:
    """Parse `git log --format=%x1e%H%x1f%aI%x1f%s --shortstat` output."""
    commits = []
    for chunk in text.split("\x1e")[1:]:
        head, _, stat = chunk.partition("\n")
        parts = head.split("\x1f")
        if len(parts) < 3:
            continue
        added = deleted = 0
        for a, d in _STAT.findall(stat):
            added += int(a or 0)
            deleted += int(d or 0)
        commits.append({"hash": parts[0], "date": parts[1], "subject": parts[2][:200],
                         "added": added, "deleted": deleted})
    return commits


_CACHE: dict = {}
_TTL = 300  # seconds; git log on big repos is slow and the page reloads often


def commits_for(cwd: Optional[str], branch: Optional[str], sessions: List[Tuple[str, str]]) -> Optional[dict]:
    """Cached `_commits_for`."""
    key = (cwd, branch, tuple(sorted(sessions)))
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    result = _commits_for(cwd, branch, sessions)
    _CACHE[key] = (time.time(), result)
    return result


def _commits_for(cwd: Optional[str], branch: Optional[str], sessions: List[Tuple[str, str]]) -> Optional[dict]:
    """Commits on `branch` inside the given (start, end) session windows; None when cwd is not a git repo."""
    root = (_git(cwd, "rev-parse", "--show-toplevel") or "").strip() if cwd and sessions else ""
    if not root:
        return None
    windows = _merge([(_parse_ts(s), _parse_ts(e) + GRACE) for s, e in sessions])
    email = (_git(cwd, "config", "user.email") or "").strip()
    # A deleted or renamed branch: fall back to all refs, marked as approximate.
    exact = bool(branch) and _git(cwd, "rev-parse", "--verify", "--quiet", "--end-of-options", f"{branch}^{{commit}}") is not None
    args = ["log", "--no-merges", f"--since={windows[0][0].isoformat()}", f"--until={windows[-1][1].isoformat()}",
            "--format=%x1e%H%x1f%aI%x1f%s", "--shortstat"]
    if email:
        args.append(f"--author={email}")
    args += ["--end-of-options", branch] if exact else ["--all"]
    text = _git(cwd, *args)
    if text is None:
        return None
    commits = [c for c in parse_log(text)
               if any(s <= _parse_ts(c["date"]) <= e for s, e in windows)]
    return {"root": root, "commits": commits, "approx": not exact, "author": email}
