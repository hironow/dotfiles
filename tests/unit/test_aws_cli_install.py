"""AWS pins and unpacking fail closed, without cloud access or downloaded code.

The small shell fixtures exercise the production hook's guards and copy semantics.
Actual Apple signature/native backend verification is a separate Mac smoke check.
"""

import hashlib
import os
import shlex
import shutil
import struct
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MAC_SHA = "ec350e9e8e9ceb49ccd2cb7fcdc69f3b6a424f83dbae64f3dc6499157a5eca07"


def aws_spec() -> dict:
    return tomllib.loads(
        (ROOT / "config/mise/config.toml").read_text(encoding="utf-8")
    )["tools"]["http:aws"]


def executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def fixture_hook(tmp_path: Path) -> tuple[str, Path, Path, Path, dict[str, str]]:
    """Inject only OS/signature/digest fixtures; never execute a payload file."""
    script = aws_spec()["postinstall"]
    install = tmp_path / "AWS ' quoted directory"
    payload = install / "payload"
    payload.mkdir(parents=True)
    archive = tmp_path / "immutable-package"
    archive.write_bytes(b"owned package fixture, not executable\n")
    os.link(archive, payload / "aws")
    runtime = tmp_path / "reference-runtime"
    runtime.mkdir()
    # A header recognized by file(1), with no executable instructions.
    macho = struct.pack("<IIIIIIII", 0xFEEDFACF, 0x0100000C, 0, 2, 0, 0, 0, 0)
    (runtime / "aws").write_bytes(macho)
    (runtime / "aws_completer").write_bytes(macho)
    (runtime / "library-data").write_bytes(b"runtime data must be copied too\n")
    (runtime / "empty-directory").mkdir()
    for name in ("aws", "aws_completer"):
        (runtime / name).chmod(0o755)
    home = tmp_path / "home"
    executable(
        home / ".local/bin/mise",
        "#!/bin/sh\nset -eu\n"
        '[ "$*" = "-C / where http:aws@2.39.6" ] || exit 79\n'
        'printf "%s\\n" "$FIXTURE_ENGINE_PATH"\n',
    )
    pkgutil = tmp_path / "pkgutil"
    executable(
        pkgutil,
        '#!/bin/sh\nset -eu\ncase "$1" in\n'
        ' --check-signature) printf "%s\\n" '
        '"Developer ID Installer: Fixture (94KV3E626L)" '
        '"Apple Root CA" "trusted by the Apple notary service";;\n'
        ' --expand-full) mkdir -p "$3/aws-cli.pkg/Payload/aws-cli"; '
        'cp -pR "$FIXTURE_RUNTIME/." "$3/aws-cli.pkg/Payload/aws-cli/";;\n'
        " *) exit 78;;\nesac\n",
    )
    script = script.replace('"$(/usr/bin/uname -s)"', '"Darwin"')
    script = script.replace(MAC_SHA, hashlib.sha256(archive.read_bytes()).hexdigest())
    script = script.replace("/usr/sbin/pkgutil", shlex.quote(str(pkgutil)))
    env = {
        "HOME": str(home),
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "MISE_TOOL_NAME": "http:aws",
        "MISE_TOOL_VERSION": "2.39.6",
        "MISE_TOOL_INSTALL_PATH": str(install),
        "FIXTURE_ENGINE_PATH": str(install),
        "FIXTURE_RUNTIME": str(runtime),
    }
    return script, install, archive, runtime, env


def run_hook(script: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    shell = shutil.which("sh")
    assert shell is not None
    return subprocess.run(
        [shell, "-c", script],
        cwd="/",
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=20,
    )


@pytest.mark.skipif(
    sys.platform == "win32", reason="Mac unpack hook uses POSIX fixtures"
)
def test_copy_unlinks_raw_cache_hardlink_and_preserves_entire_runtime(
    tmp_path: Path,
) -> None:
    script, install, archive, runtime, env = fixture_hook(tmp_path)
    before = archive.read_bytes()
    result = run_hook(script, env)
    assert result.returncode == 0, result.stderr
    assert archive.read_bytes() == before
    assert not archive.samefile(install / "payload/aws")
    assert {p.relative_to(runtime) for p in runtime.rglob("*")} == {
        p.relative_to(install / "payload") for p in (install / "payload").rglob("*")
    }
    for path in runtime.rglob("*"):
        copied = install / "payload" / path.relative_to(runtime)
        assert path.stat().st_mode & 0o111 == copied.stat().st_mode & 0o111
        if path.is_file():
            assert path.read_bytes() == copied.read_bytes()
    assert not list(install.glob(".aws-pkg.*"))


@pytest.mark.skipif(
    sys.platform == "win32", reason="Mac unpack hook uses POSIX fixtures"
)
@pytest.mark.parametrize(
    "fault",
    [
        "root",
        "relative",
        "outside",
        "symlink-root",
        "symlink-payload",
        "symlink-raw",
        "identity",
        "version",
        "extra",
        "payload-mise",
        "digest",
        "query",
        "signature",
    ],
)
def test_unpack_guards_fail_before_outside_or_archive_mutation(
    tmp_path: Path, fault: str
) -> None:
    script, install, archive, _runtime, env = fixture_hook(tmp_path)
    before = archive.read_bytes()
    sentinel = tmp_path / "outside-sentinel"
    sentinel.write_bytes(b"outside stays unchanged\n")
    payload = install / "payload"
    if fault == "root":
        env["MISE_TOOL_INSTALL_PATH"] = "/"
    elif fault == "relative":
        env["MISE_TOOL_INSTALL_PATH"] = "relative"
    elif fault == "outside":
        env["MISE_TOOL_INSTALL_PATH"] = str(tmp_path)
    elif fault == "symlink-root":
        link = tmp_path / "linked-root"
        link.symlink_to(install, target_is_directory=True)
        env["MISE_TOOL_INSTALL_PATH"] = str(link)
    elif fault == "symlink-payload":
        payload.rename(install / "displaced")
        payload.symlink_to(tmp_path, target_is_directory=True)
    elif fault == "symlink-raw":
        (payload / "aws").unlink()
        (payload / "aws").symlink_to(sentinel)
    elif fault == "identity":
        env["MISE_TOOL_NAME"] = "not-aws"
    elif fault == "version":
        env["MISE_TOOL_VERSION"] = "0.0.0"
    elif fault in {"extra", "payload-mise"}:
        executable(
            payload / ("mise" if fault == "payload-mise" else "extra"),
            '#!/bin/sh\nprintf poisoned > "$FIXTURE_SENTINEL"\n',
        )
        env["FIXTURE_SENTINEL"] = str(sentinel)
    elif fault == "digest":
        script = script.replace(hashlib.sha256(before).hexdigest(), "0" * 64)
    elif fault == "query":
        script = script.replace(
            '"$manager" -C / where http:aws@2.39.6', "/usr/bin/false"
        )
    elif fault == "signature":
        script = script.replace("94KV3E626L", "0000000000")
    result = run_hook(script, env)
    assert result.returncode != 0, fault
    assert sentinel.read_bytes() == b"outside stays unchanged\n"
    assert archive.read_bytes() == before
    assert not list(install.glob(".aws-pkg.*"))
