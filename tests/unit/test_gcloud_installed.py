"""`just dump` and `just add-gcloud` agree on what "installed" means, and a
failed gcloud call never passes for an empty or partial record.

A component with an update waiting is installed: gcloud reports its state as
"Update Available", not "Installed". The dump recipe filtered on
`state.name=Installed` only, so a Mac with updates waiting recorded neither
alpha, beta, bq, core, preview nor pubsub-emulator; add-gcloud used the same
filter and would `sudo gcloud components install` what was already there.
`state.name:(...)` is no fix: `:` matches substrings, and "Not Installed"
contains "Installed". The dump also wrote gcloud's output straight into the
record without pipefail, so a failed call left an empty record and exit 0.

The real recipes run here against a stub `gcloud` (and `sudo`) on PATH, from a
copy of the justfile, so nothing touches the tracked dump/ or the machine.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = ROOT / "justfile"
INSTALLED = 'state.name="Installed" OR state.name="Update Available"'


@pytest.fixture
def sandbox(tmp_path: Path) -> dict:
    if sys.platform == "win32":
        pytest.skip(
            "native Windows: shebang recipes need a Unix bash (see test_dump_brew_optional)"
        )
    just = shutil.which("just")
    if just is None:
        pytest.skip("just not on PATH")
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(JUSTFILE, repo / "justfile")
    shutil.copy(ROOT / "scripts/dump_host.sh", repo / "scripts/dump_host.sh")
    (repo / "dump/testhost").mkdir(parents=True)
    home = tmp_path / "home"
    (home / ".config/git").mkdir(parents=True)
    (home / ".config/git/ignore").write_text("*.swp\n", encoding="utf-8")
    stubs = tmp_path / "bin"
    stubs.mkdir()
    calls = tmp_path / "calls"
    for name in ("gcloud", "sudo"):
        stub = stubs / name
        # Listing and installation can fail independently; never run real sudo.
        stub.write_text(
            "#!/bin/sh\n"
            f'echo "{name} $*" >> "{calls}"\n'
            + (
                'if [ "$1 $2" = "components install" ]; then\n'
                '  exit "${GCLOUD_INSTALL_RC:-0}"\n'
                "fi\n"
                '[ -n "$GCLOUD_OUT" ] && printf "%b" "$GCLOUD_OUT"\n'
                'exit "${GCLOUD_RC:-0}"\n'
                if name == "gcloud"
                else "exit 0\n"
            ),
            encoding="utf-8",
        )
        stub.chmod(0o755)
    env = {
        # no brew on this PATH: the dump skips the Brewfile (test_dump_brew_optional)
        "PATH": f"{stubs}:/usr/bin:/bin",
        "HOME": str(home),
        "DOTFILES_HOST": "testhost",
    }
    return {"just": just, "repo": repo, "env": env, "calls": calls}


def _run(sandbox: dict, recipe: str, **env: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sandbox["just"], "-f", str(sandbox["repo"] / "justfile"), recipe],
        cwd=sandbox["repo"],
        env={**sandbox["env"], **env},
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )


def _record(sandbox: dict) -> Path:
    return sandbox["repo"] / "dump/testhost/gcloud"


def _calls(sandbox: dict) -> str:
    calls = sandbox["calls"]
    return calls.read_text(encoding="utf-8") if calls.exists() else ""


def test_dump_and_restore_list_with_one_filter(sandbox: dict) -> None:
    # One definition of "installed": an "Update Available" component is
    # installed, so a restore must not install it again.
    assert _run(sandbox, "dump", GCLOUD_OUT="alpha\\n").returncode == 0
    assert _run(sandbox, "add-gcloud", GCLOUD_OUT="alpha\\n").returncode == 0
    filters = re.findall(r"--filter=(.*?) --format=", _calls(sandbox))
    assert filters == [INSTALLED, INSTALLED]


def test_dump_records_what_gcloud_reports_installed(sandbox: dict) -> None:
    done = _run(sandbox, "dump", GCLOUD_OUT="kubectl\\nalpha\\nalpha\\n")
    assert done.returncode == 0, done.stderr
    assert _record(sandbox).read_text(encoding="utf-8") == "alpha\nkubectl\n"
    assert INSTALLED in _calls(sandbox)


@pytest.mark.parametrize(
    "gcloud",
    [
        {"GCLOUD_RC": "1", "GCLOUD_OUT": "alpha\\n"},  # gcloud failed (DNS, auth)
        {"GCLOUD_OUT": ""},  # nothing reported: never a real gcloud install
    ],
    ids=["failed", "empty"],
)
def test_a_failed_dump_keeps_the_previous_record(sandbox: dict, gcloud: dict) -> None:
    _record(sandbox).write_text("core\nkubectl\n", encoding="utf-8")
    done = _run(sandbox, "dump", **gcloud)
    assert done.returncode != 0
    assert _record(sandbox).read_text(encoding="utf-8") == "core\nkubectl\n"


def test_restore_installs_nothing_when_updates_are_only_waiting(sandbox: dict) -> None:
    # gcloud reports both, one of them as "Update Available": both are there
    _record(sandbox).write_text("alpha\nkubectl\n", encoding="utf-8")
    done = _run(sandbox, "add-gcloud", GCLOUD_OUT="alpha\\nkubectl\\n")
    assert done.returncode == 0, done.stderr
    assert "sudo" not in _calls(sandbox)
    assert "components install" not in _calls(sandbox)


@pytest.mark.parametrize(
    "gcloud",
    [{"GCLOUD_RC": "1", "GCLOUD_OUT": "alpha\\n"}, {"GCLOUD_OUT": ""}],
    ids=["failed", "empty"],
)
def test_restore_stops_when_gcloud_cannot_list(sandbox: dict, gcloud: dict) -> None:
    # never read a failed or empty listing as "nothing installed" and install it all
    _record(sandbox).write_text("alpha\nkubectl\n", encoding="utf-8")
    done = _run(sandbox, "add-gcloud", **gcloud)
    assert done.returncode != 0
    assert "sudo" not in _calls(sandbox)
    assert "components install" not in _calls(sandbox)


@pytest.mark.parametrize("install_rc", ["0", "7"], ids=["success", "failed-install"])
def test_restore_installs_only_missing_components_without_sudo(
    sandbox: dict, install_rc: str
) -> None:
    _record(sandbox).write_text("kubectl\nbeta\nalpha\nbeta\ncore\n", encoding="utf-8")
    done = _run(
        sandbox,
        "add-gcloud",
        GCLOUD_OUT="kubectl\\ncore\\n",
        GCLOUD_INSTALL_RC=install_rc,
    )
    assert _calls(sandbox).splitlines() == [
        f"gcloud components list --filter={INSTALLED} --format=value(id)",
        "gcloud components install --quiet alpha beta",
    ]
    if install_rc == "0":
        assert done.returncode == 0, done.stderr
    else:
        assert done.returncode != 0


def test_a_dump_that_cannot_write_keeps_the_previous_record(sandbox: dict) -> None:
    # sort fails (disk full, say) after gcloud listed fine: no truncated record
    stub = Path(sandbox["env"]["PATH"].split(":")[0]) / "sort"
    stub.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    stub.chmod(0o755)
    _record(sandbox).write_text("core\nkubectl\n", encoding="utf-8")
    done = _run(sandbox, "dump", GCLOUD_OUT="alpha\\n")
    assert done.returncode != 0
    assert _record(sandbox).read_text(encoding="utf-8") == "core\nkubectl\n"
