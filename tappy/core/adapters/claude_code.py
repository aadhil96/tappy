"""Claude Code adapter.

Claude Code stores MCP servers in:
  - user scope:    ~/.claude.json  (key: "mcpServers")
  - project scope: ./.mcp.json     (key: "mcpServers")

Both use the standard shape, so only the locations differ.
"""

from __future__ import annotations

from pathlib import Path

from .base import ClientAdapter


class ClaudeCodeAdapter(ClientAdapter):
    client_id = "claude_code"
    display_name = "Claude Code"

    def config_paths(self) -> list[Path]:
        paths = []
        project = Path.cwd() / ".mcp.json"
        paths.append(project)  # project scope first (most specific)
        paths.append(Path.home() / ".claude.json")
        return paths
