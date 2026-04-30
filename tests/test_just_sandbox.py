import subprocess
import textwrap
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "tests" / "docker" / "JustSandbox.Dockerfile"
IMAGE = "dotfiles-just-sandbox:latest"


def _run(
    cmd: list[str] | str, cwd: Path | None = None, env: dict | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        shell=isinstance(cmd, str),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _docker_available() -> bool:
    r = _run(["docker", "info"])
    return r.returncode == 0


@pytest.fixture(scope="session")
def docker_image():
    # given: docker daemon and base image availability
    if not _docker_available():
        pytest.skip("Docker is not available on host; skipping sandbox tests.")

    if not DOCKERFILE.exists():
        pytest.skip("Sandbox Dockerfile missing; skipping.")

    # when: build sandbox image using local workspace as build context
    build_cmd = [
        "docker",
        "build",
        "-t",
        IMAGE,
        "-f",
        str(DOCKERFILE),
        "--build-arg",
        "BASE_IMAGE=alpine:3.19",
        ".",
    ]
    result = _run(build_cmd, cwd=ROOT)
    if result.returncode != 0:
        # Try a second attempt without pulling (if the base image exists locally)
        fallback_cmd = [
            "docker",
            "build",
            "-t",
            IMAGE,
            "-f",
            str(DOCKERFILE),
            "--build-arg",
            "BASE_IMAGE=alpine:3.19",
            ".",
        ]
        result2 = _run(fallback_cmd, cwd=ROOT)
        if result2.returncode != 0:
            msg = (
                "Failed to build sandbox image. Ensure Docker is running and base image is available.\n"
                "Hint: docker pull alpine:3.19 && just test-verbose\n\n"
                "stdout-1:\n"
                + result.stdout
                + "\n\nstderr-1:\n"
                + result.stderr
                + "\n\nstdout-2:\n"
                + result2.stdout
                + "\n\nstderr-2:\n"
                + result2.stderr
            )
            pytest.skip(msg)

    # then: image is available
    yield IMAGE


def run_in_sandbox(image: str, script: str) -> subprocess.CompletedProcess:
    # Always run a one-shot container with bash -lc to preserve justfile semantics
    full_script = textwrap.dedent(
        f"""
        set -e
        cd /root/dotfiles
        {script}
        """
    ).strip()
    return _run(
        [
            "docker",
            "run",
            "--rm",
            image,
            "bash",
            "-lc",
            full_script,
        ]
    )


def _sh_single_quote(s: str) -> str:
    """Quote a string for single-quoted shell embedding.

    Replaces ' with the safe sequence '"'"'.
    """
    return "'" + s.replace("'", "'\"'\"'") + "'"


# Build git stub scripts using textwrap for clarity
GIT_STUB_SIMPLE = textwrap.dedent(
    """
    #!/bin/sh
    if [ "$1" = "clone" ]; then
      repo="$2"; dest="$3";
      case "$repo" in
        *tarjoilija/zgen*)
          mkdir -p "$dest"; exit 0 ;;
        *hironow/dotfiles*)
          mkdir -p "$(dirname "$dest")"; cp -a /root/dotfiles "$dest"; exit 0 ;;
      esac
    fi
    if [ "$1" = "ignore" ]; then
      exit 0
    fi
    exec /usr/bin/git "$@"
    """
).strip()

GIT_STUB_RERUN = textwrap.dedent(
    """
    #!/bin/sh
    if [ "$1" = "clone" ]; then
      repo="$2"; dest="$3";
      case "$repo" in
        *tarjoilija/zgen*)
          mkdir -p "$dest"; exit 0 ;;
        *hironow/dotfiles*)
          mkdir -p "$(dirname "$dest")"; cp -a /root/dotfiles "$dest"; exit 0 ;;
      esac
    fi
    if [ "$1" = "pull" ] || [ "$1" = "ignore" ]; then
      exit 0
    fi
    exec /usr/bin/git "$@"
    """
).strip()

SCRIPT_INSTALL_SUCCESS = textwrap.dedent(
    f"""
    STUBS=/tmp/stubs; mkdir -p "$STUBS";
    # sudo passthrough
    printf '#!/bin/sh\nexec "$@"\n' > "$STUBS/sudo" && chmod +x "$STUBS/sudo";
    # generic success stubs (keep heavy tools stubbed)
    for c in brew gcloud pnpm mise gh tldr code; do
      printf '#!/bin/sh\nexit 0\n' > "$STUBS/$c" && chmod +x "$STUBS/$c";
    done;
    # git: pass-through except clone of zgen/dotfiles and ignore; use skip flags for heavy steps
    printf %s {_sh_single_quote(GIT_STUB_SIMPLE)} > "$STUBS/git"; chmod +x "$STUBS/git";
    export PATH="$STUBS:$PATH";
    export DOTPATH=/root/sandbox/dotfiles-fresh;
    export INSTALL_SKIP_HOMEBREW=1 INSTALL_SKIP_GCLOUD=1 INSTALL_SKIP_ADD_UPDATE=1;
    # run install and verify link
    bash ./install.sh && test -L ~/.zshrc && readlink ~/.zshrc | grep '/root/dotfiles/.zshrc'
    """
).strip()

SCRIPT_INSTALL_RERUN = textwrap.dedent(
    f"""
    STUBS=/tmp/stubs; mkdir -p "$STUBS";
    # sudo passthrough
    printf '#!/bin/sh\nexec "$@"\n' > "$STUBS/sudo" && chmod +x "$STUBS/sudo";
    # generic success stubs (keep heavy tools stubbed)
    for c in brew gcloud pnpm mise gh tldr code; do
      printf '#!/bin/sh\nexit 0\n' > "$STUBS/$c" && chmod +x "$STUBS/$c";
    done;
    # git: only 'pull' is no-op in rerun path; use skip flags for heavy steps
    printf %s {_sh_single_quote(GIT_STUB_RERUN)} > "$STUBS/git"; chmod +x "$STUBS/git";
    export PATH="$STUBS:$PATH";
    export DOTPATH=/root/sandbox/dotfiles-fresh;
    export INSTALL_SKIP_HOMEBREW=1 INSTALL_SKIP_GCLOUD=1 INSTALL_SKIP_ADD_UPDATE=1;
    # first run (clone branch)
    bash ./install.sh;
    # initialize a real git repo at DOTPATH to exercise stash/checkout
    cd "$DOTPATH";
    git init;
    git add -A;
    git -c user.name=test -c user.email=test@example.com commit -m initial;
    git branch -M main;
    cd - >/dev/null;
    # second run (update branch)
    bash ./install.sh;
    # verify link remains correct
    test -L ~/.zshrc && readlink ~/.zshrc | grep '/root/dotfiles/.zshrc'
    """
).strip()


def _case_id(params):
    # Prefer the explicit human-friendly name (first param)
    if isinstance(params, (list, tuple)) and params:
        return str(params[0])
    values = getattr(params, "values", None)
    if isinstance(values, (list, tuple)) and values:
        return str(values[0])
    return None


@pytest.mark.parametrize(
    "name, script, expect_rc, expect_out, expect_err",
    [
        pytest.param(
            "help_lists_targets",
            "just help",
            0,
            "install",
            "",
            id="Help: lists targets",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "validate_path_duplicates",
            "mkdir -p /tmp/x1 /tmp/x2 && printf '#!/bin/sh\necho hi\n' > /tmp/x1/foo && chmod +x /tmp/x1/foo && cp /tmp/x1/foo /tmp/x2/foo && export PATH=/tmp/x1:/tmp/x2:$PATH && just validate-path-duplicates",
            2,
            "command: foo",
            "",
            id="Validate: duplicates found",
            marks=pytest.mark.validate,
        ),
        pytest.param(
            "validate_no_duplicates",
            "mkdir -p /tmp/only && printf '#!/bin/sh\necho ok\n' > /tmp/only/foo && chmod +x /tmp/only/foo && VALIDATE_PATH=/tmp/only just validate-path-duplicates",
            0,
            "No duplicate command names across PATH",
            "",
            id="Validate: no duplicates",
            marks=pytest.mark.validate,
        ),
        pytest.param(
            "deploy_and_clean_link",
            "rm -f ~/.zshrc && just deploy && test -L ~/.zshrc && readlink ~/.zshrc | grep '/root/dotfiles/.zshrc' && just clean && test ! -e ~/.zshrc",
            0,
            "",
            "",
            id="Deploy: basic",
            marks=pytest.mark.deploy,
        ),
        pytest.param(
            "deploy_idempotent",
            "rm -f ~/.zshrc && just deploy && just deploy && test -L ~/.zshrc && readlink ~/.zshrc | grep '/root/dotfiles/.zshrc' && just clean && test ! -e ~/.zshrc",
            0,
            "",
            "",
            id="Deploy: idempotent",
            marks=pytest.mark.deploy,
        ),
        pytest.param(
            "install_sh_success",
            SCRIPT_INSTALL_SUCCESS,
            0,
            "",
            "",
            id="Install: first run",
            marks=pytest.mark.install,
        ),
        pytest.param(
            "install_sh_rerun",
            SCRIPT_INSTALL_RERUN,
            0,
            "",
            "",
            id="Install: rerun update path",
            marks=pytest.mark.install,
        ),
        pytest.param(
            "check_path_runs",
            "just check-path",
            0,
            "\n",
            "",
            id="Check: path prints",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "nvcc_version_ok",
            "just check-version-nvcc 12.3",
            0,
            "",
            "",
            id="Versions: NVCC ok",
            marks=pytest.mark.versions,
        ),
        pytest.param(
            "nvcc_version_mismatch",
            "just check-version-nvcc 11.4",
            1,
            "",
            "Expected NVCC version 11.4",
            id="Versions: NVCC mismatch",
            marks=pytest.mark.versions,
        ),
        pytest.param(
            "torch_not_installed",
            "just check-version-torch 2.5.1",
            1,
            "",
            "PyTorch is not installed",
            id="Versions: Torch missing",
            marks=pytest.mark.versions,
        ),
    ],
)
def test_just_commands_sandbox(
    docker_image, name, script, expect_rc, expect_out, expect_err
):
    # given: sandbox image with repository and stubs
    # when: run the just command inside container
    result = run_in_sandbox(docker_image, script)

    # then: verify exit code and expected output markers
    assert result.returncode == expect_rc, (
        f"{name}: rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    if expect_out:
        assert expect_out in result.stdout, (
            f"{name}: expected stdout to contain: {expect_out!r}\nstdout:\n{result.stdout}"
        )


@pytest.mark.parametrize(
    "name, script, expect_rc, expect_out, expect_err",
    [
        pytest.param(
            "doctor_path_duplicates_warn",
            "mkdir -p /tmp/x1 /tmp/x2 && printf '#!/bin/sh\necho hi\n' > /tmp/x1/foo && chmod +x /tmp/x1/foo && cp /tmp/x1/foo /tmp/x2/foo && export VALIDATE_PATH=/tmp/x1:/tmp/x2 && just doctor",
            0,
            "duplicate command names found",
            "",
            id="Doctor: PATH duplicates warn",
            marks=pytest.mark.validate,
        ),
        pytest.param(
            "pnpm_safe_fallback_without_jq",
            "just update-pnpm-g-safe",
            0,
            "jq not found",
            "",
            id="Update: pnpm safe fallback",
            marks=pytest.mark.check,
        ),
    ],
)
def test_additional_scenarios_sandbox(
    docker_image, name, script, expect_rc, expect_out, expect_err
):
    result = run_in_sandbox(docker_image, script)
    assert result.returncode == expect_rc, (
        f"{name}: rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    if expect_out:
        assert expect_out in result.stdout


@pytest.mark.check
def test_doctor_reports_just(docker_image):
    # when
    result = run_in_sandbox(docker_image, "just doctor")
    # then
    assert result.returncode == 0, (
        f"doctor failed: rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "OK   just" in result.stdout


@pytest.mark.parametrize(
    "name, script, expect_rc, expect_out",
    [
        pytest.param(
            "Check: my IP ok",
            "just check-myip",
            0,
            "",
            id="Check: my IP ok",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "Check: docker ports guarded",
            "if command -v docker >/dev/null 2>&1; then just check-dockerport; else echo skip-docker; fi",
            0,
            "skip-docker",
            id="Check: docker ports guarded",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "Check: brew guarded",
            "if command -v brew >/dev/null 2>&1; then just check-brew; else echo skip-brew; fi",
            0,
            "skip-brew",
            id="Check: brew guarded",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "Check: gcloud guarded",
            "if command -v gcloud >/dev/null 2>&1; then just check-gcloud; else echo skip-gcloud; fi",
            0,
            "skip-gcloud",
            id="Check: gcloud guarded",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "Check: npm globals available",
            # npm is shipped in the sandbox image (needed by mise's npm-backed
            # tools), so the guard always falls through to the real recipe.
            # `npm ls --global --depth 0` exits 0 even with no globals.
            "just check-npm-g",
            0,
            "",
            id="Check: npm globals available",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "Check: pnpm globals guarded",
            "if command -v pnpm >/dev/null 2>&1; then just check-pnpm-g; else echo skip-pnpm; fi",
            0,
            "skip-pnpm",
            id="Check: pnpm globals guarded",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "Check: rust cfg guarded",
            "if command -v rustc >/dev/null 2>&1; then just check-rust; else echo skip-rust; fi",
            0,
            "skip-rust",
            id="Check: rust cfg guarded",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "Check: watchman guarded",
            "if command -v watchman >/dev/null 2>&1; then just check-watchman; else echo skip-watchman; fi",
            0,
            "skip-watchman",
            id="Check: watchman guarded",
            marks=pytest.mark.check,
        ),
    ],
)
def test_check_commands_sandbox(docker_image, name, script, expect_rc, expect_out):
    # given / when
    result = run_in_sandbox(docker_image, script)
    # then
    assert result.returncode == expect_rc, (
        f"{name}: rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    if expect_out:
        assert expect_out in result.stdout


@pytest.mark.check
def test_doctor_sandbox(docker_image):
    result = run_in_sandbox(docker_image, "just doctor")
    assert result.returncode == 0, (
        f"doctor failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Doctor summary:" in result.stdout


# The add-* recipes all share the same early guard:
#   if the dump file is missing or empty, exit 1 with "missing or empty".
# These tests cover that guard without needing gcloud/brew/pnpm in the
# sandbox: the guard fires before any tool is invoked.
@pytest.mark.parametrize(
    "recipe, dump_file",
    [
        pytest.param("add-brew", "dump/Brewfile", id="add-brew guards empty Brewfile"),
        pytest.param("add-gcloud", "dump/gcloud", id="add-gcloud guards empty dump"),
        pytest.param(
            "add-pnpm-g", "dump/npm-global", id="add-pnpm-g guards empty dump"
        ),
    ],
)
@pytest.mark.check
def test_add_recipes_guard_empty_dump(docker_image, recipe, dump_file):
    # given: the dump file is emptied
    # when: the recipe is run
    # then: it exits 1 with a clear "missing or empty" message
    script = f": > {dump_file} && just {recipe}"
    result = run_in_sandbox(docker_image, script)
    assert result.returncode == 1, (
        f"{recipe}: expected rc=1 for empty {dump_file}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "missing or empty" in result.stdout, (
        f"{recipe}: expected 'missing or empty' in stdout\nstdout:\n{result.stdout}"
    )


# =============================================================================
# Format / Lint Recipe Tests
# =============================================================================
#
# `just format` / `just lint` chain `uvx ruff` (Python), `mise x -- shellcheck`
# (lint only), and `mise x -- prettier` (both). The sandbox image ships mise,
# and shellcheck is listed in mise.toml, so shellcheck runs for real here.
#
# Prettier is intentionally NOT in mise.toml (the team relies on host install
# via brew/asdf), so we override `mise x -- prettier ...` with a no-op shim.
# We do this by injecting a wrapper named `mise` earlier on PATH that:
#   - intercepts the literal pattern `x -- prettier ...` and exits 0,
#   - delegates everything else to the real /root/.local/bin/mise.

# mise's tools (incl. shellcheck) are pre-installed in the sandbox image
# (Dockerfile runs `mise trust && mise install` at build time). We only need
# to override prettier — which is intentionally NOT in mise.toml — with a
# no-op shim so `just format`/`just lint` finish cleanly without prettier.
# Shellcheck runs for real via the pre-installed mise tool.
#
# MISE_OFFLINE=1 prevents mise from contacting GitHub at runtime to check
# for newer "latest" versions. Without it, repeated test runs trip the
# unauthenticated GitHub API rate limit and mise then fails to resolve
# `shellcheck = "latest"`.
_MISE_PRETTIER_STUB = (
    "export MISE_OFFLINE=1 && "
    "mkdir -p /tmp/stubs && "
    "printf '%s\\n' "
    "'#!/bin/sh' "
    "'if [ \"$1\" = x ] && [ \"$2\" = -- ] && [ \"$3\" = prettier ]; then exit 0; fi' "
    "'exec /root/.local/bin/mise \"$@\"' "
    "> /tmp/stubs/mise && chmod +x /tmp/stubs/mise && "
    "export PATH=/tmp/stubs:$PATH && "
)

# Backwards-compat alias used by older tests; same semantics now.
_MISE_STUB = _MISE_PRETTIER_STUB

# The sandbox image excludes .git via .dockerignore, so `git ls-files` would
# fatal. Initialize a repo and stage everything so `git ls-files` returns the
# tracked file list. Empty `git ls-files` output makes grep exit 1 (no match),
# which would then break the pipeline under `set -e`.
#
# Submodule paths are intentionally NOT staged: in a real checkout, `git
# ls-files` omits files inside submodules (each submodule is a pointer in
# the parent repo). Without this, our throwaway `git init` would include
# every submodule's .sh / file and cause shellcheck/prettier/ruff/... to
# scan third-party code the recipes are designed to skip. We derive the
# exclusion list dynamically from .gitmodules so nested submodules
# (e.g. tools/tmux/plugins/tmux-resurrect) are covered too.
_GIT_INIT = (
    "cd /root/dotfiles && "
    "git init -q && "
    "git config user.email t@e && git config user.name t && "
    "git config --file .gitmodules --get-regexp path 2>/dev/null "
    "| awk '{print $2\"/\"}' > .git/info/exclude && "
    "git add -A 2>/dev/null && "
)


@pytest.mark.check
def test_just_lint_passes_on_clean_tree(docker_image):
    """`just lint` returns 0 on the as-shipped repo (ruff finds no violations)."""
    result = run_in_sandbox(docker_image, _MISE_STUB + _GIT_INIT + "just lint")
    assert result.returncode == 0, (
        f"just lint failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Linting Python (ruff)" in result.stdout
    assert "Lint done" in result.stdout


@pytest.mark.check
def test_just_format_check_passes_on_clean_tree(docker_image):
    """`just format` returns 0 on the as-shipped repo (ruff format applies cleanly)."""
    result = run_in_sandbox(docker_image, _MISE_STUB + _GIT_INIT + "just format")
    assert result.returncode == 0, (
        f"just format failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Formatting Python (ruff)" in result.stdout
    assert "Format done" in result.stdout


@pytest.mark.check
def test_just_lint_detects_ruff_violation(docker_image):
    """`just lint` exits non-zero when a Python file has a ruff violation
    that ruff cannot auto-fix.

    Uses E741 (ambiguous variable name 'l'), which ruff reports but does NOT
    auto-fix — so even with `--fix` the lint step fails.
    """
    script = (
        _MISE_STUB
        + _GIT_INIT
        + "printf 'def f():\\n    l = 1\\n    return l\\n' > bad_lint.py && "
        + "just lint"
    )
    result = run_in_sandbox(docker_image, script)
    assert result.returncode != 0, (
        "just lint should fail on E741 violation\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "E741" in result.stdout or "E741" in result.stderr


# =============================================================================
# clean-work-env Recipe Tests
# =============================================================================


@pytest.mark.check
def test_just_clean_work_env_rejects_unknown_target(docker_image):
    """`just clean-work-env x` for x not in {a,b,c,d} fails with a clear error."""
    result = run_in_sandbox(docker_image, "just clean-work-env z")
    assert result.returncode != 0
    assert "unknown target" in result.stdout or "unknown target" in result.stderr


@pytest.mark.check
def test_just_clean_work_env_fails_when_dir_missing(docker_image):
    """`just clean-work-env a` fails if ~/.claude-work-a does not exist."""
    result = run_in_sandbox(
        docker_image,
        "rm -rf $HOME/.claude-work-a && just clean-work-env a",
    )
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "does not exist" in combined


@pytest.mark.check
def test_just_clean_work_env_resets_managed_paths_only(docker_image):
    """`just clean-work-env a` empties CLAUDE.md and removes the managed
    directories (skills/commands/agents/plans/session-env/shell-snapshots)
    while preserving plugins/, projects/, and history files.
    """
    setup = (
        "set -eu\n"
        "d=$HOME/.claude-work-a\n"
        "mkdir -p $d/skills/foo $d/commands $d/agents $d/plans $d/session-env "
        "$d/shell-snapshots $d/plugins/keep-me $d/projects/keep-me\n"
        "echo 'KEEP THIS' > $d/CLAUDE.md\n"
        "echo 'foo skill' > $d/skills/foo/SKILL.md\n"
        "echo 'cmd' > $d/commands/c.md\n"
        "echo 'plan' > $d/plans/p.md\n"
        "echo 'plugin file' > $d/plugins/keep-me/p.json\n"
        "echo 'project file' > $d/projects/keep-me/x.json\n"
        "echo 'history' > $d/.claude.json\n"
        "just clean-work-env a\n"
        "# inspect aftermath\n"
        "[ -f $d/CLAUDE.md ] && [ ! -s $d/CLAUDE.md ] && echo 'claude_md emptied'\n"
        "[ ! -e $d/skills ] && echo 'skills removed'\n"
        "[ ! -e $d/commands ] && echo 'commands removed'\n"
        "[ ! -e $d/agents ] && echo 'agents removed'\n"
        "[ ! -e $d/plans ] && echo 'plans removed'\n"
        "[ ! -e $d/session-env ] && echo 'session-env removed'\n"
        "[ ! -e $d/shell-snapshots ] && echo 'shell-snapshots removed'\n"
        "[ -d $d/plugins/keep-me ] && echo 'plugins preserved'\n"
        "[ -d $d/projects/keep-me ] && echo 'projects preserved'\n"
        "[ -f $d/.claude.json ] && echo 'history preserved'\n"
    )
    result = run_in_sandbox(docker_image, setup)
    assert result.returncode == 0, (
        f"rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    expected = [
        "claude_md emptied",
        "skills removed",
        "commands removed",
        "agents removed",
        "plans removed",
        "session-env removed",
        "shell-snapshots removed",
        "plugins preserved",
        "projects preserved",
        "history preserved",
    ]
    for line in expected:
        assert line in result.stdout, f"missing: {line}\nfull stdout:\n{result.stdout}"


# =============================================================================
# Validation Recipe Tests (semgrep meta rules)
# =============================================================================
#
# These exercise the rule-files-against-themselves workflow:
#   - meta-semgrep      : run rules in .semgrep/rules/meta/ against the repo
#   - meta-semgrep-test : verify the rules' own test annotations
#   - validate          : composite of both
#
# semgrep is installed on demand via uvx, so the first run downloads it
# (~75MB). Subsequent runs in the same container are cached.


@pytest.mark.check
def test_just_meta_semgrep_test_passes(docker_image):
    """`just meta-semgrep-test` validates the meta rules' own test annotations."""
    result = run_in_sandbox(
        docker_image,
        _GIT_INIT + "just meta-semgrep-test",
    )
    assert result.returncode == 0, (
        f"meta-semgrep-test failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.check
def test_just_meta_semgrep_clean_repo_passes(docker_image):
    """`just meta-semgrep` returns 0 on the as-shipped repo (no findings)."""
    result = run_in_sandbox(
        docker_image,
        _GIT_INIT + "just meta-semgrep",
    )
    assert result.returncode == 0, (
        f"meta-semgrep failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.check
def test_just_validate_runs_both_steps(docker_image):
    """`just validate` chains meta-semgrep-test then meta-semgrep."""
    result = run_in_sandbox(
        docker_image,
        _GIT_INIT + "just validate",
    )
    assert result.returncode == 0, (
        f"validate failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# =============================================================================
# Misc Recipe Tests (default / clean-cache / clean-all / self-check / add-all)
# =============================================================================


@pytest.mark.check
def test_just_default_lists_recipes(docker_image):
    """`just` (no args) runs `default` which delegates to help (`just --list`)."""
    result = run_in_sandbox(docker_image, "just")
    assert result.returncode == 0, (
        f"just default failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # The list output should mention at least one known recipe.
    assert "sync-agents" in result.stdout


@pytest.mark.check
def test_just_clean_cache_idempotent_on_missing_dirs(docker_image):
    """`just clean-cache` succeeds even when target cache dirs do not exist."""
    # Fresh container has none of these, so this exercises the "rm -vrf" on
    # missing paths. rc must still be 0.
    result = run_in_sandbox(docker_image, "just clean-cache")
    assert result.returncode == 0, (
        f"clean-cache failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Remove zsh caches" in result.stdout


@pytest.mark.check
def test_just_clean_all_runs_clean_then_clean_cache(docker_image):
    """`just clean-all` is a composite of `clean` + `clean-cache`. Both run."""
    result = run_in_sandbox(docker_image, "just clean-all")
    assert result.returncode == 0, (
        f"clean-all failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # Each child recipe prints a distinctive header.
    assert "Remove dotfiles" in result.stdout
    assert "Remove zsh caches" in result.stdout


@pytest.mark.check
def test_just_self_check_succeeds(docker_image):
    """`just self-check` runs doctor + validate-path-duplicates with summary."""
    result = run_in_sandbox(docker_image, "just self-check")
    assert result.returncode == 0, (
        f"self-check failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Self-check summary:" in result.stdout


@pytest.mark.check
def test_just_add_all_fails_when_dumps_empty(docker_image):
    """`just add-all` is a composite. With empty dump files it must fail at
    the first add-* guard (rc=1, "missing or empty"), not silently succeed."""
    script = (
        ": > dump/Brewfile && : > dump/gcloud && : > dump/npm-global && just add-all"
    )
    result = run_in_sandbox(docker_image, script)
    assert result.returncode != 0
    assert "missing or empty" in result.stdout


@pytest.mark.check
def test_just_install_runs_mise_install(docker_image):
    """`just install` invokes `mise install` end-to-end and provisions the
    tools listed in mise.toml.

    The sandbox image pre-installs all mise.toml tools at build time
    (single GitHub API hit). At test time we set MISE_OFFLINE=1 so mise
    re-uses what's already installed instead of re-querying GitHub for
    "latest" — repeated test runs would otherwise trip the unauthenticated
    rate limit and fail.
    """
    # mise refuses to read an untrusted config; replicate the operator's
    # one-time `mise trust` step.
    result = run_in_sandbox(
        docker_image,
        "export MISE_OFFLINE=1; mise trust >/dev/null 2>&1; just install",
    )
    assert result.returncode == 0, (
        f"just install failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert "mise install" in combined
