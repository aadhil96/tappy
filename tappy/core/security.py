"""Tool-definition pinning: detect post-approval changes to a server's tools.

On first successful probe we record a fingerprint of each server's tool definitions.
On later probes we compare; a mismatch is surfaced as a security warning ("rug-pull":
a server that changed its advertised tools after you trusted it).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

STORE_PATH = Path.home() / ".tappy" / "fingerprints.json"


@dataclass(slots=True)
class PinResult:
    status: str  # "new" | "match" | "changed"
    previous: str | None = None

    @property
    def is_changed(self) -> bool:
        return self.status == "changed"


class FingerprintStore:
    """Persisted map of ``client_id::server`` -> tool fingerprint."""

    def __init__(self, path: Path = STORE_PATH) -> None:
        self.path = path
        self._data: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    @staticmethod
    def _key(client_id: str, server_name: str) -> str:
        return f"{client_id}::{server_name}"

    def check(self, client_id: str, server_name: str, fingerprint: str) -> PinResult:
        """Compare ``fingerprint`` to the stored value (without updating it)."""
        key = self._key(client_id, server_name)
        previous = self._data.get(key)
        if previous is None:
            return PinResult(status="new")
        if previous == fingerprint:
            return PinResult(status="match")
        return PinResult(status="changed", previous=previous)

    def pin(self, client_id: str, server_name: str, fingerprint: str) -> None:
        """Trust the current fingerprint (record/overwrite it)."""
        self._data[self._key(client_id, server_name)] = fingerprint
        self._save()
