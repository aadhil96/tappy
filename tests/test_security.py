"""Fingerprint pinning + change detection tests."""

from __future__ import annotations

from tappy.core.mcp_probe import tools_fingerprint
from tappy.core.models import ToolInfo
from tappy.core.security import FingerprintStore


def test_fingerprint_is_order_independent():
    a = [ToolInfo("a", "desc a"), ToolInfo("b", "desc b")]
    b = [ToolInfo("b", "desc b"), ToolInfo("a", "desc a")]
    assert tools_fingerprint(a) == tools_fingerprint(b)


def test_fingerprint_changes_with_schema():
    a = [ToolInfo("a", "d", {"type": "object"})]
    b = [ToolInfo("a", "d", {"type": "string"})]
    assert tools_fingerprint(a) != tools_fingerprint(b)


def test_pin_then_match_then_change(tmp_path):
    store = FingerprintStore(path=tmp_path / "fp.json")
    fp1 = tools_fingerprint([ToolInfo("a", "d")])
    assert store.check("cli", "srv", fp1).status == "new"
    store.pin("cli", "srv", fp1)
    assert store.check("cli", "srv", fp1).status == "match"

    fp2 = tools_fingerprint([ToolInfo("a", "TAMPERED")])
    result = store.check("cli", "srv", fp2)
    assert result.is_changed
    assert result.previous == fp1


def test_store_persists_across_instances(tmp_path):
    path = tmp_path / "fp.json"
    fp = tools_fingerprint([ToolInfo("a", "d")])
    FingerprintStore(path=path).pin("cli", "srv", fp)
    assert FingerprintStore(path=path).check("cli", "srv", fp).status == "match"
