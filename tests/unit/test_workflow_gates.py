"""Every gate job fails when any job it needs did not succeed.

A gate gathers the results of the jobs it `needs` and is the one required
check for them, so a gate that ignores one result lets that job fail unseen.
This runs each gate's own script, the way GitHub's bash runs it, once with
every needed job passing and once for each needed job that failed or was
skipped.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github/workflows").glob("*.yaml"))
NEED_RESULT = re.compile(r"\$\{\{\s*needs\.([A-Za-z0-9_-]+)\.result\s*\}\}")


def _jobs(text: str) -> dict[str, str]:
    body = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"(?m)^  ([A-Za-z0-9_-]+):\n", body)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def _block(lines: list[str], start: int) -> list[str]:
    """The lines indented deeper than lines[start], up to the first that is not."""
    indent = len(lines[start]) - len(lines[start].lstrip())
    out = []
    for line in lines[start + 1 :]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        out.append(line)
    return out


def _gate(job: str) -> tuple[list[str], str, str] | None:
    """A gate's needed jobs, its RESULTS template, and the script that reads it."""
    needs = re.search(r"(?m)^    needs: \[([^\]]*)\]$", job)
    if not needs:
        return None
    lines = job.splitlines()
    at = next(i for i, line in enumerate(lines) if re.match(r"\s+RESULTS:", line))
    value = lines[at].split("RESULTS:", 1)[1].strip()
    if value in {">-", ">", "|"}:
        value = " ".join(line.strip() for line in _block(lines, at) if line.strip())
    run = next(
        i for i in range(at, len(lines)) if re.match(r"\s+run: \|\s*$", lines[i])
    )
    script = textwrap.dedent("\n".join(_block(lines, run)))
    return [n.strip() for n in needs.group(1).split(",")], value, script


GATES = [
    pytest.param(*gate, id=f"{path.name}:{name}")
    for path in WORKFLOWS
    for name, job in _jobs(path.read_text(encoding="utf-8")).items()
    if (gate := _gate(job))
]


def _run(script: str, results: str) -> int:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("needs bash, as GitHub's runner has")
    done = subprocess.run(
        [bash, "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
        env={"RESULTS": results, "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    return done.returncode


def _results(template: str, outcome: dict[str, str]) -> str:
    return NEED_RESULT.sub(lambda m: outcome.get(m.group(1), "success"), template)


def test_there_are_gates_to_check() -> None:
    assert len(GATES) >= 4


@pytest.mark.parametrize(("needs", "template", "script"), GATES)
def test_a_gate_passes_only_when_every_needed_job_succeeded(
    needs: list[str], template: str, script: str
) -> None:
    # given every needed job succeeded, when the gate runs, then it passes
    assert _run(script, _results(template, {})) == 0
    for job in needs:
        for outcome in ("failure", "skipped", "cancelled"):
            # given one needed job did not succeed, then the gate fails
            results = _results(template, {job: outcome})
            assert _run(script, results) != 0, f"{job}={outcome} passed the gate"
