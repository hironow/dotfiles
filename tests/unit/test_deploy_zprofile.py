"""`just deploy` gives zsh login shells the ~/.local/bin bash got from ~/.profile.

A zsh login shell reads ~/.zprofile and never ~/.profile, and only interactive
shells read .zshrc. On a WSL box switched to zsh, `zsh -lc 'just ...'` (how
scripts and agents run commands) no longer found tools in ~/.local/bin. deploy
appends one managed block to ~/.zprofile instead of linking the file, because
a Mac usually keeps its own lines there (brew shellenv).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from _bash_hook import resolve_bash

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = (ROOT / "scripts/deploy.sh").read_text(encoding="utf-8")
BASH = resolve_bash()
MARKER = "# >>> dotfiles managed block: login PATH >>>"


def _function(name: str) -> str:
    match = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", DEPLOY, re.M | re.S)
    assert match, f"deploy.sh has no {name}()"
    return match.group(0)


def _ensure(home: Path) -> None:
    script = _function("ensure_zprofile_login_path") + "ensure_zprofile_login_path\n"
    result = subprocess.run(
        [BASH, "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={"HOME": home.as_posix(), "PATH": "/usr/bin:/bin"},
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _login_path(home: Path, path: str) -> str:
    # Source the written ~/.zprofile the way a POSIX shell would
    result = subprocess.run(
        [BASH, "-c", '. "$HOME/.zprofile"; printf %s "$PATH"'],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={"HOME": home.as_posix(), "PATH": path},
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_the_block_is_added_once_after_the_users_own_lines(tmp_path: Path) -> None:
    own = 'eval "$(/opt/homebrew/bin/brew shellenv)"\n'
    (tmp_path / ".zprofile").write_text(own, encoding="utf-8", newline="\n")

    _ensure(tmp_path)
    _ensure(tmp_path)

    text = (tmp_path / ".zprofile").read_text(encoding="utf-8")
    assert text.startswith(own)
    assert text.count(MARKER) == 1


def _bash_home(home: Path) -> str:
    """HOME as bash sees it (Git Bash maps the Windows temp dir to /tmp)."""
    return subprocess.run(
        [BASH, "-c", 'printf %s "$HOME"'],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={"HOME": home.as_posix(), "PATH": "/usr/bin:/bin"},
        check=True,
    ).stdout


def test_a_login_shell_gets_local_bin(tmp_path: Path) -> None:
    (tmp_path / ".local" / "bin").mkdir(parents=True)
    _ensure(tmp_path)

    local_bin = f"{_bash_home(tmp_path)}/.local/bin"
    assert _login_path(tmp_path, "/usr/bin:/bin").split(":")[0] == local_bin
    # already on PATH: left where it is, not duplicated
    assert _login_path(tmp_path, f"/usr/bin:{local_bin}") == f"/usr/bin:{local_bin}"


def test_no_local_bin_leaves_path_alone(tmp_path: Path) -> None:
    _ensure(tmp_path)
    assert _login_path(tmp_path, "/usr/bin:/bin") == "/usr/bin:/bin"


def test_unix_deploy_adds_the_block() -> None:
    unix = DEPLOY.split('echo "==> Start to deploy dotfiles to home directory."', 1)[1]
    assert "ensure_zprofile_login_path" in unix
