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
