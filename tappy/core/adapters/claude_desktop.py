"""Claude Desktop adapter.

Config locations:
  macOS:   ~/Library/Application Support/Claude/claude_desktop_config.json
  Windows: %APPDATA%/Claude/claude_desktop_config.json
  Linux:   ~/.config/Claude/claude_desktop_config.json
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .base import ClientAdapter


class ClaudeDesktopAdapter(ClientAdapter):
    client_id = "claude_desktop"
    display_name = "Claude Desktop"

    def config_paths(self) -> list[Path]:
        home = Path.home()
        if sys.platform == "darwin":
            base = home / "Library" / "Application Support" / "Claude"
        elif sys.platform.startswith("win"):
            appdata = os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))
            base = Path(appdata) / "Claude"
        else:
            base = home / ".config" / "Claude"
        return [base / "claude_desktop_config.json"]
