"""Shared team registry: a single source-of-truth list of approved MCP servers.

The registry is an ordinary ``{"mcpServers": {...}}`` JSON file (same shape every client
uses), so it is human-editable and git-trackable. Teams commit ``tappy.team.json`` to a
repo; each developer runs ``tappy apply`` to provision it into their local clients and
``tappy lint`` to detect drift from it.

Resolution order for the registry path:
  1. explicit ``--registry PATH``
  2. ``$TAPPY_REGISTRY``
  3. ``./tappy.team.json``           (project-local, usually committed)
  4. ``~/.tappy/tappy.team.json``    (user default)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .adapters.base import server_from_raw, server_to_raw
from .models import ServerDef

PROJECT_REGISTRY = Path("tappy.team.json")
USER_REGISTRY = Path.home() / ".tappy" / "tappy.team.json"


class RegistryError(Exception):
    """Raised when the registry can't be found or parsed."""


@dataclass(slots=True)
class TeamRegistry:
    path: Path
    servers: dict[str, ServerDef] = field(default_factory=dict)


def find_registry_path(explicit: str | None = None) -> Path | None:
    """Return the first registry path that exists, or None."""
    if explicit:
        return Path(explicit)
    env = os.environ.get("TAPPY_REGISTRY")
    if env:
        return Path(env)
    for candidate in (PROJECT_REGISTRY, USER_REGISTRY):
        if candidate.exists():
            return candidate
    return None


def load_registry(explicit: str | None = None) -> TeamRegistry:
    """Load the team registry, raising RegistryError with guidance if absent/invalid."""
    path = find_registry_path(explicit)
    if path is None:
        raise RegistryError(
            "no team registry found (looked for ./tappy.team.json, "
            "~/.tappy/tappy.team.json, $TAPPY_REGISTRY). Create one with 'tappy registry --init'."
        )
    if not path.exists():
        raise RegistryError(f"registry not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise RegistryError(f"registry is not valid JSON ({path}): {exc}") from exc
    reg = TeamRegistry(path=path)
    for name, entry in (raw.get("mcpServers", {}) or {}).items():
        if isinstance(entry, dict):
            reg.servers[name] = server_from_raw(name, entry)
    return reg


def init_registry(path: Path, servers: dict[str, ServerDef] | None = None) -> Path:
    """Write a starter (or populated) registry file. Won't overwrite an existing file."""
    if path.exists():
        raise RegistryError(f"registry already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    section = {name: server_to_raw(s) for name, s in (servers or {}).items()}
    payload = {"mcpServers": section}
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def differs(a: ServerDef, b: ServerDef) -> bool:
    """True if two server definitions launch/reach differently (ignores enabled flag)."""
    return server_to_raw(_normalized(a)) != server_to_raw(_normalized(b))


def _normalized(s: ServerDef) -> ServerDef:
    # Compare launch config only; enabled state isn't part of "the same server".
    from dataclasses import replace

    return replace(s, enabled=True)
