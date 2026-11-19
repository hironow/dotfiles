"""What the shared global ignore (dump/gitignore-global) ignores, asked of git.

`just deploy` places dump/gitignore-global at ~/.config/git/ignore on every
machine. These tests run `git check-ignore` with that file as the excludes
file, so they check git's reading of each pattern, not the text.

dev/null/: on native Windows, a tool that runs git with
`-c core.hooksPath=/dev/null` (Claude Code's background git calls,
anthropics/claude-code#106536) makes git-lfs write its four hooks into
`<worktree root>/dev/null/` (git-lfs/git-lfs#6297). The folder may still be
made; the ignore keeps it out of `git status` and ordinary staging.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GLOBAL_IGNORE = ROOT / "dump" / "gitignore-global"

IGNORED = 0
NOT_IGNORED = 1


@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("ignore-repo")
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def check_ignore(repo: Path, path: str) -> int:
    """git's answer for path: 0 ignored, 1 not ignored. Anything else fails."""
    result = subprocess.run(
        [
            "git",
            "-c",
            f"core.excludesFile={GLOBAL_IGNORE.as_posix()}",
            "check-ignore",
            "--no-index",
            "-q",
            path,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode in (IGNORED, NOT_IGNORED), (
        f"git check-ignore {path}: exit {result.returncode}: {result.stderr}"
    )
    return result.returncode


@pytest.mark.parametrize(
    "path",
    [
        "dev/null/post-checkout",
        "dev/null/post-commit",
        "dev/null/post-merge",
        "dev/null/pre-push",
    ],
)
def test_the_lfs_hooks_written_to_dev_null_are_ignored(repo: Path, path: str) -> None:
    assert check_ignore(repo, path) == IGNORED


@pytest.mark.parametrize(
    "path",
    [
        "src/dev/null/pre-push",  # git-lfs writes at the worktree root only
        "dev/other.txt",
        "dev/nullx/a",
    ],
)
def test_only_the_root_dev_null_folder_is_ignored(repo: Path, path: str) -> None:
    assert check_ignore(repo, path) == NOT_IGNORED
