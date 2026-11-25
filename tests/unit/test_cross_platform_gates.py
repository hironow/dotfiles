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
from pathlib import Path

import _workflow

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = ROOT / "justfile"
WORKFLOWS = ROOT / ".github/workflows"
UNIT = WORKFLOWS / "unit-test.yaml"
DRAFT_GATE = (
    "    if: github.event_name != 'pull_request' || "
    "github.event.pull_request.draft == false\n"
)
TEMPLATE_JUSTFILE = ROOT / "templates/agent-baseline/justfile"
PLATFORMS = {"win32", "linux", "darwin"}
GOOSES = {"windows", "linux", "darwin"}


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


def test_check_runs_its_parts_and_go_last():
    # CI runs these three as parallel jobs (check.yaml); `check` runs them in
    # a row, and every other leg lives in check-except-go.
    commands = [
        line.strip().lstrip("@") for line in _recipe("check").splitlines() if line
    ]
    assert commands == ["just check-except-go", "just go-lint", "just go-test"]


def test_check_runs_ty_once_per_platform():
    check = _recipe("check-except-go")
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


def _windows_test_job(job: str) -> list[str]:
    """Checks every Windows test job shares, and returns its run commands."""
    _runs_on_windows_when_ready(job)
    # bash: GitHub runs it with -eo pipefail, and Git's /usr/bin (gpg) is on
    # PATH as it is in the Git Bash that runs the tests on a Windows host
    assert "    defaults:\n      run:\n        shell: bash\n" in job
    # the checkout keeps Git for Windows' line endings, as a new machine's does
    assert "autocrlf" not in job.replace("--get-all core.autocrlf", "")
    return [c for step in _workflow.steps(job) for c in _workflow.run_commands(step)]


def test_windows_ci_runs_every_unit_test_in_shards_and_the_5_1_tests():
    jobs = _unit_jobs()
    # last, so the tests that cut this file at "\n  windows-" keep working
    assert list(jobs)[-4:] == [
        "windows-unit-shard",
        "windows-powershell",
        "windows-unit",
        "windows-go",
    ]
    shard = jobs["windows-unit-shard"]
    runs = _windows_test_job(shard)
    (groups,) = re.findall(r"group: \[([\d, ]+)\]", shard)
    count = len(groups.split(","))
    (unit,) = [c for c in runs if c.startswith("just test-unit ")]
    assert f"--splits {count} --group ${{{{ matrix.group }}}}" in unit
    assert "--durations-path tests/durations/unit-windows.json" in unit
    # through cygpath -m: `just` hands its arguments to sh unquoted, and the
    # backslashes of D:\a\_temp would be read as escapes
    assert '--junitxml "$out/' in unit
    assert 'out="$(cygpath -m "$RUNNER_TEMP")"' in shard
    # the list is UTF-8 like the JUnit report; the test run keeps Windows'
    # default encoding, which the suite must pass under
    (collect,) = [s for s in _workflow.steps(shard) if "--collect-only" in s]
    assert 'PYTHONUTF8: "1"' in collect
    assert "PYTHONUTF8:" not in shard.replace(collect, "")
    assert _windows_test_job(jobs["windows-powershell"])[-1] == (
        "just test-windows-powershell"
    )
    # The gate keeps the job's old name, needs both, and proves that the shards
    # ran every collected test once.
    gate = jobs["windows-unit"]
    assert "    name: Unit tests on Windows, and on Windows PowerShell 5.1\n" in gate
    assert "    needs: [windows-unit-shard, windows-powershell]\n" in gate
    assert "always()" in gate
    assert '"success success"' in gate
    assert "go run . shards" in gate
    assert len(re.findall(r"--junit ", gate)) == count
    assert len(re.findall(r"--collected ", gate)) == count
    assert "--durations-in ../../tests/durations/unit-windows.json" in gate


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
    # the attribute lines above the recipe, in whatever order `just --fmt` keeps
    attrs = re.search(
        r"((?:^\[[^\]]*\]\n)+)test-windows-powershell:\n", text, re.MULTILINE
    )
    assert attrs, "test-windows-powershell must be a recipe with attributes"
    assert "[group('test')]\n" in attrs.group(1)
    assert "[windows]\n" in attrs.group(1)
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


def test_the_template_type_checks_every_os():
    # The agent-baseline template runs ty once per OS, as this repo's check-ty
    # does.
    lint = _recipe("lint", TEMPLATE_JUSTFILE.read_text(encoding="utf-8"))
    platforms = re.findall(r"ty check --python-platform (\S+)", lint)
    assert sorted(platforms) == sorted(PLATFORMS)
    assert not re.search(r"ty check(?! --python-platform)", lint)
