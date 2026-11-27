"""`scripts/harden_env.sh` must be portable (GNU sed / Linux+WSL),
idempotent, and must not touch the tracked shell rc.

Why this exists
---------------
`harden_env.sh` writes the machine-local supply-chain guards (npm
`min-release-age`, uv `~/.config/uv/uv.toml` with
`exclude-newer = "7 days"`). It was macOS-flavoured and broke on WSL:

- `sed -i ''` is BSD syntax; on GNU sed the empty `''` becomes the
  script and the next arg is misread as a filename, so the de-dup
  cleanup errors out (`set -u`, not `-e`, so it limps on) and re-runs
  APPEND duplicates instead of replacing.
- It appended a `PIP_INDEX_URL` / `alias pip` block to `~/.zshrc`,
  which `just deploy` symlinks to the tracked repo `.zshrc` — so the
  append dirtied a committed file. That block already lives in the
  tracked `.zshrc`, so the script must not write it at all.

Host-side, no Docker (part of `tests/unit/`), so it honours WSL-only.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
from _bash_hook import resolve_bash

ROOT = Path(__file__).resolve().parents[2]
HARDEN = ROOT / "scripts" / "harden_env.sh"
# Not `shutil.which("bash")`: on Windows that is the WSL launcher, which runs
# the script inside the distro where the host toolchain is absent.
BASH = resolve_bash()


def _env(home: Path, **extra: str) -> dict[str, str]:
    """The deliberately restricted environment the script runs under.

    ``TMPDIR`` is not decoration: the script calls ``mktemp``, and MSYS bash
    started from a *native-Windows* process has no writable ``/tmp`` unless it
    is told where one is (``mktemp: ... Permission denied``). On Linux ``/tmp``
    always exists, which is why leaving it out was invisible there.
    """
    tmp = home.parent / "tmp"
    tmp.mkdir(exist_ok=True)
    return {"HOME": str(home), "PATH": "/usr/bin:/bin", "TMPDIR": str(tmp), **extra}


def _run_harden(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    # Explicit utf-8: the script's output is utf-8, while `text=True` alone
    # decodes with the locale codec (cp932 on a Japanese Windows) and throws.
    return subprocess.run(
        [BASH, str(HARDEN)],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_writes_uv_toml_and_is_idempotent(tmp_path: Path) -> None:
    """Running the script (twice) writes a correct `~/.config/uv/uv.toml`,
    keeps `~/.npmrc` de-duplicated, and never writes a shell-rc block."""
    home = tmp_path / "home"
    home.mkdir()
    env = _env(home)
    for _ in range(2):  # idempotency: second run must not duplicate
        r = _run_harden(env)
        assert r.returncode == 0, f"harden_env.sh failed:\n{r.stderr}"

    uv_toml = home / ".config" / "uv" / "uv.toml"
    assert uv_toml.is_file(), "did not write ~/.config/uv/uv.toml"
    uv_content = uv_toml.read_text(encoding="utf-8")
    assert 'exclude-newer = "7 days"' in uv_content
    assert "flatt" not in uv_content, "uv must resolve from pypi.org, not a mirror"
    assert "[[index]]" not in uv_content

    npmrc = home / ".npmrc"
    assert npmrc.is_file(), "did not write ~/.npmrc"
    assert (
        npmrc.read_text(encoding="utf-8").splitlines().count("min-release-age=7") == 1
    ), (
        "min-release-age duplicated across runs — not idempotent (GNU sed cleanup broke)."
    )

    for rc in (".zshrc", ".bashrc"):
        p = home / rc
        if p.exists():
            body = p.read_text(encoding="utf-8")
            assert "Security Hardening" not in body and "PIP_INDEX_URL" not in body, (
                f"harden_env.sh wrote a hardening block into {rc}; it must not touch shell rc."
            )


def test_pi_packages_install_outside_the_release_age(tmp_path: Path) -> None:
    # Pi runs `npm install <pkg> --prefix <agent>/npm`; that prefix's project
    # .npmrc lifts the quarantine for every Pi package and its dependencies (a
    # name exclusion in ~/.npmrc left pi-web-access behind on a fresh undici)
    home = tmp_path / "home"
    home.mkdir()
    for _ in range(2):
        result = _run_harden(_env(home))
        assert result.returncode == 0, result.stderr
    pi_npmrc = home / ".pi" / "agent" / "npm" / ".npmrc"
    assert pi_npmrc.read_text(encoding="utf-8").splitlines() == ["min-release-age=0"]
    lines = (home / ".npmrc").read_text(encoding="utf-8").splitlines()
    assert not [line for line in lines if line.startswith("min-release-age-exclude")]
    assert lines.count("min-release-age=7") == 1


def test_pi_npmrc_follows_pi_coding_agent_dir(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    agent = tmp_path / "pi-agent"
    result = _run_harden(_env(home, PI_CODING_AGENT_DIR=str(agent)))
    assert result.returncode == 0, result.stderr
    assert (agent / "npm" / ".npmrc").read_text(
        encoding="utf-8"
    ) == "min-release-age=0\n"
    assert not (home / ".pi").exists()


def test_pi_npmrc_keeps_other_settings(tmp_path: Path) -> None:
    home = tmp_path / "home"
    pi_npm = home / ".pi" / "agent" / "npm"
    pi_npm.mkdir(parents=True)
    (pi_npm / ".npmrc").write_text("fund=false\nmin-release-age=7\n", encoding="utf-8")
    result = _run_harden(_env(home))
    assert result.returncode == 0, result.stderr
    assert (pi_npm / ".npmrc").read_text(
        encoding="utf-8"
    ) == "fund=false\nmin-release-age=0\n"


def test_preserves_user_npm_settings_and_exclusions(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    npmrc = home / ".npmrc"
    preserved = (
        "registry=https://registry.npmjs.org/\nmin-release-age-exclude[]=@internal/*\n"
    )
    npmrc.write_text(
        preserved
        + "min-release-age=2\nmin-release-age=3\n"
        + "min-release-age-exclude[]=pi-subagents\n" * 2,
        encoding="utf-8",
    )
    for _ in range(2):
        result = _run_harden(_env(home))
        assert result.returncode == 0, result.stderr
    content = npmrc.read_text(encoding="utf-8")
    assert content.startswith(preserved)
    lines = content.splitlines()
    # The named Pi exclusions earlier runs wrote are retired
    assert lines.count("min-release-age-exclude[]=pi-subagents") == 0
    assert [line for line in lines if line.startswith("min-release-age=")] == [
        "min-release-age=7"
    ]


def test_mirrors_uv_toml_to_windows_appdata(tmp_path: Path) -> None:
    """Native Windows uv reads %APPDATA%\\uv\\uv.toml, NOT ~/.config/uv/uv.toml,
    so on hosts where APPDATA is set the script must mirror the uv config
    there. Without it the quarantine never applies on native Windows and any
    `uv run` rewrites committed uv.locks (observed: the pre-commit `just lint`
    churned the root uv.lock, blocking every commit)."""
    home = tmp_path / "home"
    home.mkdir()
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    # HARDEN_ENV_SKIP_WIN_PATH: a fake APPDATA triggers the Windows PATH
    # section too, which would write the REAL registry from a test.
    r = _run_harden(_env(home, APPDATA=str(appdata), HARDEN_ENV_SKIP_WIN_PATH="1"))
    assert r.returncode == 0, f"harden_env.sh failed:\n{r.stderr}"
    win_toml = appdata / "uv" / "uv.toml"
    assert win_toml.is_file(), "did not mirror uv.toml to %APPDATA%/uv/"
    xdg_toml = home / ".config" / "uv" / "uv.toml"
    assert win_toml.read_text(encoding="utf-8") == xdg_toml.read_text(
        encoding="utf-8"
    ), "%APPDATA%/uv/uv.toml must be an exact mirror of ~/.config/uv/uv.toml"


def test_removes_only_the_flatt_npm_registry(tmp_path: Path) -> None:
    """Machines set `registry=https://npm.flatt.tech/` by hand; the script
    retires exactly that line and keeps every other registry and auth line."""
    home = tmp_path / "home"
    home.mkdir()
    npmrc = home / ".npmrc"
    kept = [
        "@internal:registry=https://npm.example.com/",
        "//registry.npmjs.org/:_authToken=${NPM_TOKEN}",
    ]
    npmrc.write_text(
        "registry=https://npm.flatt.tech/\r\n"
        + "\n".join(kept)
        + "\n  registry = https://npm.flatt.tech  \n",
        encoding="utf-8",
    )
    for _ in range(2):
        result = _run_harden(_env(home))
        assert result.returncode == 0, result.stderr
    lines = npmrc.read_text(encoding="utf-8").splitlines()
    assert [line for line in lines if "flatt" in line] == []
    assert lines == [*kept, "min-release-age=7"]


def test_keeps_a_non_flatt_npm_registry(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    npmrc = home / ".npmrc"
    npmrc.write_text("registry=https://registry.npmjs.org/\n", encoding="utf-8")
    result = _run_harden(_env(home))
    assert result.returncode == 0, result.stderr
    assert npmrc.read_text(encoding="utf-8").splitlines() == [
        "registry=https://registry.npmjs.org/",
        "min-release-age=7",
    ]


# ADR-0093 D4: on native Windows harden-env writes the user's persisted
# environment. Its guards (the User scope only, never the Machine scope,
# which needs elevation; the agent tools' telemetry off) are held by a run
# with a fake cygpath and a fake powershell.exe that records each command.
TELEMETRY_OFF = {
    "RTK_TELEMETRY_DISABLED": "1",
    "HEADROOM_BEACON": "off",
    "DO_NOT_TRACK": "1",
}
FAKE_POWERSHELL = """#!/bin/sh
for a in "$@"; do last="$a"; done
printf 'CMD %s\\n' "$last" >> "$FIXTURE_PS_LOG"
[ -z "${HARDEN_ENV_DIR:-}" ] || printf 'DIR %s\\n' "$HARDEN_ENV_DIR" >> "$FIXTURE_PS_LOG"
case "$last" in
  *"GetEnvironmentVariable('Path','User') + "*) printf '%s\\r\\n' 'C:\\Windows;C:\\Program Files\\Git\\usr\\bin' ;;
esac
"""
FAKE_CYGPATH = """#!/bin/sh
case "$1 $2" in
  "-w /usr/bin") printf '%s\\n' 'C:\\Program Files\\Git\\usr\\bin' ;;
  "-w /cmd") printf '%s\\n' 'C:\\Program Files\\Git\\cmd' ;;
  *) printf '%s\\n' "$2" ;;
esac
"""


def run_windows_harden(tmp_path: Path, script: Path) -> list[str]:
    """Run harden_env.sh as on native Windows; return what reached
    powershell.exe (CMD lines) and the directories passed to it (DIR)."""
    home = tmp_path / "home"
    home.mkdir()
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    fake = tmp_path / "fake-bin"
    fake.mkdir()
    for name, body in {
        "powershell.exe": FAKE_POWERSHELL,
        "cygpath": FAKE_CYGPATH,
        "uv": "#!/bin/sh\nexit 1\n",
    }.items():
        (fake / name).write_text(body, encoding="utf-8", newline="\n")
        (fake / name).chmod(0o755)
    log = tmp_path / "powershell.log"
    log.touch()
    env = _env(home, APPDATA=str(appdata), FIXTURE_PS_LOG=str(log))
    env["PATH"] = f"{fake}:{env['PATH']}"
    done = subprocess.run(
        [BASH, str(script)],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    return log.read_text(encoding="utf-8").splitlines()


def check_windows_harden_writes_the_user_scope_only(
    tmp_path: Path, script: Path
) -> None:
    calls = run_windows_harden(tmp_path, script)
    commands = [c.removeprefix("CMD ") for c in calls if c.startswith("CMD ")]
    assert commands, "harden-env reached no powershell.exe"
    for command in commands:
        # Reading the Machine PATH is fine; any other mention is a write.
        writes = re.sub(r"GetEnvironmentVariable\([^()]*\)", "", command)
        assert "'Machine'" not in writes, command
    for name, value in TELEMETRY_OFF.items():
        wanted = f"SetEnvironmentVariable('{name}', '{value}', 'User')"
        assert any(wanted in c for c in commands), (
            f"{name}={value} is not persisted: {commands}"
        )
    path_writes = [c for c in commands if "SetEnvironmentVariable('Path'" in c]
    assert path_writes and all(c.endswith(", 'User')") for c in path_writes), (
        path_writes
    )
    # Git's usr\bin is on the persisted PATH already; only cmd is appended.
    assert [c for c in calls if c.startswith("DIR ")] == [
        "DIR C:\\Program Files\\Git\\cmd"
    ], calls


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="the fakes must win over the real powershell.exe; there a miss would write the real registry",
)
def test_windows_harden_writes_the_user_scope_only(tmp_path: Path) -> None:
    check_windows_harden_writes_the_user_scope_only(tmp_path, HARDEN)
