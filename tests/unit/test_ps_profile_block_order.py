"""The starship block must come after `mise activate` in the pwsh $PROFILE.

starship is a mise-managed tool. `Get-Command starship` in the starship block
finds it only once `mise activate` has put mise's tool dirs on PATH, or when
mise's shims are on the persisted PATH anyway (true on the self-hosted runner
hosts, which add them for their jobs). deploy wrote the starship block first,
so on every other Windows host the block silently skipped and the prompt stayed
plain. deploy only appends missing blocks, so fixing the write order alone
leaves existing profiles misordered: deploy must also move the block, and
doctor must say when the order is wrong.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from _ps_profile import BASH, needs_bash, run_lib, write_profile

STARSHIP = (
    "# >>> dotfiles managed block: starship init >>>\n"
    "if (Get-Command starship -ErrorAction SilentlyContinue) {\n"
    "    Invoke-Expression (&starship init powershell)\n"
    "}\n"
    "# <<< end dotfiles managed block <<<\n"
)
MISE = (
    "# >>> dotfiles managed block: mise activate >>>\n"
    "if (Get-Command mise -ErrorAction SilentlyContinue) {\n"
    "    Invoke-Expression (&mise activate pwsh | Out-String)\n"
    "}\n"
    "# <<< end dotfiles managed block <<<\n"
)
USER_LINE = "Set-Alias ll Get-ChildItem\n"


@needs_bash
@pytest.mark.parametrize(
    ("text", "misordered"),
    [
        (STARSHIP + MISE, True),
        (MISE + STARSHIP, False),
        (STARSHIP, False),  # nothing to order against
        (MISE, False),
        ("", False),
    ],
    ids=["starship-first", "mise-first", "starship-only", "mise-only", "empty"],
)
def test_detects_starship_before_mise(
    tmp_path: Path, text: str, misordered: bool
) -> None:
    profile = write_profile(tmp_path, text)
    result = run_lib(f'ps_profile_starship_before_mise "{profile.as_posix()}"')
    assert (result.returncode == 0) is misordered, result.stderr


@needs_bash
def test_drop_block_removes_only_that_block(tmp_path: Path) -> None:
    # given a misordered profile with a user line between the blocks
    profile = write_profile(tmp_path, STARSHIP + USER_LINE + MISE)

    # when the starship block is dropped
    result = run_lib(f'ps_profile_drop_block "{profile.as_posix()}" "starship init"')

    # then the user's line and the mise block are untouched
    assert result.returncode == 0, result.stderr
    assert profile.read_text(encoding="utf-8") == USER_LINE + MISE


@needs_bash
def test_drop_block_matches_markers_in_a_crlfwrite_profile(tmp_path: Path) -> None:
    # given a profile an editor saved with CRLF line endings
    crlf = (STARSHIP + USER_LINE + MISE).replace("\n", "\r\n")
    profile = tmp_path / "profile.ps1"
    profile.write_bytes(crlf.encode("utf-8"))

    # when the starship block is dropped
    result = run_lib(f'ps_profile_drop_block "{profile.as_posix()}" "starship init"')

    # then it is gone (a missed CRLF marker would re-append a duplicate block);
    # MSYS tools may normalize the line endings, which PowerShell does not mind
    assert result.returncode == 0, result.stderr
    left = profile.read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert left == USER_LINE + MISE


@needs_bash
def test_drop_block_does_not_depend_on_gnu_sed_in_place(tmp_path: Path) -> None:
    """`sed -i` differs between GNU and BSD (macOS wants `-i ''`), so the lib
    must not use it: a sed that rejects -i stands in for BSD's here."""
    # given a sed that refuses -i, first on PATH
    real = shutil.which("sed", path=str(Path(BASH or "").parent)) or shutil.which("sed")
    assert real is not None
    fake = tmp_path / "bin"
    fake.mkdir()
    script = [
        "#!/bin/sh",
        'for a in "$@"; do case "$a" in -i*) echo "sed: no -i" >&2; exit 1;; esac; done',
        f'exec "{Path(real).as_posix()}" "$@"',
    ]
    (fake / "sed").write_text(
        "".join(line + chr(10) for line in script), encoding="utf-8", newline=chr(10)
    )
    (fake / "sed").chmod(0o755)
    profile = write_profile(tmp_path, STARSHIP + USER_LINE + MISE)

    # when the starship block is dropped
    result = run_lib(
        f'ps_profile_drop_block "{profile.as_posix()}" "starship init"', [fake]
    )

    # then it still works
    assert result.returncode == 0, result.stderr
    assert profile.read_text(encoding="utf-8") == USER_LINE + MISE
