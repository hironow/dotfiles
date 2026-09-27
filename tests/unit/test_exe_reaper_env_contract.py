"""Hold the L2 job's env var names equal to the ones exe-reaper reads.

The enforcer is configured across a stack boundary: tofu/exe-platform/
l2_enforcer.tf sets env vars on the Cloud Run job, and tools/exe-reaper/main.go
reads them. Neither side can see the other, and each has its own tests that
pass on their own: the tofu tests pin the names the job SETS, the Go tests run
with whatever names the binary READS. A drifted name therefore passes every
gate and fails only in production, where `exe-reaper enforce` exits "missing
required environment" on every tick. The money stop that is supposed to work
when everything else is broken is then broken itself, and the only signal is
a failed Cloud Run execution nobody is watching.

This is the one check that reads both files, so it is Python (cross-stack
rules only; each stack's own invariants live in its own test runner). It reads
the Go const block and the job's env blocks as TEXT: the names are string
literals in both, and a regex over them is both sufficient and honest about
what it verifies.

Stdlib + pytest only.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
REAPER_MAIN: Final = _REPO_ROOT / "tools" / "exe-reaper" / "main.go"
L2_ENFORCER_TF: Final = _REPO_ROOT / "tofu" / "exe-platform" / "l2_enforcer.tf"

#: `envBucket = "EXE_OPS_BUCKET"` in main.go's const block.
_GO_ENV_CONST: Final = re.compile(r'(?m)^\s*env[A-Z]\w*\s*=\s*"(EXE_[A-Z0-9_]+)"')

#: `name = "EXE_ZONE"` inside an `env { ... }` block of the job.
_TF_ENV_BLOCK: Final = re.compile(r'env\s*\{\s*name\s*=\s*"(EXE_[A-Z0-9_]+)"')


def go_env_names(text: str) -> set[str]:
    """Every EXE_* name main.go declares as an env const."""
    return set(_GO_ENV_CONST.findall(text))


def tf_env_names(text: str) -> set[str]:
    """Every EXE_* name set by an env block in the enforcer's .tf file."""
    return set(_TF_ENV_BLOCK.findall(text))


def test_the_scanners_see_names_on_both_sides() -> None:
    """A regex that silently matched nothing would make the equality below
    vacuous, so each side must yield names."""
    assert go_env_names(REAPER_MAIN.read_text(encoding="utf-8")), (
        f"no env const found in {REAPER_MAIN.relative_to(_REPO_ROOT)}"
    )
    assert tf_env_names(L2_ENFORCER_TF.read_text(encoding="utf-8")), (
        f"no env block found in {L2_ENFORCER_TF.relative_to(_REPO_ROOT)}"
    )


def test_the_job_sets_exactly_the_env_the_reaper_reads() -> None:
    go = go_env_names(REAPER_MAIN.read_text(encoding="utf-8"))
    tf = tf_env_names(L2_ENFORCER_TF.read_text(encoding="utf-8"))
    assert go == tf, (
        "the L2 job and exe-reaper disagree about env var names.\n"
        f"  read by the reaper, not set on the job: {sorted(go - tf)}\n"
        f"  set on the job, not read by the reaper: {sorted(tf - go)}\n"
        "A name the job does not set makes `exe-reaper enforce` exit 'missing "
        "required environment' on every tick; rename one side to match."
    )


def test_the_scanners_parse_both_shapes() -> None:
    """The two regexes, on synthetic text, both ways."""
    go = """
const (
	leaseObject = "lease.json"
	envBucket   = "EXE_OPS_BUCKET"
	envZone     = "EXE_ZONE"
)
"""
    tf = """
      env {
        name  = "EXE_OPS_BUCKET"
        value = google_storage_bucket.ops.name
      }
      # env { name = "NOT_EXE" }
      env {
        name  = "EXE_ZONE"
        value = google_container_cluster.exe.location
      }
"""
    assert go_env_names(go) == {"EXE_OPS_BUCKET", "EXE_ZONE"}
    assert tf_env_names(tf) == {"EXE_OPS_BUCKET", "EXE_ZONE"}
