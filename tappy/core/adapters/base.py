"""Base class + shared helpers for client adapters.

The standard MCP config shape (used by Claude Desktop, Claude Code, Cursor and most
others) is::

    {
      "mcpServers": {
        "name": {"command": "npx", "args": [...], "env": {...}},
        "remote": {"url": "https://...", "headers": {...}}
      }
    }

Subclasses mostly differ in *where* the file lives, so the parse/serialize logic
lives here and is reused.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..models import ClientConfig, ServerDef, Transport

# Key used by clients to mark a server as disabled-in-place (Cursor/VS Code style).
_DISABLED_KEYS = ("disabled", "_disabled")


def server_from_raw(name: str, raw: dict[str, Any]) -> ServerDef:
    """Parse one server entry from the standard ``mcpServers`` map."""
    enabled = not any(bool(raw.get(k)) for k in _DISABLED_KEYS)
    if raw.get("url"):
        transport = Transport.SSE if raw.get("type") == "sse" else Transport.HTTP
        return ServerDef(
            name=name,
            transport=transport,
            url=raw.get("url"),
            headers=dict(raw.get("headers", {})),
            enabled=enabled,
        )
    return ServerDef(
        name=name,
        transport=Transport.STDIO,
        command=raw.get("command"),
        args=list(raw.get("args", [])),
        env=dict(raw.get("env", {})),
        enabled=enabled,
    )


def server_to_raw(server: ServerDef) -> dict[str, Any]:
    """Serialize a ServerDef back to the standard ``mcpServers`` entry shape."""
    if server.transport is Transport.STDIO:
        entry: dict[str, Any] = {"command": server.command, "args": list(server.args)}
        if server.env:
            entry["env"] = dict(server.env)
    else:
        entry = {"url": server.url}
        if server.transport is Transport.SSE:
            entry["type"] = "sse"
        if server.headers:
            entry["headers"] = dict(server.headers)
    if not server.enabled:
        entry["disabled"] = True
    return entry


class ClientAdapter(ABC):
    """Translate one client's config file <-> the normalized model."""

    client_id: str
    display_name: str

    @abstractmethod
    def config_paths(self) -> list[Path]:
        """Candidate config file locations, most-specific first (e.g. project before user)."""

    # --- standard implementations (override only if the schema differs) ---

    def load(self, path: Path) -> ClientConfig:
        """Read one config file into a ClientConfig (non-destructive: keeps raw)."""
        cfg = ClientConfig(
            client_id=self.client_id,
            display_name=self.display_name,
            path=path,
            exists=path.exists(),
        )
        if not cfg.exists:
            return cfg
        try:
            cfg.raw = json.loads(path.read_text(encoding="utf-8") or "{}")
        except (json.JSONDecodeError, OSError) as exc:
            cfg.raw = {}
            cfg.exists = True
            cfg.servers = {}
            # surface parse errors via an empty config; UI can warn separately
            cfg.raw = {"__error__": str(exc)}
            return cfg
        servers_map = cfg.raw.get("mcpServers", {}) or {}
        for name, raw in servers_map.items():
            if isinstance(raw, dict):
                cfg.servers[name] = server_from_raw(name, raw)
        return cfg

    def to_raw_section(self, server: ServerDef) -> dict[str, Any]:
        return server_to_raw(server)

    @property
    def servers_key(self) -> str:
        return "mcpServers"
