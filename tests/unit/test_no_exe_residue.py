"""Neither the old Coder stack nor (later) the new exe stack is left in dotfiles.

The end state this pins: dotfiles keeps the generic agent base environment and
`tofu/tailnet`, and the exe mechanism lives elsewhere. Two retirements reach that
state at different times -- the old Coder stack now, the new exe stack after its
parity proof -- so the paths are listed in two sets and only the first is
asserted yet. The second is here to be switched on, not to be rediscovered.

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
- `docs/plan/` -- the plan that drove the migration describes it in the past
  tense; a record of what was done is not residue.
- `tofu/tailnet/` -- created by this very retirement, and the ACL outlives both
  stacks.
- the generic spokes (formal methods, cost guardrails) and the test fixtures
  that carry synthetic paths as STRINGS.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# --- check 1: paths ----------------------------------------------------

# The old Coder control plane. Every one of these is gone as of K2.
OLD_CODER_PATHS = (
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

# The new exe stack on google/ax. NOT asserted yet: it is still operated from
# here until its parity proof in the infra repo. When that lands, move this
# tuple into the assertion below and the end state is complete.
NEW_EXE_PATHS_NOT_YET_REMOVED = (
    "tofu/exe-platform/",
    "tofu/exe-cluster/",
    "tools/exe-reaper/",
    "exe/spec/",
    "exe/versions.json",
    "tests/e2e/exe/",
    "docs/plan/exe-google-ax.md",
)

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
)

# --- check 3: operational files, named one by one ----------------------

RETIRED_IN_FILES = {
    ".pre-commit-config.yaml": ("coder", "tofu/exe"),
    "pyproject.toml": ('"exe:',),
    ".github/workflows/iac-test.yaml": ("Coder template", "tofu/exe/"),
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


def test_no_file_of_the_old_coder_stack_is_tracked() -> None:
    tracked = _tracked()
    left = sorted(
        path
        for path in tracked
        for retired in OLD_CODER_PATHS
        if path == retired or path.startswith(retired)
    )
    assert left == [], f"the old Coder stack is still tracked: {left}"


def test_the_new_exe_paths_are_listed_for_the_later_half() -> None:
    """Not an absence check, and deliberately not an existence one either.

    The new exe stack is still operated from here, so asserting its paths are
    gone would fail today; asserting they are PRESENT would fail the moment the
    mover removes them, which is the reversed assert this whole test exists to
    avoid. What is checkable now is that the list is well formed and does not
    overlap the half already retired, so switching it on later is one line.
    """
    assert set(NEW_EXE_PATHS_NOT_YET_REMOVED).isdisjoint(OLD_CODER_PATHS)
    for path in NEW_EXE_PATHS_NOT_YET_REMOVED:
        assert not path.startswith("/"), f"{path!r} is absolute, not a repo path"
        assert path.strip() == path, f"{path!r} has stray whitespace"


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
        "docs/plan",
        "tofu/tailnet",
        "ROOT_AGENTS_docs_agents_formal-methods.md",
        # The docstring above has always named both generic spokes as kept, but
        # only formal-methods was asserted. This one arrived on main with #439,
        # after this branch forked, which is why it is added here at the merge
        # rather than in the retirement commits.
        "ROOT_AGENTS_docs_agents_gcp-cost-guardrails.md",
    ):
        assert (ROOT / kept).exists(), f"{kept} is not residue and must stay"
