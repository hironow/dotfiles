"""Static checks that keep the local `ci-emu` gate in step with the emulator CI.

The local `ci-emu` recipe restates what the emulator workflow already decides.
These tests read both sides, so a step that changes in one place cannot leave
the other describing a gate that no longer exists. repo-lint holds the
policies on compose.yaml and the env example (the emulator-* rules).
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
WORKFLOW = ROOT / ".github" / "workflows" / "test-emulators.yaml"

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


@pytest.mark.skipif(shutil.which("just") is None, reason="needs just to dump recipes")
def test_ci_emu_contract_rejects_unknown_just_interpolation(tmp_path: Path) -> None:
    justfile = tmp_path / "justfile"
    text = (ROOT / "justfile").read_text(encoding="utf-8")
    # UV exists, but is not an approved frozen dev runner. Never discard it.
    start = text.index("ci-emu:\n")
    end = text.index("\n# CI-equivalent gate: prek", start)
    body = text[start:end]
    # a mutation that changes nothing would let the test pass for nothing
    assert "{{ UV_RUN }}" in body
    text = text[:start] + body.replace("{{ UV_RUN }}", "{{ UV }}") + text[end:]
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
