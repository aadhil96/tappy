"""Rendering for the CLI: human-friendly rich tables and ``--json`` output.

Keeping all formatting here means command handlers in ``cli.py`` stay focused on logic.
"""

from __future__ import annotations

import json as _json
import sys

from rich import box
from rich.console import Console
from rich.table import Table

from .core.config_store import DiscoveredConfig
from .core.models import Health, HealthStatus, ServerDef, Transport

console = Console()
err_console = Console(stderr=True)

# One consistent table style for the whole CLI.
_BOX = box.ROUNDED
_HEADER = "bold cyan"

_TRANSPORT_STYLE = {
    Transport.STDIO: "blue",
    Transport.HTTP: "magenta",
    Transport.SSE: "magenta",
}


def _new_table(title: str | None = None, caption: str | None = None) -> Table:
    return Table(
        title=title,
        caption=caption,
        box=_BOX,
        header_style=_HEADER,
        title_style="bold",
        title_justify="left",
        caption_justify="right",
        expand=False,
        pad_edge=False,
    )


def _enabled_glyph(enabled: bool) -> str:
    return "[green]●[/green] on" if enabled else "[dim]○ off[/dim]"


def _transport_label(transport: Transport) -> str:
    return f"[{_TRANSPORT_STYLE.get(transport, 'white')}]{transport.value}[/]"


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
    if not rows:
        console.print("[dim]No servers found in any client config.[/dim]")
        return
    n = len(rows)
    table = _new_table(title="MCP servers", caption=f"{n} server{'s' if n != 1 else ''}")
    table.add_column("Server", style="bold", no_wrap=True)
    table.add_column("Transport", no_wrap=True)
    table.add_column("Client", style="dim", no_wrap=True)
    table.add_column("Enabled", no_wrap=True)
    # Only the launch command may be shortened — to a single line with an ellipsis.
    table.add_column("Launch", overflow="ellipsis", no_wrap=True, max_width=48, ratio=1)
    for dc, server in rows:
        table.add_row(
            server.name,
            _transport_label(server.transport),
            dc.config.display_name,
            _enabled_glyph(server.enabled),
            f"[dim]{server.summary()}[/dim]",
        )
    console.print(table)


def render_clients(discovered: list[DiscoveredConfig]) -> None:
    if not discovered:
        console.print("[dim]No client configs discovered.[/dim]")
        return
    table = _new_table(title="Discovered client configs")
    table.add_column("Client", style="bold", no_wrap=True)
    table.add_column("#", justify="right", no_wrap=True)
    table.add_column("Path", style="dim", overflow="ellipsis", no_wrap=True, ratio=1)
    for dc in discovered:
        count = len(dc.config.servers)
        table.add_row(
            dc.config.display_name,
            f"[cyan]{count}[/cyan]" if count else "[dim]0[/dim]",
            str(dc.config.path),
        )
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


def _tools_table(status: HealthStatus, title: str | None = None) -> Table:
    t = _new_table(title=title)
    # Tool names always shown in full; descriptions wrap to remain readable.
    t.add_column("Tool", style="bold green", no_wrap=True)
    t.add_column("Description", ratio=1)
    for tool in status.tools:
        t.add_row(tool.name, tool.description or "[dim]—[/dim]")
    return t


def render_inspect(server: ServerDef, status: HealthStatus, fingerprint: str | None) -> None:
    console.print()
    console.print(f"[bold]{server.name}[/bold]  {_transport_label(server.transport)}")
    console.print(f"[dim]launch:[/dim] {server.summary()}")
    render_status_line(server.name, status)
    if status.health is not Health.RUNNING:
        console.print()
        return
    if fingerprint:
        console.print(f"[dim]fingerprint:[/dim] {fingerprint[:16]}…")
    if status.tools:
        console.print()
        console.print(_tools_table(status, title=f"Tools ({len(status.tools)})"))
    if status.resources:
        console.print(f"\n[bold]Resources[/bold] [dim]({len(status.resources)})[/dim]")
        for r in status.resources:
            console.print(f"  [cyan]•[/cyan] {r}")
    if status.prompts:
        console.print(f"\n[bold]Prompts[/bold] [dim]({len(status.prompts)})[/dim]")
        for p in status.prompts:
            console.print(f"  [cyan]•[/cyan] {p}")
    console.print()


def render_tools(status: HealthStatus) -> None:
    if not status.tools:
        console.print("[dim]No tools.[/dim]")
        return
    console.print(_tools_table(status, title=f"Tools ({len(status.tools)})"))


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
