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
import tomllib
from pathlib import Path

import pytest
from _bash_hook import bash_path, resolve_bash, run_bash
from test_apt_keyring_format import _gnupg_home, _gpg, _primary_fingerprints

ROOT = Path(__file__).resolve().parents[2]
INSTALL = ROOT / ".devcontainer/features/dotfiles-tools/install.sh"
IMAGE_TOOLS = ROOT / "config/mise/image-tools.toml"
MISE_FINGERPRINT = "24853EC9F655CE80B48E6C3A8B81C9D17413A06D"
FUNCTION = "verify_artifact_with_signed_checksums"
GPG = shutil.which("gpg")


def _feature() -> str:
    return INSTALL.read_text(encoding="utf-8")


def test_the_feature_installs_mise_without_its_apt_repository():
    text = _feature()
    assert "mise.jdx.dev/deb" not in text
    assert "mise-archive-keyring" not in text
    assert not re.search(r"apt-get install[^\n]*\bmise\b", text)


def test_the_feature_pins_mise_to_the_bootstrap_version():
    pinned = tomllib.loads(IMAGE_TOOLS.read_text(encoding="utf-8"))["bootstrap"]["mise"]
    assert re.findall(r'^MISE_VERSION="([^"]*)"$', _feature(), re.MULTILINE) == [pinned]


def test_the_feature_verifies_the_tarball_with_the_pinned_key():
    text = _feature()
    base = "https://github.com/jdx/mise/releases/download/v${MISE_VERSION}"
    assert f'MISE_BASE="{base}"' in text
    assert '"${MISE_BASE}/SHASUMS256.asc"' in text
    assert (
        f"{FUNCTION} https://mise.jdx.dev/gpg-key.pub \\\n  {MISE_FINGERPRINT} \\\n"
        in text
    )
    assert 'install -m 0755 "${MISE_TMP}/mise/bin/mise" /usr/local/bin/mise' in text


def test_each_download_has_a_second_host():
    # github.com's /releases/download/ failed for 1.5 h on 2026-11-09 (#580).
    # Either host may serve the bytes; the pinned signature decides.
    text = _feature()
    assert 'MISE_HOST="https://mise.jdx.dev/v${MISE_VERSION}"' in text
    assert (
        'fetch_first "${MISE_TMP}/${MISE_FILE}" '
        '"${MISE_HOST}/${MISE_FILE}" "${MISE_BASE}/${MISE_FILE}"\n' in text
    )
    # checksums from GitHub first, as mise's docs ask
    assert (
        'fetch_first "${MISE_TMP}/SHASUMS256.asc" '
        '"${MISE_BASE}/SHASUMS256.asc" "${MISE_HOST}/SHASUMS256.asc"\n' in text
    )


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


def _signed(home: Path, signer: str, text: str, out: Path) -> Path:
    plain = out.with_suffix(".txt")
    plain.write_text(text, encoding="utf-8", newline="\n")
    signed = _gpg(
        home, "--passphrase", "", "--pinentry-mode", "loopback",
        "--local-user", signer, "--output", str(out), "--clearsign", str(plain),
    )  # fmt: skip
    assert signed.returncode == 0, signed.stderr
    return out


def _verify(tmp_path, key: Path, expected: str, signed: Path, artifact: Path):
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
        [bash_path(p) for p in (bin_dir, Path(GPG).parent, bash_dir)]
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


def test_the_check_needs_no_more_than_the_tools_the_image_has():
    # gpg, sha256sum, awk, grep and mktemp are in the image before mise.
    body = _function()
    for tool in ("gpg ", "sha256sum", "mktemp", "awk", "grep"):
        assert tool in body, tool
