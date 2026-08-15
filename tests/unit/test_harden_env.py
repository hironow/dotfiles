"""`scripts/harden_env.sh` must be portable (GNU sed / Linux+WSL),
idempotent, and must not touch the tracked shell rc.

Why this exists
---------------
`harden_env.sh` writes the machine-local supply-chain guards (npm
`min-release-age`, uv `~/.config/uv/uv.toml` with the flatt mirror +
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
from pathlib import Path

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


def test_no_bsd_sed_in_place() -> None:
    """`sed -i ''` (BSD) misparses on GNU sed — must not appear."""
    text = HARDEN.read_text(encoding="utf-8")
    assert not re.search(r"sed\s+-i\s+''", text), (
        "harden_env.sh uses BSD `sed -i ''` which breaks on GNU/Linux sed. "
        "Use a portable, sed-i-free rewrite."
    )


def test_does_not_write_shell_rc() -> None:
    """The flatt `PIP_INDEX_URL` / `alias pip` block is already committed in
    the tracked `.zshrc`; the script must not append it (it would dirty the
    symlinked repo file and duplicate on re-run)."""
    text = HARDEN.read_text(encoding="utf-8")
    assert "PIP_INDEX_URL" not in text, (
        "harden_env.sh writes PIP_INDEX_URL into a shell rc; that block is "
        "already tracked in .zshrc and the append dirties the symlinked repo file."
    )
    assert "Security Hardening" not in text, (
        "harden_env.sh appends a '# Security Hardening' block to the shell rc; "
        "remove it — the block is already in the tracked .zshrc."
    )


def test_justfile_wires_harden_env() -> None:
    """The script must be reachable as a `just` recipe (it was manual-only)."""
    just_text = (ROOT / "justfile").read_text(encoding="utf-8")
    assert re.search(r"^harden-env:", just_text, re.MULTILINE), (
        "justfile must define a `harden-env` recipe so the machine-local "
        "hardening is a discoverable one-liner, not a hand-run script."
    )
    assert "scripts/harden_env.sh" in just_text, (
        "the `harden-env` recipe must invoke scripts/harden_env.sh."
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
    assert "pypi.flatt.tech" in uv_content

    npmrc = home / ".npmrc"
    assert npmrc.is_file(), "did not write ~/.npmrc"
    assert npmrc.read_text(encoding="utf-8").count("min-release-age") == 1, (
        "min-release-age duplicated across runs — not idempotent (GNU sed cleanup broke)."
    )

    for rc in (".zshrc", ".bashrc"):
        p = home / rc
        if p.exists():
            body = p.read_text(encoding="utf-8")
            assert "Security Hardening" not in body and "PIP_INDEX_URL" not in body, (
                f"harden_env.sh wrote a hardening block into {rc}; it must not touch shell rc."
            )


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


def _script_text() -> str:
    return HARDEN.read_text(encoding="utf-8")


def test_appends_missing_git_dirs_to_windows_user_path() -> None:
    # Fresh PowerShell sessions see only the persisted (registry) PATH. A
    # stock setup can leave BOTH Git dirs off it: usr\bin (cygpath — every
    # just shebang recipe dies) and cmd (git.exe itself — fresh sessions
    # have no git at all; seen live). harden-env must append whichever is
    # missing to the persisted User PATH (end position — shadows nothing),
    # idempotently, so the bootstrap chain self-heals new machines.
    text = _script_text()
    assert re.search(r"for \_unix_dir in /usr/bin /cmd", text), (
        "must cover BOTH Git dirs (/usr/bin and /cmd), each derived via "
        "cygpath (install-location independent), not hardcode Program Files"
    )
    assert 'cygpath -w "$_unix_dir"' in text, (
        "must derive the Windows path via cygpath, not hardcode it"
    )
    assert "GetEnvironmentVariable" in text, (
        "must read the persisted User+Machine PATH from the registry — the "
        "in-process PATH always has both dirs under Git Bash, so it is "
        "useless as a signal"
    )
    assert re.search(r"SetEnvironmentVariable[^\n]*'User'", text), (
        "must persist the append via SetEnvironmentVariable on the User "
        "scope (no admin needed)"
    )
    assert "'Machine')\"" not in text.replace(
        "GetEnvironmentVariable('Path','Machine')", ""
    ), (
        "must NEVER write the Machine scope — that needs elevation and "
        "human review; doctor only detects and advises there"
    )
    assert "HARDEN_ENV_SKIP_WIN_PATH" in text, (
        "tests exercise the uv mirror with a fake APPDATA; without the "
        "skip flag they would write the real registry"
    )
    assert re.search(r"APPDATA", text), (
        "the PATH section must be gated to native Windows (APPDATA "
        "presence, like the uv mirror section) so Linux/macOS/WSL skip it"
    )


def test_powershell_fallback_when_system32_off_path() -> None:
    # The section repairs broken persisted PATHs — the very situation where
    # the current session may lack System32 (seen live: EMPTY Machine PATH),
    # so a bare `powershell.exe` invocation would die with command-not-found
    # exactly when the repair is needed most.
    text = _script_text()
    assert "WindowsPowerShell/v1.0/powershell.exe" in text, (
        "must fall back to powershell.exe by absolute path (via SYSTEMROOT) "
        "when it is not on PATH"
    )
