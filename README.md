# tappy

An **MCP management system + inspector** for your terminal — a fast keyboard-driven
**TUI** *and* a scriptable **CLI** to discover, configure, run, inspect and monitor MCP
(Model Context Protocol) servers across all your AI clients (Claude Desktop, Claude Code,
Cursor, …) from one place.

- **TUI** (`tappy`) — interactive dashboard for managing and probing servers.
- **CLI** (`tappy <command>`) — pipeable management + a terminal MCP Inspector.

## Why

MCP server config is scattered across per-client JSON files with no visibility into
whether a server is healthy or what it actually exposes. `tappy` gives you one
dashboard to see them all, safely edit them, and debug them.

## Features

**Configuration & operations**
- Auto-discovers configs across Claude Desktop, Claude Code (user + project) and Cursor.
- Add / edit servers via a guided form — never hand-edit JSON.
- **Safe writes**: non-destructive (only the `mcpServers` section changes), atomic, and
  every write is backed up to `~/.tappy/backups/` first. A diff preview is shown before
  anything is written.
- Enable / disable a server in place.

**Inspection & monitoring**
- Live status via the real MCP protocol (`● running / ○ stopped / ⚠ error`) with latency.
- Lists each server's real **tools, resources, and prompts**.
- **Tool runner** — invoke any tool with JSON args and see the raw response (a mini MCP
  Inspector in your terminal).

**Security**
- **Tool-definition pinning**: fingerprints each server's tools on first trust and warns
  you if they change later (detects post-approval "rug-pull" tool mutation).

## Install

```bash
uv venv && uv pip install -e ".[dev]"
```

## Run

### TUI (management dashboard)
```bash
tappy          # or: tappy ui  /  python -m tappy
```

### CLI (management + inspector)
```bash
# management
tappy list                       # all servers across every client (add --json to script)
tappy clients                    # discovered client config files
tappy add fs --command npx --arg -y --arg @modelcontextprotocol/server-filesystem --arg .
tappy enable fs                  # / tappy disable fs
tappy remove fs

# inspector (a named server, or an ad-hoc one not yet installed)
tappy inspect fs                 # status + tools + resources + prompts + fingerprint
tappy tools fs --json            # tool list with input schemas
tappy probe fs                   # one-line health + latency
tappy call fs read_file -a path=README.md
tappy inspect --command npx --args "-y @modelcontextprotocol/server-everything"
```

Every data command supports `--json` and returns exit code `0` on success, `1` on
error/unreachable — so it drops straight into scripts and CI. Secret env/header *values*
are masked in output.

### Team registry (standardize servers across a team)
Keep one git-tracked source of truth and provision it to everyone's local clients.

```bash
tappy registry --init --from-client claude_desktop   # create tappy.team.json, seeded
tappy registry                                        # show the approved server set
tappy apply --dry-run                                 # preview what would change
tappy apply                                           # provision into local client configs (backed up)
tappy lint                                            # report drift; exit 1 if unapproved servers exist (CI gate)
tappy sync github --from claude_desktop --to cursor   # copy one server between clients
```

Registry path resolves from `--registry`, `$TAPPY_REGISTRY`, `./tappy.team.json`, then
`~/.tappy/tappy.team.json`. Commit `tappy.team.json` to your repo; teammates run
`tappy apply`.

### Keys (TUI)
| Key | Action |
|-----|--------|
| `r` | reload / rediscover configs |
| `p` / `P` | probe selected / all servers |
| `a` / `e` / `d` | add / edit / delete server |
| `space` | enable / disable server |
| `t` | open tool runner for the selected server |
| `q` | quit |

## Tests

```bash
pytest
```
