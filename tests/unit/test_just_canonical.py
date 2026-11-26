"""The justfiles this repo ships are written as just itself writes them.

"Written as just writes them" means: `just --fmt` would not change them, they
use no feature the manual marks deprecated, and they name the oldest just they
need (`set minimum-version`). The manual and GRAMMAR.md of the pinned just are
the reference (config/mise/image-tools.toml pins it).

The manual gives `--fmt` no promise of the same output across versions, so
the formatter that writes and checks is the pinned just: the justfile's
`JUST_FMT`, and `rust-just==<pin>` wherever CI installs just.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUSTFILES = [ROOT / "justfile", ROOT / "templates/agent-baseline/justfile"]
SPOKES = sorted(ROOT.glob("ROOT_AGENTS_docs_agents_*.md"))
# The manual's table of settings and its list of functions mark these deprecated.


def _pinned() -> str:
    tools = tomllib.loads(
        (ROOT / "config/mise/image-tools.toml").read_text(encoding="utf-8")
    )["tools"]
    return tools["just"]


def _just() -> str:
    just = shutil.which("just")
    if just is None:
        pytest.skip("needs just")
    version = subprocess.run(
        [just, "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout.split()[-1]
    if version != _pinned():
        # CI installs the pin (test below); a newer local just may format
        # differently, so its verdict would not be the gate's.
        pytest.skip(
            f"just {version} is not the pinned {_pinned()}: `just fmt` uses the pin"
        )
    return just


def _just_blocks(markdown: Path) -> str:
    text = markdown.read_text(encoding="utf-8")
    return "\n".join(
        re.findall(r"^```just\n(.*?)^```$", text, re.MULTILINE | re.DOTALL)
    )


@pytest.mark.parametrize("path", JUSTFILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_just_fmt_would_not_change_the_justfile(path: Path) -> None:
    result = subprocess.run(
        [_just(), "--justfile", str(path), "--fmt", "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr


@pytest.mark.parametrize(
    "spoke", [p for p in SPOKES if _just_blocks(p)], ids=lambda p: p.name
)
def test_just_fmt_would_not_change_a_spokes_just_blocks(
    spoke: Path, tmp_path: Path
) -> None:
    # A spoke's blocks are what other repos copy: they are canonical too.
    justfile = tmp_path / "justfile"
    justfile.write_text(_just_blocks(spoke), encoding="utf-8", newline="\n")
    result = subprocess.run(
        [_just(), "--justfile", str(justfile), "--fmt", "--check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr


@pytest.mark.parametrize(
    "path", ["justfile", "templates/agent-baseline/justfile", "just/example.just"]
)
def test_justfiles_are_lf_on_every_os(path: str) -> None:
    # `just --fmt --check` compares the working tree with just's own LF
    # output: a core.autocrlf=true checkout (Windows) fails it on an unchanged
    # file. Pinned like *.sh and *.go (ADR 0020, ADR 0050); *.just covers
    # module files.
    result = subprocess.run(
        ["git", "check-attr", "eol", "--", path],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    assert result.stdout.strip().endswith(": eol: lf"), result.stdout
