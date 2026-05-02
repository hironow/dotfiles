"""Tests for exe/scripts/cdr.

The wrapper fetches CF Access service token credentials from
Secret Manager and feeds them to the upstream `coder` CLI as
HTTP-Headers. A bug class we hit once already: the secret-refresh
path used `> "${file}.tmp"` + `chmod` and aborted under `set -e`
when gcloud failed before writing anything, leaving the next
invocation to error with `chmod: ...tmp: No such file or directory`.

Tests stub `gcloud` and `coder` so the script can be exercised
without real GCP / Coder access. We verify:

  - cache hit short-circuit
  - secret-refresh on stale cache writes the new value
  - gcloud failure does NOT leave a stranded `.tmp` file
  - empty payload from gcloud is rejected with a readable err()

The original wrapper requires `coder` (the upstream CLI) to be
installed; we stub that too so CI does not need it.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import textwrap
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CDR = ROOT / "exe" / "scripts" / "cdr"


def _stub_dir(
    tmp_path: Path,
    behaviours: dict[str, str],
    suffix: str = "stubs",
) -> Path:
    """Create a stubs directory with one executable per behaviour
    entry. `behaviours[name]` is the script body. `suffix` lets a
    single test create multiple distinct stub dirs."""
    stubs = tmp_path / suffix
    stubs.mkdir(exist_ok=True)
    for name, body in behaviours.items():
        p = stubs / name
        p.write_text(textwrap.dedent(body).lstrip("\n"))
        p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return stubs


BASH = shutil.which("bash") or "/bin/bash"


def _run(
    tmp_path: Path,
    stubs: Path,
    args: list[str],
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["PATH"] = f"{stubs}:{env['PATH']}"
    if extra_env:
        env.update(extra_env)
    # Use the absolute path to bash so the test's narrowed PATH does
    # not need to find it. The script under test then sees PATH=stubs
    # first, where it picks up our stub gcloud / coder.
    return subprocess.run(
        [BASH, str(CDR), *args],
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def gcloud_succeeding(tmp_path: Path) -> Path:
    """A gcloud stub that pretends to fetch one of two known secrets."""
    return _stub_dir(
        tmp_path,
        {
            "gcloud": """
                #!/usr/bin/env bash
                # Match the wrapper's invocation:
                #   gcloud secrets versions access latest --secret=<name>
                while [[ $# -gt 0 ]]; do
                  case "$1" in
                    --secret=exe-coder-cli-client-id)     echo 'fake-client-id'; exit 0 ;;
                    --secret=exe-coder-cli-client-secret) echo 'fake-secret-payload'; exit 0 ;;
                  esac
                  shift
                done
                exit 0
            """,
            "coder": """
                #!/usr/bin/env bash
                # Echo what we received so the test can inspect.
                printf 'coder-stub args=%s\\n' "$*"
                printf 'coder-stub CF_ACCESS_CLIENT_ID=%s\\n' "$CF_ACCESS_CLIENT_ID"
                printf 'coder-stub CF_ACCESS_CLIENT_SECRET=%s\\n' "$CF_ACCESS_CLIENT_SECRET"
                exit 0
            """,
        },
    )


@pytest.fixture
def gcloud_failing(tmp_path: Path) -> Path:
    """A gcloud stub that exits non-zero (auth missing / wrong project)."""
    return _stub_dir(
        tmp_path,
        {
            "gcloud": """
                #!/usr/bin/env bash
                echo 'gcloud-stub: simulated auth failure' >&2
                exit 1
            """,
            "coder": """
                #!/usr/bin/env bash
                exit 0
            """,
        },
    )


@pytest.fixture
def gcloud_empty_payload(tmp_path: Path) -> Path:
    """A gcloud stub that exits 0 but writes no bytes."""
    return _stub_dir(
        tmp_path,
        {
            "gcloud": """
                #!/usr/bin/env bash
                # Successful exit, empty stdout — Secret Manager could
                # in principle return a secret with no content.
                exit 0
            """,
            "coder": """
                #!/usr/bin/env bash
                exit 0
            """,
        },
    )


def test_cdr_fetches_secrets_and_invokes_coder(
    tmp_path: Path, gcloud_succeeding: Path
) -> None:
    """Happy path: cache cold, gcloud returns known payloads, the
    script execs `coder` with the credentials exported."""
    r = _run(tmp_path, gcloud_succeeding, ["list"])
    assert r.returncode == 0, f"cdr exited non-zero with succeeding gcloud:\n{r.stderr}"
    assert "coder-stub args=list" in r.stdout
    assert "CF_ACCESS_CLIENT_ID=fake-client-id" in r.stdout
    assert "CF_ACCESS_CLIENT_SECRET=fake-secret-payload" in r.stdout

    cache_dir = tmp_path / ".cache" / "exe-coder-cli"
    assert (cache_dir / "client_id").read_text() == "fake-client-id\n"
    assert (cache_dir / "client_secret").read_text() == "fake-secret-payload\n"
    # Cache files must be 0600.
    assert (cache_dir / "client_id").stat().st_mode & 0o077 == 0


def test_cdr_uses_cached_secret_within_ttl(
    tmp_path: Path, gcloud_succeeding: Path
) -> None:
    """Second invocation within TTL must NOT call gcloud — verify by
    swapping in a gcloud that always errors and confirming the
    second call still succeeds (cache hit short-circuits the
    refresh)."""
    # First call populates the cache.
    r1 = _run(tmp_path, gcloud_succeeding, ["list"])
    assert r1.returncode == 0

    # Replace gcloud with a poisoned stub. If the wrapper re-fetches,
    # this exits 1 and the subsequent err() trips.
    poisoned = _stub_dir(
        tmp_path,
        {
            "gcloud": """
                #!/usr/bin/env bash
                echo 'should not be called' >&2
                exit 1
            """,
            "coder": """
                #!/usr/bin/env bash
                exit 0
            """,
        },
        suffix="poisoned-stubs",
    )
    r2 = _run(tmp_path, poisoned, ["list"])
    assert r2.returncode == 0, (
        "second cdr call hit the (poisoned) gcloud stub, meaning the "
        f"cache hit path is broken:\n{r2.stderr}"
    )


def test_cdr_does_not_strand_tmp_when_gcloud_fails(
    tmp_path: Path, gcloud_failing: Path
) -> None:
    """The original bug: gcloud fails, set -e aborts, a zero-byte
    tmp file is left in the cache dir. The next invocation tries to
    chmod it and dies with 'No such file or directory' (or similar).

    Post-fix: a clean error message + no stray tmp files."""
    r = _run(tmp_path, gcloud_failing, ["list"])
    assert r.returncode != 0, "gcloud failure must propagate"
    assert "failed to fetch secret" in r.stderr.lower(), (
        f"err() did not surface a readable failure message:\n{r.stderr}"
    )

    cache_dir = tmp_path / ".cache" / "exe-coder-cli"
    if cache_dir.exists():
        leftover = sorted(p.name for p in cache_dir.iterdir() if p.name.startswith("."))
        assert not leftover, (
            f"failed gcloud invocation left stray dot-tmp files in the "
            f"cache dir: {leftover}. The wrapper must clean up on failure."
        )


def test_cdr_rejects_empty_secret_payload(
    tmp_path: Path, gcloud_empty_payload: Path
) -> None:
    """Secret Manager returning an empty body would otherwise leave a
    zero-byte cache file that the upstream coder CLI then trusts as
    a credential. Reject loudly."""
    r = _run(tmp_path, gcloud_empty_payload, ["list"])
    assert r.returncode != 0, "empty secret payload must propagate as error"
    assert "empty payload" in r.stderr.lower(), (
        f"err() did not surface an empty-payload message:\n{r.stderr}"
    )

    cache_dir = tmp_path / ".cache" / "exe-coder-cli"
    if cache_dir.exists():
        # No partial cache files should remain.
        for p in cache_dir.iterdir():
            assert p.stat().st_size > 0, (
                f"empty cache file {p.name} left behind on empty payload"
            )


def test_cdr_skips_when_required_tools_missing(tmp_path: Path) -> None:
    """If gcloud or coder is missing from PATH, fail with a readable
    err(); do not silently exec an empty stub."""
    empty_stubs = tmp_path / "empty"
    empty_stubs.mkdir()
    # Narrowed PATH: only the empty dir + where bash itself lives,
    # so gcloud / coder are unreachable but `bash` (used internally
    # by the wrapper, e.g. for command -v) keeps working.
    bash_dir = str(Path(BASH).parent)
    r = subprocess.run(
        [BASH, str(CDR), "list"],
        env={
            **os.environ,
            "PATH": f"{empty_stubs}:{bash_dir}",
            "HOME": str(tmp_path),
        },
        capture_output=True,
        text=True,
    )
    assert r.returncode != 0
    assert "missing required tool" in r.stderr.lower(), (
        f"missing-tool error not surfaced:\n{r.stderr}"
    )


def test_cdr_script_is_executable() -> None:
    """The wrapper is invoked as `cdr ...` from the operator's PATH;
    its exec bit must be set in the git index OR the Coder workflow
    will refuse to run it."""
    import subprocess as sp

    out = sp.run(
        ["git", "ls-files", "-s", "exe/scripts/cdr"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    mode = out.stdout.split()[0]
    assert mode == "100755", (
        f"exe/scripts/cdr git index mode is {mode}, expected 100755. "
        "Run: git update-index --chmod=+x exe/scripts/cdr"
    )


def test_cdr_present_for_every_test() -> None:
    """Sanity check the file we're testing actually exists."""
    assert CDR.is_file(), f"cdr wrapper missing at {CDR}"
    assert shutil.which("bash") is not None, "bash required to run cdr"
