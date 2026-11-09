"""The dev container feature's apt keyrings are OpenPGP keyrings.

`.devcontainer/features/dotfiles-tools/install.sh`
`import_apt_key_with_fingerprint` checks a vendor key's fingerprint and
installs the apt keyring for it. The image is Debian trixie, whose apt
verifies signatures with sqv (Sequoia); sqv reads OpenPGP keyrings, not the
GnuPG keybox (KBX) that `gpg --keyring <new file> --import` writes. A KBX
keyring makes `apt-get update` fail with "Failed to parse keyring".

The function runs here with the real gpg and a fake curl that serves a
throwaway vendor key file holding two primary keys (a vendor file may hold
several; all of them reach the apt keyring, as before).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest
from _bash_hook import bash_path, resolve_bash, run_bash

ROOT = Path(__file__).resolve().parents[2]
INSTALL = ROOT / ".devcontainer/features/dotfiles-tools/install.sh"
GPG = shutil.which("gpg")
pytestmark = pytest.mark.skipif(GPG is None, reason="needs gpg to build a keyring")


def _function() -> str:
    text = INSTALL.read_text(encoding="utf-8")
    match = re.search(
        r"^import_apt_key_with_fingerprint\(\) \{\n.*?^\}\n",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match, "import_apt_key_with_fingerprint not found"
    return match.group(0)


def _homedir(home: Path) -> str:
    """home as gpg's --homedir. Git for Windows' gpg cannot start its agent
    for a homedir in Windows form ("No agent running"); the /c/... form works."""
    return bash_path(home) if os.name == "nt" else str(home)


def _gpg(home: Path, *args: str) -> subprocess.CompletedProcess:
    assert GPG is not None
    return subprocess.run(
        [GPG, "--homedir", _homedir(home), "--batch", *args],
        capture_output=True,
        check=False,
    )


def _primary_fingerprints(home: Path, keyring: Path) -> list[str]:
    """Primary-key fingerprints in a key file, in file order."""
    shown = _gpg(home, "--show-keys", "--with-colons", str(keyring))
    assert shown.returncode == 0, shown.stderr
    primaries, record = [], ""
    for line in shown.stdout.decode().splitlines():
        fields = line.split(":")
        if fields[0] in {"pub", "sub"}:
            record = fields[0]
        elif fields[0] == "fpr" and record == "pub":
            primaries.append(fields[9])
    return primaries


@contextmanager
def _gnupg_home():
    """A GnuPG homedir with a short path, removed after.

    gpg reaches gpg-agent through a socket in the homedir, and a Unix socket
    path has a short limit (104 bytes on macOS) that pytest's temp
    directories there exceed ("can't connect to the gpg-agent: File name too
    long")."""
    short = Path("/tmp") if os.name != "nt" and Path("/tmp").is_dir() else None
    home = Path(tempfile.mkdtemp(prefix="gpg-", dir=short))
    home.chmod(0o700)
    try:
        yield home
    finally:
        gpgconf = shutil.which("gpgconf")
        if gpgconf:  # stop the agent this homedir started
            subprocess.run(
                [gpgconf, "--homedir", _homedir(home), "--kill", "all"],
                capture_output=True,
                check=False,
            )
        shutil.rmtree(home, ignore_errors=True)


@pytest.fixture(scope="module")
def vendor_keys(tmp_path_factory):
    """A throwaway vendor key file with two primary keys, armored."""
    with _gnupg_home() as home:
        for name in ("Fixture Vendor A", "Fixture Vendor B"):
            made = _gpg(
                home,
                "--passphrase",
                "",
                "--quick-gen-key",
                f"{name} <vendor@example.invalid>",
                "ed25519",
                "sign",
                "1d",
            )
            assert made.returncode == 0, made.stderr
        exported = _gpg(home, "--armor", "--export")
        assert exported.returncode == 0 and exported.stdout, exported.stderr
        armored = tmp_path_factory.mktemp("vendor-key") / "vendor.asc"
        armored.write_bytes(exported.stdout)
        fingerprints = _primary_fingerprints(home, armored)
        assert len(fingerprints) == 2, fingerprints
        yield armored, fingerprints


@pytest.fixture
def gnupg_home():
    with _gnupg_home() as home:
        yield home


def _run(tmp_path, home, armored, expected, gpg_wrapper=None):
    """Run the function; its temporary files go to tmp_path/work."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    # the call ends with `-o <file> <url>`; serve the fixture key file
    curl.write_text(
        '#!/bin/sh\nwhile [ "$#" -gt 3 ]; do shift; done\n'
        f'[ "$1" = -o ] || exit 97\ncp "{bash_path(armored)}" "$2"\n',
        encoding="utf-8",
        newline="\n",
    )
    curl.chmod(0o755)
    assert GPG is not None  # the module is skipped without gpg
    if gpg_wrapper is not None:
        # a gpg that misbehaves only on --export; everything else is real
        gpg = bin_dir / "gpg"
        gpg.write_text(
            '#!/bin/sh\nfor a in "$@"; do [ "$a" = --export ] && { '
            + gpg_wrapper
            + f'; }}; done\nexec "{bash_path(Path(GPG))}" "$@"\n',
            encoding="utf-8",
            newline="\n",
        )
        gpg.chmod(0o755)
    work = tmp_path / "work"
    work.mkdir()
    out = tmp_path / "keyrings/vendor.gpg"
    out.parent.mkdir()
    script = tmp_path / "run.sh"
    script.write_text(
        "set -eu\n"
        # its temporary files go to this test's directory, not the host /tmp
        + _function().replace("/tmp/dotfiles-apt-key", f"{bash_path(work)}/apt-key")
        + "import_apt_key_with_fingerprint "
        f'https://vendor.example.invalid/key.gpg {expected} "{bash_path(out)}"\n',
        encoding="utf-8",
        newline="\n",
    )
    bash_dir = Path(resolve_bash()).parent
    # native directories through bash_path; /usr/bin and /bin are paths inside
    # bash (Git Bash's own on Windows), so they stay as written
    path = ":".join(
        [bash_path(p) for p in (bin_dir, Path(GPG).parent, bash_dir)]
        + ["/usr/bin", "/bin"]
    )
    result = run_bash(
        script,
        cwd=tmp_path,
        env={
            "PATH": path,
            "GNUPGHOME": bash_path(home),
            "SystemRoot": os.environ.get("SystemRoot", ""),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    return result, out, work


def test_the_keyring_is_openpgp_and_holds_every_vendor_key(
    tmp_path, gnupg_home, vendor_keys
):
    armored, fingerprints = vendor_keys
    result, out, work = _run(tmp_path, gnupg_home, armored, fingerprints[0])
    assert result.returncode == 0, result.stdout + result.stderr
    data = out.read_bytes()
    # A GnuPG keybox carries the magic "KBXf" at offset 8; sqv cannot read it.
    assert data[8:12] != b"KBXf", "a GnuPG keybox, not an OpenPGP keyring"
    # An OpenPGP keyring starts with a packet tag: the high bit is set.
    assert data and data[0] & 0x80, data[:16]
    # every primary key of the vendor file, not only the checked one
    assert sorted(_primary_fingerprints(gnupg_home, out)) == sorted(fingerprints)
    if os.name != "nt":  # Windows reports only a read-only bit
        assert out.stat().st_mode & 0o777 == 0o644
    assert not [p.name for p in work.iterdir() if p.name.startswith("apt-key")]


def test_a_wrong_fingerprint_installs_no_keyring(tmp_path, gnupg_home, vendor_keys):
    armored, _ = vendor_keys
    result, out, _ = _run(tmp_path, gnupg_home, armored, "0" * 40)
    assert result.returncode != 0
    assert "fingerprint mismatch" in result.stderr
    assert not out.exists()


@pytest.mark.parametrize(
    "wrapper",
    ["exit 2", "exit 0"],
    ids=["export-fails", "export-empty"],
)
def test_a_failed_export_installs_nothing_and_cleans_up(
    tmp_path, gnupg_home, vendor_keys, wrapper
):
    armored, fingerprints = vendor_keys
    result, out, work = _run(
        tmp_path, gnupg_home, armored, fingerprints[0], gpg_wrapper=wrapper
    )
    assert result.returncode != 0, result.stdout + result.stderr
    assert "export produced no keyring" in result.stderr
    assert not out.exists()
    assert not [p.name for p in work.iterdir() if p.name.startswith("apt-key")]
