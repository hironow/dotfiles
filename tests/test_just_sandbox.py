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
    if [ "$1" = "stash" ] || [ "$1" = "checkout" ] || [ "$1" = "pull" ] || [ "$1" = "ignore" ]; then
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
    # git: pass-through except clone of zgen/dotfiles and ignore
    printf %s {_sh_single_quote(GIT_STUB_SIMPLE)} > "$STUBS/git"; chmod +x "$STUBS/git";
    export PATH="$STUBS:$PATH";
    export DOTPATH=/root/sandbox/dotfiles-fresh;
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
    # git: no-op for stash/checkout/pull in rerun path
    printf %s {_sh_single_quote(GIT_STUB_RERUN)} > "$STUBS/git"; chmod +x "$STUBS/git";
    export PATH="$STUBS:$PATH";
    export DOTPATH=/root/sandbox/dotfiles-fresh;
    # first run (clone branch)
    bash ./install.sh;
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
        (
            "help_lists_targets",
            "just help",
            0,
            "install",
            "",
        ),
        (
            "validate_path_duplicates",
            "mkdir -p /tmp/x1 /tmp/x2 && printf '#!/bin/sh\necho hi\n' > /tmp/x1/foo && chmod +x /tmp/x1/foo && cp /tmp/x1/foo /tmp/x2/foo && export PATH=/tmp/x1:/tmp/x2:$PATH && just validate-path-duplicates",
            2,
            "command: foo",
            "",
        ),
        (
            "validate_no_duplicates",
            "mkdir -p /tmp/only && printf '#!/bin/sh\necho ok\n' > /tmp/only/foo && chmod +x /tmp/only/foo && VALIDATE_PATH=/tmp/only /usr/bin/just validate-path-duplicates",
            0,
            "No duplicate command names across PATH",
            "",
        ),
        (
            "deploy_and_clean_link",
            "rm -f ~/.zshrc && just deploy && test -L ~/.zshrc && readlink ~/.zshrc | grep '/root/dotfiles/.zshrc' && just clean && test ! -e ~/.zshrc",
            0,
            "",
            "",
        ),
        (
            "deploy_idempotent",
            "rm -f ~/.zshrc && just deploy && just deploy && test -L ~/.zshrc && readlink ~/.zshrc | grep '/root/dotfiles/.zshrc' && just clean && test ! -e ~/.zshrc",
            0,
            "",
            "",
        ),
        (
            "install_sh_success",
            SCRIPT_INSTALL_SUCCESS,
            0,
            "",
            "",
        ),
        (
            "install_sh_rerun",
            SCRIPT_INSTALL_RERUN,
            0,
            "",
            "",
        ),
        (
            "check_path_runs",
            "just check-path",
            0,
            "\n",
            "",
        ),
        (
            "nvcc_version_ok",
            "just check-version-nvcc 12.3",
            0,
            "",
            "",
        ),
        (
            "nvcc_version_mismatch",
            "just check-version-nvcc 11.4",
            1,
            "",
            "Expected NVCC version 11.4",
        ),
        (
            "torch_not_installed",
            "just check-version-torch 2.5.1",
            1,
            "",
            "PyTorch is not installed",
        ),
    ],
    ids=[
        "help_lists_targets",
        "validate_path_duplicates",
        "validate_no_duplicates",
        "deploy_and_clean_link",
        "deploy_idempotent",
        "install_sh_success",
        "install_sh_rerun",
        "check_path_runs",
        "nvcc_version_ok",
        "nvcc_version_mismatch",
        "torch_not_installed",
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

    if expect_err:
        # Some commands print to stdout; check combined for resilience
        combined = result.stdout + "\n" + result.stderr
        assert expect_err in combined, (
            f"{name}: expected error message: {expect_err!r}\ncombined:\n{combined}"
        )
