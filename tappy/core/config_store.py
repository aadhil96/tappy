"""ConfigStore: discover client configs, normalize them, and write back safely.

Write safety guarantees (the non-negotiables, since we edit users' live configs):
  * non-destructive  - only the ``mcpServers`` section is touched; every other key in
                       the file is preserved exactly.
  * backup-first     - a timestamped copy is made before the file is modified.
  * atomic           - we write to a temp file in the same dir then ``os.replace``.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from .adapters import ALL_ADAPTERS
from .adapters.base import ClientAdapter, server_from_raw
from .models import ClientConfig, ServerDef

BACKUP_DIR = Path.home() / ".tappy" / "backups"


@dataclass(slots=True)
class DiscoveredConfig:
    """A loaded config plus the adapter that produced it (needed for writes)."""

    config: ClientConfig
    adapter: ClientAdapter


class ConfigStore:
    """Owns discovery and safe persistence across all client adapters."""

    def __init__(self, adapters: list[ClientAdapter] | None = None) -> None:
        self.adapters = adapters if adapters is not None else list(ALL_ADAPTERS)
        self._discovered: list[DiscoveredConfig] = []

    # ------------------------------------------------------------------ discovery

    def discover(self) -> list[DiscoveredConfig]:
        """Load every existing config file from every adapter."""
        found: list[DiscoveredConfig] = []
        for adapter in self.adapters:
            for path in adapter.config_paths():
                if path is None:
                    continue
                cfg = adapter.load(path)
                if cfg.exists:
                    found.append(DiscoveredConfig(config=cfg, adapter=adapter))
        self._discovered = found
        return found

    @property
    def discovered(self) -> list[DiscoveredConfig]:
        return self._discovered

    def find(self, client_id: str, path: Path) -> DiscoveredConfig | None:
        for dc in self._discovered:
            if dc.config.client_id == client_id and dc.config.path == path:
                return dc
        return None

    # ------------------------------------------------------------------ writes

    def upsert_server(self, dc: DiscoveredConfig, server: ServerDef) -> Path:
        """Add or update a server in a config file. Returns the backup path."""
        raw = dict(dc.config.raw)
        section = dict(raw.get(dc.adapter.servers_key, {}) or {})
        section[server.name] = dc.adapter.to_raw_section(server)
        raw[dc.adapter.servers_key] = section
        backup = self._safe_write(dc.config.path, raw)
        # keep in-memory model in sync
        dc.config.raw = raw
        dc.config.servers[server.name] = server
        return backup

    def remove_server(self, dc: DiscoveredConfig, name: str) -> Path:
        """Delete a server from a config file. Returns the backup path."""
        raw = dict(dc.config.raw)
        section = dict(raw.get(dc.adapter.servers_key, {}) or {})
        section.pop(name, None)
        raw[dc.adapter.servers_key] = section
        backup = self._safe_write(dc.config.path, raw)
        dc.config.raw = raw
        dc.config.servers.pop(name, None)
        return backup

    def set_enabled(self, dc: DiscoveredConfig, name: str, enabled: bool) -> Path:
        """Toggle a server's enabled flag in place."""
        server = dc.config.servers.get(name)
        if server is None:
            raise KeyError(name)
        server.enabled = enabled
        return self.upsert_server(dc, server)

    def preview(self, dc: DiscoveredConfig, server: ServerDef) -> str:
        """Return the proposed new file content (for a diff preview), without writing."""
        raw = dict(dc.config.raw)
        section = dict(raw.get(dc.adapter.servers_key, {}) or {})
        section[server.name] = dc.adapter.to_raw_section(server)
        raw[dc.adapter.servers_key] = section
        return json.dumps(raw, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------ internals

    def _safe_write(self, path: Path, raw: dict) -> Path:
        """Backup, then atomically replace ``path`` with the new JSON."""
        backup = self._backup(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(raw, indent=2, ensure_ascii=False) + "\n"
        tmp = path.with_suffix(path.suffix + ".mcpops.tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)  # atomic on same filesystem
        return backup

    @staticmethod
    def _backup(path: Path) -> Path:
        """Copy ``path`` into the backup dir with a timestamp. No-op stamp if missing."""
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest = BACKUP_DIR / f"{path.name}.{stamp}.bak"
        if path.exists():
            shutil.copy2(path, dest)
        return dest


def parse_server_fields(
    name: str,
    transport: str,
    command: str = "",
    args: str = "",
    env: str = "",
    url: str = "",
    headers: str = "",
) -> ServerDef:
    """Build a ServerDef from raw form-string inputs (used by the add/edit form).

    ``args`` is whitespace-split; ``env``/``headers`` are ``KEY=VALUE`` per line.
    """
    raw: dict = {}
    if transport == "stdio":
        raw["command"] = command.strip()
        raw["args"] = command and args.split() or []
        raw["env"] = _parse_kv(env)
    else:
        raw["url"] = url.strip()
        if transport == "sse":
            raw["type"] = "sse"
        raw["headers"] = _parse_kv(headers)
    return server_from_raw(name.strip(), raw)


def _parse_kv(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out
