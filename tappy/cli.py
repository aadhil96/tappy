"""Tappy command-line interface: MCP management + inspector.

A thin shell over ``tappy.core`` — every command reuses the same discovery, safe-write,
and MCP-protocol code that powers the TUI, so the two surfaces can never drift.

Exit codes: 0 = ok, 1 = error (not found / unreachable / invalid args), 2 = argparse.
"""

from __future__ import annotations

import argparse
import asyncio

from . import output
from .core import mcp_probe, registry
from .core.config_store import ConfigStore, parse_server_fields
from .core.models import Health, Transport
from .core.registry import RegistryError
from .core.resolve import ResolveError, ResolvedTarget, resolve_target

# Subcommands handled here; anything else (or nothing) falls through to the TUI.
COMMANDS = {
    "list", "ls", "clients", "add", "remove", "rm", "enable", "disable",
    "inspect", "tools", "resources", "prompts", "call", "probe",
    "registry", "team", "apply", "lint", "sync",
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

    # --- team registry (provision/standardize servers across a team) ---
    sp = sub.add_parser("registry", aliases=["team"], help="show or create the team registry")
    sp.add_argument("--registry", help="path to the registry file")
    sp.add_argument("--init", action="store_true", help="create a starter registry file")
    sp.add_argument("--from-client", help="when --init, seed from this client's servers")
    sp.add_argument("--json", action="store_true")

    sp = sub.add_parser("apply", help="provision the team registry into local client configs")
    sp.add_argument("--registry", help="path to the registry file")
    sp.add_argument("--client", help="only apply to this client id")
    sp.add_argument("--dry-run", action="store_true", help="show changes without writing")
    sp.add_argument("--json", action="store_true")

    sp = sub.add_parser("lint", help="report drift between local configs and the registry")
    sp.add_argument("--registry", help="path to the registry file")
    sp.add_argument("--client", help="only check this client id")
    sp.add_argument("--json", action="store_true")

    sp = sub.add_parser("sync", help="copy a server from one client to another")
    sp.add_argument("name", help="server name to copy")
    sp.add_argument("--from", dest="from_client", help="source client id (auto if unambiguous)")
    sp.add_argument("--to", dest="to_client", required=True, help="destination client id")
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


# ----------------------------------------------------------------- team registry


def _target_clients(store: ConfigStore, client_id: str | None):
    """Discovered client configs, optionally narrowed to one client id."""
    store.discover()
    return [dc for dc in store.discovered if not client_id or dc.config.client_id == client_id]


def cmd_registry(store: ConfigStore, ns) -> int:
    if ns.init:
        seed: dict = {}
        if ns.from_client:
            clients = _target_clients(store, ns.from_client)
            if not clients:
                output.error(f"client '{ns.from_client}' not found to seed from")
                return 1
            seed = dict(clients[0].config.servers)
        path = registry.find_registry_path(ns.registry) or registry.USER_REGISTRY
        try:
            written = registry.init_registry(path, seed)
        except RegistryError as exc:
            output.error(str(exc))
            return 1
        output.console.print(
            f"[green]✓[/green] created registry at {written}"
            + (f" seeded with {len(seed)} server(s) from {ns.from_client}" if seed else "")
        )
        return 0
    try:
        reg = registry.load_registry(ns.registry)
    except RegistryError as exc:
        output.error(str(exc))
        return 1
    if ns.json:
        output.print_json({
            "path": str(reg.path),
            "servers": [output.server_to_dict(s) for s in reg.servers.values()],
        })
    else:
        output.console.print(f"[bold]Team registry[/bold]  [dim]{reg.path}[/dim]")
        output.render_servers([(_RegistrySource(), s) for s in reg.servers.values()])
    return 0


class _RegistrySource:
    """Adapter-shaped stand-in so render_servers can show registry rows."""

    class config:  # noqa: N801 - mimic DiscoveredConfig.config.display_name
        display_name = "team-registry"


def cmd_apply(store: ConfigStore, ns) -> int:
    try:
        reg = registry.load_registry(ns.registry)
    except RegistryError as exc:
        output.error(str(exc))
        return 1
    targets = _target_clients(store, ns.client)
    if not targets:
        output.error("no client configs to apply to" + (f" (client '{ns.client}')" if ns.client else ""))
        return 1

    planned: list[dict] = []
    for dc in targets:
        for name, want in reg.servers.items():
            have = dc.config.servers.get(name)
            if have is None:
                action = "add"
            elif registry.differs(have, want):
                action = "update"
            else:
                continue  # already in sync
            planned.append({"client": dc.config.client_id, "server": name, "action": action})
            if not ns.dry_run:
                store.upsert_server(dc, want)

    if ns.json:
        output.print_json({"dry_run": ns.dry_run, "changes": planned})
    elif not planned:
        output.console.print("[green]✓[/green] all clients already match the registry")
    else:
        verb = "Would apply" if ns.dry_run else "Applied"
        output.console.print(f"[bold]{verb} {len(planned)} change(s):[/bold]")
        for c in planned:
            output.console.print(f"  {c['action']:<6} {c['server']} → {c['client']}")
        if not ns.dry_run:
            output.console.print("[dim](backups written to ~/.tappy/backups/)[/dim]")
    return 0


def cmd_lint(store: ConfigStore, ns) -> int:
    try:
        reg = registry.load_registry(ns.registry)
    except RegistryError as exc:
        output.error(str(exc))
        return 1
    targets = _target_clients(store, ns.client)
    unapproved: list[dict] = []  # local server not in registry
    missing: list[dict] = []     # registry server absent locally
    drifted: list[dict] = []     # present but differs

    for dc in targets:
        local = dc.config.servers
        for name, server in local.items():
            if name not in reg.servers:
                unapproved.append({"client": dc.config.client_id, "server": name})
            elif registry.differs(server, reg.servers[name]):
                drifted.append({"client": dc.config.client_id, "server": name})
        for name in reg.servers:
            if name not in local:
                missing.append({"client": dc.config.client_id, "server": name})

    if ns.json:
        output.print_json({"unapproved": unapproved, "drifted": drifted, "missing": missing})
    else:
        if not (unapproved or drifted or missing):
            output.console.print("[green]✓[/green] all clients are in sync with the registry")
        for label, items, style in (
            ("UNAPPROVED (not in registry)", unapproved, "red"),
            ("DRIFTED (differs from registry)", drifted, "yellow"),
            ("MISSING (in registry, not local)", missing, "cyan"),
        ):
            if items:
                output.console.print(f"[{style} bold]{label}:[/{style} bold]")
                for c in items:
                    output.console.print(f"  {c['server']} @ {c['client']}")
    # Non-zero exit when there are unapproved servers — useful as a CI gate.
    return 1 if unapproved else 0


def cmd_sync(store: ConfigStore, ns) -> int:
    store.discover()
    try:
        src = resolve_target(store, ns.name, client_id=ns.from_client)
    except ResolveError as exc:
        output.error(str(exc))
        return 1
    dst = next((dc for dc in store.discovered if dc.config.client_id == ns.to_client), None)
    if dst is None:
        output.error(f"destination client '{ns.to_client}' not found (config must exist)")
        return 1
    backup = store.upsert_server(dst, src.server)
    output.console.print(
        f"[green]✓[/green] copied [bold]{ns.name}[/bold] → {dst.config.display_name}  "
        f"[dim](backup: {backup})[/dim]"
    )
    return 0


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
    "registry": cmd_registry, "team": cmd_registry,
    "apply": cmd_apply,
    "lint": cmd_lint,
    "sync": cmd_sync,
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
