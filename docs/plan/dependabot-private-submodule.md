# Skip the private submodule in Dependabot's clone

**Date:** 2026-11-17
**Status:** Merged in #633, but post-merge Dependabot failed on all jobs due to broken nesting in `protocols/UTCP`. Replaced by `docs/plan/dependabot-skip-all-submodules.md` (skip all submodules)
**Scope:** dotfiles only. Worktree `../dotfiles-dependabot-submodule`, branch `fix/dependabot-private-submodule`.

## Owner request

An audit of "areas falling behind latest" across 3 repos found dotfiles' weekly Dependabot PRs were not appearing.
The owner selected this fix (2026-11-16, "1").

## What is happening (confirmed facts)

- dotfiles' Dependabot `github_actions` runs have failed every time since 2026-07-28 (also failed 06-07 to 06-30). Last success was 07-21.
  Verified with `gh run list --workflow 'Dependabot Updates'`.
- PR #596 (2026-11-11) grouped all ecosystems into one `weekly` group. Runs on 11-10, 11-11, and 11-16 produced no weekly PR because `github_actions` failed. The last Dependabot PR was 11-08.
- Failure sequence (verified in 11-16 run log `job_1709041729`):
  1. Dependabot clones with `git clone --no-tags --depth 1 --recurse-submodules --shallow-submodules https://github.com/hironow/dotfiles`.
  2. Private `hironow/knowledge-work-plugins` fails to clone with `Repository not found` (`Failed to request additional scope: 403`).
  3. Git aborts submodule cloning mid-way, leaving the other 32 submodules empty and reported by `git status` as `modified content`.
  4. On each update, if `git status --short .` is non-empty, Dependabot runs `git add -- <repo>` and `git commit` (`store_change` in dependabot-core `common/lib/dependabot/workspace/git.rb`). The 1st item (`actions/checkout`) committed, then the 2nd item (`astral-sh/setup-uv` on 11-16; `actions/deploy-pages` earlier) failed `git commit` with exit 1, failing the whole job.
- Reproduced the clone locally (scratchpad `subrepro`, 3 `file://` repos, deleting 1 to make it unreachable). When cloning the deleted repo failed, remaining submodules stayed empty and `git status` printed `m good1` `m good2`; subsequent `git add` and `git commit` exited 1 with `no changes added to commit`.
- Personal-account repos have no setting granting Dependabot access to private repos; that setting exists only for organizations (GitHub Docs "Managing security and analysis settings for your organization" → "Allowing Dependabot to access private dependencies").
- The owner's git config has no `submodule.recurse` setting (neither global nor local).

## Comparison of fixes

| Option | Content | Decision |
|---|---|---|
| A | Add `update = none` to `knowledge-work-plugins` in `.gitmodules` | **Adopted**. Adds no secrets; 1 line to revert |
| B | Store a fine-grained PAT in a Dependabot secret and add `type: git` under `registries` in `dependabot.yaml` | Rejected. Adds long-lived credentials that break on expiry; unverified whether it helps submodule clones |
| C | Remove `knowledge-work-plugins` as a submodule or make it public | Rejected. Architectural choice belonging to the owner, beyond this fix's scope |
| D | Add `ignore = dirty` to all submodules | Rejected. Also hides dirty states on the owner's local checkouts; leaves root cause (clone failure) intact |

Local verification of Option A:

- The same clone command as Dependabot prints `Skipping submodule 'private'`, exits 0, leaves `git status` empty, and populates all other submodules.
- Side effect: on the owner's checkouts, `git submodule update` and `git submodule update --remote --force` also skip this submodule:
    - Checkouts initialized before the change: no local `submodule.<name>.update`, so `none` from `.gitmodules` applies.
    - Checkouts initialized after the change: `git submodule init` copies `none` into local `.git/config` (confirmed in repro: `fresh2` and `c2` got `none`).
- Adding `--checkout` overrides `update = none` in both cases (`--remote --force --checkout` advanced to the new commit).
- On a new machine, `git submodule update --init` skips this submodule; `--init --checkout` fetches it.

## Changes

1. **[Red]** Add `tests/unit/test_private_submodule_clone.py`, automating the local repro inside `tmp_path`:
   - Setup: create 2 public repos, 1 private repo, and a superproject with them as submodules in `tmp_path`. Copy the private submodule's `update` setting **from the real `.gitmodules` `knowledge-work-plugins` section** (regex matching `tests/unit/test_claude_md_excludes.py`). Isolate git from owner settings with `GIT_CONFIG_GLOBAL=os.devnull`, `GIT_CONFIG_NOSYSTEM=1`, `-c protocol.file.allow=always`, `-c commit.gpgsign=false`.
   - Control: in a superproject without `update` copied, deleting the private repo makes Dependabot's clone (`--no-tags --depth 1 --recurse-submodules --shallow-submodules`) fail with non-empty `git status --short`, proving the repro mirrors the real failure.
   - Main test: with the real setting copied, the same clone exits 0 with empty `git status --short` and populated public submodules.
   - Owner updates: add a commit to the private repo and run the `submodule update --remote` line extracted directly from `justfile` `update-all-submodules`, verifying the private repo advances even in a checkout initialized after the change (local `none`).
   - New machine: run the `submodule update --init ...` line extracted from README in a fresh clone of the HTTPS-role repo, verifying private repo contents are fetched.
   Extracting lines from `justfile` and README ensures reverting the wording fails the test.
   Split extracted lines with `shlex.split` and use only arguments from `submodule` onward (discarding README's `-C ~/dotfiles` and recipe's `-c ...`). Always invoke `["git", "-C", <checkout inside tmp_path>, *args]` with `shell=False`, asserting `-C` targets inside `tmp_path` before running so tests never touch the owner's real checkout.
2. **[Green]**
   - `.gitmodules`: add `update = none` under `[submodule "knowledge-work-plugins"]`.
   - `justfile`: add `--checkout` to `git -c submodule.recurse=false submodule update --remote --force` and add a 1-line comment above the recipe explaining why. Other submodules have no `update` set and keep default checkout behavior.
   - `README.md`: change `git -C ~/dotfiles submodule update --init` to `--init --checkout` and add 1 sentence explaining the private submodule is skipped by default for Dependabot's clone.
   - `.github/dependabot.yaml`: near "Out of scope" in the header comment, document why the private submodule has `update = none`. Editing this file triggers a Dependabot re-run after merge.
3. Put this plan in `docs/plan/` and update Status.

Single commit (`fix(dependabot): skip the private submodule in Dependabot's clone`); no structural changes.

## Verification (definition of done)

- `just ci` completes and passes. If any leg fails for host-specific reasons, never pass by comparison alone: fix the cause or stop and report to the owner.
- PR CI green. Squash merge under the owner's standing permission (PRs may be squash-merged once CI is green).
- Post-merge:
    - Pull local main and verify `git submodule status knowledge-work-plugins` is unchanged and `just update-all-submodules` fetches this submodule (if network prevents running all, verify with `git -c submodule.recurse=false submodule update --remote --force --checkout knowledge-work-plugins`).
    - Next Dependabot `github_actions` run succeeds and opens a weekly PR. If editing `dependabot.yaml` does not trigger a re-run, wait for the next scheduled run (Wednesday 15:39 UTC).
- On failure: open a PR reverting the entire squash commit (which removes the new test too; leaving the test would fail revert CI since it reads real config). Also check `git config --get submodule.knowledge-work-plugins.update` on any checkout initialized after the change and remove `none` with `git config --unset submodule.knowledge-work-plugins.update` (values copied by `init` are not removed by reverting). If Dependabot still fails, inspect logs for another cause (and consult the owner on Option B).
- Recovery steps test git itself, so add no test for them (not testing code in this repo).

## Out of scope

- Reviewing contents of Dependabot PRs (major bumps like setup-uv v8→v10, setup-python v6→v7); handle separately once PRs open.
- Mac main tree (`/Users/nino/dotfiles`) picks up changes on pull; updating this submodule works unchanged as long as `just update-all-submodules` is used.

## Review record

### Codex round 1 (2026-11-17)

| # | Finding | Decision | Verified |
|---|---|---|---|
| 1 | String checks alone do not prove the failure is prevented; automate the repro as a test | Adopted | Rewrote Change 1 into a repro test extracting lines from `justfile` and README |
| 2 | Checkouts initialized after the change copy `none` locally, so reverting 1 line will not recover them | Adopted (no recovery test) | Confirmed in repro that `fresh2` and `c2` got local `none`. Added `git config --unset` to rollback; no test added since it tests git behavior |
| 3 | "No more failures than main" permits commits leaving failures behind | Adopted | Changed completion criterion to full `just ci` pass |

### Codex round 2 (2026-11-17)

| # | Finding | Decision | Verified |
|---|---|---|---|
| 1 | README line contains `git -C ~/dotfiles`, risking touching the real checkout if run as-is | Adopted | Updated Change 1 to keep only args from `submodule` onward and assert `-C` is inside `tmp_path` |
| 2 | Reverting only 4 files in rollback leaves the new test, breaking revert CI | Adopted | Changed rollback to revert the entire squash commit |
