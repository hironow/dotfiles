"""headroom's MCP server is registered in every Claude home, egress pinned.

The rules (plan/wrong/declared) are pure and tested against inventories here.
One test then drives the REAL `claude mcp add` against a TEMP CLAUDE_CONFIG_DIR,
because the whole point of going through Claude Code's own CLI is that it owns
`<home>/.claude.json`: a test that only exercised a fake CLI would not notice the
CLI changing the shape it writes.

Why the registration carries HEADROOM_BEACON=off and DO_NOT_TRACK=1 in its own
`env`: Claude Code starts this server itself, so no shell's mise `[env]` reaches
it. tests/unit/test_agent_tool_telemetry.py owns the posture; this pins that the
registration repeats it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import headroom_mcp as hm  # noqa: E402

GOOD = {"mcpServers": {"headroom": hm._registration()}}


def _inventory(**server: object) -> dict:
    entry = {**hm._registration(), **server}
    return {"mcpServers": {"headroom": entry}}


# --- the rules ---------------------------------------------------------


def test_a_matching_registration_needs_nothing() -> None:
    assert hm.wrong(hm.declared(GOOD)) is None
    assert hm.plan(hm.declared(GOOD)) == []


@pytest.mark.parametrize(
    "inventory",
    [{}, {"mcpServers": {}}, {"mcpServers": {"other": {}}}, {"mcpServers": "nonsense"}],
)
def test_no_registration_is_added_once(inventory: dict) -> None:
    entry = hm.declared(inventory)
    assert hm.wrong(entry) is not None
    steps = hm.plan(entry)
    assert len(steps) == 1, "nothing to remove when there is nothing there"
    assert steps[0][:2] == ["mcp", "add"]


def test_a_registration_without_the_egress_is_replaced() -> None:
    """Fail open: a server whose env lost DO_NOT_TRACK uploads. The entry is
    removed and re-added, because `mcp add` on an existing name is an error."""
    entry = hm.declared(_inventory(env={"HEADROOM_BEACON": "off"}))
    assert "DO_NOT_TRACK=1" in (hm.wrong(entry) or "")
    assert [step[:2] for step in hm.plan(entry)] == [
        ["mcp", "remove"],
        ["mcp", "add"],
    ]


def test_a_registration_running_something_else_is_replaced() -> None:
    entry = hm.declared(_inventory(command="headroom", args=["mcp", "serve"]))
    assert "runs headroom" in (hm.wrong(entry) or "")
    assert len(hm.plan(entry)) == 2


def test_the_add_passes_both_switches_and_the_mise_command() -> None:
    add = hm.plan(None)[0]
    assert (
        add[-6:] == ["--", "mise", "x", "--", "headroom", "mcp"] or add[-1] == "serve"
    )
    assert "--env" in add
    passed = {add[i + 1] for i, flag in enumerate(add) if flag == "--env"}
    assert passed == {"HEADROOM_BEACON=off", "DO_NOT_TRACK=1"}
    # not an absolute path: a pinned one breaks on the next version bump
    assert hm.COMMAND == "mise"


# --- reconcile, against an injected CLI --------------------------------


def _reader(registries: list[dict | None]) -> hm.Read:
    """Answers each read from `registries`, in order."""
    return lambda: registries.pop(0)


def _recorder(calls: list[list[str]], *, ok: bool = True) -> hm.Cli:
    def cli(args: list[str]) -> bool:
        calls.append(args)
        return ok

    return cli


def test_check_reports_without_changing_anything() -> None:
    calls: list[list[str]] = []
    fixed, problem = hm.reconcile(_reader([{}]), _recorder(calls), check=True)
    assert fixed is None
    assert problem is not None
    assert calls == [], "--check must not call the CLI at all"


def test_an_unreadable_registry_is_never_taken_for_missing() -> None:
    calls: list[list[str]] = []
    fixed, problem = hm.reconcile(_reader([None]), _recorder(calls), check=False)
    assert (fixed, problem) == (None, "could not read the MCP registry")
    assert calls == [], "a registry that will not parse must not be written to"


def test_a_fix_is_verified_by_reading_the_registry_back() -> None:
    calls: list[list[str]] = []
    fixed, problem = hm.reconcile(_reader([{}, GOOD]), _recorder(calls), check=False)
    assert problem is None
    assert fixed is not None
    assert [step[:2] for step in calls] == [["mcp", "add"]]


def test_a_fix_that_did_not_take_is_reported_not_claimed() -> None:
    calls: list[list[str]] = []
    fixed, problem = hm.reconcile(_reader([{}, {}]), _recorder(calls), check=False)
    assert fixed is None
    assert problem is not None and "still" in problem


def test_a_failing_add_is_reported_not_swallowed() -> None:
    calls: list[list[str]] = []
    fixed, problem = hm.reconcile(
        _reader([{}, {}]), _recorder(calls, ok=False), check=False
    )
    assert fixed is None
    assert problem is not None and "failed" in problem


# --- the real CLI, against a temporary home ----------------------------


@pytest.mark.skipif(
    shutil.which("claude") is None, reason="claude not on PATH (mise install)"
)
def test_the_real_cli_writes_the_registration_we_expect(tmp_path: Path) -> None:
    """End to end against `claude mcp add --scope user`, CLAUDE_CONFIG_DIR at a
    temp dir, so no real home is touched. Also pins idempotence: a second run
    reports nothing to fix."""
    home = tmp_path / "home"
    home.mkdir()
    script = ROOT / "scripts" / "headroom_mcp.py"
    first = subprocess.run(  # noqa: S603 - fixed argv, test-only
        [sys.executable, str(script), "--home", str(home)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=False,
        env={**os.environ, "HOME": str(tmp_path)},
    )
    assert first.returncode == 0, first.stdout + first.stderr

    written = json.loads((home / ".claude.json").read_text(encoding="utf-8"))
    entry = hm.declared(written)
    assert entry is not None, written.get("mcpServers")
    assert hm.wrong(entry) is None, hm.wrong(entry)
    assert entry["env"] == hm.EGRESS, "the egress switches must be on the server itself"

    again = subprocess.run(  # noqa: S603 - fixed argv, test-only
        [sys.executable, str(script), "--check", "--home", str(home)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=False,
        env={**os.environ, "HOME": str(tmp_path)},
    )
    assert again.returncode == 0, again.stdout + again.stderr
    assert "registered, egress pinned" in again.stdout


def test_main_prints_each_home_then_the_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    homes = [tmp_path / "a", tmp_path / "b"]
    results = {
        "a": ("no headroom MCP server", None),
        "b": (None, "could not read the MCP registry"),
    }
    monkeypatch.setattr(hm.shutil, "which", lambda _: "claude")
    monkeypatch.setattr(hm, "_read", lambda home: home)
    monkeypatch.setattr(
        hm, "reconcile", lambda home, _cli, *, check: results[home.name]
    )
    argv = [arg for home in homes for arg in ("--home", str(home))]
    assert hm.main(["--check", *argv]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "OK   headroom-mcp - ~/a: fixed: no headroom MCP server",
        "WARN headroom-mcp - ~/b: could not read the MCP registry:"
        " just headroom-mcp-register",
    ]
    results["b"] = (None, None)
    assert hm.main(argv) == 0
    assert capsys.readouterr().out.splitlines()[-1] == (
        "OK   headroom-mcp - headroom registered, egress pinned, in 2 Claude home(s)"
    )
