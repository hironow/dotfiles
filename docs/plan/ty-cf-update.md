# Align declarations for ty 0.0.90 and cf beta.20

**Date:** 2026-10-21
**Status:** done. Merged in [#487](https://github.com/hironow/dotfiles/pull/487) (main `9508e5c3`). Only bumped versions; no explanation to migrate (cf pinning policy is in `config/mise/config.toml` comments)
**Scope:** dotfiles only. Run in a separate worktree and PR after Go-port PR #486.

## Owner request and current state

The owner included the uncommitted changes on main (ty 0.0.90 and cf 1.0.0-beta.20) in scope and instructed to read the changelogs.
Always keep main as main.
The current diff on main is just 2 lines in `config/mise/config.toml`, saved to `/tmp/dotfiles-live-ty-cf-2026-10-21.patch`.
In the repository, root/emulator declarations and locks for ty are still 0.0.89, and the image cf is still beta.18.
The existing Python generator's check also fails with EXIT 1 on the cf host/image mismatch.

## Official changelogs and impact

### ty 0.0.90

[Official release](https://github.com/astral-sh/ty/releases/tag/0.0.90) (published 2026-10-20).
Fetched and verified the body from the [release API](https://api.github.com/repos/astral-sh/ty/releases/tags/0.0.90).

- Fixes a crash on negating recursive aliases and a stack overflow in recursive descriptor setters.
- Fixes hashability restoration, constructor type-variable defaults, bound receivers, and read types for dynamic attributes.
- Checks `runtime_checkable` on non-protocols and `TypeAliasType` keywords.
- Reports deletion, pop, and setdefault on TypedDict read-only keys.
- Adds LSP return-type inlay hints and avoids inserting hints for stub-only types.
- Supports uv nested module ownership metadata and stabilizes macOS signing identifiers.

Verify no new diagnostics appear in this repo via gates including root/emulator `ty check`.
Existing `exclude-newer-package = { ruff = false, ty = false }` exempts ty from the 7-day wait.
Do not change quarantine settings.

### cf 1.0.0-beta.18 → beta.20

Checked beta.19 and beta.20 in the [official CHANGELOG](https://github.com/cloudflare/cf/blob/main/packages/cli/CHANGELOG.md).
Fetched blob `fcdcde11d4f068ec1c8e4d3f3bbc1165ed4f1222`.
Also checked version, publish timestamps, engines, and repository in [official npm metadata](https://registry.npmjs.org/cf).

- beta.19: adds flags persisting OAuth keyring storage settings; fixes flag generation for composed scalars, nested object arrays, and bodyless raw responses.
- beta.20: moves notices, warnings, and success messages for handwritten auth/telemetry/migrate commands to stderr (breaking change). Affects external consumers parsing stdout.
- beta.20: narrows Node.js requirement to `^22.23.0 || ^24.22.0 || ^26.12.0` (breaking change). Both measured host and image pin are 24.22.0, satisfying it.
- beta.20: adds `--temporary-account`; docs state help, auth check, and dry run create no account. None of these account features are used here.
- Also updates dependencies from Workers SDK and generated command groups.
- npm `latest` was beta.20 at fetch time. The existing comment "latest is beta.10" is stale, though we keep the existing policy of pinning beta rather than switching to `latest`.

Searching scripts/tools/workflows/tests in this repo found no runtime code parsing cf command stdout, only the old generator's description.
External repos outside the checked scope are unverified.

## Changes

1. Squash merge #486 after all CI checks pass on its latest SHA. Keep main's 2 lines untouched and create a new worktree from updated `origin/main`.
2. Verify Go check exits 0 on the clean baseline of the new worktree. Apply the saved 2-line patch after `git apply --check`, and verify Go check exits 1 specifically diagnosing the cf beta.18/beta.20 mismatch (do not treat an arbitrary non-zero exit as RED). Then run `just bump-tool ty 0.0.90` to align the 3 declarations and 2 locks across host/root/emulator. Inspect the lock diff; if anything besides ty moved, trace the cause and isolate out-of-scope updates.
3. Update host cf pin and `config/mise/image-tools.toml` cf pin to beta.20, and regenerate heredocs with Go generator `just mise-versions-sync`. Never edit generated blocks by hand. Update host comments to remove the stale dist-tag note and record the pinned beta policy and source location.
4. Run drift checks in order: clean EXIT 0 → apply saved 2 lines for cf-mismatch EXIT 1 → update remaining declarations/locks and regenerate for EXIT 0. Use existing pin/bump/oracle/install-dependent tests. Update any test fixture assuming the old cf version to read from the new declaration without weakening the check.
5. Run `just ci` (including Go lint/test and root/emulator ty). Because generated values in install scripts change, also run `just test` (budget 90 minutes based on first image build + 126 tests).
6. Obtain independent Codex diff review, sign commits, open non-draft PR, wait for all CI to pass, then squash merge.
7. Pull into main after PR merge using this constrained sequence without temporarily reverting live ty/cf values or using stash/reset:
    - Fetch the merged commit SHA via API and verify it is on fetched `origin/main` with no divergence.
    - Verify main has no staged changes and its uncommitted diff matches the saved 2-line patch byte-for-byte; stop on any discrepancy.
    - Independently compare the merged config blob against the reviewed PR config blob via `tomllib` to confirm exact equality and no settings changed outside ty/cf, with comments matching only PR-approved edits.
    - Back up current main config, verify its hash, and write the merged config blob to that file alone (because ty/cf values already match, no version downgrade occurs). Re-check current diff right before writing and abort on mismatch.
    - Stage only that file with `git add -- config/mise/config.toml`, verify the index blob matches the merged blob with no other staged diff, and run `git merge --ff-only origin/main`. Verify HEAD, index, and working file match and the saved 2 lines are integrated.
    - Stop on any rejection without extra reset/restore, keeping backups intact.
8. Run main's Go drift check, ty pin/lock consistency, and version/help-only smoke tests for cf and Node. Install only approved versions via mise if needed; perform no auth, account creation, deploy, or publishing.
9. Update scoped handover (original file backup and scope already owner-approved).

## Out of scope and stop conditions

- Hold Ruff 0.17.1 adoption in rttm until 2026-10-22T15:22:33.667796 UTC. Do not weaken rules.
- Leave other repos, skills, existing ADR bodies, mise quarantine settings, and cf pinning policy unchanged.
- If new ty emits diagnostics on existing code, report them first; never suppress rules to pass.
- Do not test auth or network mutations with cf; limit smoke tests to version/help.
- If anything besides main's 2 lines changed, re-verify backup and scope.

## Plan review #1 verification

- Adopted the finding that ff-merging with uncommitted diffs on main fails. Parent reproduced in a temp Git repo and confirmed making only the working file match the target still exits 1. Making the index blob match too let `git merge --ff-only` finish EXIT 0 with working file unchanged and status clean. Thus, integration aligns only the 1 PR-approved file into the index, avoiding reverting live pins.
- Adopted the finding that dirty diffs do not carry into a new worktree. Because the generator reads host config in the same worktree, changed to a three-step sequence: clean baseline EXIT 0, cf-diagnostic EXIT 1 after applying patch, and EXIT 0 after all updates.

## Plan review #2

Codex `bdeee4ab5` re-verified both resolutions against actual files and returned APPROVE.
Parent ran clean check EXIT 0 → cf beta.18/beta.20 mismatch diagnostic EXIT 1 in the new worktree.

## Implementation and verification

- Updated 3 declarations and 2 locks with `just bump-tool ty 0.0.90`, and regenerated cf heredoc with Go sync. Post-sync check EXIT 0.
- Targeted tests `b5432698b` EXIT 0, 69 passed (10 bump, 33 oracle, 26 existing install-dependent).
- Parsed locks as TOML against old versions and confirmed all dependencies besides ty version, artifacts, and requirement specifiers stayed identical. Only emulator lock schema revision updated 3 → 5 via uv (root already 5); do not revert schema manually.
- Main's original 2 lines stayed untouched. Go port #486 merged as `b59476e`, and its worktree and branch were deleted.
- `just ci` (`b2e85038f`) EXIT 0, 1743 passed / 33 skipped. Root and emulator ty checks also passed, both running version 0.0.90.
- Artifact check (`b0b018f7e`) EXIT 0: verified hash/size of all 18 ty artifacts in both locks against PyPI and matched downloaded macOS ARM64 wheel SHA-256. Matched downloaded cf beta.20 tarball SHA-512 against npm `dist.integrity`. Other platforms were not download-tested.
- Independent diff review (`bd6420f66`) APPROVE. Codex also ran an independent Bun TOML structural diff confirming no dependencies changed outside ty and lock schema, and heredoc matched the source.
- Before merge, verify local sandbox `just test` and all PR CI checks on latest SHA, and record results in the PR body. Local log at `/tmp/ty-cf-sandbox.log`.
