"""Adapter parse/serialize round-trip tests."""

from __future__ import annotations

import json

from tappy.core.adapters.base import server_from_raw, server_to_raw
from tappy.core.adapters.claude_desktop import ClaudeDesktopAdapter
from tappy.core.models import Transport


def test_stdio_round_trip():
    raw = {"command": "npx", "args": ["-y", "@scope/server"], "env": {"KEY": "v"}}
    server = server_from_raw("fs", raw)
    assert server.transport is Transport.STDIO
    assert server.command == "npx"
    assert server.args == ["-y", "@scope/server"]
    assert server.env == {"KEY": "v"}
    assert server.enabled is True
    # serialize back
    out = server_to_raw(server)
    assert out["command"] == "npx"
    assert out["args"] == ["-y", "@scope/server"]
    assert out["env"] == {"KEY": "v"}


def test_http_round_trip():
    raw = {"url": "https://example.com/mcp", "headers": {"Authorization": "Bearer x"}}
    server = server_from_raw("remote", raw)
    assert server.transport is Transport.HTTP
    assert server.url == "https://example.com/mcp"
    out = server_to_raw(server)
    assert out["url"] == "https://example.com/mcp"
    assert out["headers"]["Authorization"] == "Bearer x"


def test_sse_transport_marked():
    raw = {"url": "https://example.com/sse", "type": "sse"}
    server = server_from_raw("s", raw)
    assert server.transport is Transport.SSE
    out = server_to_raw(server)
    assert out["type"] == "sse"


def test_disabled_flag_parsed_and_written():
    server = server_from_raw("x", {"command": "foo", "disabled": True})
    assert server.enabled is False
    out = server_to_raw(server)
    assert out["disabled"] is True


def test_adapter_loads_standard_file(tmp_path):
    path = tmp_path / "claude_desktop_config.json"
    path.write_text(
        json.dumps(
            {
                "globalShortcut": "Cmd+X",  # unrelated key must be preserved on load
                "mcpServers": {"fs": {"command": "npx", "args": ["fs"]}},
            }
        )
    )
    cfg = ClaudeDesktopAdapter().load(path)
    assert cfg.exists
    assert "fs" in cfg.servers
    assert cfg.raw["globalShortcut"] == "Cmd+X"
