"""Modal screen to add or edit a server, with a confirm/diff step handled by the app."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Grid, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, TextArea

from ..core.config_store import parse_server_fields
from ..core.models import ServerDef, Transport


class ServerFormScreen(ModalScreen[ServerDef | None]):
    """Returns a ServerDef on save, or None on cancel."""

    CSS = """
    ServerFormScreen { align: center middle; }
    #form { width: 80; height: auto; max-height: 90%; padding: 1 2; background: $panel;
            border: thick $primary; }
    #form Label { margin-top: 1; color: $text-muted; }
    #title { color: $text; text-style: bold; margin-bottom: 1; }
    #buttons { height: auto; align: right middle; margin-top: 1; }
    #buttons Button { margin-left: 2; }
    TextArea { height: 5; }
    """

    def __init__(self, server: ServerDef | None = None) -> None:
        super().__init__()
        self._server = server

    def compose(self) -> ComposeResult:
        s = self._server
        with Vertical(id="form"):
            yield Label("Edit server" if s else "Add server", id="title")
            yield Label("Name")
            yield Input(value=s.name if s else "", placeholder="my-server", id="name")
            yield Label("Transport")
            yield Select(
                [(t.value, t.value) for t in Transport],
                value=(s.transport.value if s else Transport.STDIO.value),
                id="transport",
                allow_blank=False,
            )
            with Grid():
                yield Label("Command (stdio)")
                yield Input(value=s.command if s and s.command else "", placeholder="npx", id="command")
                yield Label("Args (space-separated)")
                yield Input(value=" ".join(s.args) if s else "", placeholder="-y @scope/server", id="args")
                yield Label("URL (http/sse)")
                yield Input(value=s.url if s and s.url else "", placeholder="https://...", id="url")
            yield Label("Env (KEY=VALUE per line)")
            yield TextArea("\n".join(f"{k}={v}" for k, v in (s.env.items() if s else [])), id="env")
            yield Label("Headers (KEY=VALUE per line)")
            yield TextArea("\n".join(f"{k}={v}" for k, v in (s.headers.items() if s else [])), id="headers")
            with Grid(id="buttons"):
                yield Button("Cancel", variant="default", id="cancel")
                yield Button("Save", variant="primary", id="save")

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#save")
    def _save(self) -> None:
        name = self.query_one("#name", Input).value.strip()
        if not name:
            self.query_one("#name", Input).focus()
            return
        server = parse_server_fields(
            name=name,
            transport=str(self.query_one("#transport", Select).value),
            command=self.query_one("#command", Input).value,
            args=self.query_one("#args", Input).value,
            env=self.query_one("#env", TextArea).text,
            url=self.query_one("#url", Input).value,
            headers=self.query_one("#headers", TextArea).text,
        )
        self.dismiss(server)
