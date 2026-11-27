"""The dev container image installs mise from a signed, pinned release (ADR 0068).

jdx's apt repository lists only the latest mise, so the feature installs the
GitHub release tarball at `config/mise/image-tools.toml` [bootstrap].mise. It
checks the tarball against the release's SHASUMS256.asc, which must be
signed by the key ADR 0001 pinned for the apt repository.

`verify_artifact_with_signed_checksums` runs here with the real gpg, a
throwaway signing key, and a fake curl that serves that key.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from _bash_hook import bash_path, resolve_bash, run_bash
from test_apt_keyring_format import _gnupg_home, _gpg, _primary_fingerprints

ROOT = Path(__file__).resolve().parents[2]
INSTALL = ROOT / ".devcontainer/features/dotfiles-tools/install.sh"
MISE_FINGERPRINT = "24853EC9F655CE80B48E6C3A8B81C9D17413A06D"
FUNCTION = "verify_artifact_with_signed_checksums"
GPG = shutil.which("gpg")
# macOS ships it in /sbin, outside the restricted PATH the function runs with.
SHA256SUM = shutil.which("sha256sum")


def _feature() -> str:
    return INSTALL.read_text(encoding="utf-8")


def _fetch_first() -> str:
    match = re.search(
        r"^fetch_first\(\) \{\n.*?^\}\n", _feature(), re.MULTILINE | re.DOTALL
    )
    assert match, "fetch_first not found"
    return match.group(0)


@pytest.mark.parametrize(
    "working, want",
    [("first second", "first"), ("second", "second"), ("", None)],
)
def test_fetch_first_takes_the_first_host_that_answers(tmp_path, working, want):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    # a fake curl: `-o <file> <url>` last; only the hosts in $WORKING answer
    curl.write_text(
        '#!/bin/sh\nwhile [ "$#" -gt 3 ]; do shift; done\n'
        "host=${3#https://}; host=${host%%/*}\n"
        'case " $WORKING " in *" $host "*) printf %s "$host" > "$2" ;; *) exit 22 ;; esac\n',
        encoding="utf-8",
        newline="\n",
    )
    curl.chmod(0o755)
    out = tmp_path / "file"
    script = tmp_path / "run.sh"
    script.write_text(
        "set -eu\n" + _fetch_first()
        + f'fetch_first "{bash_path(out)}" https://first/x https://second/x\n',
        encoding="utf-8",
        newline="\n",
    )  # fmt: skip
    bash_dir = Path(resolve_bash()).parent
    result = run_bash(
        script,
        cwd=tmp_path,
        env={
            "PATH": ":".join(
                [bash_path(bin_dir), bash_path(bash_dir), "/usr/bin", "/bin"]
            ),
            "WORKING": working,
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=30,
    )
    if want is None:
        assert result.returncode != 0, result.stdout + result.stderr
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert out.read_text(encoding="utf-8") == want


def _function() -> str:
    match = re.search(
        rf"^{FUNCTION}\(\) \{{\n.*?^\}}\n", _feature(), re.MULTILINE | re.DOTALL
    )
    assert match, f"{FUNCTION} not found"
    return match.group(0)


ARTIFACT = "mise-v2026.10.17-linux-x64-musl.tar.gz"


@pytest.fixture(scope="module")
def signing_keys(tmp_path_factory):
    """Two throwaway signing keys: the pinned one and a stranger."""
    if GPG is None:
        pytest.skip("needs gpg to sign checksums")
    with _gnupg_home() as home:
        for name in ("Fixture Release", "Fixture Stranger"):
            made = _gpg(
                home, "--passphrase", "", "--quick-gen-key",
                f"{name} <release@example.invalid>", "ed25519", "sign", "1d",
            )  # fmt: skip
            assert made.returncode == 0, made.stderr
        exported = _gpg(home, "--armor", "--export")
        assert exported.returncode == 0 and exported.stdout, exported.stderr
        key = tmp_path_factory.mktemp("release-key") / "key.asc"
        key.write_bytes(exported.stdout)
        fingerprints = _primary_fingerprints(home, key)
        assert len(fingerprints) == 2, fingerprints
        yield home, key, fingerprints


def _signed(home: Path, signer: str, text: str, out: Path, *extra: str) -> Path:
    plain = out.with_suffix(".txt")
    plain.write_text(text, encoding="utf-8", newline="\n")
    signed = _gpg(
        home, *extra, "--passphrase", "", "--pinentry-mode", "loopback",
        "--local-user", signer, "--output", str(out), "--clearsign", str(plain),
    )  # fmt: skip
    assert signed.returncode == 0, signed.stderr
    return out


def _verify(tmp_path, key: Path, expected: str, signed: Path, artifact: Path):
    if SHA256SUM is None:
        pytest.skip("needs sha256sum to check the tarball")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    curl = bin_dir / "curl"
    # the call ends with `-o <file> <url>`; serve the fixture key file
    curl.write_text(
        '#!/bin/sh\nwhile [ "$#" -gt 3 ]; do shift; done\n'
        f'[ "$1" = -o ] || exit 97\ncp "{bash_path(key)}" "$2"\n',
        encoding="utf-8",
        newline="\n",
    )
    curl.chmod(0o755)
    script = tmp_path / "run.sh"
    script.write_text(
        "set -eu\n"
        + _function()
        + f"{FUNCTION} https://release.example.invalid/key.pub {expected} "
        f'"{bash_path(signed)}" "{bash_path(artifact)}"\n',
        encoding="utf-8",
        newline="\n",
    )
    assert GPG is not None
    bash_dir = Path(resolve_bash()).parent
    path = ":".join(
        [
            bash_path(p)
            for p in (bin_dir, Path(GPG).parent, Path(SHA256SUM).parent, bash_dir)
        ]
        + ["/usr/bin", "/bin"]
    )
    return run_bash(
        script,
        cwd=tmp_path,
        env={
            "PATH": path,
            "SystemRoot": os.environ.get("SystemRoot", ""),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=60,
    )


def _artifact(tmp_path: Path, content: bytes = b"mise release fixture\n") -> Path:
    artifact = tmp_path / ARTIFACT
    artifact.write_bytes(content)
    return artifact


def _sums(artifact: Path, *names: str) -> str:
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    other = "0" * 64
    return (
        "".join(f"{digest}  {name}\n" for name in names) + f"{other}  ./other.tar.gz\n"
    )


def test_a_tarball_listed_in_checksums_signed_by_the_pinned_key_passes(
    tmp_path, signing_keys
):
    home, key, (pinned, _) = signing_keys
    artifact = _artifact(tmp_path)
    signed = _signed(home, pinned, _sums(artifact, f"./{ARTIFACT}"), tmp_path / "s.asc")
    result = _verify(tmp_path, key, pinned, signed, artifact)
    assert result.returncode == 0, result.stdout + result.stderr


NO_GOOD_SIGNATURE = "has no good signature by"
NOT_ONE_LINE = "the signed list needs exactly one line"


@pytest.mark.parametrize(
    "case, reason",
    [
        ("other fingerprint", NO_GOOD_SIGNATURE),
        ("stranger signed", NO_GOOD_SIGNATURE),
        ("tampered", NOT_ONE_LINE),
        ("missing", NOT_ONE_LINE),
        ("twice", NOT_ONE_LINE),
        ("unsigned line", NOT_ONE_LINE),
    ],
)
def test_anything_else_stops_the_build(tmp_path, signing_keys, case, reason):
    home, key, (pinned, stranger) = signing_keys
    artifact = _artifact(tmp_path)
    names = {
        "missing": [],
        "twice": [f"./{ARTIFACT}", ARTIFACT],
        "unsigned line": [],
    }.get(case, [f"./{ARTIFACT}"])
    signer = stranger if case == "stranger signed" else pinned
    signed = _signed(home, signer, _sums(artifact, *names), tmp_path / "s.asc")
    if case == "tampered":
        artifact.write_bytes(b"something else\n")
    if case == "unsigned line":
        # gpg checks only the armored part; one good line before it is not
        # signed, and a check that read the raw file would accept it
        line = _sums(artifact, f"./{ARTIFACT}").splitlines()[0] + "\n"
        signed.write_text(
            line + signed.read_text(encoding="utf-8"),
            encoding="utf-8",
            newline="\n",
        )
    expected = stranger if case == "other fingerprint" else pinned
    if case == "other fingerprint":
        # the pinned key signed it, but the build pins the other one
        signed = _signed(
            home, pinned, _sums(artifact, f"./{ARTIFACT}"), tmp_path / "s2.asc"
        )
    result = _verify(tmp_path, key, expected, signed, artifact)
    assert result.returncode != 0, (case, result.stdout + result.stderr)
    assert reason in result.stderr, (case, result.stderr)


@pytest.mark.parametrize("case", ["revoked", "expired"])
def test_a_signature_by_a_revoked_or_expired_key_stops_the_build(tmp_path, case):
    # gpg still exits 0 and prints VALIDSIG for such a signature; only GOODSIG
    # gives way to REVKEYSIG or EXPKEYSIG. apt refuses both, and so must we.
    if GPG is None:
        pytest.skip("needs gpg to sign checksums")
    made_at, signed_at = [], []
    if case == "expired":
        # made two days ago, for one day, and used an hour later. gpg's faked
        # clock keeps running from the given time, so signing at the same
        # given time could land before the key was made ("created 1 second in
        # the future") when making the key took a second.
        past = datetime.now(UTC) - timedelta(days=2)
        made_at = ["--faked-system-time", past.strftime("%Y%m%dT%H%M%S")]
        later = past + timedelta(hours=1)
        signed_at = ["--faked-system-time", later.strftime("%Y%m%dT%H%M%S")]
    with _gnupg_home() as home:  # its own: the revocation must not leak out
        made = _gpg(
            home, *made_at, "--passphrase", "", "--quick-gen-key",
            "Fixture Release <release@example.invalid>", "ed25519", "sign", "1d",
        )  # fmt: skip
        assert made.returncode == 0, made.stderr
        key = tmp_path / "key.asc"
        key.write_bytes(_gpg(home, "--armor", "--export").stdout)
        (fingerprint,) = _primary_fingerprints(home, key)
        artifact = _artifact(tmp_path)
        sums = _sums(artifact, f"./{ARTIFACT}")
        signed = _signed(home, fingerprint, sums, tmp_path / "s.asc", *signed_at)
        if case == "revoked":
            # gpg writes the certificate with ':' before its armor line, so
            # that nobody imports it by accident
            cert = home / "openpgp-revocs.d" / f"{fingerprint}.rev"
            text = cert.read_text(encoding="utf-8")
            revocation = tmp_path / "revocation.asc"
            revocation.write_text(
                text.replace(":-----BEGIN", "-----BEGIN", 1), encoding="utf-8"
            )
            imported = _gpg(home, "--import", str(revocation))
            assert imported.returncode == 0, imported.stderr
            key.write_bytes(_gpg(home, "--armor", "--export").stdout)
        result = _verify(tmp_path, key, fingerprint, signed, artifact)
    assert result.returncode != 0, (case, result.stdout + result.stderr)
    assert NO_GOOD_SIGNATURE in result.stderr, (case, result.stderr)


# ADR-0093 D4: the image runs the mise it downloads, so the feature must call
# the pinned-key check before it installs. The check itself runs above with
# real gpg; this runs the feature's own mise block (cut out of install.sh,
# after its set line and its ARCH line) with recording shell functions in
# place of the fetches, the check, tar and install.
FEATURE_FAKES = """record() { printf '%s\\n' "$*" >> "$FIXTURE_LOG"; }
uname() { echo x86_64; }
fetch_first() { record "fetch $1 $2 $3"; : > "$1"; }
verify_artifact_with_signed_checksums() { record "verify $*"; return "$FIXTURE_VERIFY_RC"; }
tar() { record "tar $*"; mkdir -p "$MISE_TMP/mise/bin"; : > "$MISE_TMP/mise/bin/mise"; }
install() { record "install $*"; }
"""


def run_feature_mise_block(
    tmp_path: Path, install: Path, *, verify_rc: int
) -> tuple[int, list[str]]:
    text = install.read_text(encoding="utf-8")
    set_line = re.search(r"(?m)^set -euo pipefail$", text)
    arch_line = re.search(r"(?m)^ARCH=\$\(uname -m\)$", text)
    block = re.search(r'(?ms)^MISE_VERSION=.*?^rm -rf "\$\{MISE_TMP\}"$', text)
    assert set_line and arch_line and block, "the feature's mise block moved"
    temp = tmp_path / "tmp"
    temp.mkdir()
    log = tmp_path / "calls"
    log.touch()
    script = "\n".join((set_line[0], FEATURE_FAKES, arch_line[0], block[0], ""))
    path = tmp_path / "block.sh"
    path.write_text(script, encoding="utf-8", newline="\n")
    bash_dir = Path(resolve_bash()).parent
    done = run_bash(
        path,
        cwd=tmp_path,
        env={
            "PATH": ":".join([bash_path(bash_dir), "/usr/bin", "/bin"]),
            "TMPDIR": bash_path(temp),
            "FIXTURE_LOG": bash_path(log),
            "FIXTURE_VERIFY_RC": str(verify_rc),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return done.returncode, log.read_text(encoding="utf-8").splitlines()


def check_a_failed_key_check_installs_nothing(tmp_path: Path, install: Path) -> None:
    rc, calls = run_feature_mise_block(tmp_path, install, verify_rc=1)
    assert rc != 0
    assert any(c.startswith("verify ") for c in calls), calls
    assert not [c for c in calls if c.startswith(("tar ", "install "))], calls


def check_mise_is_installed_after_the_pinned_key_check(
    tmp_path: Path, install: Path
) -> None:
    rc, calls = run_feature_mise_block(tmp_path, install, verify_rc=0)
    assert rc == 0, calls
    kinds = [c.split(" ", 1)[0] for c in calls]
    assert kinds == ["fetch", "fetch", "verify", "tar", "install"], calls
    verify = calls[2].split()
    assert verify[1:3] == ["https://mise.jdx.dev/gpg-key.pub", MISE_FINGERPRINT], verify
    assert verify[3].endswith("/SHASUMS256.asc") and verify[4].endswith(".tar.gz"), (
        verify
    )
    assert calls[0].split()[1] == verify[4] and calls[1].split()[1] == verify[3], calls
    assert calls[4].endswith("/mise/bin/mise /usr/local/bin/mise"), calls


@pytest.mark.skipif(sys.platform == "win32", reason="the feature runs in a Linux image")
def test_a_failed_key_check_installs_nothing(tmp_path: Path) -> None:
    check_a_failed_key_check_installs_nothing(tmp_path, INSTALL)


@pytest.mark.skipif(sys.platform == "win32", reason="the feature runs in a Linux image")
def test_mise_is_installed_after_the_pinned_key_check(tmp_path: Path) -> None:
    check_mise_is_installed_after_the_pinned_key_check(tmp_path, INSTALL)
