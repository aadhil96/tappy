"""Rendering for the CLI: human-friendly rich tables and ``--json`` output.

Keeping all formatting here means command handlers in ``cli.py`` stay focused on logic.
"""

from __future__ import annotations

import json as _json
import sys

from rich.console import Console
from rich.table import Table

from .core.config_store import DiscoveredConfig
from .core.models import Health, HealthStatus, ServerDef

console = Console()
err_console = Console(stderr=True)


def print_json(data) -> None:
    """Emit compact-ish pretty JSON to stdout (for scripting/piping)."""
    sys.stdout.write(_json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def error(message: str) -> None:
    err_console.print(f"[red]error:[/red] {message}")


# --------------------------------------------------------------------- serializers


def server_to_dict(server: ServerDef, client_id: str | None = None) -> dict:
    d = {
        "name": server.name,
        "transport": server.transport.value,
        "enabled": server.enabled,
        "launch": server.summary(),
    }
    if server.transport.value == "stdio":
        d["command"] = server.command
        d["args"] = list(server.args)
        d["env"] = {k: "***" for k in server.env}  # never leak secret values
    else:
        d["url"] = server.url
        d["headers"] = {k: "***" for k in server.headers}
    if client_id:
        d["client"] = client_id
    return d


def status_to_dict(status: HealthStatus) -> dict:
    return {
        "health": status.health.value,
        "latency_ms": round(status.latency_ms, 1) if status.latency_ms else None,
        "error": status.error,
        "tools": [
            {"name": t.name, "description": t.description, "inputSchema": t.input_schema}
            for t in status.tools
        ],
        "resources": list(status.resources),
        "prompts": list(status.prompts),
    }


# --------------------------------------------------------------------- tables


def render_servers(rows: list[tuple[DiscoveredConfig, ServerDef]]) -> None:
    table = Table(title="MCP servers", header_style="bold")
    table.add_column("Server")
    table.add_column("Transport")
    table.add_column("Client")
    table.add_column("Enabled")
    table.add_column("Launch", overflow="fold", max_width=50)
    for dc, server in rows:
        table.add_row(
            server.name,
            server.transport.value,
            dc.config.display_name,
            "[green]yes[/green]" if server.enabled else "[dim]no[/dim]",
            server.summary(),
        )
    if not rows:
        console.print("[dim]No servers found in any client config.[/dim]")
        return
    console.print(table)


def render_clients(discovered: list[DiscoveredConfig]) -> None:
    table = Table(title="Discovered client configs", header_style="bold")
    table.add_column("Client")
    table.add_column("Servers", justify="right")
    table.add_column("Path", overflow="fold")
    for dc in discovered:
        table.add_row(dc.config.display_name, str(len(dc.config.servers)), str(dc.config.path))
    if not discovered:
        console.print("[dim]No client configs discovered.[/dim]")
        return
    console.print(table)


def render_status_line(name: str, status: HealthStatus) -> None:
    if status.health is Health.RUNNING:
        console.print(
            f"{status.health.icon} [bold]{name}[/bold] running "
            f"({status.latency_ms:.0f} ms) — {status.tool_count} tools"
        )
    else:
        console.print(
            f"{status.health.icon} [bold]{name}[/bold] {status.health.value}"
            + (f" — [red]{status.error}[/red]" if status.error else "")
        )


def render_inspect(server: ServerDef, status: HealthStatus, fingerprint: str | None) -> None:
    console.print(f"[bold]{server.name}[/bold]  [dim]{server.transport.value}[/dim]")
    console.print(f"launch: {server.summary()}")
    render_status_line(server.name, status)
    if status.health is not Health.RUNNING:
        return
    if fingerprint:
        console.print(f"tools fingerprint: [dim]{fingerprint[:16]}…[/dim]")
    if status.tools:
        t = Table(title="Tools", header_style="bold", show_lines=False)
        t.add_column("Name")
        t.add_column("Description", overflow="fold")
        for tool in status.tools:
            t.add_row(tool.name, tool.description or "[dim]—[/dim]")
        console.print(t)
    if status.resources:
        console.print("\n[bold]Resources[/bold]")
        for r in status.resources:
            console.print(f"  • {r}")
    if status.prompts:
        console.print("\n[bold]Prompts[/bold]")
        for p in status.prompts:
            console.print(f"  • {p}")


def render_tools(status: HealthStatus) -> None:
    if not status.tools:
        console.print("[dim]No tools.[/dim]")
        return
    t = Table(header_style="bold")
    t.add_column("Tool")
    t.add_column("Description", overflow="fold")
    for tool in status.tools:
        t.add_row(tool.name, tool.description or "[dim]—[/dim]")
    console.print(t)


def call_result_to_dict(result) -> dict:
    """Serialize an mcp CallToolResult for ``--json``."""
    content = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        content.append({"type": type(item).__name__, "text": text})
    return {
        "isError": bool(getattr(result, "isError", False)),
        "content": content,
        "structuredContent": getattr(result, "structuredContent", None),
    }


def render_call_result(result) -> None:
    """Pretty-print an mcp CallToolResult to the terminal."""
    if getattr(result, "isError", False):
        console.print("[red]Tool returned an error:[/red]")
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        console.print(text if text is not None else f"[dim]{type(item).__name__}[/dim]")
    structured = getattr(result, "structuredContent", None)
    if structured:
        console.print("[bold]structuredContent:[/bold]")
        print_json(structured)


def render_list(title: str, items: list[str]) -> None:
    if not items:
        console.print(f"[dim]No {title}.[/dim]")
        return
    console.print(f"[bold]{title}[/bold]")
    for item in items:
        console.print(f"  • {item}")
