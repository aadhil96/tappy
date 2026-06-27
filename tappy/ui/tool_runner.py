"""Modal screen to invoke a tool: pick a tool, supply JSON args, see the response.

This is the "mini MCP Inspector" — the highest-value debugging feature.
"""

from __future__ import annotations

import json

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Select, Static, TextArea

from ..core import mcp_probe
from ..core.models import ServerDef, ToolInfo


class ToolRunnerScreen(ModalScreen[None]):
    CSS = """
    ToolRunnerScreen { align: center middle; }
    #box { width: 100; height: 90%; padding: 1 2; background: $panel; border: thick $primary; }
    #title { text-style: bold; margin-bottom: 1; }
    #desc { color: $text-muted; height: auto; max-height: 4; margin-bottom: 1; }
    #args { height: 8; }
    #result { height: 1fr; overflow-y: auto; background: $surface; padding: 0 1; margin-top: 1; }
    #buttons { height: auto; align: right middle; margin-top: 1; }
    #buttons Button { margin-left: 2; }
    """

    def __init__(self, server: ServerDef, tools: list[ToolInfo]) -> None:
        super().__init__()
        self._server = server
        self._tools = {t.name: t for t in tools}

    def compose(self) -> ComposeResult:
        with Vertical(id="box"):
            yield Label(f"Tool runner — {self._server.name}", id="title")
            yield Select(
                [(t.name, t.name) for t in self._tools.values()],
                id="tool",
                allow_blank=False,
            )
            yield Static("", id="desc")
            yield Label("Arguments (JSON)")
            yield TextArea("{}", id="args", language="json")
            yield Static("Run a tool to see its response.", id="result")
            with Horizontal(id="buttons"):
                yield Button("Close", id="close")
                yield Button("Run", variant="primary", id="run")

    def on_mount(self) -> None:
        self._update_desc()

    @on(Select.Changed, "#tool")
    def _on_tool_changed(self) -> None:
        self._update_desc()

    def _update_desc(self) -> None:
        name = str(self.query_one("#tool", Select).value)
        tool = self._tools.get(name)
        desc = tool.description if tool else ""
        self.query_one("#desc", Static).update(desc or "[dim]no description[/dim]")

    @on(Button.Pressed, "#close")
    def _close(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#run")
    def _run(self) -> None:
        name = str(self.query_one("#tool", Select).value)
        raw_args = self.query_one("#args", TextArea).text.strip() or "{}"
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError as exc:
            self.query_one("#result", Static).update(f"[red]Invalid JSON: {exc}[/red]")
            return
        self.query_one("#result", Static).update("[yellow]Running…[/yellow]")
        self._invoke(name, args)

    @work(exclusive=True)
    async def _invoke(self, name: str, args: dict) -> None:
        result_widget = self.query_one("#result", Static)
        try:
            result = await mcp_probe.call_tool(self._server, name, args)
        except Exception as exc:  # noqa: BLE001
            result_widget.update(f"[red]Error: {exc}[/red]")
            return
        result_widget.update(_render_result(result))


def _render_result(result) -> str:
    """Render an mcp CallToolResult into readable text."""
    lines: list[str] = []
    if getattr(result, "isError", False):
        lines.append("[red]Tool returned an error:[/red]")
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text is not None:
            lines.append(text)
        else:
            lines.append(f"[dim]{type(item).__name__}[/dim]")
    structured = getattr(result, "structuredContent", None)
    if structured:
        lines.append("\n[bold]structuredContent:[/bold]")
        lines.append(json.dumps(structured, indent=2, ensure_ascii=False))
    return "\n".join(lines) or "[dim](empty response)[/dim]"
