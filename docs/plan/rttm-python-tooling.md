# Align RTTM Python checks with existing conventions

**Date:** 2026-10-22
**Status:** done (→ development steps in [RTTM README](../../tools/rttm/README.md)). Merged in [#489](https://github.com/hironow/dotfiles/pull/489) (main `7a487650`). Execution on physical Windows unverified
**Branch:** `chore/rttm-python-tooling`
**Related:** ADR 0044 / `ROOT_AGENTS_docs_agents_python-tooling.md`
**Blocking decisions:** none. The owner approved aligning lint group, exact pins, and ty in session `01a159fd`, and chose to resume in session `01a15f0e`.
**Graduates to:** `tools/rttm/README.md` and existing tooling docs.

## Current state and scope

`tools/rttm` is existing Python with Ruff specified as a ranged regular dependency, ty missing, and no 7-day quarantine exemptions.
root/emulator pin Ruff 0.17.1 and ty 0.0.90 exactly and exempt both tools from quarantine.
Do not add features, refactor broadly, or bulk-update other dependencies.
Keep root's repo-side Ruff exception (`default + W605 + PTH`) unchanged rather than switching to canonical select.

## Implementation and verification

1. Pin RTTM's lint group, exact pins matching root, quarantine exemptions, and wiring into real checks via root `just` in root unit tests. Also extend `test_bump_tool.py` to support 4 declarations / 3 locks and confirm RED first.
2. Move RTTM's Ruff from regular dependencies to the lint group and add ty to that group, matching root's 0.17.1 / 0.0.90. Leave pytest placement and app dependencies unchanged. Add `exclude-newer-package = { ruff = false, ty = false }` while keeping the 7-day wait on other dependencies.
3. Generate the lock with `uv lock --project tools/rttm --upgrade-package ruff --upgrade-package ty` and diff before/after package structures. Revert and investigate any unintended updates to other packages; never hand-forge the lock.
4. Define RTTM-specific `[tool.ty.src] include` / `environment.extra-paths` / `terminal.error-on-warning` so inheriting parent settings scoped to scripts/tests does not leave zero target files. Wire RTTM fmt/lint/typecheck/check into root `justfile`, running frozen lint-group Ruff and lint-group ty (seeing regular deps) with RTTM directory as cwd. Include RTTM's existing pytest in check and run it from root `just check`. In RTTM behavioral tests, copy the same justfile and lock to an isolated project and confirm the exact typecheck task resolves valid dependency imports and rejects type errors inside RTTM. Create no sub-justfiles.
5. Extend `scripts/bump_tool.py` and existing tests to 4 declarations / 3 locks so future pin bumps do not miss RTTM, keeping the pre-read and no-write-on-error contract. Also ignore Ruff/ty in Dependabot's RTTM entry like root/emulator to avoid independent bot pin drift. Verify in unit tests that all synced projects ignore both tools.
6. Fix ty diagnostics in real code or with accurate annotations rather than blanket-ignoring unresolved imports or diagnostics. If missing type dependencies surface, check stdlib or existing packages first and document any addition needed. Preserve existing RTTM functionality with regression tests.
7. Update development steps in RTTM README and declaration counts in bump-related docs. Run unit tests, RTTM checks, `just check` / `just ci`, and independent diff review. Use full CI on the target head as the sandbox gate for justfile wiring changes without duplicating heavy local runs, per owner ruling.
8. Sign commits, open draft PR, mark ready, wait for all relevant CI checks on target head to pass, squash merge, and ff-only update main. Keep main as main at all times and protect uncommitted changes from others.

## Independent review

Codex plan review #1 returned NEEDS_FIX (`rttm-plan-review.txt` in session `01a15f0e`). Verified and adopted both findings:

- P1: changing cwd alone causes ty to pick parent root config and skip RTTM. Reproduced running parent ty 0.0.90 with RTTM cwd: it checked root's 164 files and exited 0. Added local config and type-error rejection test on exact task to step 4.
- P2: RTTM's Dependabot entry alone lacked Ruff/ty ignores. Confirmed by comparing root/emulator/RTTM entries in `.github/dependabot.yaml`. Added bot update suppression across all synced targets and unit invariant to step 5.

Independent Codex diff review returned APPROVE (`rttm-diff-review.txt` in session `01a15f0e`), verifying fixes for both findings, 4 declarations / 3 locks, and Windows path quoting. Because the review sandbox could not create a uv cache lock, the reviewer did not assert pytest passed.

## Implementation results

- Observed 10 failed / 7 passed on newly added unit tests first, then 17 passed after fixes. RTTM Ruff/ty and 7 tests passed, and in an isolated project the exact root task resolved dependency imports and rejected type errors in RTTM.
- root `just ci` EXIT 0: root unit 1760 passed / 33 skipped, Tofu 4 passed, Semgrep fixtures, etc. passed; RTTM also ran via root check.
- First ty run flagged an unneeded existing `type: ignore`, so removed only that comment. Also resolved a type error on an Optional regex match in a new unit test by asserting the match exists.
- Package records before/after lock changed only in RTTM metadata, Ruff 0.17.0→0.17.1, and adding ty 0.0.90; all other packages matched exactly. Lock revision 3→5 and quarantine exemptions for both tools were uv-generated. All archive URLs/hashes/sizes for Ruff/ty matched the adopted root lock.
- Physical Windows execution unverified. Use sandbox CI on the final head (including justfile wiring) as the merge gate without duplicating local Docker runs.
- Additional diff after final local gate and review consists only of these results and declaration-count comment fixes in existing docs.
