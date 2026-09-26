"""`scripts/exe_platform_bootstrap.sh` — the out-of-band state-bucket bootstrap.

Why this exists
---------------
`tofu/exe-platform` keeps its OpenTofu state in a GCS bucket, so that bucket has
to exist *before* `tofu init` and therefore cannot be a resource of the stack it
backs (chicken-and-egg). It is the one piece of infrastructure in the project
created outside tofu — and so the one piece with no `tofu plan` to review. The
review has to happen here instead, which is what these tests pin:

- `--dry-run` prints every `gcloud` command and runs **none**, so the mutation
  can be read before it happens. A fake `gcloud` on `PATH` (which records every
  invocation) proves the "runs none" half. No test here ever touches real
  credentials or a real project.
- the settings that make the bucket safe (uniform bucket-level access, public
  access prevention enforced, versioning, a 10-noncurrent-version lifecycle,
  soft delete off, the pinned location) are asserted against the commands the
  script would actually issue — and the lifecycle document is asserted as
  parsed **JSON**, not as a regex over shell source.
- the repo is PUBLIC: the project id may only ever arrive as an argument or an
  env var, never as a default baked into the script. Every id below is
  synthetic.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from _bash_hook import run_bash

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "exe_platform_bootstrap.sh"

# Synthetic throughout. A realistic project id must never enter this repo, and
# `zz-` prefixed names are not registrable, so a copy/paste accident is inert.
PROJECT = "zz-synthetic-project"
DERIVED_BUCKET = f"{PROJECT}-exe-tofu-state"
OVERRIDE_BUCKET = "zz-synthetic-override-state"

LOCATION_FLAG = "--location=asia-northeast1"


def _fake_gcloud(tmp_path: Path) -> tuple[Path, Path]:
    """A `gcloud` on `PATH` that records each invocation and does nothing else.

    Returns ``(bindir, marker)``. The marker file is written on the *first*
    call, so `not marker.exists()` is the assertion that dry-run stayed inert.
    `as_posix()` because MSYS bash cannot open a backslash path.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    marker = tmp_path / "gcloud-was-called"
    gcloud = bindir / "gcloud"
    gcloud.write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{marker.as_posix()}"\nexit 0\n',
        encoding="utf-8",
    )
    gcloud.chmod(0o755)
    return bindir, marker


def _run(
    *args: str,
    bindir: Path | None = None,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    # The ambient shell may well export this (the human runs the real thing);
    # the "no project" case must not silently pick it up.
    env.pop("EXE_PLATFORM_PROJECT", None)
    if bindir is not None:
        env["PATH"] = f"{bindir}{os.pathsep}{env.get('PATH', '')}"
    if env_extra:
        env.update(env_extra)
    return run_bash(
        SCRIPT,
        *args,
        cwd=SCRIPT.parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _dry_run_output(*args: str, **kwargs: Any) -> str:
    result = _run("--dry-run", *args, **kwargs)
    assert result.returncode == 0, (
        f"--dry-run must succeed; rc={result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return result.stdout + result.stderr


def test_no_project_exits_one_with_usage() -> None:
    """No project anywhere → refuse loudly. Guessing a project id is the one
    unrecoverable mistake here: it would create a bucket in, or mutate, whatever
    project happened to be `gcloud config`'d."""
    result = _run()
    assert result.returncode == 1, (
        f"missing project must exit 1, got {result.returncode}\n{result.stdout}"
    )
    err = result.stderr
    assert "usage" in err.lower(), f"usage must go to stderr, got:\n{err}"
    assert "--project" in err
    assert "EXE_PLATFORM_PROJECT" in err, (
        "the env-var route must be discoverable from the error"
    )
    assert result.stdout.strip() == "", (
        "nothing may be printed on stdout for a refused run (it is what a "
        "caller would pipe)"
    )


def test_dry_run_prints_the_whole_command_set() -> None:
    out = _dry_run_output("--project", PROJECT)
    assert DERIVED_BUCKET in out, (
        f"bucket must be derived as <project>-exe-tofu-state; got:\n{out}"
    )
    for token in (
        "gcloud storage buckets",
        LOCATION_FLAG,
        "--uniform-bucket-level-access",
        "--public-access-prevention",
        "--versioning",
        "--lifecycle-file",
        "--clear-soft-delete-policy",
        "STANDARD",
    ):
        assert token in out, f"dry-run output is missing {token!r}; got:\n{out}"
    assert "enforced" in out, (
        "public access prevention must be stated as *enforced* (the inherited "
        "default is what we are guarding against)"
    )


def test_env_var_supplies_the_project() -> None:
    out = _dry_run_output(env_extra={"EXE_PLATFORM_PROJECT": PROJECT})
    assert DERIVED_BUCKET in out, f"$EXE_PLATFORM_PROJECT was not honoured:\n{out}"


def test_explicit_bucket_overrides_the_derived_name() -> None:
    out = _dry_run_output("--project", PROJECT, "--bucket", OVERRIDE_BUCKET)
    assert OVERRIDE_BUCKET in out
    assert DERIVED_BUCKET not in out, (
        f"--bucket must replace the derived name, not add to it; got:\n{out}"
    )


def _lifecycle_document() -> dict[str, Any]:
    result = _run("--print-lifecycle")
    assert result.returncode == 0, f"--print-lifecycle failed:\n{result.stderr}"
    parsed: Any = json.loads(result.stdout)
    assert isinstance(parsed, dict)
    return parsed


def test_lifecycle_document_keeps_at_most_ten_noncurrent_versions() -> None:
    """Asserted as parsed JSON: this document is handed to
    `--lifecycle-file=`, so a shape error is a silently unbounded bucket."""
    doc = _lifecycle_document()
    rules: Any = doc["rule"]
    assert isinstance(rules, list)
    assert len(rules) == 1, (
        f"exactly one rule (a second rule is an unreviewed deletion path): {rules}"
    )
    rule: Any = rules[0]
    assert rule["action"]["type"] == "Delete"
    condition: Any = rule["condition"]
    assert condition["numNewerVersions"] == 10
    assert condition["isLive"] is False, (
        "isLive must be the JSON literal false — a string 'false' is truthy to "
        "the API and would prune live objects, i.e. the current state"
    )


def test_dry_run_shows_the_lifecycle_document_it_would_apply() -> None:
    """The dry-run is only a review if it shows the *payload* too: the
    `--lifecycle-file=` argument is a temp path whose content is the whole
    point. Cross-checks that both come from one generator."""
    text = _run("--print-lifecycle").stdout.strip()
    assert text, "--print-lifecycle printed nothing"
    out = _dry_run_output("--project", PROJECT)
    assert text in out, (
        "dry-run must print the same lifecycle document verbatim so the "
        f"reviewer sees what --lifecycle-file would contain.\nwanted:\n{text}\n"
        f"got:\n{out}"
    )


def test_dry_run_runs_no_gcloud(tmp_path: Path) -> None:
    bindir, marker = _fake_gcloud(tmp_path)
    out = _dry_run_output("--project", PROJECT, bindir=bindir)
    assert not marker.exists(), (
        "--dry-run invoked gcloud; it must only print. Recorded calls:\n"
        f"{marker.read_text(encoding='utf-8')}\nscript output:\n{out}"
    )


def test_no_project_identifier_is_baked_into_the_script() -> None:
    """PUBLIC repo: the project must arrive from the caller. A `${VAR:-default}`
    fallback is how an identifier leaks into a tracked file."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert not re.search(r"EXE_PLATFORM_PROJECT:-[^}]", text), (
        "EXE_PLATFORM_PROJECT must expand to empty when unset "
        "(`${EXE_PLATFORM_PROJECT:-}`), never to a baked-in default"
    )
    assert "gcloud config set project" not in text, (
        "the script must not mutate the caller's active gcloud project"
    )


def test_documents_why_this_bucket_is_an_iac_exception() -> None:
    """`no manual mutation of IaC-managed infra` is a standing rule; this script
    is a deliberate carve-out, so the reason has to be readable at the top of it
    rather than inferred from a plan doc."""
    text = SCRIPT.read_text(encoding="utf-8")
    head = text[: text.index("set -euo pipefail")]
    lowered = head.lower()
    for needle in ("backend", "tofu"):
        assert needle in lowered, (
            f"the header comment must explain the exception (missing {needle!r})"
        )
    assert "chicken" in lowered or "cannot create its own" in lowered, (
        "the header must name the chicken-and-egg reason explicitly"
    )


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not on PATH")
def test_shellcheck_clean() -> None:
    """`just check` runs shellcheck over every tracked *.sh; keep the gate green
    here rather than discovering it at commit time."""
    result = subprocess.run(  # noqa: S603 - fixed argv, test-only
        [shutil.which("shellcheck") or "shellcheck", str(SCRIPT)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, (
        f"shellcheck findings:\n{result.stdout}{result.stderr}"
    )
