"""Client adapters: one per AI client config schema.

Adding support for a new client = adding one adapter module here and registering
it in ``ALL_ADAPTERS``.
"""

from __future__ import annotations

from .base import ClientAdapter
from .claude_code import ClaudeCodeAdapter
from .claude_desktop import ClaudeDesktopAdapter
from .cursor import CursorAdapter
from .generic import GenericAdapter

ALL_ADAPTERS: list[ClientAdapter] = [
    ClaudeDesktopAdapter(),
    ClaudeCodeAdapter(),
    CursorAdapter(),
]

__all__ = [
    "ClientAdapter",
    "ClaudeDesktopAdapter",
    "ClaudeCodeAdapter",
    "CursorAdapter",
    "GenericAdapter",
    "ALL_ADAPTERS",
]
