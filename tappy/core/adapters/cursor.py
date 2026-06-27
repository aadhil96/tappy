"""Cursor adapter.

Config locations:
  - project scope: ./.cursor/mcp.json
  - user scope:    ~/.cursor/mcp.json

Standard ``mcpServers`` shape.
"""

from __future__ import annotations

from pathlib import Path

from .base import ClientAdapter


class CursorAdapter(ClientAdapter):
    client_id = "cursor"
    display_name = "Cursor"

    def config_paths(self) -> list[Path]:
        return [
            Path.cwd() / ".cursor" / "mcp.json",
            Path.home() / ".cursor" / "mcp.json",
        ]
