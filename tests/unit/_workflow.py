"""Read a GitHub Actions workflow as text, the way the workflow tests do.

The tests need no YAML parser: every workflow here keeps the same layout,
two spaces per level, and each job id sits at two spaces under `jobs:`.
"""

from __future__ import annotations

import re


def jobs(body: str) -> dict[str, str]:
    """Each job's text, keyed by its id, in file order."""
    section = body.split("\njobs:\n", 1)[1]
    parts = re.split(r"^  ([a-z0-9-]+):\n", section, flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def steps(job: str) -> list[str]:
    """Each step's text, in order: a step starts with `- ` at six spaces."""
    return re.split(r"^      - ", job, flags=re.MULTILINE)[1:]


def run_commands(step: str) -> list[str]:
    """The lines a step's `run:` executes, without blanks and comments.

    A one-line or folded (`>`, `>-`) run is one command; a literal block
    (`|`) runs one command per line, at ten spaces under the step's keys.
    """
    found = re.search(r"(?:^|\n) *run: ?(.*)\n", step)
    if found is None:
        return []
    value = found.group(1).strip()
    if value not in ("|", "|-"):
        return [value] if value else []
    commands = []
    for line in step[found.end() :].splitlines():
        if line.strip() and not line.startswith(" " * 10):
            break
        if line.strip() and not line.strip().startswith("#"):
            commands.append(line.strip())
    return commands
