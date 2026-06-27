# tappy

A fast, keyboard-driven **terminal app to discover, configure, run, inspect and monitor
MCP (Model Context Protocol) servers** across all your AI clients (Claude Desktop, Claude
Code, Cursor, …) from one place.

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

```bash
tappy          # or: python -m tappy
```

### Keys
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
