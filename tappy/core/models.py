"""Normalized data model shared across all clients.

Every client stores MCP servers in its own JSON shape. Adapters translate those
shapes into the structures below so the rest of the app only deals with one model.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class Transport(str, Enum):
    """How a client talks to a server."""

    STDIO = "stdio"
    HTTP = "http"  # streamable HTTP
    SSE = "sse"

    def __str__(self) -> str:  # nicer table rendering
        return self.value


@dataclass(slots=True)
class ServerDef:
    """A single MCP server, normalized across clients.

    For STDIO servers ``command``/``args``/``env`` are used.
    For HTTP/SSE servers ``url``/``headers`` are used.
    """

    name: str
    transport: Transport = Transport.STDIO
    # stdio fields
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    # http / sse fields
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    # whether the server is currently active in the owning client's config
    enabled: bool = True

    def summary(self) -> str:
        """One-line human description of how this server is launched/reached."""
        if self.transport is Transport.STDIO:
            parts = [self.command or "?", *self.args]
            return " ".join(parts)
        return self.url or "?"

    def fingerprint(self) -> str:
        """Stable string used to detect when a definition changes."""
        if self.transport is Transport.STDIO:
            return f"stdio:{self.command}:{' '.join(self.args)}"
        return f"{self.transport.value}:{self.url}"


@dataclass(slots=True)
class ClientConfig:
    """A discovered client config file and the servers it declares."""

    client_id: str  # e.g. "claude_desktop"
    display_name: str  # e.g. "Claude Desktop"
    path: Path
    servers: dict[str, ServerDef] = field(default_factory=dict)
    exists: bool = True
    # raw parsed JSON, preserved so writes can be non-destructive
    raw: dict[str, Any] = field(default_factory=dict)


class Health(str, Enum):
    """Live status of a server as observed by the probe."""

    UNKNOWN = "unknown"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"

    @property
    def icon(self) -> str:
        return {
            Health.RUNNING: "[green]●[/green]",
            Health.STOPPED: "[dim]○[/dim]",
            Health.ERROR: "[red]⚠[/red]",
            Health.UNKNOWN: "[yellow]…[/yellow]",
        }[self]


@dataclass(slots=True)
class ToolInfo:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HealthStatus:
    """Result of probing a server: status, latency, and what it exposes."""

    health: Health = Health.UNKNOWN
    latency_ms: float | None = None
    error: str | None = None
    tools: list[ToolInfo] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    checked_at: float = field(default_factory=time.time)

    @property
    def tool_count(self) -> int:
        return len(self.tools)
