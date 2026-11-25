"""Drive the read-only Go hygiene gate through its CLI (ADR 0085).

Every scanned tree is a disposable Git repository, never the live checkout.
The binary is built once, as with the mise-versions CLI oracle.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "tools/text-hygiene"


@pytest.fixture(scope="session")
def hygiene_tool(tmp_path_factory: pytest.TempPathFactory) -> Path:
    assert (MODULE / "main.go").is_file(), "the Go hygiene checker must exist"
    go = shutil.which("go")
    assert go, "the CLI tests require Go on PATH"
    binary = tmp_path_factory.mktemp("text-hygiene") / (
        "text-hygiene.exe" if os.name == "nt" else "text-hygiene"
    )
    result = subprocess.run(
        [go, "build", "-o", str(binary), "."],
        cwd=MODULE,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return binary


def git(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, check=True
    ).stdout


def repo(tmp_path: Path, files: dict[str, bytes]) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "core.autocrlf", "false")
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    git(root, "add", "--all")
    return root


def cli(tool: Path, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(tool), "--root", str(root), *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_clean_tracked_file_passes(hygiene_tool: Path, tmp_path: Path) -> None:
    root = repo(tmp_path, {"a.txt": b"one\ntwo\n"})
    result = cli(hygiene_tool, root)
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""


def test_dirty_file_fails_without_changing_bytes_or_index(
    hygiene_tool: Path, tmp_path: Path
) -> None:
    root = repo(tmp_path, {"a.txt": b"one \ntwo\t"})
    # The working copy differs from the staged bytes; neither may be rewritten.
    (root / "a.txt").write_bytes(b"working copy \n")
    before = (root / "a.txt").read_bytes()
    index = (root / ".git/index").read_bytes()
    result = cli(hygiene_tool, root)
    assert result.returncode == 1, result.stderr
    assert "a.txt:1: trailing whitespace" in result.stderr
    assert result.stdout == ""
    assert (root / "a.txt").read_bytes() == before
    assert (root / ".git/index").read_bytes() == index


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"one", "missing final newline"),
        (b"one\n\n", "blank line(s) at end of file"),
        (b"one\r\n\r\n", "blank line(s) at end of file"),
        (b"one\n\r\n", "blank line(s) at end of file"),
        (b"one\r\n\n", "blank line(s) at end of file"),
        (b"\n", "blank line(s) at end of file"),
        (b"one \r\n", "a.txt:1: trailing whitespace"),
        (b"one\n \n", "a.txt:2: trailing whitespace"),
    ],
)
def test_newline_and_whitespace_errors_are_read_only(
    hygiene_tool: Path, tmp_path: Path, data: bytes, message: str
) -> None:
    root = repo(tmp_path, {"a.txt": data})
    before = (root / ".git/index").read_bytes()
    result = cli(hygiene_tool, root)
    assert result.returncode == 1, result.stderr
    assert message in result.stderr
    assert (root / "a.txt").read_bytes() == data
    assert (root / ".git/index").read_bytes() == before


@pytest.mark.parametrize(
    "data", [b"", b"one\r\ntwo\r\n", b"\xff bad ", b"a\x00 ", b"a" * 8192 + b"\x00 "]
)
def test_empty_binary_and_clean_crlf_pass(
    hygiene_tool: Path, tmp_path: Path, data: bytes
) -> None:
    root = repo(tmp_path, {"a.txt": data})
    result = cli(hygiene_tool, root)
    assert result.returncode == 0, result.stderr
    assert (root / "a.txt").read_bytes() == data


def test_empty_repo_passes(hygiene_tool: Path, tmp_path: Path) -> None:
    root = repo(tmp_path, {})
    assert cli(hygiene_tool, root).returncode == 0


@pytest.mark.parametrize(
    "excluded",
    [
        "emulator/a.txt",
        "gcloud/a.txt",
        "knowledge-work-plugins/a.txt",
        "protocols/a.txt",
        "skills/a.txt",
        "output/a.txt",
        "node_modules/a.txt",
        ".venv/a.txt",
        "tools/rttm/.venv/a.txt",
        "docs/changelogs.md",
        "docs/changelogs.md.old",
        "site/vendor/pkg/web.js",
    ],
)
def test_exclusions_skip_bad_bytes_but_do_not_hide_site_sources(
    hygiene_tool: Path, tmp_path: Path, excluded: str
) -> None:
    root = repo(tmp_path, {excluded: b"bad ", "site/copy.js": b"bad "})
    before = (root / excluded).read_bytes()
    result = cli(hygiene_tool, root)
    assert result.returncode == 1, result.stderr
    assert excluded not in result.stderr
    assert "site/copy.js:1: trailing whitespace" in result.stderr
    assert (root / excluded).read_bytes() == before


def test_untracked_file_is_not_scanned(hygiene_tool: Path, tmp_path: Path) -> None:
    root = repo(tmp_path, {"clean.txt": b"clean\n"})
    (root / "untracked.txt").write_bytes(b"bad ")
    assert cli(hygiene_tool, root).returncode == 0


def test_explicit_paths_select_only_the_requested_file(
    hygiene_tool: Path, tmp_path: Path
) -> None:
    root = repo(tmp_path, {"clean.txt": b"clean\n", "dirty.txt": b"bad "})
    result = cli(hygiene_tool, root, "./clean.txt")
    assert result.returncode == 0, result.stderr
    assert cli(hygiene_tool, root, "dirty.txt").returncode == 1


@pytest.mark.parametrize("name", ["missing.txt", "../outside.txt", "."])
def test_invalid_explicit_paths_fail(
    hygiene_tool: Path, tmp_path: Path, name: str
) -> None:
    root = repo(tmp_path, {"clean.txt": b"clean\n"})
    (tmp_path / "outside.txt").write_bytes(b"outside secret \n")
    result = cli(hygiene_tool, root, name)
    assert result.returncode == 1, result.stderr
    assert "text hygiene:" in result.stderr
    assert "outside secret" not in result.stderr


def test_absolute_path_fails(hygiene_tool: Path, tmp_path: Path) -> None:
    root = repo(tmp_path, {"clean.txt": b"clean\n"})
    assert cli(hygiene_tool, root, str(root / "clean.txt")).returncode == 1


def test_non_git_root_and_invalid_option_fail(
    hygiene_tool: Path, tmp_path: Path
) -> None:
    assert cli(hygiene_tool, tmp_path).returncode == 1
    root = repo(tmp_path, {"clean.txt": b"clean\n"})
    assert cli(hygiene_tool, root, "--not-an-option").returncode == 1


def test_explicit_root_is_not_silently_replaced_by_its_parent_repo(
    hygiene_tool: Path, tmp_path: Path
) -> None:
    root = repo(tmp_path, {"nested/clean.txt": b"clean\n"})
    assert cli(hygiene_tool, root / "nested").returncode == 1


def test_default_discovers_git_top_level_from_subdirectory(
    hygiene_tool: Path, tmp_path: Path
) -> None:
    root = repo(tmp_path, {"dirty.txt": b"bad ", "nested/clean.txt": b"clean\n"})
    result = subprocess.run(
        [str(hygiene_tool)],
        cwd=root / "nested",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 1, result.stderr
    assert "dirty.txt:1: trailing whitespace" in result.stderr


def test_deleted_tracked_file_is_skipped(hygiene_tool: Path, tmp_path: Path) -> None:
    root = repo(tmp_path, {"deleted.txt": b"clean\n"})
    (root / "deleted.txt").unlink()
    assert cli(hygiene_tool, root).returncode == 0
    assert cli(hygiene_tool, root, "deleted.txt").returncode == 1


def test_unicode_and_newline_filenames_are_discovered(
    hygiene_tool: Path, tmp_path: Path
) -> None:
    name = "日本語 file.txt"
    root = repo(tmp_path, {name: b"bad "})
    result = cli(hygiene_tool, root)
    assert result.returncode == 1, result.stderr
    assert name in result.stderr
    if os.name != "nt":
        (root / "line\nbreak.txt").write_bytes(b"bad ")
        git(root, "add", "--all")
        assert "line\nbreak.txt" in cli(hygiene_tool, root).stderr


@pytest.mark.parametrize("directory", [False, True])
def test_symlinks_never_read_the_target(
    hygiene_tool: Path, tmp_path: Path, directory: bool
) -> None:
    root = repo(tmp_path, {"clean.txt": b"clean\n"})
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "private.txt"
    target.write_bytes(b"outside secret \n")
    link = root / "linked"
    try:
        link.symlink_to(outside if directory else target, target_is_directory=directory)
    except OSError:
        if os.name == "nt":
            pytest.skip("Windows requires symlink privileges")
        raise
    git(root, "add", "--all")
    result = cli(hygiene_tool, root)
    assert result.returncode == 0, result.stderr
    explicit = "linked/private.txt" if directory else "linked"
    assert cli(hygiene_tool, root, explicit).returncode == 0
    assert target.read_bytes() == b"outside secret \n"


def test_read_errors_fail(hygiene_tool: Path, tmp_path: Path) -> None:
    if os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0):
        pytest.skip("POSIX mode test needs an unprivileged user")
    root = repo(tmp_path, {"unreadable.txt": b"clean\n"})
    target = root / "unreadable.txt"
    target.chmod(0)
    try:
        result = cli(hygiene_tool, root)
        assert result.returncode == 1, result.stderr
        assert "unreadable.txt" in result.stderr
    finally:
        target.chmod(0o600)
