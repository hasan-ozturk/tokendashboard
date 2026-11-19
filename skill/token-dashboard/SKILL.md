---
name: token-dashboard
description: Open the local Token Dashboard and give the user a clickable link to the current Claude Code session's cost and context overview. Use when the user asks about session cost, token usage, what was read or loaded into context, which tools, MCP servers or URLs were called, cost per prompt, or says "dashboard", "token dashboard", "tdb", "bu session'ın maliyeti", "token panosu".
---

# Token Dashboard

The dashboard is a local web app in `{{REPO_DIR}}`. It reads the transcripts Claude Code writes to `~/.claude/projects/` and makes no network calls. Base URL: `{{BASE_URL}}`.

## Steps

1. Check that the server answers: `curl -s -o /dev/null -w "%{http_code}" {{BASE_URL}}/` (on Windows PowerShell use `curl.exe` and `-o NUL`).
2. If it does not return 200, start it in the background (use the tool's background option, do not wait for it to exit):
   - Windows: `$env:PORT='{{PORT}}'; Set-Location "{{REPO_DIR}}"; {{PYTHON}} cli.py dashboard --no-open`
   - macOS / Linux: `cd "{{REPO_DIR}}" && PORT={{PORT}} python3 cli.py dashboard --no-open`
   Wait about 3 seconds, then check again. The first start scans all transcripts and can take a minute.
3. Find the current session id. It is the file name, without `.jsonl`, of the most recently modified `*.jsonl` directly inside `~/.claude/projects/<slug>/`. The slug is the current working directory with every character that is not a letter or a digit replaced by `-` (example: `C:\Repos\my.app` becomes `C--Repos-my-app`).
4. Reply with the links, plus at most one line of explanation:
   - This session: `{{BASE_URL}}/#/sessions/<session-id>`
   - All sessions: `{{BASE_URL}}/#/sessions`
   - Most expensive steps: `{{BASE_URL}}/#/prompts`

New turns reach the dashboard within 30 seconds. Costs are API list prices; on a subscription plan they show what the usage would cost on the API.
