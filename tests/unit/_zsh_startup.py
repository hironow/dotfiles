"""Run the real startup file with private homes and inert startup tools."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def run_startup(tmp_path: Path, commands: str) -> subprocess.CompletedProcess[str]:
    if sys.platform == "win32":
        pytest.skip("zsh startup needs POSIX; Windows has PowerShell launchers")
    zsh = shutil.which("zsh")
    if zsh is None:
        pytest.skip("zsh unavailable; startup probes need the real shell")
    home = tmp_path / "home"
    bin_dir = home / ".local/bin"
    bin_dir.mkdir(parents=True)
    for tool in ("mise", "python3", "kubectl", "ant", "sheldon", "starship", "fzf"):
        stub = bin_dir / tool
        body = "#!/bin/sh\n"
        if tool == "mise":
            body += '[ "$#" = 2 ] && [ "$1" = activate ] && [ "$2" = zsh ] || exit 94\n'
            body += 'printf "%s\\n" "$MISE_IGNORED_CONFIG_PATHS" >> "$ACTIVATE_LOG"\n'
        elif tool == "python3":
            body += 'printf "%s\\0" "$@" >> "$LAUNCH_LOG"\n'
        stub.write_text(body, encoding="utf-8", newline="\n")
        stub.chmod(0o755)
    prelude = r"""
unsetopt bgnice
function /opt/homebrew/bin/brew() { :; }
function /home/linuxbrew/.linuxbrew/bin/brew() { :; }
kubectl() { "$PROBE_BIN/kubectl" "$@"; }
ant() { "$PROBE_BIN/ant" "$@"; }
mise() { "$PROBE_BIN/mise" "$@"; }
python3() { "$PROBE_BIN/python3" "$@"; }
sheldon() { "$PROBE_BIN/sheldon" "$@"; }
starship() { "$PROBE_BIN/starship" "$@"; }
fzf() { "$PROBE_BIN/fzf" "$@"; }
source "$STARTUP_FILE"
"""
    return subprocess.run(
        [zsh, "-dfc", prelude + commands],
        cwd=tmp_path,
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "HOME": str(home),
            "ZDOTDIR": str(home),
            "PROBE_BIN": str(bin_dir),
            "STARTUP_FILE": str(ROOT / ".zshrc"),
            "_WIN_HOME_ROOT": str(tmp_path / "mount/Users"),
            "MISE_IGNORED_CONFIG_PATHS": "/mnt/c",
            "ACTIVATE_LOG": str(tmp_path / "activate.log"),
            "LAUNCH_LOG": str(tmp_path / "launch.log"),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
