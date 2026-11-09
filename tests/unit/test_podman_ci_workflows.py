"""Static workflow/bootstrap safety contracts; no host operations."""

import hashlib
import io
import json
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
    assert "RUN_SANDBOX_TESTS" not in sandbox
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


def _engine_info(
    *, version="5.7.0", rootless=True, socket="unix:///run/user/1000/podman/podman.sock"
):
    return json.dumps(
        {
            "host": {
                "security": {"rootless": rootless},
                "remoteSocket": {"path": socket},
            },
            "version": {"Version": version},
        }
    )


# Each tool's executable as its real install lays it out: uv's archive keeps
# it in a nested directory and just's at the install root, so `mise where`
# plus /bin does not find them; `mise bin-paths` names these directories.
TOOL_LAYOUT = (
    ("bun/bin", "bun"),
    ("uv/uv-x86_64-unknown-linux-gnu", "uv"),
    ("node/bin", "node"),
    ("node/extra", "corepack"),
    ("just", "just"),
    ("devcontainers-cli/bin", "devcontainer"),
    ("podman-compose/bin", "podman-compose"),
)


def _bootstrap_checksum_attempt(
    tmp_path, names, *, corrupt=False, engine=None, extra_env=None
):
    """Run the public bootstrap with real checks and owned external boundaries.

    By default stop at unpack89; engine fixtures instead unpack an inert mise
    and execute the unchanged canonical socket helper with real jq. PATH has
    only owned wrappers: host container engines cannot be discovered.
    """
    repo = tmp_path / "repo"
    for relative in (
        ".devcontainer/ci-bootstrap.sh",
        ".devcontainer/require-podman-socket.sh",
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
    # The real guard has its own tests (test_allow_podman_stop_pasta.py);
    # here it only records that, and with what, the bootstrap ran it.
    (repo / ".devcontainer/allow-podman-stop-pasta.sh").write_text(
        'printf \'pasta-guard %s\\n\' "$*" >> "${FIXTURE_TRACE:-/dev/null}"\n'
        'exit "${FIXTURE_PASTA_GUARD_RC:-0}"\n',
        encoding="utf-8",
        newline="\n",
    )
    version = tomllib.loads(
        (repo / "config/mise/image-tools.toml").read_text(encoding="utf-8")
    )["bootstrap"]["mise"]
    artifact = f"mise-v{version}-linux-x64-musl.tar.gz"
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz", encoding="utf-8") as archive:
        content = b"harmless checksum fixture\n"
        member = "fixture.txt"
        if engine is not None:
            member = "mise/bin/mise"
            content = b"""#!/bin/sh
set -eu
printf 'mise %s\\n' "$*" >> "$FIXTURE_TRACE"
root() {
  case "$1" in
    npm:@devcontainers/cli) printf '%s\\n' "$FIXTURE_TOOLS/devcontainers-cli" ;;
    pypi:podman-compose) printf '%s\\n' "$FIXTURE_TOOLS/podman-compose" ;;
    *) printf '%s\\n' "$FIXTURE_TOOLS/$1" ;;
  esac
}
case "$*" in
  'install bun uv node just')
    printf '%s\\n' "${MISE_URL_REPLACEMENTS-UNSET}" > "$FIXTURE_TRACE.url-replacements" ;;
  'install npm:@devcontainers/cli pypi:podman-compose')
    # the npm and pypi backends run bun, node, and uv from PATH
    for command in uv bun node; do
      found=$(command -v "$command") || { echo "SECOND_PHASE_MISSING $command" >&2; exit 96; }
      case "$found" in "$FIXTURE_TOOLS"/*) ;; *) echo "SECOND_PHASE_WRONG $found" >&2; exit 96 ;; esac
    done ;;
  'where bun'|'where uv'|'where node'|'where just'|'where npm:@devcontainers/cli'|'where pypi:podman-compose')
    root "$2" ;;
  'bin-paths bun'|'bin-paths uv'|'bin-paths node'|'bin-paths just'|'bin-paths npm:@devcontainers/cli'|'bin-paths pypi:podman-compose')
    case "${FIXTURE_BIN_PATHS_BREAK:-}" in
      # a failure that still prints a real directory: only the exit status says so
      "$2:fail") printf '%s/bin\\n' "$FIXTURE_TOOLS/bun"; exit 1 ;;
      "$2:empty") exit 0 ;;
      "$2:missing") printf '%s\\n' "$FIXTURE_TOOLS/no-such-directory"; exit 0 ;;
      "$2:second-missing")
        printf '%s/bin\\n%s\\n' "$(root "$2")" "$FIXTURE_TOOLS/no-such-directory"; exit 0 ;;
    esac
    case "$2" in
      uv) printf '%s\\n' "$FIXTURE_TOOLS/uv/uv-x86_64-unknown-linux-gnu" ;;
      just) root just ;;
      # more than one directory for one tool: each is published
      node) printf '%s/bin\\n%s/extra\\n' "$(root node)" "$(root node)" ;;
      *) printf '%s/bin\\n' "$(root "$2")" ;;
    esac ;;
  *) exit 97 ;;
esac
"""
        info = tarfile.TarInfo(member)
        info.mode = 0o755
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    raw = buffer.getvalue()
    fixture = tmp_path / "fixture.tar.gz"
    fixture.write_bytes(raw + b"corrupted" if corrupt else raw)
    # The mise release as GitHub's API describes it: SHASUMS256.txt's asset id.
    release = tmp_path / "release.json"
    release.write_text(
        json.dumps(
            {
                "tag_name": f"v{version}",
                "assets": [
                    {"name": artifact, "id": 4241},
                    {"name": "SHASUMS256.txt", "id": 4242},
                    {"name": "SHASUMS256.txt.minisig", "id": 4243},
                ],
            }
        ),
        encoding="utf-8",
    )
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
        # Records each request (URL, argv, a header read from stdin) and
        # fails the URLs that start with a FIXTURE_CURL_FAIL prefix.
        "curl": """output=; url=; header=
printf 'ARGV %s\\n' "$*" >> "$FIXTURE_CURL_LOG"
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) output="$2"; shift ;;
    -H) [ "$2" = @- ] && header="$(cat)"; shift ;;
    https://*) url="$1" ;;
  esac
  shift
done
printf 'URL %s\\n' "$url" >> "$FIXTURE_CURL_LOG"
[ -z "$header" ] || printf 'STDIN-HEADER %s\\n' "$header" >> "$FIXTURE_CURL_LOG"
[ -n "$output" ] || exit 97
for prefix in ${FIXTURE_CURL_FAIL:-}; do
  case "$url" in "$prefix"*) echo "FIXTURE_CURL_FAILURE $url" >&2; exit 22 ;; esac
done
case "$url" in
  https://api.github.com/repos/jdx/mise/releases/tags/v"$FIXTURE_MISE_VERSION")
    cp "$FIXTURE_RELEASE" "$output" ;;
  https://api.github.com/repos/jdx/mise/releases/assets/"$FIXTURE_SUMS_ID")
    cp "$FIXTURE_SUMS" "$output" ;;
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

    # Never expose a host utility directory through the fixture PATH, including
    # Git Bash's bin directory (which may also contain a real Docker client).
    def real_utility(name):
        candidates = []
        if os.name == "nt":
            bash_dir = Path(resolve_bash()).parent
            candidates = [
                bash_dir / f"{name}.exe",
                bash_dir.parent / "usr/bin" / f"{name}.exe",
            ]
        found = next((str(p) for p in candidates if p.is_file()), None)
        found = found or shutil.which(name)
        assert found is not None, f"real fixture utility required: {name}"
        return shlex.quote(bash_path(Path(found)))

    for name in ("cat", "cp", "dirname", "mkdir", "grep", "wc"):
        commands[name] = f'exec {real_utility(name)} "$@"'
    commands["bash"] = f'exec {shlex.quote(bash_path(Path(resolve_bash())))} "$@"'
    runner = tmp_path / "runner"
    runner.mkdir()
    env = {
        "PATH": bash_path(bin_dir),
        "HOME": bash_path(tmp_path),
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "RUNNER_TEMP": bash_path(runner),
        "GITHUB_ENV": bash_path(tmp_path / "github-env"),
        "GITHUB_PATH": bash_path(tmp_path / "github-path"),
        "FIXTURE_ASSET": artifact,
        "FIXTURE_ARCHIVE": bash_path(fixture),
        "FIXTURE_SUMS": bash_path(sums),
        "FIXTURE_SUMS_ID": "4242",
        "FIXTURE_RELEASE": bash_path(release),
        "FIXTURE_MISE_VERSION": version,
        "FIXTURE_CURL_LOG": bash_path(tmp_path / "curl-log"),
        "SystemRoot": os.environ.get("SystemRoot", ""),
        **(extra_env or {}),
    }
    if engine is not None:
        tools = tmp_path / "tools"
        for directory, command in TOOL_LAYOUT:
            executable = tools / directory / command
            executable.parent.mkdir(parents=True, exist_ok=True)
            executable.write_text(
                f"#!/bin/sh\necho FIXTURE_TOOL {command}\n",
                encoding="utf-8",
                newline="\n",
            )
            executable.chmod(0o755)
        for name, value in (
            ("initial-info", engine.get("initial_info", _engine_info())),
            ("helper-info", engine.get("helper_info", _engine_info())),
            (
                "version",
                json.dumps(engine.get("version", {"Client": {"Version": "5.7.0"}})),
            ),
        ):
            (tmp_path / name).write_text(value, encoding="utf-8")
        env.update(
            FIXTURE_TRACE=bash_path(tmp_path / "trace"),
            FIXTURE_TOOLS=bash_path(tools),
            FIXTURE_BIN=bash_path(bin_dir),
            FIXTURE_BOOTSTRAP=bash_path(runner / "dotfiles-podman-bootstrap"),
            FIXTURE_INITIAL_INFO=bash_path(tmp_path / "initial-info"),
            FIXTURE_HELPER_INFO=bash_path(tmp_path / "helper-info"),
            FIXTURE_VERSION=bash_path(tmp_path / "version"),
            FIXTURE_INFO_SEEN=bash_path(tmp_path / "info-seen"),
            FIXTURE_CLIENT=engine.get("client", "podman version 5.7.0"),
            FIXTURE_CLIENT_RC=str(engine.get("client_rc", 0)),
            FIXTURE_INITIAL_RC=str(engine.get("initial_rc", 0)),
            FIXTURE_HELPER_RC=str(engine.get("helper_rc", 0)),
            FIXTURE_BIN_PATHS_BREAK=engine.get("bin_paths_break", ""),
            FIXTURE_PASTA_GUARD_RC=str(engine.get("pasta_guard_rc", 0)),
        )
        commands.update(
            jq=f'exec {real_utility("jq")} "$@"',
            gzip=f'exec {real_utility("gzip")} "$@"',
            cat=f'exec {real_utility("cat")} "$@"',
            tar="""[ "$#" = 4 ] && [ "$1" = -xzf ] &&
[ "$2" = "$FIXTURE_BOOTSTRAP/$FIXTURE_ASSET" ] &&
[ "$3" = -C ] && [ "$4" = "$FIXTURE_BOOTSTRAP" ] || exit 97
"""
            + f'exec {real_utility("tar")} "$@"',
            install="""[ "$#" = 4 ] && [ "$1" = -m ] && [ "$2" = 0755 ] &&
[ "$3" = "$FIXTURE_BOOTSTRAP/mise/bin/mise" ] &&
[ "$4" = "$FIXTURE_BOOTSTRAP/bin/mise" ] || exit 97
"""
            + f'exec {real_utility("install")} "$@"',
            systemctl='''[ "$*" = '--user start podman.socket' ] || exit 97
printf 'systemctl %s\n' "$*" >> "$FIXTURE_TRACE"''',
            podman="""printf 'podman %s\n' "$*" >> "$FIXTURE_TRACE"
case "$*" in
  --version) printf '%s\n' "$FIXTURE_CLIENT"; exit "$FIXTURE_CLIENT_RC" ;;
  'version --format json') cat "$FIXTURE_VERSION" ;;
  'info --format json')
    if [ -f "$FIXTURE_INFO_SEEN" ]; then
      cat "$FIXTURE_HELPER_INFO"; exit "$FIXTURE_HELPER_RC"
    else
      : > "$FIXTURE_INFO_SEEN"
      cat "$FIXTURE_INITIAL_INFO"
      if [ "$FIXTURE_INITIAL_RC" != 0 ]; then echo FIXTURE_INFO_FAILURE >&2; fi
      exit "$FIXTURE_INITIAL_RC"
    fi ;;
  *) exit 97 ;;
esac""",
            docker="echo FORBIDDEN_HOST_OPERATION >&2; exit 97",
            sudo="""case "$*" in
  '-n apt-get update -y'|'-n apt-get install -y --no-install-recommends uidmap slirp4netns fuse-overlayfs curl ca-certificates') exit 0 ;;
esac
[ "$#" = 4 ] && [ "$1" = -n ] && [ "$2" = mv ] &&
[ "$3" = "$FIXTURE_BIN/docker" ] &&
[ "$4" = "$FIXTURE_BIN/docker.disabled-for-podman-ci" ] || exit 97
printf 'DOCKER_REMOVAL\n' >> "$FIXTURE_TRACE"
shift 2
"""
            + f'exec {real_utility("mv")} "$@"',
        )
    for name, body in commands.items():
        executable = bin_dir / name
        executable.write_text("#!/bin/sh\nset -eu\n" + body + "\n", encoding="utf-8")
        executable.chmod(0o755)
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


@pytest.mark.parametrize(
    "version",
    [
        pytest.param({"Client": {"Version": "5.7.0"}}, id="native-client-only"),
        pytest.param(
            {"Client": {"Version": "5.7.0"}, "Server": {"Version": "5.7.0"}},
            id="remote-client-and-server",
        ),
    ],
)
def test_ci_bootstrap_accepts_native_and_remote_version_shapes_after_engine_validation(
    tmp_path,
    version,
):
    result = _bootstrap_checksum_attempt(
        tmp_path, ["./{artifact}"], engine={"version": version}
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FORBIDDEN_HOST_OPERATION" not in result.stdout + result.stderr
    trace = (tmp_path / "trace").read_text(encoding="utf-8")
    assert "podman --version" in trace
    assert trace.count("podman info --format json") == 2
    # Native/remote version JSON is intentionally not an engine validation API.
    assert "podman version --format json" not in trace
    assert "DOCKER_REMOVAL" in trace
    assert not (tmp_path / "bin/docker").exists()
    assert (tmp_path / "bin/docker.disabled-for-podman-ci").is_file()
    environment = (tmp_path / "github-env").read_text(encoding="utf-8")
    assert "PODMAN_COMPOSE_PROVIDER=podman-compose\n" in environment
    assert (
        "DOTFILES_PODMAN_ENGINE_SOCKET=/run/user/1000/podman/podman.sock\n"
        in environment
    )
    paths = (tmp_path / "github-path").read_text(encoding="utf-8").splitlines()
    assert paths == [
        bash_path(tmp_path / "tools" / directory) for directory, _ in TOOL_LAYOUT
    ] + [bash_path(tmp_path / "runner/dotfiles-podman-bootstrap/bin")]


@pytest.mark.parametrize(
    "engine, diagnostic",
    [
        pytest.param(
            {"client": "podman version 4.9.0"},
            "native Podman client >=5",
            id="client4-engine5",
        ),
        pytest.param(
            {
                "initial_info": _engine_info(version="4.9.0"),
                "helper_info": _engine_info(version="4.9.0"),
            },
            "selected Podman server >=5",
            id="engine4-client5",
        ),
        pytest.param(
            {"helper_info": _engine_info(version="five")},
            "malformed selected Podman server version",
            id="malformed-engine-version",
        ),
        pytest.param(
            {"helper_info": _engine_info(version=5)},
            "selected engine version missing/malformed",
            id="nonstring-engine-version",
        ),
        pytest.param(
            {"helper_info": _engine_info(version=None)},
            "selected engine version missing/malformed",
            id="null-engine-version",
        ),
        pytest.param(
            {"helper_info": '{"version": {}}'},
            "selected engine version missing/malformed",
            id="missing-engine-version",
        ),
        pytest.param(
            {"helper_info": "not json"},
            "selected engine version missing/malformed",
            id="invalid-helper-info-json",
        ),
        pytest.param(
            {"helper_rc": 23},
            "selected engine info query failed",
            id="nonzero-helper-info",
        ),
        pytest.param(
            {"helper_info": _engine_info(socket="/run/user/2000/podman/podman.sock")},
            "does not exactly match",
            id="selected-socket-mismatch",
        ),
        pytest.param(
            {"initial_info": _engine_info(rootless=False)},
            "CI must use rootless Podman",
            id="rootful-engine",
        ),
        pytest.param(
            {"initial_info": "not json"},
            "JSONDecodeError",
            id="invalid-initial-info-json",
        ),
        pytest.param(
            {"initial_rc": 23}, "FIXTURE_INFO_FAILURE", id="nonzero-initial-info"
        ),
        pytest.param(
            {"client_rc": 23},
            "native client version query failed",
            id="failed-helper-client-query",
        ),
    ],
)
def test_ci_bootstrap_rejects_invalid_engine_before_acceptance_effects(
    tmp_path, engine, diagnostic
):
    result = _bootstrap_checksum_attempt(tmp_path, ["./{artifact}"], engine=engine)
    assert result.returncode == engine.get("initial_rc", 1), (
        result.stdout + result.stderr
    )
    assert diagnostic in result.stderr
    assert "FORBIDDEN_HOST_OPERATION" not in result.stdout + result.stderr
    trace = (tmp_path / "trace").read_text(encoding="utf-8")
    assert "DOCKER_REMOVAL" not in trace
    assert (tmp_path / "bin/docker").is_file()
    assert not (tmp_path / "bin/docker.disabled-for-podman-ci").exists()
    environment = (tmp_path / "github-env").read_text(encoding="utf-8")
    assert "DOTFILES_PODMAN_ENGINE_SOCKET=" not in environment


def test_ci_bootstrap_fixture_exposes_working_external_gzip(tmp_path):
    """GNU tar needs gzip on its restricted child PATH, unlike macOS bsdtar."""
    result = _bootstrap_checksum_attempt(tmp_path, ["./{artifact}"], engine={})
    assert result.returncode == 0, result.stdout + result.stderr
    compressor = tmp_path / "bin/gzip"
    assert compressor.is_file(), "restricted tar child PATH must provide gzip"
    archives = list((tmp_path / "runner/dotfiles-podman-bootstrap").glob("*.tar.gz"))
    assert len(archives) == 1
    checked = run_bash(
        compressor,
        "-t",
        bash_path(archives[0]),
        cwd=tmp_path,
        env={
            "PATH": bash_path(tmp_path / "bin"),
            "SystemRoot": os.environ.get("SystemRoot", ""),
        },
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr


def test_a_later_step_finds_every_tool_through_github_path_alone(tmp_path):
    """The next workflow step sees only GITHUB_PATH and GITHUB_ENV: each tool
    must resolve to the bootstrap's own executable, wherever it is laid out."""
    result = _bootstrap_checksum_attempt(tmp_path, ["./{artifact}"], engine={})
    assert result.returncode == 0, result.stdout + result.stderr
    published = (tmp_path / "github-path").read_text(encoding="utf-8").splitlines()
    commands = " ".join(command for _, command in TOOL_LAYOUT)
    step = tmp_path / "later-step.sh"
    # LF only: bash does not read `done\r` as a keyword
    step.write_text(
        f'for c in {commands}; do command -v "$c" || exit 9; "$c"; done\n',
        encoding="utf-8",
        newline="\n",
    )
    later = run_bash(
        step,
        cwd=tmp_path,
        env={
            "PATH": ":".join(reversed(published)),
            "SystemRoot": os.environ.get("SystemRoot", ""),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )
    assert later.returncode == 0, later.stdout + later.stderr
    for directory, command in TOOL_LAYOUT:
        assert bash_path(tmp_path / "tools" / directory / command) in later.stdout
        assert f"FIXTURE_TOOL {command}" in later.stdout


@pytest.mark.parametrize("tool", ["uv", "node", "just", "pypi:podman-compose"])
@pytest.mark.parametrize(
    "breakage, message",
    [
        ("fail", "ci-bootstrap: mise bin-paths {tool} failed"),
        ("empty", "ci-bootstrap: mise bin-paths {tool} printed nothing"),
        ("missing", "ci-bootstrap: {tool}'s bin path"),
        ("second-missing", "ci-bootstrap: {tool}'s bin path"),
    ],
)
def test_bootstrap_stops_when_a_tool_has_no_bin_path(tmp_path, tool, breakage, message):
    result = _bootstrap_checksum_attempt(
        tmp_path, ["./{artifact}"], engine={"bin_paths_break": f"{tool}:{breakage}"}
    )
    assert result.returncode != 0, result.stdout + result.stderr
    assert message.format(tool=tool) in result.stderr, result.stderr
    # it stops before anything reaches the later steps' environment
    github_env = tmp_path / "github-env"
    assert not github_env.exists() or "DOTFILES_PODMAN_ENGINE_SOCKET=" not in (
        github_env.read_text(encoding="utf-8")
    )


def test_bootstrap_runs_the_pasta_guard_before_the_podman_socket(tmp_path):
    result = _bootstrap_checksum_attempt(tmp_path, ["./{artifact}"], engine={})
    assert result.returncode == 0, result.stdout + result.stderr
    trace = (tmp_path / "trace").read_text(encoding="utf-8").splitlines()
    guard = "pasta-guard /etc/apparmor.d/usr.bin.pasta"
    assert trace.count(guard) == 1, trace
    assert trace.index(guard) < trace.index("systemctl --user start podman.socket")


def test_bootstrap_stops_when_the_pasta_guard_fails(tmp_path):
    result = _bootstrap_checksum_attempt(
        tmp_path, ["./{artifact}"], engine={"pasta_guard_rc": 1}
    )
    assert result.returncode != 0, result.stdout + result.stderr
    trace = (tmp_path / "trace").read_text(encoding="utf-8")
    assert "pasta-guard /etc/apparmor.d/usr.bin.pasta" in trace
    assert "systemctl --user start podman.socket" not in trace
    github_env = tmp_path / "github-env"
    environment = github_env.read_text(encoding="utf-8") if github_env.exists() else ""
    assert "DOTFILES_PODMAN_ENGINE_SOCKET=" not in environment


def test_test_emulators_runs_when_the_pasta_guard_changes():
    body = (ROOT / ".github/workflows/test-emulators.yaml").read_text(encoding="utf-8")
    assert body.count("      - '.devcontainer/allow-podman-stop-pasta.sh'\n") == 2


MISE_RELEASE_DOWNLOAD = "https://github.com/jdx/mise/releases/download/"
MISE_API = "https://api.github.com/repos/jdx/mise/releases/"


def _curl_urls(tmp_path):
    log = (tmp_path / "curl-log").read_text(encoding="utf-8").splitlines()
    return [line.removeprefix("URL ") for line in log if line.startswith("URL ")]


def _bootstrap_attempt(tmp_path, *, fail=(), token=None, engine=None):
    extra_env = {"FIXTURE_CURL_FAIL": " ".join(fail)}
    if token is not None:
        extra_env["GITHUB_TOKEN"] = token
    return _bootstrap_checksum_attempt(
        tmp_path, ["./{artifact}"], engine=engine, extra_env=extra_env
    )


def test_bootstrap_fetches_mise_from_jdx_dev_first(tmp_path):
    result = _bootstrap_attempt(tmp_path)
    assert result.returncode == 89, result.stdout + result.stderr
    urls = _curl_urls(tmp_path)
    version = tomllib.loads(
        (ROOT / "config/mise/image-tools.toml").read_text(encoding="utf-8")
    )["bootstrap"]["mise"]
    artifact = f"mise-v{version}-linux-x64-musl.tar.gz"
    assert urls[0] == f"https://mise.jdx.dev/v{version}/{artifact}"
    assert not any(url.startswith(MISE_RELEASE_DOWNLOAD) for url in urls), urls
    # the job log names the route each file took
    assert f"ci-bootstrap: {artifact} from mise.jdx.dev\n" in result.stdout
    assert "ci-bootstrap: SHASUMS256.txt from the GitHub API\n" in result.stdout


def test_bootstrap_never_takes_mise_checksums_from_jdx_dev(tmp_path):
    result = _bootstrap_attempt(tmp_path)
    assert result.returncode == 89, result.stdout + result.stderr
    urls = _curl_urls(tmp_path)
    assert [url for url in urls if url.startswith("https://mise.jdx.dev/")] == [urls[0]]
    assert not urls[0].endswith("SHASUMS256.txt")
    # the checksum file is the release's SHASUMS256.txt asset, by its API id
    assert urls[1:] == [
        MISE_API + "tags/v" + urls[0].split("/")[3][1:],
        MISE_API + "assets/4242",
    ]


def test_bootstrap_falls_back_to_github_when_jdx_dev_fails(tmp_path):
    result = _bootstrap_attempt(tmp_path, fail=["https://mise.jdx.dev/"])
    assert result.returncode == 89, result.stdout + result.stderr
    urls = _curl_urls(tmp_path)
    assert urls[0].startswith("https://mise.jdx.dev/")
    assert urls[1] == MISE_RELEASE_DOWNLOAD + urls[0].removeprefix(
        "https://mise.jdx.dev/"
    )
    assert urls[-1] == MISE_API + "assets/4242"
    assert "ci-bootstrap: mise.jdx.dev failed; downloading" in result.stderr
    assert " from mise.jdx.dev\n" not in result.stdout


def test_bootstrap_falls_back_to_release_download_for_checksums_when_api_fails(
    tmp_path,
):
    result = _bootstrap_attempt(tmp_path, fail=[MISE_API])
    assert result.returncode == 89, result.stdout + result.stderr
    urls = _curl_urls(tmp_path)
    version = urls[0].split("/")[3]
    assert urls[-1] == f"{MISE_RELEASE_DOWNLOAD}{version}/SHASUMS256.txt"
    assert "ci-bootstrap: the GitHub API failed;" in result.stderr
    assert "SHASUMS256.txt from the GitHub API\n" not in result.stdout
    assert not any(url.startswith(MISE_API + "assets/") for url in urls), urls


def test_bootstrap_stops_when_every_checksum_route_fails(tmp_path):
    result = _bootstrap_attempt(tmp_path, fail=[MISE_API, MISE_RELEASE_DOWNLOAD])
    assert result.returncode != 0, result.stdout + result.stderr
    assert "FIXTURE_UNPACK_BOUNDARY" not in result.stdout


def test_bootstrap_still_rejects_a_corrupt_artifact_from_jdx_dev(tmp_path):
    result = _bootstrap_checksum_attempt(tmp_path, ["./{artifact}"], corrupt=True)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "FIXTURE_UNPACK_BOUNDARY" not in result.stdout
    assert _curl_urls(tmp_path)[0].startswith("https://mise.jdx.dev/")


def test_bootstrap_sends_the_github_token_only_to_the_api(tmp_path):
    token = "fixture-token-not-a-secret"
    result = _bootstrap_attempt(tmp_path, token=token)
    assert result.returncode == 89, result.stdout + result.stderr
    log = (tmp_path / "curl-log").read_text(encoding="utf-8").splitlines()
    # never on a command line, where other processes can read it
    assert not [line for line in log if line.startswith("ARGV ") and token in line]
    requests = [line.removeprefix("URL ") for line in log if line.startswith("URL ")]
    for index, url in enumerate(requests):
        start = log.index(f"URL {url}")
        sent = log[start + 1] if start + 1 < len(log) else ""
        has_token = sent == f"STDIN-HEADER Authorization: Bearer {token}"
        assert has_token is url.startswith(MISE_API), (index, url, sent)


def test_bootstrap_curl_retries_and_stays_on_https(tmp_path):
    result = _bootstrap_attempt(tmp_path, fail=["https://mise.jdx.dev/"])
    assert result.returncode == 89, result.stdout + result.stderr
    log = (tmp_path / "curl-log").read_text(encoding="utf-8").splitlines()
    calls = [line for line in log if line.startswith("ARGV ")]
    assert len(calls) == 4, calls
    for call in calls:
        assert call.startswith(
            "ARGV --proto =https --tlsv1.2 -fsSL --retry 3 --retry-all-errors"
            " --max-time 120 "
        ), call


def test_bootstrap_reroutes_only_uv_downloads(tmp_path):
    result = _bootstrap_attempt(tmp_path, engine={})
    assert result.returncode == 0, result.stdout + result.stderr
    recorded = (tmp_path / "trace.url-replacements").read_text(encoding="utf-8")
    assert json.loads(recorded) == {
        "regex:^https://github\\.com/astral-sh/uv/releases/download/": (
            "https://releases.astral.sh/github/uv/releases/download/"
        )
    }
    environment = (tmp_path / "github-env").read_text(encoding="utf-8")
    assert "MISE_URL_REPLACEMENTS" not in environment


def _workflow_step(workflow, run):
    """The text of the one step whose `run:` is exactly `run`."""
    body = (ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8")
    steps = re.split(r"(?m)^      - ", body.split("\n    steps:\n", 1)[1])
    matches = [
        step for step in steps if re.search(rf"(?m)^\s+run: {re.escape(run)}$", step)
    ]
    assert len(matches) == 1, (workflow, matches)
    return matches[0]


@pytest.mark.parametrize("workflow", ["test-just.yaml", "test-emulators.yaml"])
def test_bootstrap_step_itself_gets_the_github_token(workflow):
    step = _workflow_step(workflow, "bash .devcontainer/ci-bootstrap.sh")
    env = step.split("\n        env:\n", 1)
    assert len(env) == 2, step
    assert "          GITHUB_TOKEN: ${{ github.token }}\n" in env[1], step
