<div align="center">

# Tappy

**One terminal app to manage and inspect every MCP server you run.**

A fast, keyboard-driven **TUI** *and* a scriptable **CLI** to discover, configure, run,
inspect, monitor and standardize **MCP (Model Context Protocol)** servers across all your
AI clients — Claude Desktop, Claude Code, Cursor, and more.

</div>

---

## What is Tappy?

MCP servers are the plugins that give AI tools their real-world powers — filesystem
access, GitHub, databases, web search, custom APIs. But each AI client stores its servers
in its **own** JSON config file, in its own place, with no way to see whether a server
actually works or what it exposes.

**Tappy is the control panel for all of it.** It reads every client's config into one
view and lets you:

- **see** every server across every client at a glance,
- **edit** them safely (with backups and validation, never raw JSON),
- **inspect** them over the real MCP protocol — list their tools/resources/prompts and
  even call a tool to test it,
- **monitor** their health and latency,
- **standardize** a server set across a whole team.

It ships as two surfaces over the same engine:

| Surface | Command | Use it for |
|---|---|---|
| **TUI** (dashboard) | `tappy` | Interactive browsing, probing, editing |
| **CLI** (scriptable) | `tappy <command>` | Automation, CI, a terminal MCP Inspector |

## Why Tappy exists

Managing MCP servers today means:

- **Scattered config** — `claude_desktop_config.json`, `~/.claude.json`,
  `.cursor/mcp.json`… all different, all edited by hand.
- **No visibility** — you can't tell which servers start, which are healthy, or what
  tools they expose without launching a client and hoping.
- **Risky edits** — one stray comma silently breaks a server.
- **No team story** — everyone configures their own servers slightly differently.
- **Security blind spots** — a server can quietly change the tools it offers *after*
  you've trusted it ("rug-pull").

Tappy fixes each of these with one tool that speaks the MCP protocol and treats your
config files with care.

## Features

### Configuration & discovery
- **Auto-discovers** servers across Claude Desktop, Claude Code (user + project) and
  Cursor — plus any custom config path.
- **Normalized model** — stdio, HTTP and SSE servers presented the same way.
- **Guided add/edit** in the TUI — pick transport, command, args, env, headers; validated
  before saving.

### Safe operations
- **Non-destructive writes** — only the `mcpServers` section is touched; everything else
  in the file is preserved.
- **Atomic + backed up** — every change is written atomically and a timestamped backup is
  saved to `~/.tappy/backups/` first.
- **Diff preview** before anything is written.
- **Enable / disable** a server in place without deleting it.

### Inspection & debugging (a terminal MCP Inspector)
- **Live status** over the real MCP protocol: `● running / ○ stopped / ⚠ error` with
  handshake latency.
- **Capability listing** — a server's actual **tools, resources and prompts** (with input
  schemas).
- **Tool runner** — invoke any tool with JSON/`key=value` args and see the raw response.
- **Ad-hoc inspection** — point Tappy at a server that isn't installed anywhere yet via
  `--command` / `--url`.

### Monitoring
- Probe one server or all of them; see latency and tool counts at a glance.

### Security
- **Tool-definition pinning** — Tappy fingerprints each server's tools the first time it
  trusts them and **warns you if they change later**, catching post-approval tool
  mutation ("rug-pull" / tool poisoning).
- Secret `env`/`header` **values are masked** in all output.

### Team registry
- A single git-tracked **`tappy.team.json`** as the source of truth for approved servers.
- **`tappy apply`** provisions it into everyone's local clients.
- **`tappy lint`** reports drift and exits non-zero on unapproved servers — a ready-made
  **CI gate**.
- **`tappy sync`** copies a server from one client to another.

## Install

Requires Python 3.11+.

```bash
git clone https://github.com/aadhil96/tappy.git
cd tappy
uv venv && uv pip install -e ".[dev]"   # or: pip install -e ".[dev]"
```

This installs the `tappy` command.

## Quick start

```bash
tappy                 # launch the interactive TUI dashboard
tappy list            # or jump straight to the CLI
```

## CLI reference

Every data command supports `--json` (machine-readable) and returns exit code **0** on
success / **1** on error — so it drops straight into scripts and CI.

### Manage
```bash
tappy list                         # all servers across every client
tappy clients                      # discovered client config files
tappy add fs -- npx -y @modelcontextprotocol/server-filesystem .   # add a stdio server
tappy add api --url https://example.com/mcp                        # add a remote server
tappy enable fs        # / tappy disable fs
tappy remove fs
```
> Tip: put the stdio command after `--` so args like `-y` aren't mistaken for flags.

### Inspect (the MCP Inspector part)
```bash
tappy inspect fs                   # status + tools + resources + prompts + fingerprint
tappy tools fs --json              # tools with their input schemas
tappy resources fs                 # list resources
tappy prompts fs                   # list prompts
tappy probe fs                     # one-line health + latency
tappy call fs read_file -a path=README.md          # invoke a tool
tappy call fs read_file --input '{"path":"x"}'     # ...or pass JSON args

# inspect something not installed anywhere yet:
tappy inspect --command npx --args "-y @modelcontextprotocol/server-everything"
```

### Team workflow
```bash
tappy registry --init --from-client claude_desktop   # create tappy.team.json, seeded
tappy registry                                        # show the approved server set
tappy apply --dry-run                                 # preview changes
tappy apply                                           # provision into local clients (backed up)
tappy lint                                            # report drift (exit 1 = CI gate)
tappy sync github --from claude_desktop --to cursor   # copy a server between clients
```
Registry path resolves from `--registry` → `$TAPPY_REGISTRY` → `./tappy.team.json` →
`~/.tappy/tappy.team.json`. Commit `tappy.team.json`; teammates run `tappy apply`.

## TUI keys

| Key | Action |
|-----|--------|
| `r` | reload / rediscover configs |
| `p` / `P` | probe selected / all servers |
| `a` / `e` / `d` | add / edit / delete server |
| `space` | enable / disable server |
| `t` | open the tool runner for the selected server |
| `q` | quit |

## Architecture

Both surfaces sit on one shared core, so the TUI and CLI can never disagree.

```
tappy/
├── app.py            # Textual TUI (dashboard, detail pane, modals)
├── cli.py            # argparse CLI (management + inspector)
├── output.py         # rich tables + --json renderers
├── ui/               # TUI modals: add/edit form, confirm/diff, tool runner
└── core/             # the shared engine
    ├── models.py         # normalized ServerDef / HealthStatus
    ├── config_store.py   # discovery + safe (atomic, backed-up) writes
    ├── adapters/         # one per client: claude_desktop, claude_code, cursor, generic
    ├── mcp_probe.py      # speaks MCP: initialize, list, call_tool, fingerprint
    ├── resolve.py        # resolve a target by name or ad-hoc flags
    ├── registry.py       # team registry: load / apply / lint / sync
    └── security.py       # tool-definition pinning store
```

**Built with:** Python · [Textual](https://textual.textualize.io/) ·
the official [`mcp`](https://modelcontextprotocol.io/) SDK · [Rich](https://rich.readthedocs.io/).

## Development

```bash
pytest                # run the test suite
python -m tappy ...   # equivalent to the `tappy` command
```

## Roadmap

- Live `watch` mode (continuous health monitoring)
- Secrets → OS keychain
- Log tailing (stderr + client log files)
- Marketplace / registry install of popular servers

## License

MIT
