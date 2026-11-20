"""The MCP servers dotfiles declares, reconciled into every agent (ADR 0087).

dump/harness/mcp-servers.json names remote MCP servers that need no secret;
`just deploy` registers them with Claude Code (every home), Codex, Pi and
Antigravity through each one's own `mcp add`. A server that needs a secret
(google-dev-knowledge) is never registered: the run prints its setup instead.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import agent_mcp as mcp

ROOT = Path(__file__).resolve().parents[2]


# ---- The declaration ----


def test_every_declared_server_is_a_named_https_url() -> None:
    declared = mcp.load(ROOT / "dump/harness/mcp-servers.json")
    assert declared.servers, "nothing declared"
    for name, server in declared.servers.items():
        assert name and name == name.strip(), name
        assert server.url.startswith("https://"), (name, server.url)


def test_a_server_a_claude_plugin_carries_is_left_to_the_plugin() -> None:
    # these plugins register a server of the same name in Claude Code; a
    # second registration would shadow the plugin's
    declared = mcp.load(ROOT / "dump/harness/mcp-servers.json")
    plugins = json.loads(
        (ROOT / "dump/harness/claude-plugins.json").read_text(encoding="utf-8")
    )["plugins"]
    for name in ("context7", "cloudflare", "vercel"):
        assert declared.servers[name].claude_plugin == f"{name}@claude-plugins-official"
    for name, server in declared.servers.items():
        if server.claude_plugin:
            assert server.claude_plugin in plugins, name
    claude = mcp.wanted(declared, "claude")
    assert not {"context7", "cloudflare", "vercel"} & set(claude)
    assert {"context7", "cloudflare", "vercel"} <= set(mcp.wanted(declared, "pi"))


def test_codex_is_never_asked_to_add_a_server_that_needs_a_sign_in() -> None:
    # `codex mcp add` on an OAuth server starts the browser sign-in at once
    # and waits for it, which an unattended deploy cannot do
    declared = mcp.load(ROOT / "dump/harness/mcp-servers.json")
    sign_in = {name for name, server in declared.servers.items() if server.sign_in}
    assert {"cloudflare", "vercel"} <= sign_in
    assert not sign_in & set(mcp.wanted(declared, "codex"))
    assert sign_in <= set(mcp.wanted(declared, "antigravity"))


def test_a_server_that_needs_a_secret_is_guided_not_declared() -> None:
    declared = mcp.load(ROOT / "dump/harness/mcp-servers.json")
    assert "google-dev-knowledge" in declared.guided
    assert "google-dev-knowledge" not in declared.servers


# ---- Reading each agent's registry ----


def test_claude_reads_the_homes_claude_json(tmp_path: Path) -> None:
    (tmp_path / ".claude.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "deepwiki": {"type": "http", "url": "https://mcp.deepwiki.com/mcp"},
                    "headroom": {"type": "stdio", "command": "mise"},
                }
            }
        ),
        encoding="utf-8",
    )
    assert mcp.read_claude(tmp_path) == {
        "deepwiki": "https://mcp.deepwiki.com/mcp",
        "headroom": None,
    }


def test_codex_reads_its_config_toml(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text(
        '[mcp_servers.deepwiki]\nurl = "https://mcp.deepwiki.com/mcp"\n\n'
        '[mcp_servers.playwright]\ncommand = "npx"\n',
        encoding="utf-8",
    )
    assert mcp.read_codex(tmp_path) == {
        "deepwiki": "https://mcp.deepwiki.com/mcp",
        "playwright": None,
    }


def test_pi_reads_its_mcp_json(tmp_path: Path) -> None:
    (tmp_path / "mcp.json").write_text(
        json.dumps({"mcpServers": {"bun": {"url": "https://bun.com/docs/mcp"}}}),
        encoding="utf-8",
    )
    assert mcp.read_pi(tmp_path) == {"bun": "https://bun.com/docs/mcp"}


def test_antigravity_reads_server_url(tmp_path: Path) -> None:
    (tmp_path / "mcp_config.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "bun": {"disabled": False, "serverUrl": "https://bun.com/docs/mcp"}
                }
            }
        ),
        encoding="utf-8",
    )
    assert mcp.read_antigravity(tmp_path) == {"bun": "https://bun.com/docs/mcp"}


@pytest.mark.parametrize(
    "reader", [mcp.read_claude, mcp.read_codex, mcp.read_pi, mcp.read_antigravity]
)
def test_a_missing_registry_is_empty(tmp_path: Path, reader) -> None:
    # an agent that has never stored a server has no file yet
    assert reader(tmp_path) == {}


@pytest.mark.parametrize(
    ("reader", "file", "text"),
    [
        (mcp.read_claude, ".claude.json", "{not json"),
        (mcp.read_codex, "config.toml", "[mcp_servers\n"),
        (mcp.read_pi, "mcp.json", "[]"),
        (mcp.read_antigravity, "mcp_config.json", '{"mcpServers": []}'),
    ],
)
def test_an_unreadable_registry_is_none_never_empty(
    tmp_path: Path, reader, file: str, text: str
) -> None:
    (tmp_path / file).write_text(text, encoding="utf-8")
    assert reader(tmp_path) is None


# ---- The plan ----

DECLARED = {
    "deepwiki": "https://mcp.deepwiki.com/mcp",
    "bun": "https://bun.com/docs/mcp",
}


@pytest.mark.parametrize("agent", mcp.AGENTS)
def test_a_missing_server_is_added(agent: str) -> None:
    steps = mcp.plan(agent, DECLARED, {"deepwiki": "https://mcp.deepwiki.com/mcp"})
    assert steps == [mcp.add_args(agent, "bun", "https://bun.com/docs/mcp")]


@pytest.mark.parametrize("agent", mcp.AGENTS)
def test_a_server_at_another_url_is_removed_then_added(agent: str) -> None:
    # `mcp add` on a name that exists fails in these CLIs
    steps = mcp.plan(
        agent, {"bun": "https://bun.com/docs/mcp"}, {"bun": "https://old.example/mcp"}
    )
    assert steps == [
        mcp.remove_args(agent, "bun"),
        mcp.add_args(agent, "bun", "https://bun.com/docs/mcp"),
    ]


@pytest.mark.parametrize("agent", mcp.AGENTS)
def test_nothing_happens_when_every_server_is_right_and_others_are_left(
    agent: str,
) -> None:
    registry = {**DECLARED, "nexlev": "https://example.invalid/mcp", "headroom": None}
    assert mcp.plan(agent, DECLARED, registry) == []


def test_each_agent_is_driven_through_its_own_cli() -> None:
    url = "https://bun.com/docs/mcp"
    assert mcp.add_args("claude", "bun", url) == [
        "mcp", "add", "--scope", "user", "--transport", "http", "bun", url,
    ]  # fmt: skip
    assert mcp.add_args("codex", "bun", url) == ["mcp", "add", "bun", "--url", url]
    assert mcp.add_args("pi", "bun", url) == ["mcp", "add", "bun", "--url", url]
    assert mcp.add_args("antigravity", "bun", url) == ["mcp", "add", "bun", url]
    assert mcp.remove_args("claude", "bun") == [
        "mcp", "remove", "bun", "--scope", "user",
    ]  # fmt: skip
    for agent in ("codex", "pi", "antigravity"):
        assert mcp.remove_args(agent, "bun") == ["mcp", "remove", "bun"]


def test_antigravity_is_found_by_its_mise_name_first() -> None:
    # mise installs the CLI as `antigravity` (rename_exe); `agy` is its own name
    assert mcp.EXECUTABLES["antigravity"] == ("antigravity", "agy")


# ---- Reconciling one agent ----


class FakeAgent:
    """A registry and the CLI that writes it, as one agent keeps them."""

    def __init__(self, agent: str, registry: dict[str, str | None] | None) -> None:
        self.agent = agent
        self.registry = registry
        self.calls: list[list[str]] = []

    def read(self) -> dict[str, str | None] | None:
        return None if self.registry is None else dict(self.registry)

    def cli(self, args: list[str]) -> bool:
        self.calls.append(args)
        assert self.registry is not None
        if args[1] == "remove":
            self.registry.pop(args[2], None)
        else:
            name = next(
                a
                for a in args[2:]
                if not a.startswith("-") and a not in {"user", "http"}
            )
            self.registry[name] = args[-1]
        return True


def test_reconcile_adds_what_is_missing_and_reads_it_back() -> None:
    fake = FakeAgent("codex", {})
    fixed, problem = mcp.reconcile(fake.read, fake.cli, "codex", DECLARED, check=False)
    assert problem is None
    assert sorted(fixed) == ["added bun", "added deepwiki"]
    assert fake.registry == DECLARED


def test_check_reports_without_writing() -> None:
    fake = FakeAgent("pi", {})
    fixed, problem = mcp.reconcile(fake.read, fake.cli, "pi", DECLARED, check=True)
    assert fixed == []
    assert problem == "missing bun, deepwiki"
    assert fake.calls == []


def test_an_unreadable_registry_stops_that_agent_without_writing() -> None:
    fake = FakeAgent("antigravity", None)
    fixed, problem = mcp.reconcile(
        fake.read, fake.cli, "antigravity", DECLARED, check=False
    )
    assert fixed == []
    assert problem == "could not read the MCP registry"
    assert fake.calls == []


def test_a_cli_that_fails_is_a_problem_not_a_fix() -> None:
    fake = FakeAgent("codex", {})
    fixed, problem = mcp.reconcile(
        fake.read, lambda _args: False, "codex", DECLARED, check=False
    )
    assert fixed == []
    assert problem is not None and "failed" in problem


# ---- Guidance for a server that needs a secret ----


def test_guidance_names_each_agent_that_lacks_the_server() -> None:
    declared = mcp.load(ROOT / "dump/harness/mcp-servers.json")
    registries: Mapping[str, dict[str, str | None]] = {
        "claude": {
            "google-dev-knowledge": "https://developerknowledge.googleapis.com/mcp"
        },
        "codex": {},
    }
    lines = mcp.guidance(declared, registries)
    assert all(level == "INFO" for level, _name, _detail in lines)
    text = "\n".join(detail for _level, _name, detail in lines)
    assert "codex" in text and "X-Goog-Api-Key" in text
    assert "claude mcp add" not in text  # claude already has it
    assert "developerknowledge.googleapis.com" in text
    assert all("\n" not in detail for _level, _name, detail in lines)
    # the README no longer carries these steps, so the run must
    assert (
        "gcloud beta services mcp enable developerknowledge.googleapis.com "
        "--project=<project-id>"
    ) in text
    assert "gcloud services api-keys create --project=<project-id>" in text
    assert "tofu" in text  # a personal project only, never one IaC manages


def test_claude_guidance_sets_the_config_dir_only_for_a_named_home() -> None:
    # a plain `claude` reads ~/.claude.json; with CLAUDE_CONFIG_DIR=~/.claude it
    # reads ~/.claude/.claude.json, a different registry
    declared = mcp.load(ROOT / "dump/harness/mcp-servers.json")
    lines = mcp.guidance(declared, {"claude ~": {}, "claude ~/.claude": {}})
    by_label = {detail.split(":")[0]: detail for _level, _name, detail in lines}
    plain = by_label["google-dev-knowledge for claude ~"]
    named = by_label["google-dev-knowledge for claude ~/.claude"]
    assert "CLAUDE_CONFIG_DIR" not in plain
    assert "CLAUDE_CONFIG_DIR=~/.claude claude mcp add" in named


def test_no_guidance_once_every_agent_has_the_server() -> None:
    declared = mcp.load(ROOT / "dump/harness/mcp-servers.json")
    present = {"google-dev-knowledge": "https://developerknowledge.googleapis.com/mcp"}
    assert mcp.guidance(declared, {"claude": present, "pi": present}) == []


def test_codex_is_shown_how_to_add_a_sign_in_server_it_lacks() -> None:
    declared = mcp.load(ROOT / "dump/harness/mcp-servers.json")
    gdk = {"google-dev-knowledge": "https://developerknowledge.googleapis.com/mcp"}
    lines = mcp.guidance(
        declared,
        {"codex": {**gdk, "cloudflare": "https://mcp.cloudflare.com/mcp"}, "pi": gdk},
    )
    text = [detail for _level, _name, detail in lines]
    assert any("codex mcp add vercel --url https://mcp.vercel.com" in t for t in text)
    assert not any("codex mcp add cloudflare" in t for t in text)
    assert not any("pi mcp add vercel" in t for t in text)  # the run adds it


@pytest.mark.parametrize(
    ("agent", "expected"),
    [
        ("pi", "pi mcp login vercel"),
        ("antigravity", "sign in"),
        ("claude", None),
        ("codex", None),
    ],
)
def test_adding_a_sign_in_server_says_how_to_sign_in(
    agent: str, expected: str | None
) -> None:
    note = mcp.sign_in_note(agent, "vercel")
    if expected is None:
        assert note is None
    else:
        assert note is not None and expected in note
