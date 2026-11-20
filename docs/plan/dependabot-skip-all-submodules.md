# Skip all submodules in Dependabot's clone

**Date:** 2026-11-17
**Status:** In progress (2 Codex reviews with no findings)
**Scope:** dotfiles only. Worktree `../dotfiles-dependabot-submodules`, branch `fix/dependabot-skip-all-submodules`.
Previous plan: `docs/plan/dependabot-private-submodule.md` (#633, merged).

## What happened (confirmed facts)

- #633 added `update = none` to `knowledge-work-plugins`. After merge (2026-11-16 16:31 UTC), Dependabot re-ran all ecosystems.
- All **9 jobs** (`github_actions`, 3 `uv` jobs, `bun`, `go_modules`, `docker`, `docker_compose`, `opentofu`) **failed**.
  Before #633, only `github_actions` (and `bun`) had failed.
- Logs (job 1709405958, etc.):
    - `Skipping submodule 'knowledge-work-plugins'` appeared, confirming #633 took effect.
    - Next, `fatal: No url found for submodule path 'protocols/UTCP/temp/openapi-directory' in .gitmodules` and `fatal: Failed to recurse into submodule path 'protocols/UTCP'` appeared, aborting with `Error during file fetching; aborting`.
- Cause: `protocols/UTCP`'s pinned commit (`4a9ed93`, 2026-09-16) contains a gitlink `temp/openapi-directory` not listed in its `.gitmodules`. Upstream HEAD (same `4a9ed93`) is identical, so bumping the pin does not fix it.
  Before #633, git stopped on the private submodule failure before recursing to this broken nesting.
- Why it went unnoticed locally: line 3 of `just update-all-submodules` (`git submodule foreach ... 'git submodule update --init --recursive --checkout 2>/dev/null || true'`) discards this error.
- How Dependabot clones (`_clone_repo_contents` in dependabot-core `common/lib/dependabot/file_fetchers/base.rb`):
    - Always clones with `--no-tags --depth 1 --recurse-submodules --shallow-submodules`; no configuration option disables it.
    - Only two errors are tolerated: `fatal: clone of '...' into submodule path '...' failed` and `fatal: unable to access ...`. Any other failure raises and aborts the job.
- Audited nested gitlinks across all submodules: only `protocols/UTCP` lacks a `.gitmodules` entry; other nested submodules (3 in `payments/x402`, 1 in `tools/tmux/plugins/tmux-resurrect`, 1 in `protocols/webmcp-tools`) are listed.
- All Dependabot target directories (`/`, `/tools/rttm`, `/emulator`, `/emulator/*`, `/tests/docker`, `/telemetry`, `/tofu/tailnet`) live inside the main repo; Dependabot never uses submodule contents.
- CI workflows do not fetch submodules (`claude-lint.yaml` and `pages.yaml` specify `submodules: false`; others use the default of not fetching).

## Comparison of fixes

| Option | Content | Decision |
|---|---|---|
| A | Add `update = none` to `protocols/UTCP` too | Rejected. Fixes only this 1 case; if any of the 34 submodules (mostly third-party repos) breaks similarly, all jobs stop again |
| B | Add `update = none` to **all** submodules | **Adopted**. Dependabot's clone fetches zero submodules and becomes independent of third-party repo state; Dependabot never uses submodule contents, so nothing is lost |
| C | Revert #633 | Rejected. Merely restores the previous state (weekly PRs blocked by `github_actions` failure) |

Side effects of Option B (same `update = none` behavior verified in #633):

- On the owner's checkouts, bare `git submodule update` and `--remote` skip all submodules; adding `--checkout` works as before.
- `just update-all-submodules` and the README fetch steps already include `--checkout` from #633, so they keep working.
- Checkouts initialized with `git submodule init` after this change copy `none` into local `.git/config`.

## Changes

1. **[Red]** Rename `tests/unit/test_private_submodule_clone.py` to `tests/unit/test_dependabot_submodule_clone.py` (`git mv`, structural commit first), then add the following (behavioral commit second):
   - Static: **every** submodule in `.gitmodules` has `update = none`.
   - Setup: add a **broken-nesting role** (repo containing a gitlink absent from `.gitmodules`, created with `git update-index --add --cacheinfo 160000,<sha>,temp/x`) alongside the public and private roles in the repro superproject. Copy each role's `update` from the corresponding entry in real `.gitmodules` (public = `protocols/A2A`, private = `knowledge-work-plugins`, broken = `protocols/UTCP`).
   - Control: when settings are not copied, even if the private role is reachable, the broken role fails Dependabot's clone; assert stderr contains `No url found for submodule path` and the broken nested path (`broken/temp/x`) so unrelated failures cannot pass.
   - Control (#633 state): setting `none` on the private role alone still fails with `No url found`, pinning this exact regression.
   - Keep the existing private-role control.
   - Main test: with real settings copied and the private role deleted, the clone exits 0 with empty `git status --short` and fetches no public-role contents (drop the #633 assertion that public-role contents exist).
   - Keep the README and `update-all-submodules` command tests unchanged (they fetch and advance `none` submodules).
2. **[Green]**
   - `.gitmodules`: set `update = none` on all submodules (via `git config -f .gitmodules submodule.<name>.update none`).
   - `.github/dependabot.yaml`: change the reason comment from "one private submodule" to "all submodules" and mention `protocols/UTCP`. Editing this file triggers a Dependabot re-run after merge.
   - Update the comment above `update-all-submodules` in `justfile` and the 1 sentence in README to refer to "all submodules".
   - Note in `docs/plan/dependabot-private-submodule.md` Status that this plan supersedes it.

## Verification (definition of done)

- `just ci` completes and passes (run without a timeout cap).
- **Before merge, verify Dependabot's exact clone against the real repo.** After pushing the branch, isolate from the owner's git config (`GIT_CONFIG_GLOBAL=/dev/null`, `GIT_CONFIG_NOSYSTEM=1`, `GIT_TERMINAL_PROMPT=0`, no auth) and run `git clone --no-tags --depth 1 --recurse-submodules --shallow-submodules --branch fix/dependabot-skip-all-submodules https://github.com/hironow/dotfiles <tmp>`. Verify exit 0, empty `git status --short`, and none of the 34 submodules fetched (`git submodule status` lines all start with `-`), and record the result in the PR. (#633 missed this: synthetic fixtures and CI passed, without cloning all real submodules the way Dependabot does.)
- PR CI green. Squash merge under the owner's standing permission.
- Post-merge:
    - Pull local main and verify submodule pins are unchanged, bare `git submodule update <path>` skips, and `--checkout` updates (same check as #633).
    - In Dependabot's re-run, **all 8 jobs except `bun` succeed**. If any fails, inspect logs for the next cause and fix with the same workflow (plan, review, repro test).
    - The `bun` job is expected to keep failing for another reason ("Out of scope" below). Weekly PRs will resume once `bun` is fixed too.
- On failure: revert the entire squash commit for this PR. On any checkout initialized after the change, find `none` entries with `git config --get-regexp '^submodule\..*\.update$'` and remove them with `git config --unset`.

## Out of scope

- **`bun` job failure** (since the 14:36 run before #633, job 1709041923). Dependabot's bun rejects `minimumReleaseAge = "7d"` in `bunfig.toml` with `Expected number of seconds for minimumReleaseAge`. `"7d"` is mandated by a global spoke (`ROOT_AGENTS_docs_agents_web-ui.md`) and 2 tests (`test_frontend_ci_conformance.py`, `test_web_ui_guidance.py`). Local bun 1.4.4 also accepts numeric `604800`. Because changing a global rule is involved, consult the owner and handle in a separate PR.
- Line 3 of `update-all-submodules` discarding errors. It hides broken nested fetches, yet removing it would make the recipe fail every run on `protocols/UTCP`. Only report to the owner.
- Reviewing contents of PRs opened by Dependabot.

## Review record

### Codex round 1 (2026-11-17)

| # | Finding | Decision | Verified |
|---|---|---|---|
| 1 | Synthetic fixtures and CI alone omit cloning all real submodules like Dependabot until after merge (gap in #633) | Adopted | Made cloning the pushed branch from GitHub with Dependabot's exact command a mandatory pre-merge check |
| 2 | Broken-nesting control should verify the failure reason (`No url found` and nested path), plus add a control for the #633 state | Adopted | Split Change 1 controls into 2 cases and asserted stderr contents |
