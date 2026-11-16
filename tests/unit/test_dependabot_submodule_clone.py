"""Dependabot's clone must not break on the private submodule.

Dependabot clones with ``--recurse-submodules`` and cannot read the private
``hironow/knowledge-work-plugins``. Git then stops checking out the other
submodules, they show as modified, and Dependabot's ``git commit`` for its
second update fails, so the weekly pull request never opens. ``update = none``
in ``.gitmodules`` makes the clone skip that submodule. The owner's checkouts
still fetch and update it through ``--checkout`` in the README step and in
``just update-all-submodules``.

The tests rebuild that clone from local ``file://`` repositories in tmp_path.
They copy the real ``.gitmodules`` setting and run the real README and recipe
commands, but only against throwaway checkouts under tmp_path.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = "knowledge-work-plugins"

# Isolate git from the owner's config: no signing, no global hooks or URL
# rewrites, and file:// submodules allowed for the local fixture repositories.
GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_COUNT": "3",
    "GIT_CONFIG_KEY_0": "protocol.file.allow",
    "GIT_CONFIG_VALUE_0": "always",
    "GIT_CONFIG_KEY_1": "commit.gpgsign",
    "GIT_CONFIG_VALUE_1": "false",
    "GIT_CONFIG_KEY_2": "init.defaultBranch",
    "GIT_CONFIG_VALUE_2": "main",
}

# The clone Dependabot runs (seen in its job log, 2026-11-16).
DEPENDABOT_CLONE = [
    "clone",
    "--no-tags",
    "--depth",
    "1",
    "--recurse-submodules",
    "--shallow-submodules",
]


def _git(
    *args: str | Path, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *map(str, args)],
        cwd=cwd,
        env=GIT_ENV,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _ok(*args: str | Path, cwd: Path | None = None) -> str:
    result = _git(*args, cwd=cwd)
    assert result.returncode == 0, f"git {args} failed:\n{result.stdout}{result.stderr}"
    return result.stdout


def _real_setting(name: str, key: str) -> str | None:
    """Value of ``key`` in the ``[submodule "name"]`` section of .gitmodules."""
    text = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    section = re.search(
        rf'^\[submodule "{re.escape(name)}"\]\n((?:[ \t].*\n?)*)', text, re.MULTILINE
    )
    assert section, f'.gitmodules has no [submodule "{name}"] section'
    value = re.search(
        rf"^\s*{re.escape(key)}\s*=\s*(\S+)\s*$", section[1], re.MULTILINE
    )
    return value[1] if value else None


def _submodule_args(line: str) -> list[str]:
    """The ``submodule ...`` part of a git command line, without -C or -c."""
    tokens = shlex.split(line)
    assert "submodule" in tokens, f"not a git submodule command: {line!r}"
    return tokens[tokens.index("submodule") :]


def _readme_fetch_args() -> list[str]:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    lines = re.findall(r"^git .*\bsubmodule update --init\b.*$", text, re.MULTILINE)
    assert len(lines) == 1, (
        f"expected one submodule fetch step in README.md, got {lines}"
    )
    return _submodule_args(lines[0])


def _recipe_update_args() -> list[str]:
    lines = (ROOT / "justfile").read_text(encoding="utf-8").splitlines()
    start = next(
        (
            i
            for i, line in enumerate(lines)
            if re.match(r"^update-all-submodules[^:\n]*:", line)
        ),
        None,
    )
    assert start is not None, "recipe 'update-all-submodules' not found in justfile"
    for line in lines[start + 1 :]:
        if line and not line.startswith((" ", "\t")):
            break
        if "submodule update --remote" in line:
            return _submodule_args(line.strip())
    pytest.fail("update-all-submodules has no `submodule update --remote` line")


def _run_in(checkout: Path, tmp_path: Path, args: list[str]) -> str:
    """Run a submodule command from the docs, pinned to a throwaway checkout."""
    assert checkout.resolve().is_relative_to(tmp_path.resolve())
    return _ok("-C", checkout, *args)


def _repo(path: Path) -> str:
    path.mkdir()
    _ok("init", "-q", path)
    (path / "a.txt").write_text("a\n", encoding="utf-8")
    _ok("-C", path, "add", "a.txt")
    _ok("-C", path, "commit", "-qm", "a")
    return path.as_uri()


def _superproject(tmp_path: Path, private_update: str | None) -> str:
    """public1, private, public2 as submodules (in .gitmodules order)."""
    urls = {name: _repo(tmp_path / name) for name in ("public1", "private", "public2")}
    sup = tmp_path / "super"
    sup.mkdir()
    _ok("init", "-q", sup)
    for name, url in urls.items():
        _ok("-C", sup, "submodule", "add", "-q", url, name)
    if private_update is not None:
        _ok(
            "-C",
            sup,
            "config",
            "-f",
            ".gitmodules",
            "submodule.private.update",
            private_update,
        )
    _ok("-C", sup, "add", ".gitmodules")
    _ok("-C", sup, "commit", "-qm", "submodules")
    return sup.as_uri()


def _dependabot_clone(
    tmp_path: Path, super_url: str
) -> tuple[subprocess.CompletedProcess[str], Path]:
    (tmp_path / "private").rename(tmp_path / "private-unreachable")
    dest = tmp_path / "dependabot"
    return _git(*DEPENDABOT_CLONE, super_url, dest), dest


def test_fixture_reproduces_the_dependabot_failure(tmp_path: Path) -> None:
    """Without the setting, the clone fails and leaves the tree dirty."""
    result, dest = _dependabot_clone(
        tmp_path, _superproject(tmp_path, private_update=None)
    )
    assert result.returncode != 0
    assert _ok("-C", dest, "status", "--short", ".").strip()


def test_dependabot_clone_skips_the_private_submodule(tmp_path: Path) -> None:
    super_url = _superproject(tmp_path, private_update=_real_setting(PRIVATE, "update"))
    result, dest = _dependabot_clone(tmp_path, super_url)
    assert result.returncode == 0, result.stderr
    assert _ok("-C", dest, "status", "--short", ".").strip() == ""
    assert (dest / "public1" / "a.txt").is_file()
    assert (dest / "public2" / "a.txt").is_file()


def test_readme_step_fetches_a_skipped_submodule(tmp_path: Path) -> None:
    checkout = tmp_path / "machine"
    _ok("clone", "-q", _superproject(tmp_path, private_update="none"), checkout)
    _run_in(checkout, tmp_path, _readme_fetch_args())
    assert (checkout / "private" / "a.txt").is_file()


def test_update_recipe_advances_a_skipped_submodule(tmp_path: Path) -> None:
    checkout = tmp_path / "machine"
    _ok("clone", "-q", _superproject(tmp_path, private_update="none"), checkout)
    # Initialized after the change, so init copied `none` into the local config.
    _ok("-C", checkout, "submodule", "update", "--init", "--checkout", "-q")
    assert _ok("-C", checkout, "config", "submodule.private.update").strip() == "none"
    private = tmp_path / "private"
    (private / "b.txt").write_text("b\n", encoding="utf-8")
    _ok("-C", private, "add", "b.txt")
    _ok("-C", private, "commit", "-qm", "b")
    _run_in(checkout, tmp_path, _recipe_update_args())
    assert (checkout / "private" / "b.txt").is_file()
