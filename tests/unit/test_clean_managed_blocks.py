"""`just clean` must actually remove the deploy-managed blocks (ADR 0022/0024/
0031/0033).

Found live (2026-08-20): every managed-block removal in clean.sh used
`sed -i '\#ADDR>>>/,/ADDR<<</d'` — a `\#` custom address delimiter that is
then closed with `/` instead of `#`. GNU sed rejects the expression
("unknown command: `<'"), so `just clean` aborted mid-run on any host whose
$PROFILE carries a managed block: the config files before the sed were
removed, everything after it was not, and the recipe exited non-zero.

These tests run every `sed -i` expression from clean.sh against a synthetic
profile, so the next delimiter slip fails CI instead of a live clean.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLEAN = ROOT / "scripts" / "clean.sh"
BASH = shutil.which("bash") or "/bin/bash"


def _sed_invocations() -> list[str]:
    """Every managed-block `sed -i` line, with the shell variable that names
    the target file normalized to `$target`."""
    lines = []
    for line in CLEAN.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("sed -i"):
            lines.append(re.sub(r'"\$\w+"\s*$', '"$target"', stripped))
    return lines


def test_clean_has_managed_block_seds() -> None:
    assert len(_sed_invocations()) >= 4, (
        "clean.sh should remove the starship/mise-activate/mise-corepack/"
        "git-aliases managed blocks via sed."
    )


@pytest.mark.parametrize("sed_line", _sed_invocations())
def test_managed_block_sed_removes_the_block(sed_line: str, tmp_path: Path) -> None:
    """Each expression must (a) be valid sed at all and (b) delete exactly the
    managed block, leaving user content on both sides untouched."""
    # Reconstruct the start marker this sed targets from its own address.
    m = re.search(r"managed block: ([^>]+?) ?>>>", sed_line)
    assert m is not None, f"cannot find a start marker in: {sed_line!r}"
    start = f"# >>> dotfiles managed block: {m.group(1).strip()} >>>"
    end = "# <<< end dotfiles managed block <<<"

    target = tmp_path / "profile.ps1"
    target.write_text(
        f"user line above\n{start}\nmanaged payload\n{end}\nuser line below\n",
        encoding="utf-8",
    )

    proc = subprocess.run(
        [BASH, "-c", f'target="{target.as_posix()}"; {sed_line}'],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"sed expression is not valid sed: {sed_line!r}\n{proc.stderr}"
    )

    remaining = target.read_text(encoding="utf-8")
    assert start not in remaining and "managed payload" not in remaining, (
        f"block not removed by: {sed_line!r}"
    )
    assert "user line above" in remaining and "user line below" in remaining, (
        f"user content clobbered by: {sed_line!r}"
    )
