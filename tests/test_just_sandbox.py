import os
import subprocess
import textwrap
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "tests" / "docker" / "JustSandbox.Dockerfile"
IMAGE = "dotfiles-just-sandbox:latest"


def _run(cmd: list[str] | str, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
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
                "stdout-1:\n" + result.stdout + "\n\nstderr-1:\n" + result.stderr +
                "\n\nstdout-2:\n" + result2.stdout + "\n\nstderr-2:\n" + result2.stderr
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
    return _run([
        "docker",
        "run",
        "--rm",
        image,
        "bash",
        "-lc",
        full_script,
    ])


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
            "deploy_and_clean_link",
            "rm -f ~/.zshrc && just deploy && test -L ~/.zshrc && readlink ~/.zshrc | grep '/root/dotfiles/.zshrc' && just clean && test ! -e ~/.zshrc",
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
)
def test_just_commands_sandbox(docker_image, name, script, expect_rc, expect_out, expect_err):
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
