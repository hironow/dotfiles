"""The Windows bootstrap one-liner must connect a bare machine to the
existing just chain without tripping the known Windows traps (ADR 0039).

Why this exists
---------------
Every failure mode below is *silent or late* — the script would appear to
work on an already-provisioned machine and only break on the bare machine
it exists for:

- **SSH before keys.** ``.gitmodules`` and origin use ``git@github.com:``
  URLs; a bare machine has no SSH keys, so any submodule step or SSH clone
  dies on authentication. Bootstrap must clone over HTTPS and leave
  submodules to the operator.
- **WSL bash shadowing.** ``C:\\Windows\\System32\\bash.exe`` (WSL) shadows
  Git Bash for a bare ``bash``; and a non-login Git Bash (``-c`` without
  ``-l``) lacks ``/usr/bin`` on PATH, so shebang recipes fail with
  "could not find cygpath". Bootstrap must resolve Git Bash explicitly and
  invoke it as a login shell (``-lc``).
- **Stale scoop just.** scoop's ``just`` can lag mise's; just <= 1.45
  resolves ``bash`` to WSL and older versions reject the repo's justfile
  attributes. Bootstrap must update and gate on a minimum version.
- **pwsh-7-only profile.** ``just deploy`` writes
  ``Documents/PowerShell/Microsoft.PowerShell_profile.ps1`` — the PowerShell
  7 path. Without ``pwsh`` in the base set the injected profile is dead
  config on a stock Windows 11 install.
- **Mojibake via irm|iex.** PowerShell 5.1 reads BOM-less UTF-8 as ANSI, so
  the script must stay ASCII-only to survive both ``irm | iex`` and
  ``-File`` execution.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / "bootstrap.ps1"

CHAIN = [
    "add-scoop",
    "deploy",
    "harden-env",
    "sync-agents",
    "restore-skills-lock",
    "doctor",
]


def _text() -> str:
    return BOOTSTRAP.read_text(encoding="ascii")


def _code() -> str:
    """The script minus full-line comments — assertions about what bootstrap
    *executes* must not trip on comments that explain why it doesn't."""
    lines = _text().splitlines()
    return "\n".join(ln for ln in lines if not ln.lstrip().startswith("#"))


def test_bootstrap_exists() -> None:
    assert BOOTSTRAP.is_file(), (
        "bootstrap.ps1 must exist at the repo root (ADR 0039: the Windows "
        "one-liner entrypoint)."
    )


def test_ascii_only() -> None:
    raw = BOOTSTRAP.read_bytes()
    assert all(b < 128 for b in raw), (
        "bootstrap.ps1 must be ASCII-only: PowerShell 5.1 reads BOM-less "
        "UTF-8 as ANSI, and irm|iex decodes without a charset — non-ASCII "
        "turns into mojibake on the exact machines bootstrap targets."
    )


def test_runs_full_chain_in_order() -> None:
    text = _text()
    positions = []
    for recipe in CHAIN:
        match = re.search(rf"Invoke-Just\s+[\"']{re.escape(recipe)}\b", text)
        assert match, (
            f"bootstrap.ps1 must run 'just {recipe}' via Invoke-Just (the "
            "wrapper that enforces the login-shell Git Bash invocation)."
        )
        positions.append(match.start())
    assert positions == sorted(positions), (
        "bootstrap.ps1 must run the chain in dependency order: " + " -> ".join(CHAIN)
    )


def test_clones_over_https_never_ssh() -> None:
    text = _text()
    assert "https://github.com/hironow/dotfiles" in text, (
        "bootstrap.ps1 must clone over HTTPS — a bare machine has no SSH "
        "keys, and origin/.gitmodules default to git@github.com URLs."
    )
    assert "git@github.com" not in _code(), (
        "bootstrap.ps1 must not use SSH URLs in executable code; switching "
        "the remote to SSH is a documented operator step, not a bootstrap "
        "step."
    )


def test_no_submodule_update() -> None:
    assert "submodule" not in _code().lower(), (
        "bootstrap.ps1 must not touch submodules: all but one use SSH URLs "
        "(auth-fails on a bare machine) and none of the chained recipes "
        "need them."
    )


def test_invokes_git_bash_as_login_shell() -> None:
    text = _text()
    assert re.search(r"bash\.exe", text), (
        "bootstrap.ps1 must resolve an explicit ...\\bin\\bash.exe — a bare "
        "'bash' resolves to System32's WSL bash ahead of Git Bash."
    )
    assert "-lc" in text, (
        "bootstrap.ps1 must invoke Git Bash as a login shell (-lc): "
        "non-login shells lack /usr/bin (cygpath) on PATH and every shebang "
        "recipe (deploy, add-scoop) fails."
    )


def test_resolves_git_bash_via_scoop_prefix() -> None:
    assert "scoop prefix git" in _text(), (
        "bootstrap.ps1 must resolve Git Bash via 'scoop prefix git' — the "
        "scoop shim's parent directory has no bin\\bash.exe, so deriving "
        "from Get-Command git yields a nonexistent path."
    )


def test_gates_on_minimum_just_version() -> None:
    text = _text()
    assert "scoop update just" in text, (
        "bootstrap.ps1 must 'scoop update just': a stale scoop just "
        "resolves bash to WSL (<=1.45) and rejects the justfile's "
        "attributes."
    )
    assert re.search(r"1\.51", text), (
        "bootstrap.ps1 must gate on just >= 1.51 before running the chain."
    )


def test_base_tool_set_membership() -> None:
    code = _code()
    match = re.search(r"\$baseTools\s*=\s*@\(([^)]*)\)", code)
    assert match, "bootstrap.ps1 must declare its base tool set as $baseTools."
    tools = set(re.findall(r"'([^']+)'", match.group(1)))
    assert {"git", "just", "jq", "mise", "pwsh"} <= tools, (
        "base set must cover git/just/jq (chain floor), mise (deploy's "
        "toolset + every UV_RUN recipe), and pwsh (deploy writes the "
        "PowerShell 7 profile path — dead config without it). "
        f"Found: {sorted(tools)}"
    )
    assert "scoop install" in code, (
        "bootstrap.ps1 must install missing base tools via scoop."
    )


def test_installs_only_missing_tools() -> None:
    assert re.search(r"Get-Command\s+\$_", _code()), (
        "bootstrap.ps1 must filter the base set to tools missing from PATH: "
        "an unconditional scoop install adds a second copy next to an "
        "existing Program Files git/pwsh and lets scoop shims shadow it."
    )


def test_handles_execution_policy() -> None:
    assert "ExecutionPolicy" in _text(), (
        "bootstrap.ps1 must check/set the CurrentUser execution policy: "
        "scoop's installer aborts under the default Restricted policy."
    )


def test_refreshes_path_after_scoop() -> None:
    text = _text()
    assert re.search(r"GetEnvironmentVariable\(\s*['\"]Path['\"]", text), (
        "bootstrap.ps1 must re-read Machine+User PATH after scoop installs: "
        "the current process PATH does not pick up new shims on its own."
    )
    assert re.search(r'\$env:Path\s*=\s*"\$env:Path;', text), (
        "the registry PATH must be APPENDED to the process PATH, not "
        "replace it: the inherited PATH can hold entries the registry "
        "lacks (seen live: git resolved only via the parent shell)."
    )
    assert "ExpandEnvironmentVariables" in text, (
        "the rebuilt PATH must be expanded: Machine PATH is REG_EXPAND_SZ "
        "and GetEnvironmentVariable returns %SystemRoot% entries unexpanded, "
        "silently dropping System32 (powershell.exe) — doctor's win-cygpath "
        "check then dies with 'command not found'."
    )


def test_scoop_mutations_run_out_of_process() -> None:
    code = _code()
    for cmd in ("scoop install", "scoop update"):
        for line in code.splitlines():
            if cmd in line:
                assert "cmd /c" in line, (
                    f"'{cmd}' must run via cmd /c: a bare scoop runs "
                    "shims\\scoop.ps1 in-process, and a crash inside "
                    "scoop's own scripts (seen live mid-update) terminates "
                    "bootstrap under ErrorActionPreference=Stop, leaving "
                    "the app shim-less."
                )


def test_scoop_prefix_trusts_exit_code() -> None:
    assert re.search(r"scoop prefix git[\s\S]{0,200}LASTEXITCODE", _code()), (
        "bootstrap.ps1 must gate 'scoop prefix git' on $LASTEXITCODE: scoop "
        "prints its 'Could not find app path' error to stdout, so the "
        "captured string would otherwise be fed to Join-Path as a prefix."
    )


def test_guards_existing_clone_identity() -> None:
    text = _text()
    assert re.search(r"remote\s+get-url\s+origin", text), (
        "bootstrap.ps1 must verify an existing ~/dotfiles points at "
        "hironow/dotfiles before deploying from it — the justfile "
        "hardcodes ~/dotfiles paths."
    )


def test_reads_dotfiles_host_env() -> None:
    assert "DOTFILES_HOST" in _text(), (
        "bootstrap.ps1 must honor DOTFILES_HOST (dump_host.sh's primary "
        "interface): irm|iex cannot bind parameters, so the env var is the "
        "one-liner's only way to pick a scoop manifest host."
    )


def test_never_invokes_forbidden_package_managers() -> None:
    text = _text()
    for tool in ("npm", "yarn", "pnpm"):
        assert not re.search(rf"\b{tool}\b", text), (
            f"bootstrap.ps1 must not invoke {tool}: Node is bun-only and "
            "global CLIs come from mise (ADR 0027/0036)."
        )


def test_parses_as_valid_powershell() -> None:
    import shutil
    import subprocess

    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if pwsh is None:
        import pytest

        pytest.skip("no PowerShell available to parse-check bootstrap.ps1")
    check = (
        "$t=$null;$e=$null;"
        "[System.Management.Automation.Language.Parser]::ParseFile("
        f"'{BOOTSTRAP}',[ref]$t,[ref]$e)|Out-Null;"
        "if($e.Count -gt 0){$e|ForEach-Object{$_.ToString()};exit 1}"
    )
    proc = subprocess.run(
        [pwsh, "-NoProfile", "-Command", check],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        "bootstrap.ps1 has PowerShell syntax errors:\n" + proc.stdout
    )
