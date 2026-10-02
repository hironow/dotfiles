"""The justfile must evaluate in PowerShell environments with no HOME.

This used to pin one variable, `_EXE_SRC_DIR`, which built a cache path from
`home_directory()` rather than `env("HOME")`. That variable left with the exe
stack, so the test is now the rule instead of the instance: no justfile variable
may reach for `$HOME` at all. `home_directory()` is just's own portable
accessor and falls back to `USERPROFILE` on Windows; `env("HOME")` aborts there,
and it aborts at PARSE time, which takes every recipe down with it rather than
only the one that needed a home directory.

Checking the text rather than evaluating a named variable is deliberate: there
is nothing to evaluate when no variable currently needs a home directory, and a
test that passes because its subject no longer exists is worse than no test.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# just's own env accessors, in both the modern and the legacy spelling.
_HOME_ENV = re.compile(
    r"""env(?:_var)?(?:_or_default)?\(\s*["'](?:HOME|USERPROFILE)["']"""
)


def test_no_justfile_variable_reads_home_from_the_environment() -> None:
    text = (ROOT / "justfile").read_text(encoding="utf-8")
    offenders = sorted(
        f"{number}: {line.strip()}"
        for number, line in enumerate(text.splitlines(), start=1)
        if _HOME_ENV.search(line) and not line.lstrip().startswith("#")
    )
    assert offenders == [], (
        "use just's home_directory() instead of reading HOME from the "
        f"environment; it aborts at parse time on Windows: {offenders}"
    )


def test_the_justfile_parses_with_no_home_in_the_environment() -> None:
    """The end state the rule exists for, exercised rather than assumed."""
    just = shutil.which("just")
    if not just:
        pytest.skip("just unavailable")
    result = subprocess.run(
        [just, "--summary"],
        cwd=ROOT,
        env={"PATH": str(Path(just).parent) + ":/usr/bin:/bin"},
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr
