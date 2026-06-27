"""McpProbe: speak the MCP protocol to get a server's *real* status and capabilities.

We never infer health from config alone. We open a session, run ``initialize``, and
list tools/resources/prompts. This is also where tool-definition fingerprints are
computed so the security layer can detect post-approval "rug-pull" changes.

The mcp SDK is imported lazily so the rest of the app (and tests) work even when the
SDK or a server's runtime isn't installed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from contextlib import AsyncExitStack

from .models import Health, HealthStatus, ServerDef, ToolInfo, Transport

# How long to wait for a server to initialize before giving up.
DEFAULT_TIMEOUT_S = 20.0


async def probe(server: ServerDef, timeout: float = DEFAULT_TIMEOUT_S) -> HealthStatus:
    """Connect to ``server`` and return its live status + capabilities."""
    started = time.perf_counter()
    try:
        status = await asyncio.wait_for(_probe_inner(server), timeout=timeout)
    except asyncio.TimeoutError:
        return HealthStatus(health=Health.ERROR, error=f"timed out after {timeout:g}s")
    except Exception as exc:  # noqa: BLE001 - surface any connection failure to the UI
        return HealthStatus(health=Health.ERROR, error=_short_error(exc))
    status.latency_ms = (time.perf_counter() - started) * 1000
    return status


async def _probe_inner(server: ServerDef) -> HealthStatus:
    # Imported here so a missing SDK only breaks probing, not the whole app.
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async with AsyncExitStack() as stack:
        if server.transport is Transport.STDIO:
            if not server.command:
                return HealthStatus(health=Health.ERROR, error="no command configured")
            params = StdioServerParameters(
                command=server.command,
                args=list(server.args),
                env=server.env or None,
            )
            read, write = await stack.enter_async_context(stdio_client(params))
        elif server.transport is Transport.HTTP:
            from mcp.client.streamable_http import streamablehttp_client

            if not server.url:
                return HealthStatus(health=Health.ERROR, error="no url configured")
            read, write, _ = await stack.enter_async_context(
                streamablehttp_client(server.url, headers=server.headers or None)
            )
        else:  # SSE
            from mcp.client.sse import sse_client

            if not server.url:
                return HealthStatus(health=Health.ERROR, error="no url configured")
            read, write = await stack.enter_async_context(
                sse_client(server.url, headers=server.headers or None)
            )

        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        status = HealthStatus(health=Health.RUNNING)
        status.tools = await _list_tools(session)
        status.resources = await _list_resources(session)
        status.prompts = await _list_prompts(session)
        return status


async def _list_tools(session) -> list[ToolInfo]:
    try:
        result = await session.list_tools()
    except Exception:  # noqa: BLE001 - server may not support tools
        return []
    out: list[ToolInfo] = []
    for tool in result.tools:
        out.append(
            ToolInfo(
                name=tool.name,
                description=tool.description or "",
                input_schema=getattr(tool, "inputSchema", {}) or {},
            )
        )
    return out


async def _list_resources(session) -> list[str]:
    try:
        result = await session.list_resources()
    except Exception:  # noqa: BLE001
        return []
    return [str(r.uri) for r in result.resources]


async def _list_prompts(session) -> list[str]:
    try:
        result = await session.list_prompts()
    except Exception:  # noqa: BLE001
        return []
    return [p.name for p in result.prompts]


async def call_tool(
    server: ServerDef, tool_name: str, arguments: dict, timeout: float = DEFAULT_TIMEOUT_S
):
    """Invoke a single tool and return its raw CallToolResult (for the tool runner)."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def _run():
        async with AsyncExitStack() as stack:
            if server.transport is Transport.STDIO:
                params = StdioServerParameters(
                    command=server.command,
                    args=list(server.args),
                    env=server.env or None,
                )
                read, write = await stack.enter_async_context(stdio_client(params))
            elif server.transport is Transport.HTTP:
                from mcp.client.streamable_http import streamablehttp_client

                read, write, _ = await stack.enter_async_context(
                    streamablehttp_client(server.url, headers=server.headers or None)
                )
            else:
                from mcp.client.sse import sse_client

                read, write = await stack.enter_async_context(
                    sse_client(server.url, headers=server.headers or None)
                )
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            return await session.call_tool(tool_name, arguments)

    return await asyncio.wait_for(_run(), timeout=timeout)


# ----------------------------------------------------------------- security helpers


def tools_fingerprint(tools: list[ToolInfo]) -> str:
    """Stable hash of a server's tool definitions.

    Stored on first approval; a later mismatch means the server's advertised tools
    changed (potential rug-pull / tool poisoning) and should be flagged to the user.
    """
    payload = [
        {"name": t.name, "description": t.description, "schema": t.input_schema}
        for t in sorted(tools, key=lambda t: t.name)
    ]
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _short_error(exc: Exception) -> str:
    msg = str(exc).strip() or exc.__class__.__name__
    return msg.splitlines()[0][:200]
