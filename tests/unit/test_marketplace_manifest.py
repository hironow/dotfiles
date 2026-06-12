"""Unit tests for .claude-plugin/marketplace.json.

The marketplace is consumed as a local file source by Claude Code's plugin
resolver. These tests pin what the manifest promises: every plugin source
resolves to an existing plugin directory in this repo, each carries its own
.claude-plugin/plugin.json whose name/version match the marketplace entry
(version drift between the two files broke silently before), and source
resolution is unambiguous — `metadata.pluginRoot` (prepended to relative
sources by the resolver) must not be combined with path-style sources,
which would invite double-prefixing.
"""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / ".claude-plugin" / "marketplace.json"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text())


def test_no_plugin_root_alongside_path_sources() -> None:
    manifest = _manifest()
    assert "pluginRoot" not in manifest.get("metadata", {}), (
        "metadata.pluginRoot is prepended to relative plugin sources; mixing "
        "it with './plugins/...'-style sources invites double-prefixing — "
        "keep exactly one resolution mechanism (explicit path sources)"
    )


def test_every_source_resolves_to_a_plugin_directory() -> None:
    for entry in _manifest()["plugins"]:
        source_dir = (REPO / entry["source"]).resolve()
        assert source_dir.is_dir(), f"{entry['name']}: missing {entry['source']}"
        assert (source_dir / ".claude-plugin" / "plugin.json").is_file(), (
            f"{entry['name']}: {entry['source']} has no .claude-plugin/plugin.json"
        )


def test_marketplace_entries_match_plugin_manifests() -> None:
    for entry in _manifest()["plugins"]:
        plugin_json = json.loads(
            (REPO / entry["source"] / ".claude-plugin" / "plugin.json").read_text()
        )
        assert plugin_json["name"] == entry["name"]
        assert plugin_json.get("version") == entry.get("version"), (
            f"{entry['name']}: marketplace version {entry.get('version')} != "
            f"plugin.json version {plugin_json.get('version')} — bump both together"
        )
