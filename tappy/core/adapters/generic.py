"""Generic adapter: point at any JSON file that uses the standard ``mcpServers`` shape."""

from __future__ import annotations

from pathlib import Path

from .base import ClientAdapter


class GenericAdapter(ClientAdapter):
    client_id = "generic"
    display_name = "Generic"

    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    def config_paths(self) -> list[Path]:
        return [self._path] if self._path else []
