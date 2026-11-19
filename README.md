# Token Dashboard

A local dashboard for the cost and context of your Claude Code sessions. It answers:
- What did this session cost?
- Which prompt was expensive, and why?
- What went into the context?
- Which files were read, and which MCP servers and URLs were called?
- What did the subagents spend?
- What did the work on a branch cost, and how many commits did it produce?

Everything runs on your computer. No network calls, no telemetry, no tokens spent, no `pip install`.

## Pages

| Page | What it shows |
|---|---|
| **Overview** | Total tokens and cost for a date range, daily charts, split by model and project, top tools. A **Subagents** section shows cost by subagent type (Explore, general-purpose, workflow…) and the most expensive subagent runs. |
| **Sessions** | Sessions with their titles, filterable by project. Click a session for KPI cards and the tabs below. |
| **Prompts** | The most expensive steps across all sessions: real cost, what drove it (output, cache read or cache write) and a ⚠ cache-rebuild flag. Filter by date, project and model. |
| **Projects** | Tokens per project. The **Cost by project & branch** table shows cost per git branch, the commits made during that branch's sessions, lines added and deleted, and cost per commit. |
| **Skills / Tips / Settings** | Skill usage, saving tips, plan selection. |

**Session page tabs:**

| Tab | What it shows |
|---|---|
| Overview | Context size per turn (chart), cost by model |
| Steps | Every prompt you typed: its cost, how many turns it took, which tools it called |
| Auto-loaded | What entered the context without a tool call: CLAUDE.md, rules and memory files, skills, hook output, MCP instructions, tool and skill lists |
| Tools | Calls, errors and result tokens per tool; the 10 largest tool results |
| Subagents | Each subagent run in the session: type, description, cost |
| Files | Files read and written |
| MCP & web | MCP servers and URLs called |
| Turn-by-turn | Token counts for every record |

Every table ends with a total row. **⬇ export .md** downloads the session summary as a Markdown file, ready to drop into project docs.

## Install (Windows)

Needs Python 3. With git installed, commit matching works too.

```powershell
git clone https://github.com/hasan-ozturk/tokendashboard.git C:\Repos\tokendashboard
cd C:\Repos\tokendashboard
.\install.ps1                                   # http://localhost:8765
.\install.ps1 -HostName tdb.local -AutoStart    # http://tdb.local:8765, starts at Windows logon
```

The script:
1. Installs the `token-dashboard` skill for Claude Code into `~/.claude/skills/`.
2. With `-HostName`, adds one line to the hosts file. Windows asks for admin rights once.
3. With `-AutoStart`, puts a hidden launcher in the Startup folder.
4. Starts the dashboard.

The first start scans all transcripts, which can take about a minute.

If the script fails with an `ExecutionPolicy` error, run it as `powershell -ExecutionPolicy Bypass -File .\install.ps1`.

## Install (macOS / Linux)

```bash
cd tokendashboard
PORT=8765 python3 cli.py dashboard
```

To use the skill, copy `skill/token-dashboard/SKILL.md` to `~/.claude/skills/token-dashboard/SKILL.md` and fill in the `{{...}}` fields:

| Field | Value |
|---|---|
| `{{REPO_DIR}}` | path to this repo |
| `{{BASE_URL}}` | `http://localhost:8765` |
| `{{PORT}}` | `8765` |
| `{{PYTHON}}` | `python3` |

## Usage

In Claude Code, ask for the "token dashboard" or "what did this session cost". Claude checks the dashboard, starts it if it is not running, and replies with a link to the current session.

You can also open it in a browser: `http://localhost:8765` (or `http://tdb.local:8765`).

## What it sees

| Source | Included |
|---|---|
| Claude Code: VS Code and Cursor extension, terminal (CLI) | Yes |
| The "Code" tab in Claude Desktop | Probably (it runs Claude Code locally) |
| Regular chats in Claude Desktop and claude.ai | No, they leave no local record |
| Cursor's own Chat and Agent | No |

## Good to know

- **Costs use API list prices** (`pricing.json`). On a subscription you do not pay this amount; it shows what the same usage would cost on the API.
- **Some token counts are estimates.** Tool results and auto-loaded content are counted as characters / 4.
- **Commit matching is by time.** It counts commits by your git user made during a session on that branch or up to 1 hour after it. Commits made by hand in the same window count too. Line counts include generated and vendored files.
- **Cache rebuild:** a turn that writes more than 100K tokens of context to the cache again is flagged with ⚠. This usually happens when you return to an old session after more than 1 hour, or switch models. Starting a new session or running `/compact` first is cheaper.
- **Privacy:** the dashboard reads prompt text and keeps it in a local database, but sends nothing anywhere. The database is `~/.claude/token-dashboard.db`; delete it and the next start rescans the transcripts.
- **Delay:** new turns show up within 30 seconds.

## Tests

```bash
python -m unittest discover -s tests
```

## Credits

Forked from [nateherkai/token-dashboard](https://github.com/nateherkai/token-dashboard) (MIT license, see `LICENSE`). Original README: [docs/UPSTREAM_README.md](docs/UPSTREAM_README.md). The branch cost and subagent ideas come from [phuryn/claude-usage](https://github.com/phuryn/claude-usage) and [xiufengsun/TokenTracker](https://github.com/xiufengsun/TokenTracker).

Added in this fork:
- Session overview with tabs and total rows
- Cost per prompt and per step, cache-rebuild detection
- Breakdown of auto-loaded context
- Cost per project and git branch, with matching commits
- Cost per subagent type and run
- Markdown export, session titles, project-to-sessions filter
- Claude Code skill and Windows install script
- Current model prices (Fable, Opus 5.5, Sonnet 5.5, Haiku 5.5)
- An index that fixes slow scans on large databases
- Plan selection stored in the database instead of the browser
