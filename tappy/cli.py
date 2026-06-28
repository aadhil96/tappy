"""Tappy command-line interface: MCP management + inspector.

A thin shell over ``tappy.core`` — every command reuses the same discovery, safe-write,
and MCP-protocol code that powers the TUI, so the two surfaces can never drift.

Exit codes: 0 = ok, 1 = error (not found / unreachable / invalid args), 2 = argparse.
"""

from __future__ import annotations

import argparse
import asyncio

from . import output
from .core import mcp_probe
from .core.config_store import ConfigStore, parse_server_fields
from .core.models import Health, Transport
from .core.resolve import ResolveError, ResolvedTarget, resolve_target

# Subcommands handled here; anything else (or nothing) falls through to the TUI.
COMMANDS = {
    "list", "ls", "clients", "add", "remove", "rm", "enable", "disable",
    "inspect", "tools", "resources", "prompts", "call", "probe",
}


def _kv(values: list[str] | None) -> dict[str, str]:
    """Parse repeated ``KEY=VALUE`` flags into a dict."""
    out: dict[str, str] = {}
    for item in values or []:
        key, _, val = item.partition("=")
        if key:
            out[key.strip()] = val.strip()
    return out


# ----------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tappy",
        description="Manage and inspect MCP servers across AI clients. "
        "Run with no command to launch the TUI.",
    )
    sub = p.add_subparsers(dest="subcommand")

    def add_target_flags(sp: argparse.ArgumentParser, with_name: bool = True) -> None:
        if with_name:
            sp.add_argument("name", nargs="?", help="server name from a client config")
        sp.add_argument("--client", help="restrict to a client id (e.g. claude_desktop)")
        sp.add_argument("--transport", choices=[t.value for t in Transport])
        sp.add_argument("--command", help="ad-hoc: stdio command")
        sp.add_argument("--arg", action="append", dest="args", help="ad-hoc: stdio arg (repeatable)")
        sp.add_argument("--args", dest="args_str", help="ad-hoc: stdio args as one string")
        sp.add_argument("--env", action="append", help="ad-hoc: KEY=VALUE (repeatable)")
        sp.add_argument("--url", help="ad-hoc: http/sse url")
        sp.add_argument("--header", action="append", help="ad-hoc: KEY=VALUE (repeatable)")
        sp.add_argument("--timeout", type=float, default=mcp_probe.DEFAULT_TIMEOUT_S)
        sp.add_argument("--json", action="store_true", help="machine-readable output")

    # --- management ---
    sp = sub.add_parser("list", aliases=["ls"], help="list all servers across clients")
    sp.add_argument("--client")
    sp.add_argument("--json", action="store_true")

    sub.add_parser("clients", help="list discovered client configs").add_argument(
        "--json", action="store_true"
    )

    sp = sub.add_parser(
        "add",
        help="add/update a server in a client config",
        epilog="stdio example:  tappy add fs -- npx -y @scope/server .",
    )
    sp.add_argument("name")
    sp.add_argument("--client", help="target client id (default: first discovered)")
    sp.add_argument("--transport", choices=[t.value for t in Transport], default="stdio")
    sp.add_argument("--command", help="stdio command (or use the '-- CMD ARGS…' form)")
    sp.add_argument("--arg", action="append", dest="args", help="stdio arg (repeatable)")
    sp.add_argument("--env", action="append", help="KEY=VALUE (repeatable)")
    sp.add_argument("--url", help="http/sse url")
    sp.add_argument("--header", action="append", help="KEY=VALUE (repeatable)")
    # Note: the stdio command line after `--` is split off in parse() before argparse.

    sp = sub.add_parser("remove", aliases=["rm"], help="remove a server")
    sp.add_argument("name")
    sp.add_argument("--client")

    for verb in ("enable", "disable"):
        sp = sub.add_parser(verb, help=f"{verb} a server in place")
        sp.add_argument("name")
        sp.add_argument("--client")

    # --- inspector ---
    add_target_flags(sub.add_parser("inspect", help="full report for a server"))
    add_target_flags(sub.add_parser("tools", help="list a server's tools"))
    add_target_flags(sub.add_parser("resources", help="list a server's resources"))
    add_target_flags(sub.add_parser("prompts", help="list a server's prompts"))
    add_target_flags(sub.add_parser("probe", help="one-line health check"))

    sp = sub.add_parser("call", help="invoke a tool on a server")
    add_target_flags(sp)
    sp.add_argument("tool", help="tool name to call")
    sp.add_argument("--input", dest="call_args", help="tool arguments as a JSON object")
    sp.add_argument("-a", "--arg-kv", action="append", dest="call_kv",
                    help="tool argument as key=value (repeatable; string values)")
    return p


# ----------------------------------------------------------------- helpers


def _target_args(ns: argparse.Namespace) -> dict:
    """Collect the shared target flags from a namespace into resolve_target kwargs."""
    args = list(ns.args or [])
    if getattr(ns, "args_str", None):
        args = ns.args_str.split()
    return dict(
        name=getattr(ns, "name", None),
        client_id=ns.client,
        transport=ns.transport,
        command=ns.command,
        args=args,
        env=_kv(ns.env),
        url=ns.url,
        headers=_kv(ns.header),
    )


def _resolve(store: ConfigStore, ns: argparse.Namespace) -> ResolvedTarget:
    return resolve_target(store, **_target_args(ns))


# ----------------------------------------------------------------- handlers


def cmd_list(store: ConfigStore, ns) -> int:
    store.discover()
    rows = [
        (dc, s)
        for dc in store.discovered
        for s in dc.config.servers.values()
        if not ns.client or dc.config.client_id == ns.client
    ]
    if ns.json:
        output.print_json([output.server_to_dict(s, dc.config.client_id) for dc, s in rows])
    else:
        output.render_servers(rows)
    return 0


def cmd_clients(store: ConfigStore, ns) -> int:
    store.discover()
    if ns.json:
        output.print_json([
            {
                "client": dc.config.client_id,
                "display_name": dc.config.display_name,
                "path": str(dc.config.path),
                "servers": len(dc.config.servers),
            }
            for dc in store.discovered
        ])
    else:
        output.render_clients(store.discovered)
    return 0


def cmd_add(store: ConfigStore, ns) -> int:
    store.discover()
    if not store.discovered:
        output.error("no client configs found to add to")
        return 1
    dc = next((d for d in store.discovered if d.config.client_id == ns.client), None) \
        if ns.client else store.discovered[0]
    if dc is None:
        output.error(f"client '{ns.client}' not found")
        return 1
    # `tappy add NAME -- npx -y pkg` -> passthrough = ["npx", "-y", "pkg"] (split in parse()).
    rest = list(getattr(ns, "passthrough", []) or [])
    command = ns.command or (rest[0] if rest else "")
    args = ns.args or (rest[1:] if rest else [])
    if not command and not ns.url:
        output.error("provide a stdio command (--command or '-- CMD ARGS…') or --url")
        return 1
    server = parse_server_fields(
        name=ns.name,
        transport="http" if ns.url else ns.transport,
        command=command,
        args=" ".join(args),
        env="\n".join(ns.env or []),
        url=ns.url or "",
        headers="\n".join(ns.header or []),
    )
    backup = store.upsert_server(dc, server)
    output.console.print(
        f"[green]✓[/green] wrote [bold]{server.name}[/bold] to {dc.config.path}  "
        f"[dim](backup: {backup})[/dim]"
    )
    return 0


def cmd_remove(store: ConfigStore, ns) -> int:
    try:
        target = resolve_target(store, ns.name, client_id=ns.client)
    except ResolveError as exc:
        output.error(str(exc))
        return 1
    backup = store.remove_server(target.source, ns.name)
    output.console.print(f"[green]✓[/green] removed [bold]{ns.name}[/bold]  [dim](backup: {backup})[/dim]")
    return 0


def cmd_toggle(store: ConfigStore, ns, enabled: bool) -> int:
    try:
        target = resolve_target(store, ns.name, client_id=ns.client)
    except ResolveError as exc:
        output.error(str(exc))
        return 1
    backup = store.set_enabled(target.source, ns.name, enabled)
    word = "enabled" if enabled else "disabled"
    output.console.print(f"[green]✓[/green] {ns.name} {word}  [dim](backup: {backup})[/dim]")
    return 0


def cmd_inspect(store: ConfigStore, ns) -> int:
    target = _resolve(store, ns)
    status = asyncio.run(mcp_probe.probe(target.server, timeout=ns.timeout))
    fp = mcp_probe.tools_fingerprint(status.tools) if status.tools else None
    if ns.json:
        data = output.status_to_dict(status)
        data["server"] = output.server_to_dict(target.server)
        data["fingerprint"] = fp
        output.print_json(data)
    else:
        output.render_inspect(target.server, status, fp)
    return 0 if status.health is Health.RUNNING else 1


def cmd_probe(store: ConfigStore, ns) -> int:
    target = _resolve(store, ns)
    status = asyncio.run(mcp_probe.probe(target.server, timeout=ns.timeout))
    if ns.json:
        output.print_json(output.status_to_dict(status))
    else:
        output.render_status_line(target.server.name, status)
    return 0 if status.health is Health.RUNNING else 1


def cmd_tools(store: ConfigStore, ns) -> int:
    target = _resolve(store, ns)
    status = asyncio.run(mcp_probe.probe(target.server, timeout=ns.timeout))
    if status.health is not Health.RUNNING:
        output.error(status.error or "server not reachable")
        return 1
    if ns.json:
        output.print_json([
            {"name": t.name, "description": t.description, "inputSchema": t.input_schema}
            for t in status.tools
        ])
    else:
        output.render_tools(status)
    return 0


def cmd_resources(store: ConfigStore, ns) -> int:
    return _cmd_simple_list(store, ns, "resources")


def cmd_prompts(store: ConfigStore, ns) -> int:
    return _cmd_simple_list(store, ns, "prompts")


def _cmd_simple_list(store: ConfigStore, ns, attr: str) -> int:
    target = _resolve(store, ns)
    status = asyncio.run(mcp_probe.probe(target.server, timeout=ns.timeout))
    if status.health is not Health.RUNNING:
        output.error(status.error or "server not reachable")
        return 1
    items = getattr(status, attr)
    if ns.json:
        output.print_json(items)
    else:
        output.render_list(attr, items)
    return 0


def cmd_call(store: ConfigStore, ns) -> int:
    import json as _json

    target = _resolve(store, ns)
    arguments: dict = {}
    if ns.call_args:
        try:
            arguments = _json.loads(ns.call_args)
        except _json.JSONDecodeError as exc:
            output.error(f"--args is not valid JSON: {exc}")
            return 1
    arguments.update(_kv(ns.call_kv))
    try:
        result = asyncio.run(
            mcp_probe.call_tool(target.server, ns.tool, arguments, timeout=ns.timeout)
        )
    except Exception as exc:  # noqa: BLE001
        output.error(str(exc))
        return 1
    if ns.json:
        output.print_json(output.call_result_to_dict(result))
    else:
        output.render_call_result(result)
    return 1 if getattr(result, "isError", False) else 0


_HANDLERS = {
    "list": cmd_list, "ls": cmd_list,
    "clients": cmd_clients,
    "add": cmd_add,
    "remove": cmd_remove, "rm": cmd_remove,
    "enable": lambda s, ns: cmd_toggle(s, ns, True),
    "disable": lambda s, ns: cmd_toggle(s, ns, False),
    "inspect": cmd_inspect,
    "probe": cmd_probe,
    "tools": cmd_tools,
    "resources": cmd_resources,
    "prompts": cmd_prompts,
    "call": cmd_call,
}


def parse(argv: list[str]) -> argparse.Namespace:
    """Parse argv, splitting off any ``-- CMD ARGS…`` stdio passthrough first.

    Handling ``--`` ourselves (rather than via argparse REMAINDER) keeps later flags
    like ``--url`` from being swallowed, and lets stdio args start with a dash.
    """
    passthrough: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        passthrough = argv[i + 1:]
        argv = argv[:i]
    ns = build_parser().parse_args(argv)
    ns.passthrough = passthrough
    return ns


def run(argv: list[str]) -> int:
    """Parse ``argv`` and dispatch. Returns a process exit code."""
    parser = build_parser()
    ns = parse(argv)
    if not ns.subcommand:
        parser.print_help()
        return 0
    handler = _HANDLERS[ns.subcommand]
    store = ConfigStore()
    try:
        return handler(store, ns)
    except ResolveError as exc:
        output.error(str(exc))
        return 1
    except KeyboardInterrupt:
        return 130
