"""Static checks that keep the emulator's side files in step with compose.yaml.

The env example, the local `ci-emu` gate, and the published ports each restate
something compose.yaml or the emulator workflow already decides. These tests
read both sides, so a port or a step that changes in one place cannot leave the
other describing a stack that no longer exists.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EMULATOR = ROOT / "emulator"
WORKFLOW = ROOT / ".github" / "workflows" / "test-emulators.yaml"

# A published port is `"127.0.0.1:<host>:<container>"`, where <host> is a
# number or `${VAR:-<default>}`.
_PUBLISHED = re.compile(r'"127\.0\.0\.1:(?:\$\{\w+:-(\d+)\}|(\d+)):(\d+)"')
_ENV_LOCALHOST = re.compile(r"^export (\w+)=localhost:(\d+)\s*$", re.MULTILINE)


def _published_host_ports() -> set[str]:
    text = (EMULATOR / "compose.yaml").read_text(encoding="utf-8")
    return {default or fixed for default, fixed, _ in _PUBLISHED.findall(text)}


def test_env_example_localhost_ports_are_published_host_ports() -> None:
    published = _published_host_ports()
    env = (EMULATOR / ".env.local.example").read_text(encoding="utf-8")
    pairs = _ENV_LOCALHOST.findall(env)
    assert pairs, "the env example names no localhost:<port> address"
    stale = {name: port for name, port in pairs if port not in published}
    assert not stale, (
        f"{stale} point at ports compose.yaml does not publish on the host. "
        "Use the default host port from emulator/compose.yaml."
    )


_SERVICES = "firebase-emulator,spanner-emulator,pgadapter,postgres"
_MANIFEST = "$DOTFILES_PODMAN_RUN_MANIFEST"
_SELECTIONS = [
    ["tests/", "-v", "-m", "not e2e"],
    ["tests/e2e", "-v", "-m", "e2e", "-ra"],
    ["tests/test_postgres18_features.py", "tests/test_postgres18_emulator.py", "-v"],
]


def _local_ci_emu(justfile: Path = ROOT / "justfile") -> str:
    if shutil.which("just") is None:
        pytest.skip("needs just to dump recipes")
    dump = subprocess.run(
        ["just", "--justfile", str(justfile), "--dump", "--dump-format", "json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    data = json.loads(dump.stdout)
    lines = []
    for fragments in data["recipes"]["ci-emu"]["body"]:
        line = ""
        for part in fragments:
            if isinstance(part, str):
                line += part
            elif part == [["variable", "UV_RUN"]]:
                line += data["assignments"]["UV_RUN"]["value"]
            elif part == [["call", "justfile_directory"]]:
                line += "REPO"
            else:
                raise AssertionError(f"unsupported just interpolation: {part!r}")
        lines.append(line)
    return "\n".join(lines)


def _isolation_contract(
    text: str, *, local: bool
) -> tuple[str, tuple[str, ...], list[list[str]]]:
    """Recognize only the reviewed invocation grammar; never compare empty sets.

    Cleanup's definition precedes execution locally; Actions runs it in a later
    always-step. Public dispatch tests independently check actual execution order.
    """
    assert text.strip(), "empty isolation contract"
    assert not re.search(
        r"\bemu-(?:start(?:-full)?|clean|prebuild|test-fast|test-e2e)\b|scripts/[\w-]+\.sh",
        # CI bootstrap is infrastructure, not part of the lifecycle contract.
        text.replace("bash .devcontainer/ci-bootstrap.sh", ""),
    ), "shared lifecycle/script inserted"
    if local:
        assert "export DOTFILES_E2E_REQUIRED=1" in text
        assert "export PODMAN_COMPOSE_PROVIDER=podman-compose" in text
        assert 'export DOTFILES_PODMAN_RUN_MANIFEST="$run_dir/run.json"' in text
        assert 'cd "$repo/emulator"' in text
        assert "trap cleanup EXIT" in text
        assert "trap 'interrupt 130' INT" in text
        assert "trap 'interrupt 143' TERM" in text
    else:
        assert re.search(r"DOTFILES_E2E_REQUIRED: ['\"]1['\"]", text)
        assert "PODMAN_COMPOSE_PROVIDER: podman-compose" in text
        assert (
            "DOTFILES_PODMAN_RUN_MANIFEST: ${{ github.workspace }}/podman-run.json"
            in text
        )
        assert "working-directory: emulator" in text
        assert re.search(
            r"if: always\(\)\n\s+run: \|\n(?:(?!      - name:).)*isolation cleanup",
            text,
            re.DOTALL,
        )
    lifecycle = []
    selections = []
    execution = []
    # Join shell continuations before shlex; do not split marker expressions.
    for line in text.replace("\\\n", " ").splitlines():
        line = line.strip()
        line = line.removeprefix("run: ")
        if "uv run" not in line:
            continue
        tokens = shlex.split(line)
        if local:
            assert tokens[:7] == [
                "mise",
                "exec",
                "--",
                "uv",
                "run",
                "--frozen",
                "--group",
            ]
            assert tokens[7] == "dev"
            args = tokens[8:]
        else:
            assert tokens[:3] == ["uv", "run", "--frozen"]
            args = tokens[3:]
            if args[0] in {"--only-group", "--group"}:
                assert args[1] == "lint"
                continue
        if args[:3] == ["python", "-m", "tests.utils.isolation"]:
            operation, *options = args[3:]
            if operation == "prepare":
                assert options == [
                    "--source",
                    "$repo" if local else "$GITHUB_WORKSPACE",
                    "--manifest",
                    _MANIFEST,
                    "--services",
                    _SERVICES,
                    "--telemetry",
                ]
            else:
                assert operation in {"start", "wait", "cleanup", "status"}
                assert options == ["--manifest", _MANIFEST]
            if operation != "status":
                lifecycle.append(operation)
            if operation in {"prepare", "start", "wait"}:
                execution.append(operation)
        else:
            assert args[0] == "pytest", f"unrecognized invocation: {args}"
            args = args[1:]
            if not local and "|" in args:
                pipe = args.index("|")
                assert args[pipe:] == ["|", "tee", "e2e.log"]
                args = args[:pipe]
            # Report placement is not test selection; no other flags are dropped.
            args = [a for a in args if not a.startswith("--junitxml=")]
            selections.append(args)
            execution.append(args[0])
    assert lifecycle == (
        ["cleanup", "prepare", "start", "wait"]
        if local
        else ["prepare", "start", "wait", "cleanup"]
    )
    assert lifecycle.count("cleanup") == 1
    assert [op for op in lifecycle if op != "cleanup"] == ["prepare", "start", "wait"]
    assert selections == _SELECTIONS, "missing/changed pytest selections"
    # Commands must precede tests, and tests must retain workflow order.
    assert execution == [
        "prepare",
        "start",
        "wait",
        "tests/",
        "tests/e2e",
        "tests/test_postgres18_features.py",
    ]
    return (_SERVICES, tuple(op for op in lifecycle if op != "cleanup"), selections)


@pytest.mark.skipif(shutil.which("just") is None, reason="needs just to dump recipes")
def test_ci_emu_matches_required_isolated_workflow_contract() -> None:
    local = _isolation_contract(_local_ci_emu(), local=True)
    workflow = _isolation_contract(WORKFLOW.read_text(encoding="utf-8"), local=False)
    assert local == workflow


@pytest.mark.parametrize("local", [False, True])
@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("isolation prepare", "isolation absent"),
        ("isolation start", "isolation absent"),
        ("isolation wait", "isolation absent"),
        ("isolation cleanup", "isolation absent"),
        ("DOTFILES_E2E_REQUIRED", "OPTIONAL_E2E"),
        ("DOTFILES_PODMAN_RUN_MANIFEST", "OTHER_MANIFEST"),
        ("isolation start", "isolation wait"),
        ("tests/ -v -m 'not e2e'", "tests/ -v -m 'not e2e' -k subset"),
        ("PODMAN_COMPOSE_PROVIDER", "OPTIONAL_PROVIDER"),
        (_SERVICES, "postgres"),
        (" --telemetry", ""),
        ("-m 'not e2e'", "-m e2e"),
        ("tests/e2e -v", "tests/e2e/subset -v"),
        ("tests/test_postgres18_emulator.py", "tests/test_other.py"),
        ('--manifest "$DOTFILES_PODMAN_RUN_MANIFEST"', '--manifest "other.json"'),
        ("isolation wait", "isolation wait --unexpected"),
    ],
)
def test_ci_emu_contract_rejects_semantic_mutations(
    local: bool, old: str, new: str
) -> None:
    text = _local_ci_emu() if local else WORKFLOW.read_text(encoding="utf-8")
    assert old in text
    with pytest.raises(AssertionError):
        _isolation_contract(text.replace(old, new), local=local)


@pytest.mark.parametrize("local", [False, True])
@pytest.mark.parametrize(
    "insertion", ["", "just emu-clean", "bash scripts/test-e2e.sh"]
)
def test_ci_emu_contract_is_nonempty_and_rejects_shared_cleanup(
    local: bool, insertion: str
) -> None:
    text = _local_ci_emu() if local else WORKFLOW.read_text(encoding="utf-8")
    with pytest.raises(AssertionError):
        _isolation_contract(text + "\n" + insertion if insertion else "", local=local)


def _service_block(name: str) -> str:
    text = (EMULATOR / "compose.yaml").read_text(encoding="utf-8")
    match = re.search(
        rf"^  {re.escape(name)}:\n(.*?)(?=^  [\w-]+:\n|^\S)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"compose.yaml has no {name} service"
    return match.group(1)


def test_mcp_inspector_publishes_its_proxy_for_the_browser() -> None:
    # The Inspector UI runs in the browser and calls its proxy directly on
    # <page host>:6277 (upstream client/src/utils/configUtils.ts). The proxy
    # accepts only origins in ALLOWED_ORIGINS and needs its session token.
    block = _service_block("mcp-inspector")
    ports = re.findall(r'^\s+- "([^"]+)"', block, re.MULTILINE)
    assert ports, "mcp-inspector publishes no port"
    assert all(port.startswith("127.0.0.1:") for port in ports), (
        f"bind every Inspector port to loopback: {ports}"
    )
    assert "127.0.0.1:${MCP_INSPECTOR_PORT:-6274}:6274" in ports
    assert any(port.endswith(":6277") for port in ports), (
        "publish the proxy port 6277; the browser UI cannot reach it otherwise"
    )
    origins = re.search(r"^\s+- ALLOWED_ORIGINS=(\S+)$", block, re.MULTILINE)
    assert origins, "set ALLOWED_ORIGINS so the proxy accepts the published UI"
    assert "http://localhost:${MCP_INSPECTOR_PORT:-6274}" in origins.group(1).split(",")
    assert re.search(r"^\s+- MCP_AUTO_OPEN_ENABLED=false$", block, re.MULTILINE), (
        "turn off the auto-open; there is no browser inside the container"
    )
    assert "DANGEROUSLY_OMIT_AUTH" not in block, "keep the proxy's auth token"


@pytest.mark.skipif(shutil.which("just") is None, reason="needs just to dump recipes")
def test_ci_emu_contract_rejects_unknown_just_interpolation(tmp_path: Path) -> None:
    justfile = tmp_path / "justfile"
    text = (ROOT / "justfile").read_text(encoding="utf-8")
    # UV exists, but is not an approved frozen dev runner. Never discard it.
    start = text.index("ci-emu:\n")
    end = text.index("\n# CI-equivalent gate: prek", start)
    text = text[:start] + text[start:end].replace("{{UV_RUN}}", "{{UV}}") + text[end:]
    justfile.write_text(text, encoding="utf-8")
    with pytest.raises(AssertionError, match="unsupported just interpolation"):
        _local_ci_emu(justfile)


@pytest.mark.parametrize("local", [False, True])
@pytest.mark.parametrize(
    "command",
    [
        "prepare",
        "start",
        "wait",
        "cleanup",
        "pytest tests/",
        "pytest tests/e2e",
        "pytest tests/test_postgres18_features.py",
    ],
)
def test_ci_emu_contract_rejects_missing_invocations(local: bool, command: str) -> None:
    text = _local_ci_emu() if local else WORKFLOW.read_text(encoding="utf-8")
    needle = command if command.startswith("pytest") else "isolation " + command
    lines = text.splitlines()
    assert any(needle in line for line in lines)
    mutated = "\n".join(line for line in lines if needle not in line)
    with pytest.raises(AssertionError):
        _isolation_contract(mutated, local=local)


def _compose_groups() -> set[str]:
    """The `emu-up-group` names: every Compose profile except the `cli` tools."""
    text = (EMULATOR / "compose.yaml").read_text(encoding="utf-8")
    blocks = re.findall(r"^    profiles:\n((?:      - .*\n)+)", text, re.MULTILINE)
    profiles = {
        p for b in blocks for p in re.findall(r"^      - (\S+)$", b, re.MULTILINE)
    }
    return profiles - {"cli"}


def test_emulator_runs_no_prometheus_exporters() -> None:
    # ADR 0072: nothing scrapes them since telemetry is upstream otel-lgtm.
    text = (EMULATOR / "compose.yaml").read_text(encoding="utf-8")
    assert not re.findall(r"^  ([\w-]+-exporter):$", text, re.MULTILINE)
    assert "exporters" not in _compose_groups()


@pytest.mark.parametrize(
    ("path", "pattern", "separator"),
    [
        ("justfile", r"^# Groups: ([a-z ]+)\.$", " "),
        ("README.md", r"\(([a-z ]+)\)$", " "),
        ("AGENTS.md", r"capability \(([a-z/\n ]+)\)", "/"),
    ],
)
def test_documented_emulator_groups_match_compose_profiles(
    path: str, pattern: str, separator: str
) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    if path == "README.md":
        text = next(line for line in text.splitlines() if "emu-up-group" in line)
        text = text.replace("（", "(").replace("）", ")")
    found = re.search(pattern, text, re.MULTILINE)
    assert found, f"{path} no longer lists the emu-up-group names"
    names = {n.strip() for n in found[1].replace("\n", " ").split(separator)}
    assert names - {""} == _compose_groups()
