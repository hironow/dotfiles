"""The gates check code for every OS it runs on, from any one machine.

Code that runs on Windows, Linux, and macOS hides some of its errors on the
OS that checks it: ty narrows `sys.platform` and golangci-lint builds for
one GOOS, so a branch for another OS goes unchecked. On 2026-11-09 a Linux
`just check` was green while Windows had 32 ty findings and 3 unused Go
functions (#576). `just check` runs both for each OS.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = ROOT / "justfile"
PLATFORMS = {"win32", "linux", "darwin"}
GOOSES = {"windows", "linux", "darwin"}


def _recipe(name: str) -> str:
    """A recipe's body: the indented lines under `<name>:` or `<name> args:`."""
    lines = JUSTFILE.read_text(encoding="utf-8").splitlines()
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


def test_go_lint_runs_golangci_once_per_goos():
    body = _recipe("go-lint")
    loop = re.search(r"for goos in ([^;\n]+); do", body)
    assert loop and set(loop.group(1).split()) == GOOSES
    assert re.search(r'GOOS="\$goos" [^\n]*golangci-lint run ', body)
    # the formatter does not depend on GOOS: once per module is enough
    assert len(re.findall(r"golangci-lint fmt ", body)) == 1
