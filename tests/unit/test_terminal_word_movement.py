"""Run zsh's main keymaps and an isolated tmux server."""

import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from _zsh_startup import ROOT, run_zsh


@pytest.mark.skipif(shutil.which("zsh") is None, reason="needs zsh")
def test_zshrc_parses() -> None:
    result = subprocess.run(
        ["zsh", "-n", str(ROOT / ".zshrc")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("keymap", ["-e", "-v"])
def test_zsh_main_keymap(tmp_path: Path, keymap: str) -> None:
    output = run_zsh(
        tmp_path,
        f"builtin bindkey {keymap}\n"
        + r"""
source "$1"
builtin zle -la
for key in '^[[1;3D' '^[[1;3C' '^[[1;5D' '^[[1;5C' '^[[13;5u' '^[[27;5;13~'; do
    builtin bindkey "$key"
done
""",
    )
    expected = {
        "^[[1;3D": "backward-word",
        "^[[1;3C": "forward-word",
        "^[[1;5D": "backward-word",
        "^[[1;5C": "forward-word",
        "^[[13;5u": "_ctrl_enter_newline",
        "^[[27;5;13~": "_ctrl_enter_newline",
    }
    assert "_ctrl_enter_newline" in output.splitlines()
    for sequence, widget in expected.items():
        assert f'"{sequence}" {widget}' in output.splitlines()
    calls = [
        line.split("\t")
        for line in (tmp_path / "bindings").read_text(encoding="utf-8").splitlines()
    ]
    arrows = [
        call
        for call in calls
        if any(re.fullmatch(r"\^\[\[1;\d[DC]", arg) for arg in call)
    ]
    newline = [call for call in calls if "_ctrl_enter_newline" in call]
    assert sorted(arrows) == sorted(
        [
            [key, value]
            for key, value in expected.items()
            if value != "_ctrl_enter_newline"
        ]
    )
    assert sorted(newline) == [
        ["^[[13;5u", "_ctrl_enter_newline"],
        ["^[[27;5;13~", "_ctrl_enter_newline"],
    ]


def test_tmux_extended_keys(tmp_path: Path) -> None:
    if sys.platform == "win32":
        pytest.skip("needs POSIX tmux and a private Unix socket")
    tmux = shutil.which("tmux")
    if tmux is None:
        pytest.skip("needs tmux")
    home = tmp_path / "home"
    plugin = home / "dotfiles/tools/tmux/plugins/tmux-resurrect/resurrect.tmux"
    plugin.parent.mkdir(parents=True)
    plugin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8", newline="\n")
    plugin.chmod(0o755)
    # Keep the socket below macOS's Unix socket path limit.
    socket_dir = Path(tempfile.mkdtemp(prefix="dotfiles-tmux-", dir="/tmp"))
    socket_path = socket_dir / "s"
    try:
        with socket.socket(socket.AF_UNIX) as probe:
            probe.bind(str(socket_path))
    except PermissionError:
        socket_dir.rmdir()
        pytest.skip("host sandbox forbids binding the private tmux Unix socket")
    socket_path.unlink()
    env = {
        "HOME": str(home),
        "PATH": "/usr/bin:/bin",
        "TERM": "xterm-256color",
        "TMPDIR": str(tmp_path),
    }

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [tmux, "-S", str(socket_path), *args],
            env=env,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=15,
        )

    try:
        start = run(
            "-f",
            str(ROOT / "tools/tmux/tmux.conf"),
            "new-session",
            "-d",
            "-s",
            "keys",
            "/bin/sh -c 'while :; do sleep 60; done'",
        )
        assert start.returncode == 0, start.stderr
        for option, expected in (
            ("extended-keys", "always"),
            ("terminal-features", "xterm*:extkeys"),
        ):
            value = run("show-options", "-s", option)
            assert value.returncode == 0, value.stderr
            assert expected in value.stdout, value.stdout
        format_option = run("show-options", "-sv", "extended-keys-format")
        if format_option.returncode == 0:
            assert format_option.stdout.strip() == "xterm"
        else:
            assert "invalid option" in format_option.stderr, format_option.stderr
    finally:
        run("kill-server")
        socket_path.unlink(missing_ok=True)
        socket_dir.rmdir()
