"""`set windows-shell` must force /usr/bin-first PATH inside plain recipes.

Why this guard exists
---------------------
The #231 assumption "`sh` resolves to Git Bash's sh, and the inner `bash`
then inherits Git Bash's /usr/bin-first PATH" is false for a fresh
PowerShell: Git's raw `usr\\bin\\sh.exe` is a NON-login msys sh, which
preserves the caller's PATH order verbatim (it only path-converts entries,
it does not prepend /usr/bin). A fresh persisted PATH puts
C:\\Windows\\System32 (Machine) before Git usr\\bin (User), so the recipe
body's bare `bash` resolved to System32's WSL bash.exe and the whole recipe
ran inside the WSL default distro — `just doctor` reported Ubuntu's apt
just 1.21.0 ("Unknown attribute `group`"), missing uv/mise, linux-gnu bash
(reproduced live 2026-08-16).

The fix keeps `sh` as the entrypoint but makes the outer sh prepend
/usr/bin (msys-self-relative, so it never hardcodes the Git install
location) and exec an inner `/usr/bin/sh` that runs the recipe body with
the normal `-c` contract ($0 is the shell, not the recipe text). This is a
scoped prepend inside the recipe shell only — NOT the blanket PowerShell
PATH prepend that CLAUDE.md advises against.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = ROOT / "justfile"

WINDOWS_SH = Path("C:/Program Files/Git/usr/bin/sh.exe")


def _windows_shell_argv() -> list[str]:
    """Parse the `set windows-shell := [...]` array from the justfile."""
    text = JUSTFILE.read_text(encoding="utf-8")
    m = re.search(r"^set windows-shell := \[(.+)\]\s*$", text, flags=re.M)
    assert m, "justfile must have a single-line `set windows-shell := [...]`"
    # just string literals: '...' is raw, "..." is escaped; neither kind is
    # nested inside the other in this line, so a simple alternation works.
    parts = re.findall(r"'([^']*)'|\"([^\"]*)\"", m.group(1))
    argv = [raw or cooked for raw, cooked in parts]
    assert argv, "could not parse windows-shell array elements"
    return argv


def test_windows_shell_prepends_usr_bin_and_execs_inner_sh() -> None:
    argv = _windows_shell_argv()
    assert argv[0] == "sh", "entrypoint must stay `sh` (not in System32)"
    assert argv[-2] == "-c", "recipe text must be handed to a -c command"
    prelude = argv[-1]
    assert 'PATH="/usr/bin:$PATH"' in prelude, (
        "outer sh must prepend /usr/bin so bash/find/sort/env resolve to Git "
        "Bash's, not System32/WSL, from a fresh persisted PATH"
    )
    assert re.search(r'exec /usr/bin/sh .*-c "\$0"', prelude), (
        "recipe text must run in an inner /usr/bin/sh with the normal -c "
        "contract ($0 = shell, positional args empty)"
    )
    for flag in ("-eu", "pipefail"):
        assert flag in prelude, f"inner sh must keep {flag} semantics"


def _host_bash() -> str:
    """Absolute path to a real bash — NEVER a bare "bash".

    CreateProcess searches System32 before PATH, so a bare "bash" from a
    native parent (python here, just.exe in production) resolves to WSL's
    C:\\Windows\\System32\\bash.exe — the very shadowing this guard exists
    for (WSL's launcher also drops args after the -c string).
    """
    if sys.platform == "win32":
        bash = WINDOWS_SH.with_name("bash.exe")
        if not bash.exists():
            pytest.skip("Git for Windows bash.exe not found")
        return str(bash)
    import shutil

    return shutil.which("bash") or "/usr/bin/bash"


def _run_mechanism(recipe: str) -> subprocess.CompletedProcess[str]:
    """Run the windows-shell argv against a recipe body, portably.

    On non-Windows hosts /usr/bin/sh is dash (no pipefail) and there is no
    msys sh, so the interpreter is substituted with bash; the *mechanism*
    (prelude + inner -c "$0" contract) is what is under test.
    """
    bash = _host_bash()
    argv = _windows_shell_argv()
    argv[-1] = argv[-1].replace("exec /usr/bin/sh", f'exec "{bash}"')
    argv[0] = bash
    return subprocess.run([*argv, recipe], capture_output=True, text=True, check=False)


def test_mechanism_recipe_sees_usr_bin_first_path() -> None:
    res = _run_mechanism('printf %s "$PATH"')
    assert res.returncode == 0, res.stderr
    assert res.stdout.startswith("/usr/bin:")


def test_mechanism_keeps_dash_c_contract() -> None:
    res = _run_mechanism('printf "%s|%s" "$0" "$#"')
    assert res.returncode == 0, res.stderr
    zero, argc = res.stdout.rsplit("|", 1)
    assert "printf" not in zero, "$0 must be the shell, not the recipe text"
    assert argc == "0"


def test_mechanism_keeps_errexit_and_pipefail() -> None:
    assert _run_mechanism("false; echo reached").returncode != 0
    assert _run_mechanism("false | true").returncode != 0


@pytest.mark.skipif(
    sys.platform != "win32" or not WINDOWS_SH.exists(),
    reason="needs Git for Windows' raw usr/bin sh.exe",
)
def test_real_msys_sh_resolves_git_bash_from_system32_first_path() -> None:
    """The live regression: System32-first PATH must NOT reach WSL bash."""
    argv = _windows_shell_argv()
    argv[0] = str(WINDOWS_SH)
    res = subprocess.run(
        [*argv, "command -v bash && bash -c 'echo $OSTYPE'"],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": r"C:\Windows\System32", "SYSTEMROOT": r"C:\Windows"},
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.splitlines()[0] == "/usr/bin/bash"
    assert "msys" in res.stdout.splitlines()[1]
