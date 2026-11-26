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

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = ROOT / "justfile"
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
