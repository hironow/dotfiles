"""The hook scripts read all of their input, wherever they run.

Two ways a guard used to pass what it should block:

- `printf ... | grep -q` under `set -o pipefail` reports "no match" whenever grep
  finds a match and exits before the writer is done: the writer dies of
  SIGPIPE, and pipefail makes its failure the pipeline's. The secrets guard
  passed a large write holding a key. Such a pipeline runs without pipefail, so
  its status is grep's alone: `(set +o pipefail; printf ... | grep -q ...)`.
- bash 3.2 writes a here-string (`<<<`) to a temp file. Where none can be
  written, the command reading it never runs: the files guard passed `a.yml`.
  Process substitution (`< <(printf ...)`) needs no file.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOKS = sorted(ROOT.glob("ROOT_AGENTS_hooks_*.sh"))
# A pipe into grep with -q among its options (alone or in a cluster such as -Eq).
EARLY_EXIT_GREP = re.compile(r"\|\s*grep\s+(-[A-Za-z]+\s+)*-[A-Za-z]*q[A-Za-z]*\b")
WITHOUT_PIPEFAIL = "(set +o pipefail;"
EXIT_BLOCK = 2


def _code_lines(path: Path) -> list[tuple[int, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [
        (n, line)
        for n, line in enumerate(lines, 1)
        if not line.lstrip().startswith("#")
    ]


def pipes_into_grep_q_under_pipefail(line: str) -> bool:
    """A pipe into an early-exiting grep, not inside `(set +o pipefail; ...)`."""
    match = EARLY_EXIT_GREP.search(line)
    return match is not None and WITHOUT_PIPEFAIL not in line[: match.start()]


@pytest.mark.parametrize(
    ("line", "flagged"),
    [
        ("if printf '%s' \"$c\" | grep -Eq 'x'; then", True),
        ("printf x | grep -q y", True),
        ("printf x | grep -E -q y", True),
        ("if (set +o pipefail; printf '%s' \"$c\" | grep -Eq 'x'); then", False),
        ("grep -q y file", False),
        ("printf x | grep -E y", False),
    ],
)
def test_the_check_finds_early_exit_greps(line: str, flagged: bool) -> None:
    assert pipes_into_grep_q_under_pipefail(line) is flagged


def test_no_hook_script_pipes_into_grep_q_under_pipefail() -> None:
    offenders = [
        f"{path.name}:{number}: {line.strip()}"
        for path in HOOKS
        for number, line in _code_lines(path)
        if pipes_into_grep_q_under_pipefail(line)
    ]
    assert offenders == [], (
        "run the pipeline without pipefail, as `(set +o pipefail; printf ... | "
        "grep -q ...)`: " + "; ".join(offenders)
    )


def test_no_hook_script_reads_a_here_string() -> None:
    offenders = [
        f"{path.name}:{number}: {line.strip()}"
        for path in HOOKS
        for number, line in _code_lines(path)
        if "<<<" in line
    ]
    assert offenders == [], "use `< <(printf ...)` instead: " + "; ".join(offenders)


BASHES = [
    pytest.param("bash", id="bash-on-PATH"),
    pytest.param(
        "/bin/bash",
        id="bin-bash",
        marks=pytest.mark.skipif(not Path("/bin/bash").exists(), reason="no /bin/bash"),
    ),
]
NO_FILE_CASES = [
    pytest.param("block-prohibited-files", {"file_path": "a.yml"}, id="files-guard"),
    pytest.param(
        "block-secrets",
        {"file_path": "c.py", "content": "v = 'sk-" + "a" * 20 + "'"},
        id="secrets-guard-small",
    ),
    pytest.param(
        "block-secrets",
        {"file_path": "c.py", "content": "sk-" + "a" * 20 + "\n" + "x" * (1 << 20)},
        id="secrets-guard-large",
    ),
]


@pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("jq") is None,
    reason="the guards need bash and jq (POSIX)",
)
@pytest.mark.parametrize("bash", BASHES)
@pytest.mark.parametrize(("hook", "tool_input"), NO_FILE_CASES)
def test_a_guard_blocks_where_no_file_can_be_written(
    bash: str, hook: str, tool_input: dict
) -> None:
    # given a shell that may not write any file (ulimit -f 0), as when no temp
    # directory is writable
    script = ROOT / f"ROOT_AGENTS_hooks_{hook}.sh"
    result = subprocess.run(
        [bash, "-c", 'ulimit -f 0; exec "$0" "$1"', bash, str(script)],
        input=json.dumps({"tool_input": tool_input}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        cwd=ROOT,
    )
    # then the guard still blocks
    assert result.returncode == EXIT_BLOCK, result.stderr
