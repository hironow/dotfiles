"""deploy runs the agent steps (Pi extensions, Claude plugins, headroom's MCP
server) on every OS, once mise has installed the tools.

The steps are one list (AGENT_STEPS) run by run_agent_steps in both the native
Windows branch, which exits early, and the shared Unix tail: a step written in
the tail alone never reached Windows (headroom's MCP server, on a second host).
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from _bash_hook import bash_path, resolve_bash

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = (ROOT / "scripts/deploy.sh").read_text(encoding="utf-8")
JUSTFILE = (ROOT / "justfile").read_text(encoding="utf-8")
WINDOWS, UNIX = DEPLOY.split("    exit 0", 1)
STEPS_BLOCK = DEPLOY[
    DEPLOY.index("AGENT_STEPS='") : DEPLOY.index('case "$(uname -s)" in')
]


def _steps() -> list[tuple[str, str]]:
    body = STEPS_BLOCK.split("'", 2)[1].replace("'\"'\"'", "'")
    return [
        (script, recipe)
        for script, recipe, *_what in (line.split() for line in body.splitlines())
    ]


def test_the_steps_are_the_agent_scripts_and_their_recipes() -> None:
    steps = _steps()
    assert [script for script, _ in steps] == [
        "install_pi_extensions.py",
        "claude_plugins.py",
        "headroom_mcp.py",
    ]
    for script, recipe in steps:
        assert (ROOT / "scripts" / script).is_file()
        assert re.search(rf"^{re.escape(recipe)}\b.*:", JUSTFILE, re.MULTILINE), recipe


def test_unix_deploy_runs_the_steps_after_mise_installs() -> None:
    unix = DEPLOY.split('echo "==> Start to deploy dotfiles to home directory."', 1)[1]
    assert "mise -C / install" in unix
    assert unix.index("mise -C / install") < unix.index("    run_agent_steps\n")


def test_windows_deploy_runs_the_steps_after_mise_installs() -> None:
    assert "MISE_NODE_COREPACK=0 mise -C / install" in WINDOWS
    call = "(export MISE_NODE_COREPACK=0 && run_agent_steps)"
    assert call in WINDOWS
    assert WINDOWS.index("MISE_NODE_COREPACK=0 mise -C / install") < WINDOWS.index(call)


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_each_step_runs_through_mise_and_a_failure_only_warns(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls"
    mise = bin_dir / "mise"
    mise.write_text(
        "#!/bin/sh\n"
        f'printf "%s %s\\n" "${{MISE_NODE_COREPACK:-}}" "$6" >> "{log.as_posix()}"\n'
        'case "$6" in *claude_plugins.py) exit 1 ;; esac\n',
        encoding="utf-8",
        newline="\n",
    )
    mise.chmod(0o755)
    script = (
        f'PATH="{bash_path(bin_dir)}:$PATH"\n'
        + STEPS_BLOCK
        + "(export MISE_NODE_COREPACK=0 && run_agent_steps)\n"
    )
    done = subprocess.run(
        [resolve_bash(), "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert done.returncode == 0, done.stderr
    calls = log.read_text(encoding="utf-8").splitlines()
    assert [call.split()[0] for call in calls] == ["0", "0", "0"]
    assert [call.rsplit("/", 1)[-1] for call in calls] == [
        "install_pi_extensions.py",
        "claude_plugins.py",
        "headroom_mcp.py",
    ]
    assert "WARN: claude_plugins.py failed; run 'just claude-plugins-install'" in (
        done.stdout
    )
    assert "==> Registering headroom's MCP server..." in done.stdout
