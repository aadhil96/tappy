"""ConfigStore safety tests: non-destructive, backed-up, atomic writes."""

from __future__ import annotations

import json

import tappy.core.config_store as cs_mod
from tappy.core.adapters.claude_desktop import ClaudeDesktopAdapter
from tappy.core.config_store import ConfigStore, DiscoveredConfig, parse_server_fields


def _make_dc(tmp_path, extra_keys=None):
    path = tmp_path / "claude_desktop_config.json"
    data = {"mcpServers": {"existing": {"command": "old"}}}
    if extra_keys:
        data.update(extra_keys)
    path.write_text(json.dumps(data))
    adapter = ClaudeDesktopAdapter()
    return DiscoveredConfig(config=adapter.load(path), adapter=adapter), path


def test_upsert_preserves_unrelated_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(cs_mod, "BACKUP_DIR", tmp_path / "backups")
    dc, path = _make_dc(tmp_path, extra_keys={"theme": "dark", "window": {"w": 100}})
    store = ConfigStore()
    server = parse_server_fields(name="new", transport="stdio", command="npx", args="a b")
    store.upsert_server(dc, server)

    on_disk = json.loads(path.read_text())
    # unrelated keys survive
    assert on_disk["theme"] == "dark"
    assert on_disk["window"] == {"w": 100}
    # both servers present
    assert set(on_disk["mcpServers"]) == {"existing", "new"}
    assert on_disk["mcpServers"]["new"]["args"] == ["a", "b"]


def test_write_creates_backup(tmp_path, monkeypatch):
    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(cs_mod, "BACKUP_DIR", backup_dir)
    dc, path = _make_dc(tmp_path)
    store = ConfigStore()
    server = parse_server_fields(name="new", transport="stdio", command="x")
    backup = store.upsert_server(dc, server)

    assert backup.exists()
    backed_up = json.loads(backup.read_text())
    # backup is the PRE-write content (only "existing")
    assert set(backed_up["mcpServers"]) == {"existing"}


def test_set_enabled_toggles(tmp_path, monkeypatch):
    monkeypatch.setattr(cs_mod, "BACKUP_DIR", tmp_path / "backups")
    dc, path = _make_dc(tmp_path)
    store = ConfigStore()
    store.set_enabled(dc, "existing", False)
    on_disk = json.loads(path.read_text())
    assert on_disk["mcpServers"]["existing"]["disabled"] is True


def test_remove_server(tmp_path, monkeypatch):
    monkeypatch.setattr(cs_mod, "BACKUP_DIR", tmp_path / "backups")
    dc, path = _make_dc(tmp_path)
    store = ConfigStore()
    store.remove_server(dc, "existing")
    on_disk = json.loads(path.read_text())
    assert on_disk["mcpServers"] == {}


def test_preview_does_not_write(tmp_path, monkeypatch):
    monkeypatch.setattr(cs_mod, "BACKUP_DIR", tmp_path / "backups")
    dc, path = _make_dc(tmp_path)
    store = ConfigStore()
    before = path.read_text()
    server = parse_server_fields(name="ghost", transport="stdio", command="x")
    preview = store.preview(dc, server)
    assert "ghost" in preview
    assert path.read_text() == before  # unchanged on disk
