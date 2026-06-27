"""The tappy Textual application: dashboard + detail pane + actions.

Layout:
  +--------------------------------------------------+
  | Header                                            |
  | DataTable (servers across all clients)  | Detail  |
  | Log pane (status messages)                        |
  | Footer (key bindings)                             |
  +--------------------------------------------------+
"""

from __future__ import annotations

from dataclasses import dataclass

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, RichLog, Static

from .core import mcp_probe
from .core.config_store import ConfigStore, DiscoveredConfig
from .core.models import Health, HealthStatus, ServerDef
from .core.security import FingerprintStore
from .ui.confirm import ConfirmScreen
from .ui.server_form import ServerFormScreen
from .ui.tool_runner import ToolRunnerScreen


@dataclass(slots=True)
class Row:
    """One dashboard row: a server within a specific discovered client config."""

    dc: DiscoveredConfig
    server: ServerDef
    status: HealthStatus | None = None

    @property
    def key(self) -> str:
        return f"{self.dc.config.client_id}|{self.dc.config.path}|{self.server.name}"


class TappyApp(App):
    TITLE = "tappy"
    SUB_TITLE = "manage MCP servers across clients"

    CSS = """
    #main { height: 1fr; }
    #table { width: 2fr; }
    #detail { width: 1fr; border-left: solid $primary; padding: 0 1; overflow-y: auto; }
    #log { height: 8; border-top: solid $primary; }
    DataTable { height: 1fr; }
    """

    BINDINGS = [
        ("r", "rediscover", "Reload"),
        ("p", "probe", "Probe"),
        ("P", "probe_all", "Probe all"),
        ("a", "add", "Add"),
        ("e", "edit", "Edit"),
        ("d", "delete", "Delete"),
        ("space", "toggle", "Enable/disable"),
        ("t", "tools", "Tool runner"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.store = ConfigStore()
        self.fingerprints = FingerprintStore()
        self.rows: list[Row] = []

    # ----------------------------------------------------------------- layout

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main"):
            with Horizontal():
                yield DataTable(id="table", cursor_type="row", zebra_stripes=True)
                yield Static("Select a server.", id="detail")
        yield RichLog(id="log", markup=True, highlight=False)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#table", DataTable)
        table.add_columns("", "Server", "Transport", "Client", "Enabled", "Tools", "Latency")
        self.action_rediscover()

    # ----------------------------------------------------------------- helpers

    def log_line(self, message: str) -> None:
        self.query_one("#log", RichLog).write(message)

    def _current_row(self) -> Row | None:
        table = self.query_one("#table", DataTable)
        if not self.rows or table.cursor_row is None or table.cursor_row < 0:
            return None
        if table.cursor_row >= len(self.rows):
            return None
        return self.rows[table.cursor_row]

    def _refresh_table(self) -> None:
        table = self.query_one("#table", DataTable)
        saved = table.cursor_row
        table.clear()
        for row in self.rows:
            st = row.status
            health_icon = st.health.icon if st else Health.UNKNOWN.icon
            tools = str(st.tool_count) if st and st.health is Health.RUNNING else "-"
            latency = f"{st.latency_ms:.0f}ms" if st and st.latency_ms else "-"
            enabled = "[green]yes[/green]" if row.server.enabled else "[dim]no[/dim]"
            table.add_row(
                health_icon,
                row.server.name,
                str(row.server.transport),
                row.dc.config.display_name,
                enabled,
                tools,
                latency,
            )
        if saved is not None and self.rows:
            table.move_cursor(row=min(saved, len(self.rows) - 1))

    def _render_detail(self, row: Row | None) -> None:
        detail = self.query_one("#detail", Static)
        if row is None:
            detail.update("Select a server.")
            return
        s = row.server
        st = row.status
        lines = [
            f"[b]{s.name}[/b]",
            f"[dim]{row.dc.config.display_name}[/dim]  [dim]{row.dc.config.path}[/dim]",
            "",
            f"transport : {s.transport}",
            f"launch    : {s.summary()}",
            f"enabled   : {'yes' if s.enabled else 'no'}",
        ]
        if s.env:
            lines.append(f"env       : {', '.join(s.env)}  [dim](values masked)[/dim]")
        if st is None:
            lines += ["", "[dim]Press 'p' to probe this server.[/dim]"]
        elif st.health is Health.RUNNING:
            lines += [
                "",
                f"[green]● running[/green]  ({st.latency_ms:.0f} ms)",
                f"tools     : {st.tool_count}",
                f"resources : {len(st.resources)}",
                f"prompts   : {len(st.prompts)}",
            ]
            if st.tools:
                lines.append("\n[b]Tools[/b]")
                for t in st.tools[:30]:
                    lines.append(f"  • {t.name} — [dim]{(t.description or '')[:50]}[/dim]")
        else:
            lines += ["", f"[red]⚠ {st.health.value}[/red]", f"[red]{st.error or ''}[/red]"]
        detail.update("\n".join(lines))

    @on(DataTable.RowHighlighted)
    def _on_highlight(self) -> None:
        self._render_detail(self._current_row())

    # ----------------------------------------------------------------- actions

    def action_rediscover(self) -> None:
        discovered = self.store.discover()
        self.rows = [
            Row(dc=dc, server=server)
            for dc in discovered
            for server in dc.config.servers.values()
        ]
        self._refresh_table()
        clients = {dc.config.display_name for dc in discovered}
        self.log_line(
            f"Discovered [b]{len(self.rows)}[/b] servers across "
            f"{len(clients)} client config(s): {', '.join(sorted(clients)) or 'none'}"
        )
        self._render_detail(self._current_row())

    def action_probe(self) -> None:
        row = self._current_row()
        if row is None:
            return
        self.log_line(f"Probing [b]{row.server.name}[/b]…")
        self._probe_row(row)

    def action_probe_all(self) -> None:
        if not self.rows:
            return
        self.log_line(f"Probing all {len(self.rows)} servers…")
        for row in self.rows:
            self._probe_row(row)

    @work(exclusive=False)
    async def _probe_row(self, row: Row) -> None:
        row.status = await mcp_probe.probe(row.server)
        self._check_fingerprint(row)
        self._refresh_table()
        if row is self._current_row():
            self._render_detail(row)

    def _check_fingerprint(self, row: Row) -> None:
        st = row.status
        if not st or st.health is not Health.RUNNING:
            return
        fp = mcp_probe.tools_fingerprint(st.tools)
        result = self.fingerprints.check(row.dc.config.client_id, row.server.name, fp)
        if result.status == "new":
            self.fingerprints.pin(row.dc.config.client_id, row.server.name, fp)
            self.log_line(f"[green]✓[/green] pinned tool definitions for {row.server.name}")
        elif result.is_changed:
            self.log_line(
                f"[red bold]⚠ SECURITY:[/red bold] tool definitions for "
                f"[b]{row.server.name}[/b] CHANGED since last trusted. "
                f"Review before use (possible rug-pull)."
            )

    @work
    async def action_add(self) -> None:
        if not self.store.discovered:
            self.log_line("[red]No client configs found to add a server to.[/red]")
            return
        server = await self.push_screen_wait(ServerFormScreen())
        if server is None:
            return
        # Add to the first discovered config by default.
        dc = self.store.discovered[0]
        await self._write_with_confirm(dc, server, action="add")

    @work
    async def action_edit(self) -> None:
        row = self._current_row()
        if row is None:
            return
        server = await self.push_screen_wait(ServerFormScreen(row.server))
        if server is None:
            return
        await self._write_with_confirm(row.dc, server, action="edit")

    async def _write_with_confirm(
        self, dc: DiscoveredConfig, server: ServerDef, action: str
    ) -> None:
        preview = self.store.preview(dc, server)
        ok = await self.push_screen_wait(
            ConfirmScreen(
                title=f"{action.title()} '{server.name}' in {dc.config.display_name}",
                body=preview,
                confirm_label="Write",
            )
        )
        if not ok:
            self.log_line("Cancelled.")
            return
        backup = self.store.upsert_server(dc, server)
        self.log_line(
            f"[green]✓[/green] wrote [b]{server.name}[/b] to {dc.config.path} "
            f"[dim](backup: {backup})[/dim]"
        )
        self.action_rediscover()

    @work
    async def action_delete(self) -> None:
        row = self._current_row()
        if row is None:
            return
        ok = await self.push_screen_wait(
            ConfirmScreen(
                title="Delete server",
                body=f"Remove '{row.server.name}' from {row.dc.config.path}?",
                confirm_label="Delete",
            )
        )
        if not ok:
            return
        backup = self.store.remove_server(row.dc, row.server.name)
        self.log_line(
            f"[green]✓[/green] removed [b]{row.server.name}[/b] "
            f"[dim](backup: {backup})[/dim]"
        )
        self.action_rediscover()

    def action_toggle(self) -> None:
        row = self._current_row()
        if row is None:
            return
        new_state = not row.server.enabled
        backup = self.store.set_enabled(row.dc, row.server.name, new_state)
        self.log_line(
            f"[green]✓[/green] {row.server.name} "
            f"{'enabled' if new_state else 'disabled'} [dim](backup: {backup})[/dim]"
        )
        self.action_rediscover()

    @work
    async def action_tools(self) -> None:
        row = self._current_row()
        if row is None:
            return
        if not row.status or row.status.health is not Health.RUNNING:
            self.log_line("[yellow]Probe the server first (press 'p') to load its tools.[/yellow]")
            return
        if not row.status.tools:
            self.log_line("[yellow]This server exposes no tools.[/yellow]")
            return
        await self.push_screen_wait(ToolRunnerScreen(row.server, row.status.tools))
