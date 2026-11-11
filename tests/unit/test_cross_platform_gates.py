"""The gates check code for every OS it runs on, from any one machine.

Code that runs on Windows, Linux, and macOS hides some of its errors on the
OS that checks it: ty narrows `sys.platform` and golangci-lint builds for
one GOOS, so a branch for another OS goes unchecked. On 2026-11-09 a Linux
`just check` was green while Windows had 32 ty findings and 3 unused Go
functions (#576). `just check` runs both for each OS, and the global rules
(the python-tooling and go-tooling spokes) and the agent-baseline template ask
every repo to do the same (ADR 0069).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import _workflow
import pytest

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = ROOT / "justfile"
WORKFLOWS = ROOT / ".github/workflows"
UNIT = WORKFLOWS / "unit-test.yaml"
DRAFT_GATE = (
    "    if: github.event_name != 'pull_request' || "
    "github.event.pull_request.draft == false\n"
)
PYTHON_SPOKE = ROOT / "ROOT_AGENTS_docs_agents_python-tooling.md"
GO_SPOKE = ROOT / "ROOT_AGENTS_docs_agents_go-tooling.md"
COMMIT_SPOKE = ROOT / "ROOT_AGENTS_docs_agents_commit-discipline.md"
RUST_SPOKE = ROOT / "ROOT_AGENTS_docs_agents_rust-tooling.md"
TEMPLATE_JUSTFILE = ROOT / "templates/agent-baseline/justfile"
PLATFORMS = {"win32", "linux", "darwin"}
GOOSES = {"windows", "linux", "darwin"}
EVERY_OS = "for every OS the code runs on"


def _recipe(name: str, source: str | None = None) -> str:
    """A recipe's body: the indented lines under `<name>:` or `<name> args:`.

    `source` is justfile text (the repo's justfile when omitted).
    """
    if source is None:
        source = JUSTFILE.read_text(encoding="utf-8")
    lines = source.splitlines()
    for start, line in enumerate(lines):
        if re.match(rf"^{re.escape(name)}(?:\s[^:]*)?:(?:\s|$)", line):
            break
    else:
        raise AssertionError(f"no recipe {name}")
    body = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        # commands only: what a recipe prints or explains runs nothing
        if not re.match(r"\s*(?:@?echo\s|#(?!!))", line):
            body.append(line)
    return "\n".join(body)


def test_check_runs_ty_once_per_platform():
    check = _recipe("check")
    assert re.search(r"(?m)^\s+@?just check-ty\s*$", check)
    assert "ty check" not in check, "check runs ty only through check-ty"
    platforms = re.findall(r"ty check --python-platform (\S+)", _recipe("check-ty"))
    assert sorted(platforms) == sorted(PLATFORMS)


def _unit_jobs() -> dict[str, str]:
    return _workflow.jobs(UNIT.read_text(encoding="utf-8"))


def _runs_on_windows_when_ready(job: str) -> None:
    assert DRAFT_GATE in job
    assert "    runs-on: windows-latest\n" in job
    assert re.search(r"\n    timeout-minutes: \d+\n", job)
    for action in re.findall(r"uses:\s+(\S+)", job):
        assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", action), action


def test_windows_ci_runs_every_unit_test_then_the_5_1_tests():
    jobs = _unit_jobs()
    # last, so the tests that cut this file at "\n  windows-" keep working
    assert list(jobs)[-2:] == ["windows-unit", "windows-go"]
    job = jobs["windows-unit"]
    _runs_on_windows_when_ready(job)
    # bash: GitHub runs it with -eo pipefail, and Git's /usr/bin (gpg) is on
    # PATH as it is in the Git Bash that runs the tests on a Windows host
    assert "    defaults:\n      run:\n        shell: bash\n" in job
    runs = [c for step in _workflow.steps(job) for c in _workflow.run_commands(step)]
    assert runs.index("just test-unit") < runs.index("just test-windows-powershell")
    # the checkout keeps Git for Windows' line endings, as a new machine's does
    assert "autocrlf" not in job.replace("--get-all core.autocrlf", "")


def test_windows_ci_runs_the_go_tests():
    job = _unit_jobs()["windows-go"]
    _runs_on_windows_when_ready(job)
    assert "go-version-file: tools/agent-hooks/go.mod" in job
    assert "cache-dependency-path: tools/*/go.sum" in job
    (step,) = [s for s in _workflow.steps(job) if s.startswith("name: Go tests")]
    assert "        shell: bash\n" in step
    assert "          GOTOOLCHAIN: auto\n" in step
    assert _workflow.run_commands(step) == ["just go-test go"]


def test_the_5_1_recipe_checks_the_runtime_then_runs_the_scripts_tests():
    text = JUSTFILE.read_text(encoding="utf-8")
    assert "[windows]\n[group('Test')]\ntest-windows-powershell:\n" in text
    body = _recipe("test-windows-powershell")
    assert '"5.1."*" Desktop")' in body
    run = body.index(
        "export DOTFILES_TEST_PWSH=powershell.exe PODMAN_GC_REQUIRE_PWSH=1"
    )
    assert body.index("esac") < run
    for name in (
        "test_podman_gc_simulation.py -k powershell",
        "test_runner_gc.py",
        "test_bootstrap_ps1.py",
        "test_podman_provisioning_ps1.py",
    ):
        assert f"tests/unit/{name}" in body[run:], name


def test_no_windows_powershell_step_hides_a_failed_command():
    # pwsh does not stop at a failed native command unless
    # $PSNativeCommandUseErrorActionPreference is set, and the step then takes
    # the last command's exit code: an earlier failure passes as green.
    checked = 0
    for workflow in sorted(WORKFLOWS.glob("*.yaml")):
        for name, job in _workflow.jobs(workflow.read_text(encoding="utf-8")).items():
            if "\n    runs-on: windows-" not in job:
                continue
            default = re.search(
                r"\n    defaults:\n      run:\n        shell: (\S+)", job
            )
            for step in _workflow.steps(job):
                shell = re.search(r"(?m)^ *shell: (\S+)$", step)
                if shell:
                    chosen = shell.group(1)
                elif default:
                    chosen = default.group(1)
                else:
                    chosen = "pwsh"  # a Windows job's default shell
                commands = _workflow.run_commands(step)
                if chosen != "pwsh" or len(commands) < 2:
                    continue
                checked += 1
                assert (
                    commands[0] == "$PSNativeCommandUseErrorActionPreference = $true"
                ), f"{workflow.name} {name}: {step}"
    assert checked, "no multi-command pwsh step found; is the parser still right?"


def test_check_runs_the_go_legs_last():
    # golangci for three GOOS is the slowest leg (about 5 min on a cold cache
    # in the dev container job); a cheaper leg that fails ends the run first.
    commands = [
        line.strip().lstrip("@") for line in _recipe("check").splitlines() if line
    ]
    assert commands[-2:] == ["just go-lint", "just go-test"]


def test_go_lint_runs_golangci_once_per_goos():
    body = _recipe("go-lint")
    loop = re.search(r"for goos in ([^;\n]+); do", body)
    assert loop and set(loop.group(1).split()) == GOOSES
    assert re.search(r'GOOS="\$goos" [^\n]*golangci-lint run ', body)
    # the formatter does not depend on GOOS: once per module is enough
    assert len(re.findall(r"golangci-lint fmt ", body)) == 1


def _just_blocks(markdown: Path) -> str:
    """Every fenced just block of a spoke, joined."""
    text = markdown.read_text(encoding="utf-8")
    blocks = re.findall(r"^```just\n(.*?)^```$", text, re.MULTILINE | re.DOTALL)
    assert blocks, f"no just block in {markdown.name}"
    return "\n".join(blocks)


def test_the_python_spoke_and_the_template_type_check_every_os():
    # One gate shape: the spoke's example is what the template runs, and both
    # run ty once per OS, as this repo's check-ty does.
    spoke = _recipe("lint", _just_blocks(PYTHON_SPOKE))
    template = _recipe("lint", TEMPLATE_JUSTFILE.read_text(encoding="utf-8"))
    assert spoke.splitlines() == template.splitlines()
    platforms = re.findall(r"ty check --python-platform (\S+)", spoke)
    assert sorted(platforms) == sorted(PLATFORMS)
    assert not re.search(r"ty check(?! --python-platform)", spoke)
    assert EVERY_OS in " ".join(PYTHON_SPOKE.read_text(encoding="utf-8").split())


def test_the_go_spoke_lints_for_every_os_it_ships_to():
    block = _recipe("go-lint", _just_blocks(GO_SPOKE))
    # a shebang recipe with errexit: a loop in just's default `sh -cu` would
    # return only the last GOOS's exit code
    assert block.lstrip().startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in block
    loop = re.search(r"for goos in ([^;\n]+); do", block)
    assert loop and set(loop.group(1).split()) == GOOSES
    assert re.search(r'GOOS="\$goos" golangci-lint run ', block)
    assert len(re.findall(r"golangci-lint fmt ", block)) == 1
    # the OSes the spoke ships binaries for
    text = GO_SPOKE.read_text(encoding="utf-8")
    ship = text.split("\n## Ship binaries", 1)[1].split("\n## ", 1)[0]
    assert (
        set(re.findall(r"\b(linux|darwin|windows)/(?:amd64|arm64)\b", ship)) == GOOSES
    )


def test_commit_discipline_asks_for_ty_on_every_os():
    words = " ".join(COMMIT_SPOKE.read_text(encoding="utf-8").split())
    assert f"ty reports zero diagnostics {EVERY_OS}" in words


TRIPLE = r"\b(?:x86_64|aarch64)-[a-z0-9_]+-[a-z0-9_]+(?:-[a-z0-9_]+)?\b"


def test_the_rust_spoke_lints_for_every_target_it_ships_to():
    # clippy checks one target; code under #[cfg(target_os = ...)] is linted
    # only for that target (measured 2026-11-10: a macOS-only error showed up
    # only with --target aarch64-apple-darwin, from every host) (ADR 0071).
    blocks = _just_blocks(RUST_SPOKE)
    listed = re.search(r'^rust_targets := "([^"]+)"$', blocks, re.MULTILINE)
    assert listed, "the rust block must list the shipped targets once"
    targets = set(listed.group(1).split())
    body = _recipe("rust-lint", blocks)
    assert body.lstrip().startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in body
    assert re.search(r"for target in \{\{targets\}\}; do", body)
    assert 'rustup target add "$target"' in body
    assert re.search(
        r'cargo clippy --all-targets --all-features --target "\$target" -- -D warnings',
        body,
    )
    assert len(re.findall(r"cargo fmt ", body)) == 1
    # the recipe defaults to that list, and the release build uses it too
    assert re.search(r"^rust-lint \*targets=rust_targets:", blocks, re.MULTILINE)
    text = RUST_SPOKE.read_text(encoding="utf-8")
    ship = text.split("\n## Ship binaries", 1)[1]
    assert set(re.findall(TRIPLE, ship)) == targets


def test_the_rust_recipe_parses_and_expands_its_targets(tmp_path):
    just = shutil.which("just")
    if just is None:
        pytest.skip("needs just to parse the recipe")
    justfile = tmp_path / "justfile"
    justfile.write_text(_just_blocks(RUST_SPOKE), encoding="utf-8", newline="\n")
    shown = subprocess.run(
        [just, "--justfile", str(justfile), "--evaluate", "rust_targets"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert shown.returncode == 0, shown.stderr
    listed = subprocess.run(
        [just, "--justfile", str(justfile), "--show", "rust-lint"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert listed.returncode == 0, listed.stderr
    assert "rust-lint *targets=rust_targets:" in listed.stdout
