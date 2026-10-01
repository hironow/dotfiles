"""Every Claude home gets the plugins dotfiles requires (codex@openai-codex).

j-cc hands Codex work to `codex:codex-rescue`, which only exists with the Codex
plugin; jev-claude-verify stayed BLOCKED on hosts without it. The plugins are
declared in dump/harness/claude-plugins.json (marketplaces pinned to a tag) and
installed through Claude Code's own plugin CLI. The steps come from that CLI's
--json inventory; a fake CLI with real state checks the whole round trip:
replacing a marketplace drops its plugins, a second run changes nothing, and
an unreadable inventory is never read as "missing".
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import claude_plugins as plugins  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DECLARED = plugins.Declaration(
    marketplaces={"openai-codex": "openai/codex-plugin-cc#v1.0.6"},
    plugins=("codex@openai-codex",),
)


def test_the_repo_declares_the_codex_plugin_pinned_to_a_tag() -> None:
    declared = plugins.load(ROOT / "dump/harness/claude-plugins.json")
    assert "codex@openai-codex" in declared.plugins
    repo, ref = plugins.parse_source(declared.marketplaces["openai-codex"])
    assert repo == "openai/codex-plugin-cc"
    assert ref is not None and ref.startswith("v")


def test_a_source_splits_into_repo_and_ref() -> None:
    assert plugins.parse_source("o/r#v1.2.3") == ("o/r", "v1.2.3")
    assert plugins.parse_source("o/r") == ("o/r", None)


class FakeClaude:
    """`claude plugin ...` against in-memory state, as the real CLI behaves."""

    def __init__(self, markets: list[dict], installed: list[dict]) -> None:
        self.markets, self.installed = markets, installed
        self.mutations: list[list[str]] = []
        self.readable = True
        self.failing: list[str] | None = None  # e.g. ["marketplace", "add"]

    def __call__(self, args: list[str]) -> str | None:
        if args[-1] == "--json":
            if not self.readable:
                return None
            return json.dumps(self.markets if "marketplace" in args else self.installed)
        self.mutations.append(args)
        if self.failing and args[1:3] == self.failing:
            return None
        match args[1:]:
            case ["marketplace", "add", source, "--scope", "user"]:
                repo, ref = plugins.parse_source(source)
                self.markets.append({"name": "openai-codex", "repo": repo, "ref": ref})
            case ["marketplace", "remove", name, "--scope", "user"]:
                # removing a marketplace uninstalls what came from it
                self.markets = [m for m in self.markets if m["name"] != name]
                self.installed = [
                    p for p in self.installed if not p["id"].endswith("@" + name)
                ]
            case ["install", pid, "--scope", "user"]:
                self.installed.append(
                    {"id": pid, "version": "1.0.6", "scope": "user", "enabled": True}
                )
            case ["uninstall", pid, "--scope", "user"]:
                self.installed = [
                    p
                    for p in self.installed
                    if not (p["id"] == pid and p["scope"] == "user")
                ]
            case ["enable", pid, "--scope", "user"]:
                for p in self.installed:
                    if p["id"] == pid and p["scope"] == "user":
                        p["enabled"] = True
            case _:
                raise AssertionError(f"unexpected claude {args}")
        return ""


MARKET = {"name": "openai-codex", "repo": "openai/codex-plugin-cc", "ref": "v1.0.6"}
PLUGIN = {
    "id": "codex@openai-codex",
    "version": "1.0.6",
    "scope": "user",
    "enabled": True,
}


def _run(cli: FakeClaude, *, check: bool = False) -> tuple[list[str], list[str]]:
    return plugins.reconcile(DECLARED, cli, check=check)


def test_an_empty_home_gets_the_marketplace_and_the_plugin_once() -> None:
    cli = FakeClaude([], [])
    done, problems = _run(cli)
    assert problems == []
    assert [m[1:3] for m in cli.mutations] == [
        ["marketplace", "add"],
        ["install", "codex@openai-codex"],
    ]
    cli.mutations.clear()
    assert _run(cli) == ([], [])
    assert cli.mutations == []


def test_a_marketplace_at_another_ref_is_replaced_and_the_plugin_reinstalled() -> None:
    old = {**MARKET, "ref": "v1.0.5"}
    cli = FakeClaude([old], [{**PLUGIN, "version": "1.0.5"}])
    done, problems = _run(cli)
    assert problems == []
    assert len(done) == len(set(done))  # remove and add share one reason
    assert cli.markets == [MARKET]
    assert cli.installed == [PLUGIN]


@pytest.mark.parametrize(
    ("installed", "steps"),
    [
        ([{**PLUGIN, "enabled": False}], [["enable", "codex@openai-codex"]]),
        # a project or local install does not count for the user
        ([{**PLUGIN, "scope": "project"}], [["install", "codex@openai-codex"]]),
        (
            [{**PLUGIN, "version": "1.0.4"}],
            [["uninstall", "codex@openai-codex"], ["install", "codex@openai-codex"]],
        ),
    ],
)
def test_the_plugin_converges_on_the_declared_user_install(
    installed: list[dict], steps: list[list[str]]
) -> None:
    cli = FakeClaude([dict(MARKET)], installed)
    assert _run(cli)[1] == []
    assert [m[1:3] for m in cli.mutations] == steps
    assert all(m[-2:] == ["--scope", "user"] for m in cli.mutations)


def test_an_unreadable_inventory_is_reported_never_acted_on() -> None:
    cli = FakeClaude([], [])
    cli.readable = False
    done, problems = _run(cli)
    assert done == []
    assert cli.mutations == []
    assert problems and "cannot read" in problems[0]


def test_check_reports_without_changing_anything() -> None:
    cli = FakeClaude([], [])
    _done, problems = _run(cli, check=True)
    assert cli.mutations == []
    assert any("openai-codex" in p for p in problems)
    assert any("codex@openai-codex" in p for p in problems)


def test_a_complete_home_has_no_steps() -> None:
    cli = FakeClaude([dict(MARKET)], [dict(PLUGIN)])
    assert _run(cli, check=True) == ([], [])


def test_doctor_checks_and_deploy_installs_the_plugins() -> None:
    import ai_tools_check  # noqa: PLC0415

    assert "claude_plugins.py" in ai_tools_check.CHECKERS["claude"][1]
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    assert "claude-plugins-install *args:" in justfile
    deploy = (ROOT / "scripts/deploy.sh").read_text(encoding="utf-8")
    # both the native Windows path and the Unix path
    assert deploy.count("claude_plugins.py") >= 2


@pytest.mark.parametrize(
    "fragment",
    sorted(
        [*(ROOT / ".claude").glob("settings.shared*.json")]
        + [*(ROOT / ".claude/settings.profiles").glob("*.json")]
    ),
    ids=lambda path: path.name,
)
def test_no_settings_fragment_claims_the_plugin_keys(fragment: Path) -> None:
    # The plugin CLI owns them (ADR 0037, ADR 0048): a fragment declaring them
    # would replace what claude_plugins.py installed on every sync
    data = json.loads(fragment.read_text(encoding="utf-8"))
    sections = [data, data.get("settings", {})]
    for key in ("enabledPlugins", "extraKnownMarketplaces"):
        assert all(key not in section for section in sections)


@pytest.mark.parametrize(
    ("deadline", "now", "timeout"),
    [
        (None, 0.0, plugins.CALL_TIMEOUT),  # installing: no overall budget
        (1000.0, 0.0, plugins.CALL_TIMEOUT),
        (100.0, 90.0, 10.0),  # the budget's rest, so doctor gets every line
        (100.0, 100.0, None),  # spent: skip, reported as unreadable
    ],
)
def test_each_call_fits_the_overall_budget(
    deadline: float | None, now: float, timeout: float | None
) -> None:
    assert plugins.call_timeout(deadline, now) == timeout


def test_the_check_budget_ends_before_doctor_stops_waiting() -> None:
    import ai_tools_check  # noqa: PLC0415

    assert plugins.CHECK_BUDGET < ai_tools_check.CHECKER_TIMEOUT


def test_a_repair_that_fails_halfway_is_not_reported_as_done() -> None:
    # remove succeeds, add fails: the marketplace is now missing, not fixed
    cli = FakeClaude([{**MARKET, "ref": "v1.0.5"}], [])
    cli.failing = ["marketplace", "add"]
    done, problems = _run(cli)
    assert done == []
    assert problems and "failed" in problems[0]
