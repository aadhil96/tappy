"""Generic confirm modal, used for diff-preview-before-write and deletions."""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class ConfirmScreen(ModalScreen[bool]):
    """Show a title + body (e.g. a config diff/preview); return True if confirmed."""

    CSS = """
    ConfirmScreen { align: center middle; }
    #box { width: 90; height: auto; max-height: 90%; padding: 1 2; background: $panel;
           border: thick $warning; }
    #title { text-style: bold; margin-bottom: 1; }
    #body { height: auto; max-height: 24; overflow-y: auto; background: $surface;
            padding: 0 1; }
    #buttons { height: auto; align: right middle; margin-top: 1; }
    #buttons Button { margin-left: 2; }
    """

    def __init__(self, title: str, body: str, confirm_label: str = "Apply") -> None:
        super().__init__()
        self._title = title
        self._body = body
        self._confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical(id="box"):
            yield Label(self._title, id="title")
            yield Static(self._body, id="body")
            with Vertical(id="buttons"):
                yield Button("Cancel", variant="default", id="cancel")
                yield Button(self._confirm_label, variant="primary", id="ok")

    @on(Button.Pressed, "#ok")
    def _ok(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(False)
