"""Resolve a CLI "target" to a concrete ServerDef.

A target is either:
  * a **name** of a server already declared in some client config, or
  * an **ad-hoc** server described inline with ``--command``/``--url`` flags (so you can
    inspect a server before it is installed anywhere).

This is shared by every inspector/management command so they all agree on what a target
means.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config_store import ConfigStore, DiscoveredConfig
from .models import ServerDef, Transport


class ResolveError(Exception):
    """Raised when a target can't be resolved (not found / ambiguous / invalid)."""


@dataclass(slots=True)
class ResolvedTarget:
    server: ServerDef
    # The config the server came from, or None for an ad-hoc target.
    source: DiscoveredConfig | None = None


def build_adhoc(
    name: str = "adhoc",
    *,
    transport: str | None = None,
    command: str | None = None,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    url: str | None = None,
    headers: dict[str, str] | None = None,
) -> ServerDef:
    """Construct a transient ServerDef from inline flags."""
    if url:
        tr = Transport(transport) if transport else Transport.HTTP
        if tr is Transport.STDIO:  # url given but transport said stdio -> fix it
            tr = Transport.HTTP
        return ServerDef(name=name, transport=tr, url=url, headers=headers or {})
    if command:
        return ServerDef(
            name=name,
            transport=Transport.STDIO,
            command=command,
            args=list(args or []),
            env=env or {},
        )
    raise ResolveError("ad-hoc target needs --command (stdio) or --url (http/sse)")


def resolve_name(
    store: ConfigStore, name: str, client_id: str | None = None
) -> ResolvedTarget:
    """Find a server by name across discovered configs.

    Raises ResolveError if not found, or if it exists in multiple clients and no
    ``client_id`` was given to disambiguate.
    """
    if not store.discovered:
        store.discover()
    matches: list[DiscoveredConfig] = []
    for dc in store.discovered:
        if client_id and dc.config.client_id != client_id:
            continue
        if name in dc.config.servers:
            matches.append(dc)
    if not matches:
        scope = f" in client '{client_id}'" if client_id else ""
        raise ResolveError(f"no server named '{name}'{scope}")
    if len(matches) > 1:
        clients = ", ".join(dc.config.client_id for dc in matches)
        raise ResolveError(
            f"server '{name}' exists in multiple clients ({clients}); "
            f"disambiguate with --client"
        )
    dc = matches[0]
    return ResolvedTarget(server=dc.config.servers[name], source=dc)


def resolve_target(
    store: ConfigStore,
    name: str | None,
    *,
    client_id: str | None = None,
    transport: str | None = None,
    command: str | None = None,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    url: str | None = None,
    headers: dict[str, str] | None = None,
) -> ResolvedTarget:
    """Resolve either a named config server or an ad-hoc inline server.

    Ad-hoc wins when ``--command``/``--url`` are supplied; otherwise ``name`` is looked
    up in the discovered configs.
    """
    if command or url:
        server = build_adhoc(
            name=name or "adhoc",
            transport=transport,
            command=command,
            args=args,
            env=env,
            url=url,
            headers=headers,
        )
        return ResolvedTarget(server=server, source=None)
    if not name:
        raise ResolveError("provide a server NAME, or --command/--url for an ad-hoc target")
    return resolve_name(store, name, client_id)
