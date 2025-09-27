import os
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
        pytest.param("help_lists_targets", "just help", 0, "install", "", id="Help: lists targets", marks=pytest.mark.check),
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
            "mkdir -p /tmp/only && printf '#!/bin/sh\necho ok\n' > /tmp/only/foo && chmod +x /tmp/only/foo && VALIDATE_PATH=/tmp/only /usr/bin/just validate-path-duplicates",
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
        pytest.param("install_sh_success", SCRIPT_INSTALL_SUCCESS, 0, "", "", id="Install: first run", marks=pytest.mark.install),
        pytest.param("install_sh_rerun", SCRIPT_INSTALL_RERUN, 0, "", "", id="Install: rerun update path", marks=pytest.mark.install),
        pytest.param("check_path_runs", "just check-path", 0, "\n", "", id="Check: path prints", marks=pytest.mark.check),
        pytest.param("nvcc_version_ok", "just check-version-nvcc 12.3", 0, "", "", id="Versions: NVCC ok", marks=pytest.mark.versions),
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
    assert result.returncode == 0, f"doctor failed: rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
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
            "Check: npm globals guarded",
            "if command -v npm >/dev/null 2>&1; then just check-npm-g; else echo skip-npm; fi",
            0,
            "skip-npm",
            id="Check: npm globals guarded",
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
    assert result.returncode == 0, f"doctor failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "Doctor summary:" in result.stdout
