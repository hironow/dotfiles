"""Neither the old Coder stack nor the new exe stack is left in dotfiles.

The end state this pins: dotfiles keeps the generic agent base environment and
`tofu/tailnet`, and the exe mechanism lives elsewhere. Both retirements have
happened, so there is one set of paths and it is asserted -- no "not yet"
half, which is what let four files slip through the first time (see below).

Three checks, and the shape of each is deliberate (the mover's plan, §F-5):

1. **Paths, not strings.** `git ls-files` must not list the retired stacks'
   files. Looking at paths rather than grepping for "coder" means a sentence in
   a document that mentions the stack does not fail the gate, and means this
   test does not match itself.
2. **Recipe and workflow names.** A deleted directory with a `just` recipe still
   pointing at it is a worse state than either, because the failure surfaces to
   whoever runs the recipe rather than to CI.
3. **Operational files, explicitly listed.** Scanning everything would hit the
   fixtures and the generic spokes; the list says exactly which files are read
   and why, so the test cannot grow a grudge against a document.

What deliberately SURVIVES, because the obvious "scrub every mention" instinct
would delete it:

- `docs/adr/` -- 0011, 0012 and 0034 are accepted and therefore immutable. The
  history of a decision outlives the thing it decided.
- `tofu/tailnet/` -- created by this very retirement, and the ACL outlives both
  stacks.
- the generic spokes (formal methods, cost guardrails) and the test fixtures
  that carry synthetic paths as STRINGS.

`docs/plan/` is in NEITHER list. The migration plan moved with the stack it
planned, so `docs/plan/exe-google-ax.md` is named as retired -- but the
directory itself is not, because #439 put an unrelated live plan in it. Listing
the directory would make this test delete-by-assertion for a document that has
nothing to do with either stack; listing it as a survivor would assert something
this retirement does not require.
"""

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

# --- check 2: recipe and workflow names --------------------------------

# Recipes the old Coder stack owned. `tofu/tailnet`'s recipes are NOT here: that
# stack stays, and banning `tailnet-*` would ban the thing this retirement built.
RETIRED_RECIPES = (
    "exe-bootstrap",
    "exe-init",
    "exe-plan",
    "exe-apply",
    "exe-down",
    "exe-validate",
    "exe-output",
    "exe-smoke",
    "exe-teardown",
    "exe-cdr-install",
    "_exe-encryption",
    "_exe_tailscale_targets",
    # The new exe stack's recipes, plus the two gates that only ever had exe
    # inputs: spec-check (exe/spec + the exe-reaper simulation) and the
    # exe-specific name the tofu suite ran under.
    "exe-platform",
    "exe-cluster",
    "exe-reaper",
    "exe-ctx",
    "exe-sleep",
    "exe-status",
    "exe-keep",
    "exe-ax-job",
    "exe-ax-exec",
    "exe-e2e",
    "exe-snapshot-gc",
    "exe-l2-run",
    "exe-substrate-teardown",
    "exe-worker-images",
    "exe-spike-task-image",
    "spec-check",
    "test-iac-exe",
)

# --- check 3: operational files, named one by one ----------------------

RETIRED_IN_FILES = {
    ".pre-commit-config.yaml": ("coder", "tofu/exe"),
    "pyproject.toml": ('"exe:',),
    ".github/workflows/iac-test.yaml": (
        "Coder template",
        "tofu/exe/",
        "exe-platform",
        "exe-cluster",
    ),
    # The two tool pins that existed only for the exe stack. quint and java are
    # NOT listed: they are base tooling for a non-negotiable that other repos on
    # this machine rely on, and they stay even though dotfiles has no model.
    "config/mise/config.toml": ("google/ax", "ko-build/ko"),
    ".github/dependabot.yaml": ("exe-reaper",),
    ".gitignore": ("exe-reaper",),
}


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


def test_no_recipe_of_the_old_coder_stack_survives() -> None:
    """A recipe pointing at a deleted directory fails in the operator's hands
    instead of in CI, which is the worse of the two."""
    text = (ROOT / "justfile").read_text(encoding="utf-8")
    left = sorted(name for name in RETIRED_RECIPES if name in text)
    assert left == [], f"the justfile still carries retired recipes: {left}"


def test_no_workflow_runs_the_old_coder_stack() -> None:
    workflows = ROOT / ".github" / "workflows"
    offenders = sorted(
        f"{path.name}: {needle}"
        for path in workflows.glob("*.yaml")
        for needle in ("tofu/exe/", "Coder template", "publish-devcontainer")
        if needle in path.read_text(encoding="utf-8")
    )
    assert offenders == [], f"a workflow still reaches the old stack: {offenders}"


def test_the_named_operational_files_no_longer_mention_it() -> None:
    """One file at a time, with the needle spelled out, so this check can never
    grow into a repo-wide grep that hits a fixture or a spoke."""
    offenders = []
    for name, needles in RETIRED_IN_FILES.items():
        path = ROOT / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        offenders += [f"{name}: {needle}" for needle in needles if needle in text]
    assert offenders == [], f"operational files still name the old stack: {offenders}"


def test_what_survives_is_still_here() -> None:
    """The counterweight. Every check above removes; this one states what the
    retirement must NOT have taken with it, because "scrub every mention" would
    have deleted the record of why any of it happened."""
    for kept in (
        "docs/adr",
        "tofu/tailnet",
        # Kept although dotfiles no longer has a Quint model of its own: the
        # non-negotiable it states applies to every repo this machine scaffolds,
        # and deleting the guidance with the last local model is how a rule
        # quietly stops being one.
        "ROOT_AGENTS_docs_agents_formal-methods.md",
        # The docstring above has always named both generic spokes as kept, but
        # only formal-methods was asserted. This one arrived on main with #439,
        # after this branch forked, which is why it is added here at the merge
        # rather than in the retirement commits.
        "ROOT_AGENTS_docs_agents_gcp-cost-guardrails.md",
    ):
        assert (ROOT / kept).exists(), f"{kept} is not residue and must stay"
