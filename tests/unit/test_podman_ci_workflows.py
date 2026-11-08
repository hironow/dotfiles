"""Static workflow/bootstrap safety contracts; no host operations."""

import hashlib
import io
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path

import pytest
from _bash_hook import bash_path, resolve_bash, run_bash

ROOT = Path(__file__).resolve().parents[2]


def test_both_engine_jobs_use_one_rootless_native_bootstrap():
    for name in ("test-just.yaml", "test-emulators.yaml"):
        body = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
        assert "runs-on: ubuntu-26.04" in body
        assert "bash .devcontainer/ci-bootstrap.sh" in body
        assert "devcontainers/ci@" not in body
        assert "github.event.pull_request.draft == false" in body
        assert "ready_for_review" in body
        for action in re.findall(r"uses:\s+(\S+)", body):
            assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", action), action
    sandbox = (ROOT / ".github/workflows/test-just.yaml").read_text(encoding="utf-8")
    assert "vars.RUN_SANDBOX_TESTS == 'true'" in sandbox
    assert "${GITHUB_WORKSPACE}/pytest-report.xml" in sandbox
    assert "path: ${{ github.workspace }}/pytest-report.xml" in sandbox


def test_emulator_ci_never_kills_by_port_or_shared_compose_project():
    body = (ROOT / ".github/workflows/test-emulators.yaml").read_text(encoding="utf-8")
    for unsafe in (
        "publish=$port",
        "docker stop",
        "docker rm",
        "docker compose down",
        "sudo lsof",
    ):
        assert unsafe not in body
    assert "if: always()" in body
    assert "DOTFILES_E2E_REQUIRED: '1'" in body
    assert "DOTFILES_PODMAN_RUN_MANIFEST:" in body
    for operation in ("prepare", "start", "wait", "cleanup"):
        assert f"python -m tests.utils.isolation {operation}" in body
    assert (
        "--services firebase-emulator,spanner-emulator,pgadapter,postgres --telemetry"
        in body
    )
    assert "pytest tests/e2e -v -m e2e -ra" in body
    assert "tests/test_postgres18_features.py tests/test_postgres18_emulator.py" in body
    assert "Docker executable unexpectedly present" in body


def test_ci_bootstrap_refuses_operator_hosts_before_installation(tmp_path):
    result = run_bash(
        ROOT / ".devcontainer/ci-bootstrap.sh",
        cwd=tmp_path,
        env=dict(
            os.environ, GITHUB_ACTIONS="false", RUNNER_ENVIRONMENT="github-hosted"
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 1
    assert "ephemeral non-root GitHub Actions Linux runner" in result.stderr


def test_bootstrap_is_ci_only_and_uses_canonical_pins_and_order():
    body = (ROOT / ".devcontainer/ci-bootstrap.sh").read_text(encoding="utf-8")
    assert '"${GITHUB_ACTIONS:-}" != true' in body
    assert '"${RUNNER_ENVIRONMENT:-}" != github-hosted' in body
    assert 'bash "$repo/install.sh" --podman-only' in body
    assert "source['bootstrap']['mise']" in body
    assert "generated mise tools missing" in body
    assert "MISE_GLOBAL_CONFIG_FILE" in body
    assert body.index("mise install bun uv node just") < body.index(
        "mise install npm:@devcontainers/cli pypi:podman-compose"
    )
    assert "systemctl --user start podman.socket" in body
    assert '"host"]["remoteSocket"]["path"]' in body
    assert "PODMAN_COMPOSE_PROVIDER=podman-compose" in body
    assert "sudo podman" not in body
    assert "Docker remains on PATH" in body
    assert not re.search(r"podman-compose[=@][0-9]|devcontainers/cli[=@][0-9]", body)


@pytest.mark.parametrize(
    "label, valid", [("ubuntu-26.04", True), ("ubuntu-unknown-podman", False)]
)
def test_actionlint_exact_runner_extension_retains_unknown_label_rejection(
    tmp_path, label, valid
):
    executable = shutil.which("actionlint")
    if executable is None:
        pytest.skip("actionlint not installed; workflow schema control unverified")
    workflow = tmp_path / "runner.yaml"
    workflow.write_text(
        f"name: Runner control\non: push\njobs:\n  control:\n    runs-on: {label}\n    steps:\n      - run: echo control\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            executable,
            "-config-file",
            str(ROOT / ".github/actionlint.yaml"),
            str(workflow),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert (result.returncode == 0) is valid, result.stdout + result.stderr
    if not valid:
        assert "runner-label" in result.stdout + result.stderr


def _bootstrap_checksum_attempt(tmp_path, names, *, corrupt=False):
    """Run the public bootstrap, stopping at the external unpack boundary.

    Installer/privilege/download/identity operations are inert fixtures.
    The checksum checker is real; no tool install or service is reached.
    """
    repo = tmp_path / "repo"
    for relative in (
        ".devcontainer/ci-bootstrap.sh",
        ".devcontainer/features/dotfiles-tools/install.sh",
        "config/mise/image-tools.toml",
    ):
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    (repo / "install.sh").write_text(
        '#!/bin/sh\n[ "$#" = 1 ] && [ "$1" = --podman-only ]\n',
        encoding="utf-8",
    )
    version = tomllib.loads(
        (repo / "config/mise/image-tools.toml").read_text(encoding="utf-8")
    )["bootstrap"]["mise"]
    artifact = f"mise-v{version}-linux-x64-musl.tar.gz"
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz", encoding="utf-8") as archive:
        content = b"harmless checksum fixture\n"
        info = tarfile.TarInfo("fixture.txt")
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    raw = buffer.getvalue()
    fixture = tmp_path / "fixture.tar.gz"
    fixture.write_bytes(raw + b"corrupted" if corrupt else raw)
    sums = tmp_path / "SHASUMS256.txt"
    sums.write_text(
        "".join(
            f"{hashlib.sha256(raw).hexdigest()}  {name.format(artifact=artifact)}\n"
            for name in names
        ),
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    checker = "/usr/bin/sha256sum" if Path("/usr/bin/sha256sum").is_file() else None
    checker_args = ""
    if checker is None and os.name == "nt":
        bash_directory = Path(resolve_bash()).parent
        for candidate in (
            bash_directory / "sha256sum.exe",
            bash_directory.parent / "usr/bin/sha256sum.exe",
        ):
            if candidate.is_file():
                checker = str(candidate)
                break
    if checker is None:
        checker = "/usr/bin/shasum" if Path("/usr/bin/shasum").is_file() else None
        checker_args = " -a 256"
    assert checker is not None, "a real SHA256 checksum checker is required"
    commands = {
        "uname": 'case "$1" in -s) echo Linux ;; -m) echo x86_64 ;; *) exit 97 ;; esac',
        "id": '[ "$1" = -u ] || exit 97; echo 1000',
        "sudo": '[ "$1" = -n ] && [ "$2" = apt-get ] || exit 97; exit 0',
        "python3": f'exec {shlex.quote(bash_path(Path(sys.executable)))} -I "$@"',
        "curl": """output=; url=
while [ "$#" -gt 0 ]; do
  case "$1" in -o) output="$2"; shift ;; https://*) url="$1" ;; esac
  shift
done
[ -n "$output" ] || exit 97
case "$url" in
  */SHASUMS256.txt) cp "$FIXTURE_SUMS" "$output" ;;
  */"$FIXTURE_ASSET")
    cp "$FIXTURE_ARCHIVE" "$output"
    # A valid alias makes a wildcard-dot selector observably wrong, rather
    # than accidentally rejected by the later checksum file lookup.
    mkdir -p "$(dirname "$output")/x"
    cp "$FIXTURE_ARCHIVE" "$(dirname "$output")/x/$FIXTURE_ASSET"
    ;;
  *) exit 97 ;;
esac""",
        "sha256sum": f'exec {shlex.quote(bash_path(Path(checker)))}{checker_args} "$@"',
        "tar": "echo FIXTURE_UNPACK_BOUNDARY; exit 89",
    }
    for name in ("mise", "podman", "systemctl", "apt-get", "git", "brew", "install"):
        commands[name] = "echo FORBIDDEN_HOST_OPERATION >&2; exit 97"
    for name, body in commands.items():
        executable = bin_dir / name
        executable.write_text("#!/bin/sh\nset -eu\n" + body + "\n", encoding="utf-8")
        executable.chmod(0o755)
    runner = tmp_path / "runner"
    runner.mkdir()
    bash_dir = Path(resolve_bash()).parent
    env = {
        "PATH": ":".join(
            bash_path(entry)
            for entry in (
                bin_dir,
                bash_dir,
                bash_dir.parent / "usr/bin",
                Path("/usr/bin"),
                Path("/bin"),
            )
        ),
        "HOME": bash_path(tmp_path),
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_TEMP": bash_path(runner),
        "GITHUB_ENV": bash_path(tmp_path / "github-env"),
        "GITHUB_PATH": bash_path(tmp_path / "github-path"),
        "FIXTURE_ASSET": artifact,
        "FIXTURE_ARCHIVE": bash_path(fixture),
        "FIXTURE_SUMS": bash_path(sums),
        "SystemRoot": os.environ.get("SystemRoot", ""),
    }
    return run_bash(
        repo / ".devcontainer/ci-bootstrap.sh",
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )


def test_bootstrap_verifies_official_dot_slash_checksum_before_unpacking(tmp_path):
    result = _bootstrap_checksum_attempt(tmp_path, ["./{artifact}"])
    # This is an intentional external-boundary stop, not bootstrap success.
    assert result.returncode == 89, result.stdout + result.stderr
    assert "FIXTURE_UNPACK_BOUNDARY" in result.stdout
    assert "FORBIDDEN_HOST_OPERATION" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "names, corrupt, verified",
    [
        pytest.param(["{artifact}"], False, True, id="bare-name"),
        pytest.param(
            ["./unrelated.tar.gz", "./{artifact}", "{artifact}.sig"],
            False,
            True,
            id="exact-name-among-other-assets",
        ),
        pytest.param([], False, False, id="missing"),
        pytest.param(["{artifact}", "{artifact}"], False, False, id="duplicate-bare"),
        pytest.param(
            ["./{artifact}", "./{artifact}"], False, False, id="duplicate-dot-slash"
        ),
        pytest.param(
            ["{artifact}", "./{artifact}"], False, False, id="duplicate-mixed"
        ),
        pytest.param(["{artifact}.sig"], False, False, id="near-match"),
        pytest.param(["other/{artifact}"], False, False, id="other-directory"),
        pytest.param(["./../{artifact}"], False, False, id="traversal"),
        pytest.param(["x/{artifact}"], False, False, id="dot-must-be-literal"),
        pytest.param(["/{artifact}"], False, False, id="absolute-path"),
        pytest.param(["./{artifact}"], True, False, id="corrupt-dot-slash"),
        pytest.param(["{artifact}"], True, False, id="corrupt-bare"),
    ],
)
def test_bootstrap_only_unpacks_one_exact_verified_artifact(
    tmp_path, names, corrupt, verified
):
    result = _bootstrap_checksum_attempt(tmp_path, names, corrupt=corrupt)
    assert result.returncode == (89 if verified else 1), result.stdout + result.stderr
    assert ("FIXTURE_UNPACK_BOUNDARY" in result.stdout) is verified
    assert "FORBIDDEN_HOST_OPERATION" not in result.stdout + result.stderr
