"""Public root recipes must use Podman without a Docker fallback."""

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX recipe boundary; Windows dispatch is checked separately",
)


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("bash", "sh", "jq", "xargs", "grep"):
        executable = shutil.which(name)
        assert executable, f"fixture needs {name}"
        path = bin_dir / name
        path.write_text(
            f'#!/bin/sh\nexec {shlex.quote(executable)} "$@"\n',
            encoding="utf-8",
            newline="\n",
        )
        path.chmod(0o755)
    podman = bin_dir / "podman"
    podman.write_text(
        "#!/bin/sh\n"
        'echo "$*" >> "$HOME/podman.log"\n'
        'case "$*" in\n'
        '  "info --format json")\n'
        '    [ "$MODE" != engine_error ] || exit 17\n'
        '    if [ "$MODE" = malformed_info ]; then echo invalid; else\n'
        '      printf \'%s\\n\' \'{"host":{"remoteSocket":{"path":"unix:///run/user/501/podman/podman.sock"}}}\'\n'
        "    fi\n"
        "    ;;\n"
        '  compose*) printf \'%s\\n\' "$PODMAN_COMPOSE_PROVIDER" > "$HOME/provider.log"; [ "$MODE" != compose_error ] || exit 27 ;;\n'
        '  "network inspect shared-otel-net") ;;\n'
        '  "ps -q")\n'
        '    [ "$MODE" != engine_error ] || exit 17\n'
        '    [ "$MODE" = empty ] || echo abc123\n'
        "    ;;\n"
        '  "inspect abc123")\n'
        '    [ "$MODE" != inspect_error ] || exit 18\n'
        '    printf \'%s\\n\' \'[{"Name":"/fixture","NetworkSettings":{"Ports":{"5432/tcp":[{"HostIp":"127.0.0.1","HostPort":"15432"}]}}}]\'\n'
        "    ;;\n"
        "  *) exit 99 ;;\n"
        "esac\n",
        encoding="utf-8",
        newline="\n",
    )
    podman.chmod(0o755)
    docker = bin_dir / "docker"
    docker.write_text(
        '#!/bin/sh\necho forbidden >> "$HOME/docker.log"; exit 99\n',
        encoding="utf-8",
        newline="\n",
    )
    docker.chmod(0o755)
    return tmp_path


def _run(
    sandbox: Path,
    mode: str = "one",
    recipe: str = "check-podmanport",
    *,
    args: tuple[str, ...] = (),
    project: Path | None = None,
    justfile: Path | None = None,
    env_overrides: dict[str, str] | None = None,
):
    just = shutil.which("just")
    assert just, "just is required for public recipe verification"
    env = os.environ.copy()
    for name in ("BASH_ENV", "ENV"):
        env.pop(name, None)
    env.update(
        HOME=str(sandbox),
        PATH=str(sandbox / "bin"),
        MODE=mode,
        PODMAN_COMPOSE_PROVIDER="docker-compose",
    )
    env.update(env_overrides or {})
    workdir = project or ROOT
    result = subprocess.run(
        [
            just,
            "--justfile",
            str(justfile or ROOT / "justfile"),
            "--working-directory",
            str(workdir),
            recipe,
            *args,
        ],
        cwd=workdir,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=15,
    )
    assert not (sandbox / "docker.log").exists(), "Docker must never be invoked"
    return result


@pytest.fixture
def test_project(sandbox: Path) -> Path:
    project = sandbox / "project"
    scripts = project / ".devcontainer"
    scripts.mkdir(parents=True)
    (scripts / "require-podman-socket.sh").write_text(
        '[ "$DOTFILES_PODMAN_ENGINE_SOCKET" = /run/user/501/podman/podman.sock ]\n',
        encoding="utf-8",
    )
    (sandbox / "bin" / "mise").write_text(
        '#!/bin/sh\n[ "$1 $2" = "exec --" ] || exit 95\nshift 2\nexec "$@"\n',
        encoding="utf-8",
        newline="\n",
    )
    (sandbox / "bin" / "mise").chmod(0o755)
    uv = (
        f"#!{sys.executable}\n"
        "import json, os, subprocess, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "if args[:3] == ['run', '--frozen', 'python']:\n"
        "    raise SystemExit(subprocess.run([sys.executable, *args[3:]], check=False).returncode)\n"
        "if 'pytest' not in args: raise SystemExit(96)\n"
        "Path(os.environ['HOME'], 'pytest.json').write_text(json.dumps({\n"
        "    'args': args, 'provider': os.environ.get('PODMAN_COMPOSE_PROVIDER'),\n"
        "    'socket': os.environ.get('DOTFILES_PODMAN_ENGINE_SOCKET'),\n"
        "}), encoding='utf-8')\n"
        "raise SystemExit(21 if os.environ['MODE'] == 'pytest_error' else 0)\n"
    )
    for name in ("uv", "uvx"):
        path = sandbox / "bin" / name
        path.write_text(uv, encoding="utf-8", newline="\n")
        path.chmod(0o755)
    return project


@pytest.mark.parametrize("mode", ["one", "pytest_error"])
def test_installer_recipe_requires_frozen_acceptance_without_raw_build_context(
    sandbox: Path, test_project: Path, mode: str
) -> None:
    result = _run(sandbox, recipe="test-install", project=test_project, mode=mode)
    assert (result.returncode == 0) == (mode == "one"), result.stdout + result.stderr
    receipt = json.loads((sandbox / "pytest.json").read_text(encoding="utf-8"))
    assert receipt["args"] == [
        "run",
        "--frozen",
        "--group",
        "dev",
        "pytest",
        "-q",
        "tests/test_install.py",
    ]
    assert not (sandbox / "podman.log").exists(), "fixture must own safe build context"


@pytest.mark.parametrize(
    ("recipe", "args"), [("test", ()), ("test-mark", ("validate",))]
)
def test_sandbox_recipe_uses_selected_socket_and_frozen_dependencies(
    sandbox: Path, test_project: Path, recipe: str, args: tuple[str, ...]
) -> None:
    result = _run(sandbox, recipe=recipe, args=args, project=test_project)
    assert result.returncode == 0, result.stdout + result.stderr
    audit = json.loads((sandbox / "pytest.json").read_text(encoding="utf-8"))
    assert audit["provider"] == "podman-compose"
    assert audit["socket"] == "/run/user/501/podman/podman.sock"
    assert audit["args"][:5] == ["run", "--frozen", "--group", "dev", "pytest"]
    if recipe == "test":
        assert "tests/test_sync_agents.py" in audit["args"]
    else:
        assert audit["args"][audit["args"].index("-m") + 1] == "validate"
    assert (sandbox / "podman.log").read_text(encoding="utf-8").splitlines() == [
        "info --format json"
    ]


@pytest.mark.parametrize("recipe,args", [("test", ()), ("test-mark", ("validate",))])
@pytest.mark.parametrize("mode", ["engine_error", "malformed_info", "pytest_error"])
def test_required_sandbox_failures_cannot_be_reported_as_success(
    sandbox: Path,
    test_project: Path,
    recipe: str,
    args: tuple[str, ...],
    mode: str,
) -> None:
    result = _run(sandbox, recipe=recipe, args=args, project=test_project, mode=mode)
    assert result.returncode != 0
    if mode != "pytest_error":
        assert not (sandbox / "pytest.json").exists()


def test_empty_marker_fails_before_any_engine_or_pytest_probe(
    sandbox: Path, test_project: Path
) -> None:
    result = _run(sandbox, recipe="test-mark", project=test_project)
    assert result.returncode != 0
    assert not (sandbox / "podman.log").exists()
    assert not (sandbox / "pytest.json").exists()


@pytest.fixture
def model_project(sandbox: Path, test_project: Path) -> Path:
    models = test_project / "scripts" / "spec"
    models.mkdir(parents=True)
    (models / "podman_image_gc.qnt").write_text("module fixture {}\n", encoding="utf-8")
    (sandbox / "bin" / "mise").write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\nfrom pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "with Path(os.environ['HOME'], 'mise.jsonl').open('a', encoding='utf-8') as f:\n"
        "    f.write(json.dumps(args) + '\\n')\n"
        "cmd = args[args.index('--') + 1:]\n"
        "os.execvp(cmd[0], cmd)\n",
        encoding="utf-8",
        newline="\n",
    )
    checker = sandbox / "bin" / "quint"
    checker.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\nfrom pathlib import Path\n"
        "with Path(os.environ['HOME'], 'quint.jsonl').open('a', encoding='utf-8') as f:\n"
        "    f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "raise SystemExit(31 if os.environ['MODE'] == sys.argv[1] + '_error' else 0)\n",
        encoding="utf-8",
        newline="\n",
    )
    checker.chmod(0o755)
    return test_project


def test_formal_gate_runs_pinned_models_then_actual_script_simulation(
    sandbox: Path, model_project: Path
) -> None:
    result = _run(sandbox, recipe="spec-check", project=model_project)
    assert result.returncode == 0, result.stdout + result.stderr
    checks = [
        json.loads(line)
        for line in (sandbox / "quint.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    model = "scripts/spec/podman_image_gc.qnt"
    assert checks == [
        ["typecheck", model],
        ["test", model, "--backend", "typescript", "--max-samples", "100"],
        [
            "run",
            model,
            "--backend",
            "typescript",
            "--invariant",
            "Safety",
            "--max-samples",
            "1000",
            "--max-steps",
            "12",
            "--seed",
            "565",
            "--verbosity",
            "1",
        ],
    ]
    tools = [
        json.loads(line)
        for line in (sandbox / "mise.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert all(
        row[:4] == ["x", "npm:@informalsystems/quint@0.33.0", "--", "quint"]
        for row in tools[:3]
    )
    audit = json.loads((sandbox / "pytest.json").read_text(encoding="utf-8"))
    assert audit["args"][:5] == ["run", "--frozen", "--group", "dev", "pytest"]
    assert "tests/unit/test_podman_gc_simulation.py" in audit["args"]
    assert not (sandbox / "podman.log").exists()


@pytest.mark.parametrize(
    "mode", ["typecheck_error", "test_error", "run_error", "pytest_error"]
)
def test_formal_gate_does_not_suppress_checker_or_simulation_failures(
    sandbox: Path, model_project: Path, mode: str
) -> None:
    result = _run(sandbox, recipe="spec-check", project=model_project, mode=mode)
    assert result.returncode != 0
    if mode != "pytest_error":
        assert not (sandbox / "pytest.json").exists()


def test_formal_gate_refuses_an_empty_model_inventory(
    sandbox: Path, model_project: Path
) -> None:
    (model_project / "scripts/spec/podman_image_gc.qnt").unlink()
    result = _run(sandbox, recipe="spec-check", project=model_project)
    assert result.returncode != 0
    assert not (sandbox / "quint.jsonl").exists()
    assert not (sandbox / "pytest.json").exists()


def test_strict_check_includes_the_required_formal_gate() -> None:
    just = shutil.which("just")
    assert just
    result = subprocess.run(
        [just, "--justfile", str(ROOT / "justfile"), "--dump", "--dump-format", "json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    body = json.loads(result.stdout)["recipes"]["check"]["body"]
    assert ["@just spec-check"] in body


@pytest.fixture
def emulator_project(sandbox: Path) -> Path:
    scripts = sandbox / "emulator" / "scripts"
    scripts.mkdir(parents=True)
    for name in ("prebuild-images", "start-services", "wait-for-services"):
        (scripts / f"{name}.sh").write_text(
            f'printf \'%s\\n\' "$*" >> "$HOME/{name}.log"\n',
            encoding="utf-8",
            newline="\n",
        )
    return sandbox


def test_emulator_cleanup_uses_native_provider_and_propagates_failure(
    sandbox: Path, emulator_project: Path
) -> None:
    result = _run(sandbox, recipe="emu-clean", project=emulator_project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (sandbox / "provider.log").read_text(
        encoding="utf-8"
    ).strip() == "podman-compose"
    assert (sandbox / "podman.log").read_text(encoding="utf-8").splitlines() == [
        "compose --in-pod=false down -v --remove-orphans"
    ]
    result = _run(
        sandbox, recipe="emu-clean", project=emulator_project, mode="compose_error"
    )
    assert result.returncode != 0


@pytest.mark.parametrize(
    "override",
    [
        {"DOTFILES_PODMAN_RUN_MANIFEST": "controlled.json"},
        {"DOTFILES_E2E_REQUIRED": "1"},
    ],
)
@pytest.mark.parametrize(
    "recipe", ["emu-clean", "emu-start", "emu-start-full", "emu-prebuild"]
)
def test_canonical_emulator_cleanup_refuses_isolated_mode_before_shared_resources(
    sandbox: Path, emulator_project: Path, override: dict[str, str], recipe: str
) -> None:
    result = _run(
        sandbox, recipe=recipe, project=emulator_project, env_overrides=override
    )
    assert result.returncode != 0
    assert not (sandbox / "podman.log").exists()


@pytest.mark.parametrize(
    ("recipe", "images"),
    [
        ("emu-start", "firebase-emulator postgres"),
        ("emu-start-full", "a2a-inspector firebase-emulator mcp-inspector postgres"),
    ],
)
def test_emulator_start_uses_native_cleanup_before_existing_scripts(
    sandbox: Path, emulator_project: Path, recipe: str, images: str
) -> None:
    result = _run(sandbox, recipe=recipe, project=emulator_project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (sandbox / "podman.log").read_text(encoding="utf-8").splitlines() == [
        "compose --in-pod=false down -v --remove-orphans"
    ]
    assert (sandbox / "prebuild-images.log").read_text(
        encoding="utf-8"
    ).strip() == images
    assert (sandbox / "start-services.log").exists()
    assert (sandbox / "wait-for-services.log").exists()


@pytest.mark.parametrize("recipe", ["emu-start", "emu-start-full"])
def test_emulator_start_aborts_before_build_when_cleanup_fails(
    sandbox: Path, emulator_project: Path, recipe: str
) -> None:
    result = _run(
        sandbox, recipe=recipe, project=emulator_project, mode="compose_error"
    )
    assert result.returncode != 0
    assert not (sandbox / "prebuild-images.log").exists()
    assert not (sandbox / "start-services.log").exists()


@pytest.fixture
def telemetry_project(sandbox: Path) -> Path:
    (sandbox / "telemetry").mkdir()
    return sandbox


@pytest.mark.parametrize(
    ("recipe", "args", "operation"),
    [
        ("tel-up", (), "up -d"),
        ("tel-down", (), "down"),
        ("tel-check", (), "ps"),
        ("tel-logs", ("fixture",), "logs -f fixture"),
    ],
)
def test_root_telemetry_recipes_use_native_podman_and_explicit_provider(
    sandbox: Path,
    telemetry_project: Path,
    recipe: str,
    args: tuple[str, ...],
    operation: str,
) -> None:
    result = _run(sandbox, recipe=recipe, args=args, project=telemetry_project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (sandbox / "provider.log").read_text(
        encoding="utf-8"
    ).strip() == "podman-compose"
    commands = (sandbox / "podman.log").read_text(encoding="utf-8").splitlines()
    expected = [f"compose --in-pod=false {operation}"]
    if recipe == "tel-up":
        expected.insert(0, "network inspect shared-otel-net")
    assert commands == expected


@pytest.mark.parametrize("recipe", ["tel-up", "tel-down", "tel-check", "tel-logs"])
@pytest.mark.parametrize(
    "override",
    [
        {"DOTFILES_PODMAN_RUN_MANIFEST": "controlled.json"},
        {"DOTFILES_E2E_REQUIRED": "1"},
    ],
)
def test_canonical_telemetry_recipes_refuse_isolated_mode_before_shared_resources(
    sandbox: Path, telemetry_project: Path, recipe: str, override: dict[str, str]
) -> None:
    result = _run(
        sandbox, recipe=recipe, project=telemetry_project, env_overrides=override
    )
    assert result.returncode != 0
    assert not (sandbox / "podman.log").exists()


@pytest.fixture
def selfcheck_project(sandbox: Path) -> Path:
    (sandbox / "bin" / "docker").unlink()
    just = sandbox / "bin" / "just"
    just.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$HOME/just.log"\n'
        'case "$*" in\n'
        '  --version) echo "just 1.59.0" ;;\n'
        '  doctor) echo "Doctor fixture healthy" ;;\n'
        '  validate-path-duplicates) echo "No duplicates" ;;\n'
        '  "test-mark validate") [ "$MODE" != pytest_error ] || exit 21 ;;\n'
        "  *) exit 95 ;;\n"
        "esac\n",
        encoding="utf-8",
        newline="\n",
    )
    just.chmod(0o755)
    return sandbox


def test_requested_selfcheck_tests_use_the_required_podman_marker_path(
    sandbox: Path, selfcheck_project: Path
) -> None:
    result = _run(
        sandbox, recipe="self-check", args=("yes",), project=selfcheck_project
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (sandbox / "just.log").read_text(encoding="utf-8").splitlines()[
        -1
    ] == "test-mark validate"
    assert "skip tests" not in result.stdout


def test_requested_selfcheck_tests_propagate_failure(
    sandbox: Path, selfcheck_project: Path
) -> None:
    result = _run(
        sandbox,
        recipe="self-check",
        args=("yes",),
        project=selfcheck_project,
        mode="pytest_error",
    )
    assert result.returncode != 0
    assert "tests: validate failed" in result.stdout


@pytest.mark.parametrize(
    ("recipe", "operation"),
    [("trace-up", "up -d jaeger"), ("trace-down", "stop jaeger")],
)
def test_scaffold_observability_uses_only_the_declared_podman_provider(
    sandbox: Path, recipe: str, operation: str
) -> None:
    result = _run(
        sandbox,
        recipe=recipe,
        project=sandbox,
        justfile=ROOT / "templates/agent-baseline/justfile",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (sandbox / "provider.log").read_text(
        encoding="utf-8"
    ).strip() == "podman-compose"
    assert (sandbox / "podman.log").read_text(encoding="utf-8").splitlines() == [
        f"compose --in-pod=false -f compose.yaml {operation}"
    ]


def test_port_recipe_queries_the_selected_podman_engine(sandbox: Path) -> None:
    result = _run(sandbox)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "name": "/fixture",
        "ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "15432"}]},
    }
    assert (sandbox / "podman.log").read_text(encoding="utf-8").splitlines() == [
        "ps -q",
        "inspect abc123",
    ]


@pytest.mark.parametrize("mode", ["engine_error", "inspect_error"])
def test_port_recipe_propagates_failures_without_docker_fallback(
    sandbox: Path, mode: str
) -> None:
    result = _run(sandbox, mode=mode)
    assert result.returncode != 0


def test_port_recipe_keeps_empty_inventory_json(sandbox: Path) -> None:
    result = _run(sandbox, mode="empty")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []
    assert (sandbox / "podman.log").read_text(encoding="utf-8").splitlines() == [
        "ps -q"
    ]


def test_legacy_recipe_name_is_only_a_podman_compatibility_alias(sandbox: Path) -> None:
    result = _run(sandbox, recipe="check-dockerport")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["name"] == "/fixture"
    assert (sandbox / "podman.log").read_text(encoding="utf-8").splitlines() == [
        "ps -q",
        "inspect abc123",
    ]


@pytest.fixture
def ci_emu_project(sandbox: Path) -> Path:
    """Copy public dispatch; all run directories and process fakes stay disposable."""
    project = sandbox / "ci project"
    (project / "emulator").mkdir(parents=True)
    shutil.copyfile(ROOT / "justfile", project / "justfile")
    for name in ("mkdir", "mktemp"):
        executable = shutil.which(name)
        assert executable
        (sandbox / "bin" / name).symlink_to(executable)
    boundary = (
        f"#!{sys.executable}\n"
        "import json, os, signal, sys, time\nfrom pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "tool = Path(sys.argv[0]).name\n"
        "if tool == 'mise':\n"
        "    assert args[:2] == ['exec', '--']\n"
        "    os.execvp(args[2], args[2:])\n"
        "mode = os.environ['MODE']\n"
        "if tool == 'just':\n"
        "    assert args == ['emu-lint']\n"
        "    action = 'lint'\n"
        "else:\n"
        "    assert args[:4] == ['run', '--frozen', '--group', 'dev']\n"
        "    cmd = args[4:]\n"
        "    if cmd[0] == 'pytest':\n"
        "        action = {'tests/': 'unit', 'tests/e2e': 'e2e', 'tests/test_postgres18_features.py': 'postgres'}[cmd[1]]\n"
        "    else:\n"
        "        assert cmd[:3] == ['python', '-m', 'tests.utils.isolation']\n"
        "        action = cmd[3]\n"
        "        manifest = Path(cmd[cmd.index('--manifest') + 1])\n"
        "        assert str(manifest) == os.environ['DOTFILES_PODMAN_RUN_MANIFEST']\n"
        "with Path(os.environ['HOME'], 'ci-emu.jsonl').open('a', encoding='utf-8') as f:\n"
        "    f.write(json.dumps({'action': action, 'args': args, 'cwd': str(Path.cwd()),\n"
        "        'env': {k: os.environ.get(k) for k in ['DOTFILES_E2E_REQUIRED',\n"
        "        'DOTFILES_PODMAN_RUN_MANIFEST', 'PODMAN_COMPOSE_PROVIDER', 'TMPDIR',\n"
        "        'UV_PROJECT_ENVIRONMENT', 'UV_NO_SYNC', 'UV_OFFLINE']}}) + '\\n')\n"
        "if action == 'prepare' and mode != 'fail_prepare_before':\n"
        "    assert not manifest.exists()\n"
        "    manifest.write_text('{}', encoding='utf-8')\n"
        "    (manifest.parent / 'snapshot').mkdir()\n"
        "if mode in {'INT_' + action, 'TERM_' + action}:\n"
        "    os.kill(os.getppid(), signal.SIGINT if mode.startswith('INT') else signal.SIGTERM)\n"
        "    time.sleep(0.05)\n"
        "    (manifest.parent / 'creator-stopped').write_text(action, encoding='utf-8')\n"
        "if mode == 'fail_prepare_before' and action == 'prepare': raise SystemExit(41)\n"
        "if mode == 'fail_' + action: raise SystemExit(42)\n"
        "if mode == 'fail_wait_and_cleanup' and action in {'wait', 'cleanup'}:\n"
        "    raise SystemExit(43 if action == 'wait' else 44)\n"
    )
    for name in ("mise", "uv", "just"):
        path = sandbox / "bin" / name
        path.write_text(boundary, encoding="utf-8", newline="\n")
        path.chmod(0o755)
    return project


def _ci_emu(sandbox: Path, project: Path, mode: str = "one", **overrides):
    result = _run(
        sandbox,
        recipe="ci-emu",
        mode=mode,
        project=project,
        justfile=project / "justfile",
        env_overrides={
            "DOTFILES_PODMAN_RUN_MANIFEST": "",
            "UV_PROJECT_ENVIRONMENT": str(sandbox / "existing-emulator-env"),
            "UV_NO_SYNC": "1",
            "UV_OFFLINE": "1",
            "MISE_AUTO_INSTALL": "false",
            "MISE_EXEC_AUTO_INSTALL": "false",
            **overrides,
        },
    )
    log = sandbox / "ci-emu.jsonl"
    events = (
        [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        if log.exists()
        else []
    )
    assert not (sandbox / "podman.log").exists(), (
        "only mocked uv owns the engine boundary"
    )
    return result, events


def test_ci_emu_public_dispatch_isolated_order_manifest_and_emulator_project(
    sandbox: Path,
    ci_emu_project: Path,
) -> None:
    result, events = _ci_emu(sandbox, ci_emu_project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert [e["action"] for e in events] == [
        "lint",
        "prepare",
        "start",
        "wait",
        "unit",
        "e2e",
        "postgres",
        "cleanup",
    ]
    manifests = {e["env"]["DOTFILES_PODMAN_RUN_MANIFEST"] for e in events[1:]}
    assert len(manifests) == 1
    manifest = Path(manifests.pop())
    assert manifest.parent.parent == ci_emu_project / ".pi/tasks"
    assert manifest.name == "run.json"
    assert manifest.is_file()
    for event in events[1:]:
        assert event["cwd"] == str(ci_emu_project / "emulator")
        assert event["env"]["DOTFILES_E2E_REQUIRED"] == "1"
        assert event["env"]["PODMAN_COMPOSE_PROVIDER"] == "podman-compose"
        assert event["env"]["TMPDIR"] == str(manifest.parent / "tmp")
        assert event["env"]["UV_PROJECT_ENVIRONMENT"] == str(
            sandbox / "existing-emulator-env"
        )
        assert event["env"]["UV_NO_SYNC"] == event["env"]["UV_OFFLINE"] == "1"
    assert events[1]["args"][7:] == [
        "prepare",
        "--source",
        str(ci_emu_project),
        "--manifest",
        str(manifest),
        "--services",
        "firebase-emulator,spanner-emulator,pgadapter,postgres",
        "--telemetry",
    ]
    assert [e["args"][5:] for e in events[4:7]] == [
        ["tests/", "-v", "-m", "not e2e"],
        ["tests/e2e", "-v", "-m", "e2e", "-ra"],
        [
            "tests/test_postgres18_features.py",
            "tests/test_postgres18_emulator.py",
            "-v",
        ],
    ]
    assert (manifest.parent / "tmp").is_dir()
    assert (manifest.parent / "snapshot").is_dir(), (
        "wrapper must not remove recovery paths"
    )


def test_ci_emu_refuses_inherited_manifest_before_actions(
    sandbox: Path, ci_emu_project: Path
) -> None:
    result, events = _ci_emu(
        sandbox, ci_emu_project, DOTFILES_PODMAN_RUN_MANIFEST="other.json"
    )
    assert result.returncode != 0
    assert events == []
    assert not (ci_emu_project / ".pi").exists()


@pytest.mark.parametrize(
    "action",
    [
        "lint",
        "prepare_before",
        "prepare",
        "start",
        "wait",
        "unit",
        "e2e",
        "postgres",
        "cleanup",
        "wait_and_cleanup",
    ],
)
def test_ci_emu_preserves_failures_and_only_cleans_existing_manifest(
    sandbox: Path,
    ci_emu_project: Path,
    action: str,
) -> None:
    result, events = _ci_emu(sandbox, ci_emu_project, "fail_" + action)
    assert result.returncode != 0
    names = [e["action"] for e in events]
    expected = [
        "lint",
        "prepare",
        "start",
        "wait",
        "unit",
        "e2e",
        "postgres",
        "cleanup",
    ]
    failed = (
        "prepare"
        if action == "prepare_before"
        else "wait"
        if action == "wait_and_cleanup"
        else action
    )
    prefix = expected[: expected.index(failed) + 1]
    if action not in {"lint", "prepare_before", "cleanup"}:
        prefix += ["cleanup"]
    assert names == prefix
    # just exposes the recipe's original exit status in its diagnostic.
    code = (
        41 if action == "prepare_before" else 43 if action == "wait_and_cleanup" else 42
    )
    assert f"exit code {code}" in result.stderr
    if action in {"cleanup", "wait_and_cleanup"}:
        assert "run.json" in result.stderr
    if action not in {"lint", "prepare_before"}:
        manifest = Path(events[1]["env"]["DOTFILES_PODMAN_RUN_MANIFEST"])
        assert manifest.is_file()
        assert (manifest.parent / "snapshot").is_dir()


@pytest.mark.parametrize("signal_name,code", [("INT", 130), ("TERM", 143)])
@pytest.mark.parametrize("action", ["prepare", "start"])
def test_ci_emu_actual_signals_retain_journal_without_competing_cleanup(
    sandbox: Path,
    ci_emu_project: Path,
    signal_name: str,
    code: int,
    action: str,
) -> None:
    result, events = _ci_emu(sandbox, ci_emu_project, signal_name + "_" + action)
    assert result.returncode != 0
    assert f"exit code {code}" in result.stderr
    assert [e["action"] for e in events] == (
        ["lint", "prepare"] if action == "prepare" else ["lint", "prepare", "start"]
    )
    manifest = Path(events[1]["env"]["DOTFILES_PODMAN_RUN_MANIFEST"])
    assert manifest.is_file()
    assert (manifest.parent / "snapshot").is_dir()
    assert (manifest.parent / "creator-stopped").read_text(encoding="utf-8") == action
    assert str(manifest) in result.stderr


def test_ci_emu_allocates_a_fresh_owned_manifest_each_invocation(
    sandbox: Path,
    ci_emu_project: Path,
) -> None:
    first, events = _ci_emu(sandbox, ci_emu_project)
    assert first.returncode == 0, first.stderr
    first_manifest = events[1]["env"]["DOTFILES_PODMAN_RUN_MANIFEST"]
    second, events = _ci_emu(sandbox, ci_emu_project)
    assert second.returncode == 0, second.stderr
    prepares = [e for e in events if e["action"] == "prepare"]
    assert len(prepares) == 2
    second_manifest = prepares[1]["env"]["DOTFILES_PODMAN_RUN_MANIFEST"]
    assert second_manifest != first_manifest
    assert Path(first_manifest).is_file() and Path(second_manifest).is_file()
