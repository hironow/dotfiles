"""Retired stack paths stay absent; the shared environment stays present."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# --- check 1: paths ----------------------------------------------------

# The old Coder control plane, retired by K2.
#
# `exe/README.md` and `exe/docs/` are named individually even though the
# `exe/` entry below already covers them. They are the four files K2 missed:
# pure Coder documentation, left describing a destroyed stack and linking to a
# `tofu/exe/` that K2 had already deleted. They slipped through because the
# only asserted set was this one and nobody had put them in it. Naming them
# means a future edit cannot quietly drop the coverage along with the prefix.
OLD_CODER_PATHS = (
    "exe/README.md",
    "exe/docs/",
    "exe/coder/",
    "exe/cloudflared/",
    "exe/tailscale/",
    "tofu/exe/",
    "tests/exe/",
    "tests/docker/ExeStartup.Dockerfile",
    "tests/test_actor_type_injection.py",
    "tests/unit/test_cdr_wrapper.py",
    "tests/unit/test_vm_bootstrap.py",
    "tests/unit/test_publish_workflow.py",
    "tests/unit/test_exe_stack_mode.py",
    ".github/workflows/publish-devcontainer.yaml",
    "exe/scripts/cdr",
    "exe/scripts/cdr-exec",
    "exe/scripts/cdr-header",
    "exe/scripts/cdr-job",
    "exe/scripts/cdr-project",
    "exe/scripts/bootstrap.sh",
    "exe/scripts/smoke.sh",
    "exe/scripts/teardown.sh",
    "exe/scripts/project-up.sh",
    "exe/scripts/project-down.sh",
    "exe/scripts/fetch-projects-env.sh",
    "exe/scripts/test-fetch-projects-env.sh",
)

# The new exe stack on google/ax, moved out at the cutover. `exe/` is listed
# whole: nothing under it stayed, so a prefix is both shorter and safer than an
# enumeration that a later addition could sidestep.
NEW_EXE_PATHS = (
    "exe/",
    "tofu/exe-platform/",
    "tofu/exe-cluster/",
    "tools/exe-reaper/",
    "tests/e2e/",
    # The one file, not the directory: `docs/plan/` also holds the
    # cost-guardrails rollout plan (#439), which is neither stack's residue.
    "docs/plan/exe-google-ax.md",
    "docker/exe-task.Dockerfile",
    "scripts/check_exe_pins.py",
    "scripts/exe_platform_bootstrap.sh",
    ".semgrep/rules/e2e/",
    "submodules/",
)

RETIRED_PATHS = OLD_CODER_PATHS + NEW_EXE_PATHS


def _tracked() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return out.stdout.splitlines()


def test_no_file_of_either_retired_stack_is_tracked() -> None:
    """The one end-state check: neither stack has a tracked file left."""
    tracked = _tracked()
    left = sorted(
        path
        for path in tracked
        for retired in RETIRED_PATHS
        if path == retired or path.startswith(retired)
    )
    assert left == [], f"a retired stack is still tracked: {left}"


def test_the_retired_path_list_is_well_formed() -> None:
    """Cheap guards on the list itself, so a typo cannot disarm the check above.

    A path with a leading slash or stray whitespace would match nothing that
    `git ls-files` prints, and the absence check would pass for a reason that
    has nothing to do with the repository.
    """
    for path in RETIRED_PATHS:
        assert not path.startswith("/"), f"{path!r} is absolute, not a repo path"
        assert path.strip() == path, f"{path!r} has stray whitespace"
    assert len(set(RETIRED_PATHS)) == len(RETIRED_PATHS), "duplicate retired path"


def test_what_survives_is_still_here() -> None:
    """The counterweight. Every check above removes; this one states what the
    retirement must NOT have taken with it, because "scrub every mention" would
    have deleted the record of why any of it happened."""
    for kept in (
        "docs/adr",
        "tofu/tailnet",
        # Kept independently of any one model: the formal-methods policy applies
        # to every scaffolded repo and now also to the local runner-GC model.
        # Retiring the exe models must not retire that shared guidance.
        "ROOT_AGENTS_docs_agents_formal-methods.md",
        # The docstring above has always named both generic spokes as kept, but
        # only formal-methods was asserted. This one arrived on main with #439,
        # after this branch forked, which is why it is added here at the merge
        # rather than in the retirement commits.
        "ROOT_AGENTS_docs_agents_gcp-cost-guardrails.md",
    ):
        assert (ROOT / kept).exists(), f"{kept} is not residue and must stay"
