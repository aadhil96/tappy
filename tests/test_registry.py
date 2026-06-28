"""Team registry: init/load + apply/lint/sync across clients (no network)."""

from __future__ import annotations

import json

import pytest

import tappy.core.config_store as cs_mod
from tappy import cli
from tappy.core.adapters.generic import GenericAdapter
from tappy.core.config_store import ConfigStore


class _Adapter(GenericAdapter):
    """GenericAdapter with a distinct client id, so we can model several clients."""

    def __init__(self, path, client_id):
        super().__init__(path)
        self.client_id = client_id
        self.display_name = client_id


def _write(path, servers):
    path.write_text(json.dumps({"mcpServers": servers}))


def _ns(*argv):
    return cli.parse(list(argv))


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(cs_mod, "BACKUP_DIR", tmp_path / "backups")
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    _write(a, {"existing": {"command": "old"}})
    _write(b, {})
    store = ConfigStore(adapters=[_Adapter(a, "alpha"), _Adapter(b, "beta")])
    registry_path = tmp_path / "tappy.team.json"
    return store, registry_path, a, b


def test_registry_init_and_load(env, capsys):
    store, reg_path, *_ = env
    assert cli.cmd_registry(store, _ns("registry", "--init", "--registry", str(reg_path))) == 0
    assert reg_path.exists()
    capsys.readouterr()  # discard the init message
    # load shows it as json
    assert cli.cmd_registry(store, _ns("registry", "--registry", str(reg_path), "--json")) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["servers"] == []


def test_init_seed_from_client(env):
    store, reg_path, *_ = env
    rc = cli.cmd_registry(
        store, _ns("registry", "--init", "--registry", str(reg_path), "--from-client", "alpha")
    )
    assert rc == 0
    on_disk = json.loads(reg_path.read_text())
    assert "existing" in on_disk["mcpServers"]


def test_apply_adds_missing(env):
    store, reg_path, a, b = env
    _write(reg_path, {"github": {"command": "npx", "args": ["gh"]}})
    rc = cli.cmd_apply(store, _ns("apply", "--registry", str(reg_path)))
    assert rc == 0
    # github added to BOTH clients
    assert "github" in json.loads(a.read_text())["mcpServers"]
    assert "github" in json.loads(b.read_text())["mcpServers"]


def test_apply_dry_run_writes_nothing(env):
    store, reg_path, a, b = env
    _write(reg_path, {"github": {"command": "npx"}})
    before_a = a.read_text()
    rc = cli.cmd_apply(store, _ns("apply", "--registry", str(reg_path), "--dry-run"))
    assert rc == 0
    assert a.read_text() == before_a  # unchanged


def test_apply_to_single_client(env):
    store, reg_path, a, b = env
    _write(reg_path, {"github": {"command": "npx"}})
    cli.cmd_apply(store, _ns("apply", "--registry", str(reg_path), "--client", "beta"))
    assert "github" not in json.loads(a.read_text())["mcpServers"]
    assert "github" in json.loads(b.read_text())["mcpServers"]


def test_lint_flags_unapproved(env, capsys):
    store, reg_path, a, b = env
    _write(reg_path, {"approved": {"command": "ok"}})
    # 'existing' is in client alpha but not the registry -> unapproved -> exit 1
    rc = cli.cmd_lint(store, _ns("lint", "--registry", str(reg_path)))
    assert rc == 1
    out = capsys.readouterr().out
    assert "UNAPPROVED" in out and "existing" in out


def test_lint_clean_when_synced(env):
    store, reg_path, a, b = env
    _write(reg_path, {"existing": {"command": "old"}})
    _write(b, {"existing": {"command": "old"}})
    store.discover()
    rc = cli.cmd_lint(store, _ns("lint", "--registry", str(reg_path)))
    assert rc == 0


def test_sync_copies_between_clients(env):
    store, reg_path, a, b = env
    rc = cli.cmd_sync(store, _ns("sync", "existing", "--from", "alpha", "--to", "beta"))
    assert rc == 0
    assert "existing" in json.loads(b.read_text())["mcpServers"]


def test_sync_missing_destination(env, capsys):
    store, reg_path, a, b = env
    rc = cli.cmd_sync(store, _ns("sync", "existing", "--to", "ghost"))
    assert rc == 1
    assert "ghost" in capsys.readouterr().err
