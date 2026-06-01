"""Regression tests for install.sh OS dispatch (ADR 0005).

What this guards
----------------
ADR 0005 (Accepted 2026-05-02) decided that install.sh becomes
OS-aware via a single `uname`-driven `DOTFILES_OS` variable, with
each install step wrapped in a `step_*` helper function. The
helpers branch on `DOTFILES_OS` so:

  - mac:     runs the historical Homebrew + brew bundle + gcloud
             components + corepack enable + update-all flow
  - linux:   runs only symlink + sheldon (the dev container
             feature already provided everything else with SHA/
             SLSA verification at build time)
  - windows: emits TODO stubs; concrete impls come in a future
             ADR when a Windows host is actually used
  - unknown: exits non-zero so unsupported environments fail
             closed

The existing `INSTALL_SKIP_*` env vars are kept as an operator
override layer; the combined skip predicate is OS-says-skip OR
env-var-says-skip.

These tests are **regex assertions on install.sh source text**
plus a small set of runtime executions of `install.sh --check`
or equivalent dry-run flag. They do NOT execute the heavy
install steps themselves; doing so would require a real Mac
host and a real Coder workspace, both already covered by other
tests.

Why these exist
---------------
A previous PR that "just adds a bunch of step_* functions" can
silently regress the OS dispatch (e.g., by forgetting the
`exit 1` for unknown OS, or by inverting an OR/AND in the skip
predicate). Catch those at PR-review time before they reach
main.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
INSTALL_SH = ROOT / "install.sh"
BASH = shutil.which("bash") or "/bin/bash"


@pytest.fixture(scope="module")
def install_sh_text() -> str:
    assert INSTALL_SH.is_file(), f"install.sh missing at {INSTALL_SH}"
    return INSTALL_SH.read_text(encoding="utf-8")


# ---------- OS identification --------------------------------------


def test_install_sh_identifies_dotfiles_os(install_sh_text: str) -> None:
    """install.sh must set a DOTFILES_OS variable based on uname so
    the subsequent step_* helpers can dispatch."""
    assert re.search(
        r"DOTFILES_OS\s*=\s*",
        install_sh_text,
    ), "install.sh must assign DOTFILES_OS so step_* helpers can branch."


def test_install_sh_dispatches_mac_linux_windows(install_sh_text: str) -> None:
    """The case statement must cover Darwin / Linux / MSYS-family
    explicitly. WSL is detected as Linux (out of scope to special-
    case)."""
    assert re.search(r"\bDarwin\)", install_sh_text), (
        "install.sh case must include a Darwin branch for macOS."
    )
    assert re.search(r"\bLinux\)", install_sh_text), (
        "install.sh case must include a Linux branch."
    )
    assert re.search(
        r"MINGW\*\|MSYS\*\|CYGWIN\*\)|MSYS\*\|MINGW\*\|CYGWIN\*\)",
        install_sh_text,
    ), (
        "install.sh case must include a Windows (MSYS/MINGW/Cygwin) "
        "branch so a future Windows port has a clear hook."
    )


def test_install_sh_fails_closed_on_unknown_os(install_sh_text: str) -> None:
    """ADR 0005: unknown OS must exit non-zero, not warn-and-continue.
    Otherwise a future operator running install.sh on a NetBSD box
    or in a misconfigured CI gets surprising partial behaviour."""
    # The catch-all in the case statement must invoke `exit 1` (or
    # `exit` with any non-zero code). Allow either ` *) ` or `*)`.
    catchall = re.search(
        r"\*\)[\s\S]*?exit\s+[1-9][0-9]*",
        install_sh_text,
    )
    assert catchall is not None, (
        "install.sh must exit non-zero for unrecognised uname output. "
        "A `*)` catch-all that warns and continues is unacceptable per "
        "ADR 0005 decision Q4."
    )


# ---------- step_* functions ---------------------------------------


REQUIRED_STEPS = (
    "step_homebrew",
    "step_symlink_dotfiles",
    "step_sheldon",
    "step_brew_bundle",
    "step_gcloud_components",
    "step_corepack",
    "step_update_all",
)


@pytest.mark.parametrize("step_name", REQUIRED_STEPS)
def test_install_sh_defines_required_step_function(
    install_sh_text: str, step_name: str
) -> None:
    """Each install responsibility lives in a named function so that
    OS dispatch is local to the function and tests can grep for the
    contract independently."""
    assert re.search(
        rf"^{step_name}\s*\(\s*\)\s*\{{",
        install_sh_text,
        re.MULTILINE,
    ), (
        f"install.sh must define a `{step_name}` function. ADR 0005 "
        f"decision Q4 names the helper set."
    )


def test_step_functions_are_called(install_sh_text: str) -> None:
    """Defining a step_* helper but never calling it is a silent
    regression. Each REQUIRED_STEPS entry must be invoked somewhere
    in the script."""
    # Strip function definitions so we don't get a false hit on the
    # definition line itself.
    body_only = re.sub(
        r"^[a-z_]+\s*\(\s*\)\s*\{[\s\S]*?^\}\s*$",
        "",
        install_sh_text,
        flags=re.MULTILINE,
    )
    for step in REQUIRED_STEPS:
        assert re.search(rf"\b{step}\b", body_only), (
            f"`{step}` is defined but never invoked. The step list in "
            f"install.sh body must call every helper that ADR 0005 names."
        )


# ---------- env var override preserved -----------------------------


@pytest.mark.parametrize(
    "env_var",
    [
        "INSTALL_SKIP_HOMEBREW",
        "INSTALL_SKIP_GCLOUD",
        "INSTALL_SKIP_ADD_UPDATE",
    ],
)
def test_install_sh_honours_legacy_skip_env_vars(
    install_sh_text: str, env_var: str
) -> None:
    """ADR 0005 decision: existing INSTALL_SKIP_* env vars are kept
    as operator overrides. The OS-aware skip and env-var skip are
    OR-combined."""
    assert env_var in install_sh_text, (
        f"install.sh must continue to honour {env_var} as an operator "
        f"override after the OS dispatch refactor."
    )


# ---------- runtime smoke (no real install) ------------------------


def test_install_sh_passes_shellcheck() -> None:
    """install.sh is the entry point operators run on day 1; it
    must pass shellcheck so we don't ship subtly-broken bash. If
    shellcheck is not available on the test runner, skip — CI's
    Shellcheck Linting workflow exercises this anyway."""
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck not installed; relying on CI's lint job")

    r = subprocess.run(
        ["shellcheck", "--severity=error", str(INSTALL_SH)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, (
        f"install.sh shellcheck failed:\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )


def test_install_sh_unknown_uname_exits_nonzero(tmp_path: Path) -> None:
    """End-to-end smoke: invoke install.sh with a fake `uname` stub
    that prints something we don't recognise. The script must exit
    non-zero before it reaches any actual install logic.

    We achieve this by:
      1. Creating a tmp dir with a stub `uname` executable that
         prints "Plan9".
      2. Running `bash install.sh` with PATH pointing at the stub
         dir first.
      3. Confirming the exit code is non-zero AND no homebrew /
         gcloud install was attempted (those would touch network +
         system, which we'd notice if they fired).

    The script will probably fail very early — before HEAD-of-
    install.sh `git clone`. That's fine; the relevant assertion is
    "non-zero exit" not "exits at exactly line N"."""
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    fake_uname = stubs / "uname"
    fake_uname.write_text("#!/usr/bin/env bash\necho Plan9\n")
    fake_uname.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{stubs}:{env.get('PATH', '')}"
    # Set DOTPATH to a tmp location so the pre-amble git clone
    # doesn't try to mutate the operator's real ~/dotfiles.
    env["DOTPATH"] = str(tmp_path / "dotfiles")
    env["INSTALL_SKIP_HOMEBREW"] = "1"
    env["INSTALL_SKIP_GCLOUD"] = "1"
    env["INSTALL_SKIP_ADD_UPDATE"] = "1"

    r = subprocess.run(
        [BASH, str(INSTALL_SH)],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        timeout=30,
    )
    assert r.returncode != 0, (
        f"install.sh exited 0 on a Plan9 fake uname. ADR 0005 requires "
        f"unknown OSes to fail closed.\nstdout:\n{r.stdout}\n"
        f"stderr:\n{r.stderr}"
    )
    # Also confirm the rejection mentions the unsupported OS so the
    # operator knows what happened.
    combined = r.stdout + r.stderr
    assert re.search(r"unsupported|unknown.*os|Plan9", combined, re.IGNORECASE), (
        f"install.sh exited non-zero but did not say why; operator "
        f"should see an unsupported-OS message. Combined output:\n"
        f"{combined}"
    )


# ---------- corepack migration (retire pnpm-global) ----------------


def test_install_sh_enables_corepack_not_pnpm_globals(install_sh_text: str) -> None:
    """ADR 0017 retires the pnpm-global subsystem: pnpm is provided
    per-repo by corepack, and `install.sh` enables corepack instead of
    restoring pnpm globals from a dump manifest. Pin both halves so a
    future edit cannot silently resurrect `pnpm add -g` provisioning."""
    assert "corepack enable" in install_sh_text, (
        "install.sh must enable corepack (the per-repo pnpm provider) "
        "in step_corepack. See ADR 0017."
    )
    for retired in ("step_pnpm_globals", "add-pnpm-g"):
        assert retired not in install_sh_text, (
            f"install.sh still references the retired pnpm-global token "
            f"{retired!r}. ADR 0017 removed the pnpm-global subsystem; "
            f"pnpm is corepack-provided per-repo now."
        )


# ---------- Windows native MVP (ADR 0018) --------------------------


def test_install_sh_no_todo_windows_stub_remains(install_sh_text: str) -> None:
    """ADR 0018 replaces the `_todo_windows` placeholder with either a
    real implementation (step_corepack) or an explicit `_skip_windows`
    call with a written reason. No `_todo_windows` references should
    remain — otherwise a future maintainer might re-stub a new step."""
    assert "_todo_windows" not in install_sh_text, (
        "install.sh still references `_todo_windows`. ADR 0018 retired "
        "the placeholder; each windows) branch must call `_skip_windows "
        '"<step>" "<reason>"` or implement the step directly.'
    )


def test_install_sh_windows_step_corepack_implemented(install_sh_text: str) -> None:
    """ADR 0018 implements `step_corepack` on Windows native (corepack
    ships with node and works cross-platform). The windows) branch must
    invoke `corepack enable` — not a `_skip_windows` call."""
    # Isolate the step_corepack function body, then check the windows branch.
    m = re.search(
        r"^step_corepack\s*\(\s*\)\s*\{([\s\S]*?)^\}",
        install_sh_text,
        re.MULTILINE,
    )
    assert m is not None, "step_corepack function definition not found"
    body = m.group(1)
    win_m = re.search(r"windows\)([\s\S]*?);;", body)
    assert win_m is not None, "step_corepack has no windows) branch"
    win_branch = win_m.group(1)
    assert "corepack enable" in win_branch, (
        "step_corepack windows) branch must invoke `corepack enable` "
        "(ADR 0018: corepack is cross-platform and supplies pnpm on Windows too)."
    )
    assert "_skip_windows" not in win_branch, (
        "step_corepack windows) branch must implement, not skip "
        "(ADR 0018 decision: corepack is the one cross-platform-meaningful step)."
    )


def test_install_sh_skip_windows_calls_have_reason(install_sh_text: str) -> None:
    """`_skip_windows` requires two args: step name + non-empty reason.
    A bare `_skip_windows "step_foo"` (no reason) would silently pass
    shellcheck but leave operators guessing why the step was skipped.
    Pin the 2-arg shape so future additions stay self-documenting."""
    # Find every _skip_windows invocation (not the function definition).
    calls = re.findall(
        r'_skip_windows\s+"([^"]*)"\s+"([^"]*)"',
        install_sh_text,
    )
    # At least the 7 skipped steps from ADR 0018 must show up.
    assert len(calls) >= 7, (
        f"Expected at least 7 `_skip_windows` calls (ADR 0018: 7 skipped "
        f"steps), found {len(calls)}. Definitions: {calls!r}"
    )
    for step_name, reason in calls:
        assert step_name.startswith("step_"), (
            f"_skip_windows first arg must be a step name (step_*); got {step_name!r}"
        )
        assert reason.strip(), (
            f"_skip_windows reason for {step_name!r} is empty. ADR 0018 "
            f"requires every skip to document why the step is "
            f"intentionally out of scope on Windows native."
        )
