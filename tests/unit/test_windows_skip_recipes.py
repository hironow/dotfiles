"""Four recipes skip cleanly on native Windows, and only there.

semgrep's native-Windows engine mis-fires rules; Windows has no brew and no
gcloud; and the PATH duplicate scan would flag System32 and Program Files.
So semgrep-test, update-brew, update-gcloud and validate-path-duplicates
dispatch on `uname -s` and exit 0 on Windows, which keeps `just ci`,
`update-all` and `doctor` going there. A fake `uname` takes each branch on
Linux and macOS; fake tools log and fail, so a Windows run that reaches a tool
fails, and a Linux run that skips is caught too (ADR-0093).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WINDOWS_UNAMES = ["MINGW64_NT-10.0-26100", "MSYS_NT-10.0-26100", "CYGWIN_NT-10.0-26100"]
RECIPES = ["semgrep-test", "update-brew", "update-gcloud", "validate-path-duplicates"]
# what each recipe runs past the Windows branch
FAKES = ("uvx", "uv", "mise", "semgrep", "brew", "gcloud", "sudo", "git")

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="runs the Windows branch on POSIX through a fake uname",
)


def _run(
    tmp_path: Path, recipe: str, uname: str
) -> tuple[subprocess.CompletedProcess[str], str]:
    just = shutil.which("just")
    if just is None:
        pytest.skip("needs just")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls"
    log.touch()

    def stub(name: str, body: str) -> None:
        path = bin_dir / name
        path.write_text("#!/bin/sh\n" + body, encoding="utf-8", newline="\n")
        path.chmod(0o755)

    stub("uname", f'printf "%s\\n" "{uname}"\n')
    for name in FAKES:
        stub(name, f'echo "{name} $*" >> "{log}"\nexit 1\n')
    # Two user directories that hold the same command: the Unix scan reports
    # them, the Windows branch never looks.
    for user_dir in ("a", "b"):
        (tmp_path / user_dir).mkdir()
        stub_path = tmp_path / user_dir / "dupcmd"
        stub_path.write_text("#!/bin/sh\n", encoding="utf-8", newline="\n")
        stub_path.chmod(0o755)
    done = subprocess.run(
        [just, "--justfile", str(ROOT / "justfile"), recipe],
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "HOME": str(tmp_path),
            "VALIDATE_PATH": f"{tmp_path / 'a'}:{tmp_path / 'b'}",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return done, log.read_text(encoding="utf-8")


@pytest.mark.parametrize("uname", WINDOWS_UNAMES)
@pytest.mark.parametrize("recipe", RECIPES)
def test_the_recipe_skips_on_windows(tmp_path: Path, recipe: str, uname: str) -> None:
    done, calls = _run(tmp_path, recipe, uname)
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    assert calls == ""


@pytest.mark.parametrize("recipe", RECIPES)
def test_the_recipe_runs_elsewhere(tmp_path: Path, recipe: str) -> None:
    # The skip is the Windows branch only: on Linux the recipe goes on, to a
    # failing fake tool or to the duplicate the scan reports.
    done, calls = _run(tmp_path, recipe, "Linux")
    assert done.returncode != 0, done.stdout[-2000:] + done.stderr[-2000:]
    if recipe == "validate-path-duplicates":
        assert "dupcmd" in done.stdout + done.stderr
    else:
        assert calls != ""
