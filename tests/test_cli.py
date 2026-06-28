"""CLI management-command tests + target resolution (no network)."""

from __future__ import annotations

import json

import pytest

import tappy.core.config_store as cs_mod
from tappy import cli
from tappy.core.adapters.generic import GenericAdapter
from tappy.core.config_store import ConfigStore
from tappy.core.models import Transport
from tappy.core.resolve import ResolveError, resolve_target


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A ConfigStore backed by a single temp 'generic' config file."""
    monkeypatch.setattr(cs_mod, "BACKUP_DIR", tmp_path / "backups")
    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({"mcpServers": {"existing": {"command": "old"}}}))
    return ConfigStore(adapters=[GenericAdapter(cfg)]), cfg


def _ns(*argv):
    return cli.parse(list(argv))


def test_list_json(store, capsys):
    s, _ = store
    assert cli.cmd_list(s, _ns("list", "--json")) == 0
    data = json.loads(capsys.readouterr().out)
    assert data[0]["name"] == "existing"
    assert data[0]["client"] == "generic"


def test_add_writes_and_backs_up(store, capsys):
    s, cfg = store
    # `--` passthrough handles args that start with a dash (e.g. -y)
    rc = cli.cmd_add(s, _ns("add", "fs", "--", "npx", "-y", "pkg"))
    assert rc == 0
    on_disk = json.loads(cfg.read_text())
    assert set(on_disk["mcpServers"]) == {"existing", "fs"}
    assert on_disk["mcpServers"]["fs"]["command"] == "npx"
    assert on_disk["mcpServers"]["fs"]["args"] == ["-y", "pkg"]


def test_add_http_url(store):
    s, cfg = store
    rc = cli.cmd_add(s, _ns("add", "remote", "--url", "https://example.com/mcp"))
    assert rc == 0
    entry = json.loads(cfg.read_text())["mcpServers"]["remote"]
    assert entry["url"] == "https://example.com/mcp"


def test_enable_disable(store):
    s, cfg = store
    assert cli.cmd_toggle(s, _ns("disable", "existing"), enabled=False) == 0
    assert json.loads(cfg.read_text())["mcpServers"]["existing"]["disabled"] is True
    assert cli.cmd_toggle(s, _ns("enable", "existing"), enabled=True) == 0
    assert "disabled" not in json.loads(cfg.read_text())["mcpServers"]["existing"]


def test_remove(store):
    s, cfg = store
    assert cli.cmd_remove(s, _ns("remove", "existing")) == 0
    assert json.loads(cfg.read_text())["mcpServers"] == {}


def test_remove_missing_returns_error(store, capsys):
    s, _ = store
    assert cli.cmd_remove(s, _ns("remove", "ghost")) == 1
    assert "no server named 'ghost'" in capsys.readouterr().err


def test_clients_json(store, capsys):
    s, _ = store
    assert cli.cmd_clients(s, _ns("clients", "--json")) == 0
    data = json.loads(capsys.readouterr().out)
    assert data[0]["client"] == "generic"
    assert data[0]["servers"] == 1


# ----------------------------------------------------------------- resolver


def test_resolve_adhoc_stdio():
    s = ConfigStore(adapters=[])
    target = resolve_target(s, None, command="npx", args=["-y", "pkg"])
    assert target.source is None
    assert target.server.transport is Transport.STDIO
    assert target.server.command == "npx"


def test_resolve_adhoc_url_defaults_http():
    s = ConfigStore(adapters=[])
    target = resolve_target(s, None, url="https://x/mcp")
    assert target.server.transport is Transport.HTTP
    assert target.server.url == "https://x/mcp"


def test_resolve_name(store):
    s, _ = store
    target = resolve_target(s, "existing")
    assert target.server.name == "existing"
    assert target.source is not None


def test_resolve_missing_raises(store):
    s, _ = store
    with pytest.raises(ResolveError):
        resolve_target(s, "nope")


def test_resolve_ambiguous_raises(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    for p in (a, b):
        p.write_text(json.dumps({"mcpServers": {"dup": {"command": "x"}}}))
    s = ConfigStore(adapters=[GenericAdapter(a), GenericAdapter(b)])
    with pytest.raises(ResolveError, match="multiple clients"):
        resolve_target(s, "dup")
