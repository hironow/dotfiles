"""Every download in the devcontainer feature retries transient errors (inbox M61).

.devcontainer/features/dotfiles-tools/install.sh runs at image build, in every
PR's sandbox job. One upstream 5xx on a single `curl` (a GitHub release asset
returned 500 while #390's job fetched sheldon) failed the whole build, with
nothing tested. Each download now retries a bounded number of times and still
fails on an HTTP error (`-f`), and every checksum and signature check after it
stays as it was: a retry fetches the same pinned URL again, it never trusts a
different artifact.
"""

from __future__ import annotations

import re
from pathlib import Path

INSTALL = (
    Path(__file__).resolve().parents[2]
    / ".devcontainer"
    / "features"
    / "dotfiles-tools"
    / "install.sh"
)


def commands() -> list[str]:
    """install.sh's commands, one per logical line (backslash continuations
    joined), comments dropped."""
    out: list[str] = []
    pending = ""
    for raw in INSTALL.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not pending and (not line or line.startswith("#")):
            continue
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        out.append(pending + line)
        pending = ""
    return out


def curls() -> list[str]:
    return [c for c in commands() if re.match(r"curl\s", c)]


def test_the_scan_finds_the_downloads() -> None:
    # uv, its checksum, just, its SHA256SUMS, sheldon, rustup-init, and the
    # apt-key helper's fetch.
    assert len(curls()) >= 7


def test_every_curl_retries_and_still_fails_on_http_errors() -> None:
    for c in curls():
        assert re.search(r"(?:^|\s)-\w*f\w*(?:\s|$)", c), (
            f"no -f (fail on HTTP error): {c}"
        )
        assert re.search(r"--retry \d+\b", c), f"no bounded --retry: {c}"
        assert "--retry-all-errors" in c, f"a 5xx or reset is not retried: {c}"
        assert re.search(r"--retry-delay \d+\b", c), f"no --retry-delay: {c}"


def test_git_fetches_retry() -> None:
    # git has no retry of its own: every network git call goes through
    # install.sh's retry_git.
    fetches = [
        c for c in commands() if re.match(r"(?:retry_)?git\s.*\b(?:fetch|clone)\b", c)
    ]
    assert fetches, "the scan found no git fetch"
    for c in fetches:
        assert c.startswith("retry_git "), f"a git fetch without retry_git: {c}"


def test_apt_retries_too() -> None:
    # apt-get fetches every package over the network as well.
    assert re.search(r'Acquire::Retries "\d+"', INSTALL.read_text(encoding="utf-8"))
