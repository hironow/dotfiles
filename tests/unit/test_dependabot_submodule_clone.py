"""Dependabot's clone must not stop on any submodule.

Dependabot always clones with ``--recurse-submodules`` and stops the job on any
submodule error it does not expect. Two submodules stopped it:

- the private ``knowledge-work-plugins``, which it cannot read: the failed
  clone left the other submodules empty and dirty, and its ``git commit``
  failed;
- ``protocols/UTCP``, whose pinned commit has a gitlink with no ``.gitmodules``
  entry (``temp/openapi-directory``): ``No url found for submodule path``
  stopped every job.

Dependabot reads no file inside a submodule, so ``.gitmodules`` marks every
submodule ``update = none`` and the clone skips them all. The owner's checkouts
still fetch and update them through ``--checkout`` in the README step and in
``just update-all-submodules``.

The tests rebuild that clone from local ``file://`` repositories in tmp_path.
Each fixture submodule copies the setting of a real submodule in the same role,
and the README and recipe commands run only against throwaway checkouts.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Fixture role -> the real submodule whose .gitmodules setting it copies.
REAL_SUBMODULE = {
    "public": "protocols/A2A",
    "private": "knowledge-work-plugins",
    "broken": "protocols/UTCP",
}
# The gitlink inside the broken role that .gitmodules does not list.
BROKEN_NESTED = "temp/x"

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


def _gitmodules_sections() -> dict[str, str]:
    """Body of each ``[submodule "name"]`` section of .gitmodules, by name."""
    text = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    return dict(
        re.findall(r'^\[submodule "([^"]+)"\]\n((?:[ \t].*\n?)*)', text, re.MULTILINE)
    )


def _setting(body: str, key: str) -> str | None:
    value = re.search(rf"^\s*{re.escape(key)}\s*=\s*(\S+)\s*$", body, re.MULTILINE)
    return value[1] if value else None


def _real_update(name: str) -> str | None:
    sections = _gitmodules_sections()
    assert name in sections, f'.gitmodules has no [submodule "{name}"] section'
    return _setting(sections[name], "update")


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


def _broken_repo(path: Path) -> str:
    """A repository with a gitlink that its .gitmodules does not list."""
    url = _repo(path)
    head = _ok("-C", path, "rev-parse", "HEAD").strip()
    _ok(
        "-C",
        path,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{head},{BROKEN_NESTED}",
    )
    _ok("-C", path, "commit", "-qm", "gitlink without a .gitmodules entry")
    return url


def _superproject(tmp_path: Path, updates: Mapping[str, str | None]) -> str:
    """public, private, broken as submodules, each with its ``update`` value."""
    urls = {
        "public": _repo(tmp_path / "public"),
        "private": _repo(tmp_path / "private"),
        "broken": _broken_repo(tmp_path / "broken"),
    }
    sup = tmp_path / "super"
    sup.mkdir()
    _ok("init", "-q", sup)
    for role, url in urls.items():
        _ok("-C", sup, "submodule", "add", "-q", url, role)
        update = updates.get(role)
        if update is not None:
            _ok(
                "-C",
                sup,
                "config",
                "-f",
                ".gitmodules",
                f"submodule.{role}.update",
                update,
            )
    _ok("-C", sup, "add", ".gitmodules")
    _ok("-C", sup, "commit", "-qm", "submodules")
    return sup.as_uri()


def _real_updates() -> dict[str, str | None]:
    return {role: _real_update(name) for role, name in REAL_SUBMODULE.items()}


def _dependabot_clone(
    tmp_path: Path, super_url: str, *, private_reachable: bool = False
) -> tuple[subprocess.CompletedProcess[str], Path]:
    if not private_reachable:
        (tmp_path / "private").rename(tmp_path / "private-unreachable")
    dest = tmp_path / "dependabot"
    return _git(*DEPENDABOT_CLONE, super_url, dest), dest


def test_every_submodule_is_skipped_by_default() -> None:
    sections = _gitmodules_sections()
    assert sections, ".gitmodules lists no submodule"
    missing = [
        name for name, body in sections.items() if _setting(body, "update") != "none"
    ]
    assert not missing, (
        "Dependabot clones every submodule it is not told to skip, and any "
        f"submodule error stops it; add `update = none` to {missing} in .gitmodules"
    )


def test_fixture_reproduces_the_private_submodule_failure(tmp_path: Path) -> None:
    """Without settings, the unreachable private repo fails the clone, dirty."""
    result, dest = _dependabot_clone(tmp_path, _superproject(tmp_path, {}))
    assert result.returncode != 0
    assert re.search(r"fatal: clone of '.*private' into submodule path", result.stderr)
    assert _ok("-C", dest, "status", "--short", ".").strip()


def test_fixture_reproduces_the_broken_nested_gitlink_failure(tmp_path: Path) -> None:
    """Without settings, the broken nested gitlink fails the clone by itself."""
    super_url = _superproject(tmp_path, {})
    result, _ = _dependabot_clone(tmp_path, super_url, private_reachable=True)
    assert result.returncode != 0
    assert f"No url found for submodule path 'broken/{BROKEN_NESTED}'" in result.stderr


def test_skipping_only_the_private_submodule_still_fails(tmp_path: Path) -> None:
    """The state after #633: the private repo skipped, the broken one still fails."""
    result, _ = _dependabot_clone(
        tmp_path, _superproject(tmp_path, {"private": "none"})
    )
    assert result.returncode != 0
    assert f"No url found for submodule path 'broken/{BROKEN_NESTED}'" in result.stderr


def test_dependabot_clone_skips_every_submodule(tmp_path: Path) -> None:
    result, dest = _dependabot_clone(tmp_path, _superproject(tmp_path, _real_updates()))
    assert result.returncode == 0, result.stderr
    assert _ok("-C", dest, "status", "--short", ".").strip() == ""
    status = _ok("-C", dest, "submodule", "status").splitlines()
    assert len(status) == len(REAL_SUBMODULE)
    assert all(line.startswith("-") for line in status), status


def test_readme_step_fetches_skipped_submodules(tmp_path: Path) -> None:
    checkout = tmp_path / "machine"
    all_none = dict.fromkeys(REAL_SUBMODULE, "none")
    _ok("clone", "-q", _superproject(tmp_path, all_none), checkout)
    _run_in(checkout, tmp_path, _readme_fetch_args())
    for role in REAL_SUBMODULE:
        assert (checkout / role / "a.txt").is_file(), role


def test_update_recipe_advances_a_skipped_submodule(tmp_path: Path) -> None:
    checkout = tmp_path / "machine"
    all_none = dict.fromkeys(REAL_SUBMODULE, "none")
    _ok("clone", "-q", _superproject(tmp_path, all_none), checkout)
    # Initialized after the change, so init copied `none` into the local config.
    _ok("-C", checkout, "submodule", "update", "--init", "--checkout", "-q")
    assert _ok("-C", checkout, "config", "submodule.private.update").strip() == "none"
    private = tmp_path / "private"
    (private / "b.txt").write_text("b\n", encoding="utf-8")
    _ok("-C", private, "add", "b.txt")
    _ok("-C", private, "commit", "-qm", "b")
    _run_in(checkout, tmp_path, _recipe_update_args())
    assert (checkout / "private" / "b.txt").is_file()
