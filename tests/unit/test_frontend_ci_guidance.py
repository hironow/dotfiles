"""The agent instructions keep frontend CI under two minutes without losing a check.

ADR-0078: the owner's five rules are `bun check` in place of `tsc`, oxlint with
every rule that can be on, shards filled by recorded test time, pull requests
that run only the tests the diff can reach, and lint, typecheck, build, and
tests in parallel. Each one has a way to pass while checking nothing (a `check`
script that shadows the type checker, a fixture no import reaches, a skipped
required job), so the spoke states the guard next to the rule. Each assertion is
scoped to the paragraph or bullet that carries the rule: moving or dropping the
rule fails the test, a stray mention elsewhere does not pass it.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HUB = ROOT / "ROOT_AGENTS.md"
SPOKE = ROOT / "ROOT_AGENTS_docs_agents_frontend-ci.md"
TESTING = ROOT / "ROOT_AGENTS_docs_agents_testing.md"

OXLINT_CATEGORIES = (
    "correctness",
    "suspicious",
    "pedantic",
    "perf",
    "style",
    "restriction",
    "nursery",
)


def _blocks(path: Path) -> list[str]:
    """Paragraphs and list items, each on one line."""
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*\n|\n(?=\s*(?:[-*]|\d+\.)\s)", text)
    return [" ".join(block.split()) for block in blocks if block.strip()]


def _block_with(path: Path, needle: str) -> str:
    matching = [block for block in _blocks(path) if needle in block]
    assert len(matching) == 1, f"expected one block in {path.name} with {needle!r}"
    return matching[0]


def test_the_hub_lists_the_frontend_ci_guide() -> None:
    rows = [
        line
        for line in HUB.read_text(encoding="utf-8").splitlines()
        if "docs/agents/frontend-ci.md" in line
    ]
    assert any(line.startswith("|") and "CI" in line for line in rows), rows


def test_the_testing_guide_points_to_how_ci_runs_typescript_tests() -> None:
    assert "bun:test" in _block_with(TESTING, "docs/agents/frontend-ci.md")


def test_the_target_is_a_minute_at_the_median_and_is_measured() -> None:
    target = _block_with(SPOKE, "under one minute at the median")
    assert "pull request" in target
    assert "p95" in target
    assert "Measure" in target
    assert "docs/agents/ci-speed.md" in _block_with(SPOKE, "Read this when")


def test_no_rule_may_drop_a_check_to_save_time() -> None:
    kept = _block_with(SPOKE, "the same required checks")
    assert "before and after" in kept


def test_bun_check_replaces_the_type_check_and_cannot_be_shadowed() -> None:
    table = SPOKE.read_text(encoding="utf-8")
    assert re.search(r"\|\s*`tsc --noEmit`\s*\|\s*`bun check --no-script`\s*\|", table)
    assert re.search(r"\|\s*`tsc -b`\s*\|\s*`bun check --no-script -b`\s*\|", table)
    shadowed = _block_with(SPOKE, "`check` script")
    assert "--no-script" in shadowed
    assert "exits 0" in shadowed


def test_tsc_stays_where_it_writes_files() -> None:
    emits = _block_with(SPOKE, "never writes files")
    assert "`.d.ts`" in emits
    assert "`tsc -b`" in emits
    stricter = _block_with(SPOKE, "behaves like TypeScript 7")
    assert "do not go back to `tsc`" in stricter


def test_lint_and_format_cannot_be_shadowed_by_a_script() -> None:
    shadowed = _block_with(SPOKE, "has a script with the same")
    assert "`bun lint`" in shadowed and "`bun fmt`" in shadowed
    assert "exits 0" in shadowed
    assert "negative control" in shadowed
    lint = _block_with(SPOKE, "Lint with `bun lint --no-script`")
    assert ".oxlintrc.json" in lint
    assert "has no `bun lint` yet" in lint
    assert "canary" in lint
    assert "recommended" in lint
    assert "decides, each time" in lint
    fmt = _block_with(SPOKE, "Check formatting with")
    assert "`bun fmt --no-script --check`" in fmt
    assert "formatting commit" in fmt


def test_oxlint_turns_on_every_category_and_opts_out_by_rule() -> None:
    categories = _block_with(SPOKE, "all seven categories")
    for category in OXLINT_CATEGORIES:
        assert f"`{category}`" in categories, category
    assert "replaces the default set" in _block_with(SPOKE, "`plugins`")
    type_aware = _block_with(SPOKE, "typeAware")
    assert "oxlint-tsgolint" in type_aware
    opt_out = _block_with(SPOKE, "turn off that one rule by name")
    assert "reason" in opt_out
    assert "Never turn off a category" in opt_out


def test_oxlint_is_pinned_and_never_fetched_at_run_time() -> None:
    pinned = _block_with(SPOKE, "bunx --no-install oxlint")
    assert "docs/agents/dependency-policy.md" in pinned
    assert "exact" in pinned


def test_shards_are_cut_by_recorded_time_from_one_snapshot() -> None:
    assert "--parallel" in _block_with(SPOKE, "Split the suite across CI machines")
    same = _block_with(SPOKE, "the same recorded files")
    assert "--timings" in same
    own = _block_with(SPOKE, "Each shard passes `--update-timings`")
    assert "its own file" in own
    assert "still running" in own
    assert "writes to the first `--timings` path" in own
    command = SPOKE.read_text(encoding="utf-8").split("--update-timings \\\n", 1)[1]
    first, recorded = command.splitlines()[:2]
    assert "--timings=timings/next/<i>.json" in first
    assert "--timings=" in recorded and "next/" not in recorded
    publish = _block_with(SPOKE, "after every shard passed")
    assert "cache" in publish
    assert "default branch and the merge queue" in publish
    accounting = _block_with(SPOKE, "Prove that the shards together ran every")
    assert "missing file" in accounting and "duplicate" in accounting
    assert "In a full run" in accounting and "In a selected run" in accounting
    order = _block_with(SPOKE, "bun test --parallel --isolate --randomize")
    assert "--seed" in order
    assert "Buy cores before shards" in _block_with(SPOKE, "Buy cores before shards")


def test_a_pull_request_runs_the_reachable_tests_only_when_imports_cover_the_diff() -> (
    None
):
    default = _block_with(SPOKE, "The whole suite is the default")
    assert "--changed=$(git merge-base origin/<base branch> HEAD)" in default
    assert "only when imports cover the diff" in default
    assert "every changed file" in default
    assert "static `import`" in default
    imports = _block_with(SPOKE, "follows `import` statements only")
    for unreached in ("fixture", "snapshot", "`package.json`", "lockfile", "workflow"):
        assert unreached in imports, unreached
    assert "run the whole suite" in imports
    decided = _block_with(SPOKE, "root `just` recipe decides")
    assert "Test that recipe" in decided
    assert "missing ref fails" in _block_with(SPOKE, "Fetch enough history")
    before_main = _block_with(SPOKE, "The full suite runs before anything reaches")
    assert "merge queue" in before_main
    assert "docs/agents/ci-speed.md" in before_main


def test_the_merge_base_is_passed_never_the_tip_of_the_target() -> None:
    rule = _block_with(SPOKE, "Pass the merge base")
    assert "tip of the target branch" in rule
    assert "behind its target" in rule


def test_the_bun_flags_cover_bun_test_suites_only() -> None:
    scope = _block_with(SPOKE, "Rules 3 and 4 are for `bun:test` suites")
    assert "End-to-end suites" in scope
    assert "docs/agents/testing.md" in scope
    assert "`vitest` imports" in scope


def test_the_jobs_run_side_by_side() -> None:
    parallel = _block_with(SPOKE, "separate jobs")
    for job in ("lint", "typecheck", "build", "test shard"):
        assert job in parallel, job
    assert "`needs`" in parallel
    assert "root `just` recipe" in _block_with(SPOKE, "the same command")


def test_the_required_check_cannot_pass_by_being_skipped() -> None:
    gate = _block_with(SPOKE, "the required check for this workflow")
    assert "every required job of this workflow" in gate
    assert "`if: always()`" in gate
    assert "`success`" in gate
    assert "draft" in gate
    skipped = _block_with(SPOKE, "counts a skipped required check as passed")
    assert "`needs`" in skipped
    assert "stay required" in _block_with(SPOKE, "covers its own workflow only")
    assert "every job on it" in _block_with(SPOKE, "workflow lint")
