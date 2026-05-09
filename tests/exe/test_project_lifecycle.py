"""Tests for exe/scripts/project-up.sh, project-down.sh, and cdr-project.

These three scripts implement refs/docs/issues/0020-multi-project-lifecycle-completion
軸 2 (workspace VM scripts) + 軸 3 (host-side cdr-project wrapper).

What is covered here (= partial / static):
    - bash syntax (= bash -n) for all three scripts.
    - shellcheck warnings = 0 for all three scripts.
    - id-validation regex matches the runops-gateway domain spec
      (`[a-zA-Z0-9_-]+`, max 64) — drift detection between the four
      copy-sync sites (project-up.sh, project-down.sh, cdr-project,
      and the gateway domain spec referenced in dotfiles ADR 0011).
    - cdr-project orchestration order, verified with stubs:
        - up: gateway `runops project create` → workspace `project-up.sh`
              (gateway-side failure aborts before workspace mutation).
        - down: workspace `project-down.sh` → gateway `runops project archive`
              (workspace-side failure aborts before gateway mutation).
    - cdr-project --hard requires explicit flag (= soft archive default).

What is NOT covered (= deferred to refs 0020-multi 軸 5):
    - full integration test (= 2 project full lifecycle on a real VM /
      container, with running phonewave + dmail-receiver / dmail-emitter
      and Pub/Sub end-to-end). Requires actual Coder workspace + GCP
      access, beyond the scope of static unit tests.
    - AI agent forbidden path (= dotfiles ADR 0013 bypass #3 mitigation,
      asserts that cdr-project rejects AI agent invocation). Requires
      the gateway-side approval-gate ADR + implementation, deferred to
      that follow-up PR.
"""

from __future__ import annotations

import re
import shutil
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "exe" / "scripts"
PROJECT_UP = SCRIPTS_DIR / "project-up.sh"
PROJECT_DOWN = SCRIPTS_DIR / "project-down.sh"
CDR_PROJECT = SCRIPTS_DIR / "cdr-project"

ALL_SCRIPTS = [PROJECT_UP, PROJECT_DOWN, CDR_PROJECT]

BASH = shutil.which("bash") or "/bin/bash"


# ---------------------------------------------------------------------------
# 1. bash syntax + shellcheck (= static checks, no execution side effects)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("script", ALL_SCRIPTS, ids=lambda p: p.name)
def test_bash_syntax_check(script: Path) -> None:
    """`bash -n` parses each script without syntax errors."""
    result = subprocess.run(
        [BASH, "-n", str(script)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )
    assert result.returncode == 0, f"bash -n failed for {script.name}: {result.stderr}"


@pytest.mark.parametrize("script", ALL_SCRIPTS, ids=lambda p: p.name)
def test_shellcheck_warnings_zero(script: Path) -> None:
    """`shellcheck` reports zero warnings on each script.

    The dotfiles convention is shellcheck-clean for all scripts under
    exe/scripts/ (see existing cdr / cdr-job / cdr-exec which are clean).
    Allowing warnings here would let drift accumulate.
    """
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck not installed locally")
    result = subprocess.run(
        ["shellcheck", str(script)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )
    assert result.returncode == 0, (
        f"shellcheck failed for {script.name}:\n{result.stdout}"
    )


# ---------------------------------------------------------------------------
# 2. id-validation regex drift (= cross-site canonical lock)
# ---------------------------------------------------------------------------

# runops-gateway internal/core/domain/project.go canonical spec:
#   regex: ^[a-zA-Z0-9_-]+$
#   max len: 64
EXPECTED_REGEX = "[a-zA-Z0-9_-]+"
EXPECTED_MAX_LEN = "64"


@pytest.mark.parametrize("script", ALL_SCRIPTS, ids=lambda p: p.name)
def test_project_id_validation_canonical(script: Path) -> None:
    """All three scripts use the same project_id regex + max-len constants
    as the runops-gateway domain spec (= drift detection)."""
    text = script.read_text()
    assert EXPECTED_REGEX in text, (
        f"{script.name}: missing canonical project_id regex {EXPECTED_REGEX!r}"
    )
    assert EXPECTED_MAX_LEN in text, (
        f"{script.name}: missing canonical max-len {EXPECTED_MAX_LEN!r}"
    )


# ---------------------------------------------------------------------------
# 3. cdr-project orchestration order (= stub-based control-flow test)
# ---------------------------------------------------------------------------


def _make_stub(stubs_dir: Path, name: str, body: str) -> Path:
    """Create an executable stub script under `stubs_dir` and return its
    path. `body` is the bash content (with optional dedent)."""
    p = stubs_dir / name
    p.write_text(textwrap.dedent(body).lstrip("\n"))
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


def _run_cdr_project(
    tmp_path: Path,
    args: list[str],
    cdr_exec_body: str,
    extra_env: dict[str, str] | None = None,
    stdin_input: str | None = None,
) -> tuple[subprocess.CompletedProcess, list[str]]:
    """Execute cdr-project with a stubbed cdr-exec.

    Returns (CompletedProcess, list of cdr-exec invocation lines logged
    via the stub to `tmp_path / cdr-exec.log`).

    Args:
        extra_env: Additional env vars (e.g. CDR_PROJECT_NO_TYPED_CONFIRM=1
            to skip typed confirmation in --hard tests).
        stdin_input: Text fed to cdr-project stdin (e.g. typed confirmation
            input). When None, no stdin is provided.
    """
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    log_file = tmp_path / "cdr-exec.log"
    _make_stub(stubs, "cdr-exec", cdr_exec_body.replace("__LOG__", str(log_file)))

    env = {
        "PATH": f"{stubs}:/usr/bin:/bin",
        "HOME": str(tmp_path),
    }
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        [BASH, str(CDR_PROJECT), *args],
        text=True,
        env=env,
        input=stdin_input,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )
    log_lines = log_file.read_text().splitlines() if log_file.exists() else []
    return result, log_lines


def test_cdr_project_up_invokes_gateway_create_then_workspace_script(
    tmp_path: Path,
) -> None:
    """`cdr-project up <id>` invokes:
    1. cdr-exec runner -- 'runops project create <id>'
    2. cdr-exec runner -- 'sudo bash /root/dotfiles/exe/scripts/project-up.sh <id>'
    """
    cdr_exec_body = """
        #!/usr/bin/env bash
        # log invocation: $@ joined by spaces, written one per line.
        printf '%s\\n' "$*" >> __LOG__
        exit 0
    """
    result, logs = _run_cdr_project(
        tmp_path,
        ["up", "demo-foo"],
        cdr_exec_body,
    )
    assert result.returncode == 0, (
        f"cdr-project up should succeed; stderr:\n{result.stderr}"
    )
    assert len(logs) == 2, f"expected 2 cdr-exec invocations, got {logs!r}"
    assert "project create" in logs[0], (
        f"first invocation should be gateway 'project create', got {logs[0]!r}"
    )
    assert "project-up.sh" in logs[1], (
        f"second invocation should be workspace project-up.sh, got {logs[1]!r}"
    )


def test_cdr_project_up_aborts_workspace_script_on_gateway_failure(
    tmp_path: Path,
) -> None:
    """`cdr-project up` does NOT execute the workspace VM script when
    the gateway-side `runops project create` step fails (= rollback-not-needed,
    at-least-once OK; refs 0020-multi 軸 3 受入基準)."""
    # Stub: fail the FIRST invocation (= gateway create), succeed any later.
    cdr_exec_body = """
        #!/usr/bin/env bash
        printf '%s\\n' "$*" >> __LOG__
        # Fail the gateway-create step (= first invocation containing 'project create').
        if printf '%s' "$*" | grep -q 'project create'; then
          exit 7
        fi
        exit 0
    """
    result, logs = _run_cdr_project(
        tmp_path,
        ["up", "demo-foo"],
        cdr_exec_body,
    )
    assert result.returncode != 0, (
        "cdr-project up should fail when gateway create fails"
    )
    assert len(logs) == 1, (
        f"only the gateway-create invocation should be logged, got {logs!r}"
    )
    assert "project create" in logs[0]


def test_cdr_project_down_invokes_workspace_script_then_gateway_archive(
    tmp_path: Path,
) -> None:
    """`cdr-project down <id>` (default = soft archive) invokes:
    1. cdr-exec runner -- 'sudo bash /root/dotfiles/exe/scripts/project-down.sh <id>'
    2. cdr-exec runner -- 'runops project archive <id>'
    """
    cdr_exec_body = """
        #!/usr/bin/env bash
        printf '%s\\n' "$*" >> __LOG__
        exit 0
    """
    result, logs = _run_cdr_project(
        tmp_path,
        ["down", "demo-foo"],
        cdr_exec_body,
    )
    assert result.returncode == 0, (
        f"cdr-project down should succeed; stderr:\n{result.stderr}"
    )
    assert len(logs) == 2
    assert "project-down.sh" in logs[0], (
        f"first invocation should be workspace project-down.sh, got {logs[0]!r}"
    )
    assert "project archive" in logs[1], (
        f"second invocation should be gateway 'project archive', got {logs[1]!r}"
    )
    # Default = soft, so 'project delete' should NOT appear.
    assert "project delete" not in logs[1]


def test_cdr_project_down_hard_invokes_gateway_delete(tmp_path: Path) -> None:
    """`cdr-project down <id> --hard` calls `runops project delete --hard`
    (= not `archive`).

    ADR 0013 Bypass #4 mitigation: hard-delete typed confirmation prompt
    is skipped here via env so the test exercises the underlying
    cdr-exec invocations rather than the prompt.
    """
    cdr_exec_body = """
        #!/usr/bin/env bash
        printf '%s\\n' "$*" >> __LOG__
        exit 0
    """
    result, logs = _run_cdr_project(
        tmp_path,
        ["down", "demo-foo", "--hard"],
        cdr_exec_body,
        extra_env={"CDR_PROJECT_NO_TYPED_CONFIRM": "1"},
    )
    assert result.returncode == 0
    assert len(logs) == 2
    # Workspace script invoked with --hard.
    assert "--hard" in logs[0]
    # Gateway invoked with delete --hard, NOT archive.
    assert "project delete" in logs[1]


def test_cdr_project_hard_requires_typed_confirmation(tmp_path: Path) -> None:
    """`cdr-project down <id> --hard` (no env hatch) prompts for typed
    project_id confirmation; matching input proceeds with the destructive
    chain.

    ADR 0013 Bypass #4 mitigation guard #2.
    """
    cdr_exec_body = """
        #!/usr/bin/env bash
        printf '%s\\n' "$*" >> __LOG__
        exit 0
    """
    # Provide the matching project_id on stdin (= operator typed it).
    result, logs = _run_cdr_project(
        tmp_path,
        ["down", "demo-foo", "--hard"],
        cdr_exec_body,
        stdin_input="demo-foo\n",
    )
    assert result.returncode == 0, (
        f"matching confirmation should proceed; stderr:\n{result.stderr}"
    )
    assert "confirmation matched" in result.stderr
    # Both cdr-exec invocations happened (= prompt did not abort the chain).
    assert len(logs) == 2


def test_cdr_project_hard_typed_mismatch_rejects(tmp_path: Path) -> None:
    """`cdr-project down <id> --hard` rejects when the typed confirmation
    does not exactly match the project id; no cdr-exec invocations occur.

    ADR 0013 Bypass #4 mitigation guard #2 (= reject path)."""
    cdr_exec_body = """
        #!/usr/bin/env bash
        printf '%s\\n' "$*" >> __LOG__
        exit 0
    """
    result, logs = _run_cdr_project(
        tmp_path,
        ["down", "demo-foo", "--hard"],
        cdr_exec_body,
        stdin_input="demo-bar\n",  # mismatch
    )
    assert result.returncode != 0, "mismatched confirmation must fail-loud, not proceed"
    assert "confirmation mismatch" in result.stderr
    # NO cdr-exec invocations should have happened.
    assert len(logs) == 0


def test_cdr_project_hard_dry_run_no_side_effect(tmp_path: Path) -> None:
    """`cdr-project down <id> --hard --dry-run` prints the planned
    invocations and exits 0 without touching cdr-exec or prompting.

    ADR 0013 Bypass #4 mitigation guard #3 (= dry-run preview).
    """
    cdr_exec_body = """
        #!/usr/bin/env bash
        printf '%s\\n' "$*" >> __LOG__
        exit 0
    """
    result, logs = _run_cdr_project(
        tmp_path,
        ["down", "demo-foo", "--hard", "--dry-run"],
        cdr_exec_body,
        # No stdin: dry-run path must not prompt.
    )
    assert result.returncode == 0
    # No cdr-exec invocations (= zero side effect).
    assert len(logs) == 0
    # DRY-RUN preview lines should appear on stderr (= log channel).
    assert "DRY-RUN" in result.stderr
    assert "project-down.sh" in result.stderr
    assert "project delete" in result.stderr  # --hard branch
    assert "--hard" in result.stderr


def test_cdr_project_down_aborts_gateway_on_workspace_failure(
    tmp_path: Path,
) -> None:
    """`cdr-project down` does NOT execute gateway archive/delete when
    the workspace-side `project-down.sh` step fails (= data-integrity-first,
    refs 0020-multi 軸 3 受入基準)."""
    cdr_exec_body = """
        #!/usr/bin/env bash
        printf '%s\\n' "$*" >> __LOG__
        if printf '%s' "$*" | grep -q 'project-down.sh'; then
          exit 9
        fi
        exit 0
    """
    result, logs = _run_cdr_project(
        tmp_path,
        ["down", "demo-foo"],
        cdr_exec_body,
    )
    assert result.returncode != 0
    assert len(logs) == 1
    assert "project-down.sh" in logs[0]
    # Gateway archive/delete must NOT have been invoked.
    for line in logs:
        assert "project archive" not in line
        assert "project delete" not in line


# ---------------------------------------------------------------------------
# 4. id-validation rejects bad input (= shellcheck-orthogonal runtime check)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_id",
    ["foo bar", "foo/bar", "foo;rm", "foo$(date)", "../escape", "a" * 65],
    ids=["space", "slash", "semicolon", "subshell", "traversal", "65chars"],
)
def test_project_up_rejects_invalid_id(tmp_path: Path, bad_id: str) -> None:
    """project-up.sh rejects ids violating the runops-gateway domain spec.

    Without this validation a hostile id could inject metacharacters into
    later mkdir / git clone / systemd Environment= lines.
    """
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "WORKSPACE_HOME": str(tmp_path),
    }
    result = subprocess.run(
        [BASH, str(PROJECT_UP), bad_id],
        text=True,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=5,
    )
    assert result.returncode != 0, (
        f"project-up.sh should reject {bad_id!r}, got rc=0; stderr:\n{result.stderr}"
    )
    # The script's err() prefixes messages with [project-up], so a graceful
    # rejection should produce stderr (not e.g. an unhandled bash trap).
    assert "[project-up]" in result.stderr or "regex" in result.stderr.lower()


# ---------------------------------------------------------------------------
# 5. unit literal: `project_id` regex string is identical across the three
#    scripts (= drift detection narrowed to the regex itself, not just any
#    "[a-zA-Z0-9_-]+" substring).
# ---------------------------------------------------------------------------


def test_project_id_regex_literal_is_byte_identical_across_scripts() -> None:
    """The exact `PROJECT_ID_RE='^[a-zA-Z0-9_-]+$'` literal must appear
    in all three scripts (= byte-identical canonical, drift detector)."""
    expected_literal = "PROJECT_ID_RE='^[a-zA-Z0-9_-]+$'"
    for script in ALL_SCRIPTS:
        text = script.read_text()
        # cdr-project declares the regex at module scope; the .sh files use
        # the same literal; we check exact occurrence in each.
        # (Allow either single-line declaration or multi-line; use re.search
        # to permit any leading whitespace.)
        assert re.search(re.escape(expected_literal), text), (
            f"{script.name} missing canonical literal {expected_literal!r}"
        )
