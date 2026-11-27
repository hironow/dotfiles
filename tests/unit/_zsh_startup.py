"""Source the real zsh startup in a disposable home with recording tools."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def run_zsh(tmp_path: Path, program: str, *, docker_host: str | None = None) -> str:
    if sys.platform == "win32":
        pytest.skip("needs POSIX zsh and executable shell fakes")
    zsh = shutil.which("zsh")
    if zsh is None:
        pytest.skip("needs zsh")
    home = tmp_path / "home"
    bin_dir = home / ".local/bin"
    bin_dir.mkdir(parents=True)
    for directory in ("cache", "config", "tmp"):
        (tmp_path / directory).mkdir()
    cache = tmp_path / "cache/zsh"
    cache.mkdir()
    for name in ("kubectl_completion.zsh", "ant_completion.zsh", "fzf_init.zsh"):
        (cache / name).write_text(":\n", encoding="utf-8")
    log = tmp_path / "tools"
    log.touch()
    # Functions below also cover absolute Homebrew commands and PATH prepends.
    names = (
        "mise",
        "kubectl",
        "ant",
        "fzf",
        "sheldon",
        "starship",
        "tty",
        "podman",
        "docker",
        "curl",
        "git",
        "wget",
        "brew",
        "orb",
    )
    for name in names:
        fake = bin_dir / name
        fake.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$0 $*" >> "$TOOL_LOG"\n',
            encoding="utf-8",
            newline="\n",
        )
        fake.chmod(0o755)
    # Retired completion sources announce themselves if startup loads them.
    for rel in (".orbstack/shell/init.zsh", ".docker/completions/_docker"):
        path = home / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('print -r -- RETIRED >> "$TOOL_LOG"\n', encoding="utf-8")
    prelude = r"""
unsetopt bgnice
record_tool() { print -r -- "$*" >> "$TOOL_LOG"; }
function /opt/homebrew/bin/brew { record_tool brew "$@"; }
function /home/linuxbrew/.linuxbrew/bin/brew { record_tool brew "$@"; }
autoload() { [[ "$*" == *compinit* ]] || builtin autoload "$@"; }
compinit() { :; }
"""
    for name in names:
        prelude += f'{name}() {{ record_tool {name} "$@"; }}\n'
    prelude += r"""
bindkey() {
    print -r -- "${(pj:\t:)@}" >> "$BIND_LOG"
    builtin bindkey "$@"
}
zle() {
    print -r -- "${(pj:\t:)@}" >> "$ZLE_LOG"
    [[ "$1" == accept-line ]] || builtin zle "$@"
}
command_not_found_handler() { record_tool UNKNOWN "$@"; return 127; }
"""
    env = {
        "HOME": str(home),
        "ZDOTDIR": str(home),
        "PATH": str(bin_dir),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "TMPDIR": str(tmp_path / "tmp"),
        "TOOL_LOG": str(log),
        "BIND_LOG": str(tmp_path / "bindings"),
        "ZLE_LOG": str(tmp_path / "widgets"),
        "TERM": "xterm-256color",
    }
    if docker_host is not None:
        env["DOCKER_HOST"] = docker_host
    result = subprocess.run(
        [zsh, "-f", "-c", prelude + program, "startup", str(ROOT / ".zshrc")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == "", result.stderr
    calls = log.read_text(encoding="utf-8").splitlines()
    assert not [
        line
        for line in calls
        if line.startswith(
            (
                "podman ",
                "docker ",
                "curl ",
                "git ",
                "wget ",
                "orb ",
                "RETIRED",
                "UNKNOWN",
            )
        )
    ], calls
    return result.stdout
