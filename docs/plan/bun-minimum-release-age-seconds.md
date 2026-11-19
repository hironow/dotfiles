# Write minimumReleaseAge in bunfig in seconds

**Date:** 2026-11-17
**Status:** Implemented (2 Codex reviews with no findings). Verify after merge with `just sync-agents all` and a Dependabot re-run
**Scope:** dotfiles only. Worktree `../dotfiles-bun-release-age`, branch `fix/bun-minimum-release-age-seconds`.
Also updates global spokes (`ROOT_AGENTS_docs_agents_web-ui.md`, `ROOT_AGENTS_docs_agents_dependency-policy.md`), so distribute after merge with `just sync-agents`.

## Owner request

The owner said, "I want the version used to always be the latest" (translated), and chose Option 1 (changing only the syntax to seconds) (2026-11-17 02:15, "ok").
Do not file an issue on dependabot-core since that posts externally.

## What is happening (confirmed facts)

- Dependabot's `bun` job fails because it cannot parse `minimumReleaseAge = "7d"` in `bunfig.toml` (2026-11-16 14:36 UTC, job 1709041923, `Error: Expected number of seconds for minimumReleaseAge`).
  Because `bun` belongs to the weekly multi-ecosystem group, this failure also prevents the weekly PR from opening.
- Dependabot runs bun 1.4.2 (`ARG BUN_VERSION=1.4.2` in dependabot-core `bun/Dockerfile`, last updated 2026-10-06).
- Duration syntax (`90m`, `3d`, `2 weeks`, etc.) landed in bun PR #44968 (merged 2026-10-14); it is not in `bun-v1.4.3`, and landed in `bun-v1.4.4` (2026-10-22, current latest) (verified via GitHub compare).
- Tested locally (temporary project installing only `is-number@7.0.0`):

  | bun | `minimumReleaseAge = 604800` | `minimumReleaseAge = "7d"` |
  |---|---|---|
  | 1.4.4 (local, latest) | Succeeded | Succeeded |
  | 1.4.2 (official GitHub release zip, verified against `SHASUMS256.txt`) | Succeeded | `Invalid Bunfig: failed to load bunfig`, exit 1 |

- Keep the bun version unchanged: local and CI stay on latest bun. Change only the syntax in `bunfig.toml`.
- Three places specify `"7d"` syntax:
    - `bunfig.toml` (added in ADR-0079; ADR-0079 D2 only states "wait 7 days" without prescribing syntax, so leave the ADR unchanged)
    - Global spoke `ROOT_AGENTS_docs_agents_web-ui.md` example under "With a package:"
    - Tests `tests/unit/test_frontend_ci_conformance.py` (`== "7d"`) and `tests/unit/test_web_ui_guidance.py` (`'minimumReleaseAge = "7d"' in ...`)
- `.gpus` and shorts-factory have neither `minimumReleaseAge` in `bunfig.toml` nor Dependabot `bun`.

## Changes

1. **[Red]** Update tests first:
   - `test_frontend_ci_conformance.py`: `bunfig["install"]["minimumReleaseAge"] == 604800`.
   - `test_web_ui_guidance.py` `test_the_wait_is_set_where_bun_installs`: the "With a package:" paragraph has `minimumReleaseAge = 604800`. Keep the CLI `--minimum-release-age 7d` check unchanged (the CLI is read by local latest bun, where duration syntax works).
   - `test_web_ui_guidance.py` `test_the_dependency_policy_says_how_bun_waits`: the dependency-policy paragraph includes `604800` and explains that Dependabot accepts only `seconds`.
2. **[Green]**
   - `bunfig.toml`: `minimumReleaseAge = 604800`, with a comment above explaining "7 days in seconds; Dependabot's bun (1.4.2) cannot parse `"7d"`".
   - `ROOT_AGENTS_docs_agents_web-ui.md`: update example to `[install] minimumReleaseAge = 604800` (7 days in seconds).
   - `ROOT_AGENTS_docs_agents_dependency-policy.md`: add to the bun paragraph: "In `bunfig.toml`, write it in seconds (7 days = `604800`); Dependabot's bun cannot parse durations like `"7d"`." Keep the normative rule here and only an example in the web-ui spoke (DRY).

Single commit (`fix(bun): write minimumReleaseAge in seconds so Dependabot's bun can read it`); no structural changes.

## Verification (definition of done)

- `just ci` completes and passes (run without a timeout cap), including the `instruction-budget` leg.
- Before merge, test the PR branch's `bunfig.toml` with both bun 1.4.2 and 1.4.4 to confirm install succeeds in both (drop the branch's `bunfig.toml` verbatim into the same temporary project as the table above).
- PR CI green. Squash merge under the owner's standing permission.
- Post-merge:
    - Pull local main, inspect targets and diffs with `just sync-agents-preview all`, then distribute to all agents with `just sync-agents all`. Verify `604800` appears in `docs/agents/dependency-policy.md` and `docs/agents/web-ui.md` in every target home (running `just sync-agents` without arguments updates only `~/.claude`, leaving stale `"7d"` examples in Codex and Gemini).
    - Completion criterion for this change: on Dependabot's re-run, `Expected number of seconds for minimumReleaseAge` disappears from the `bun` job and the job finishes. A weekly PR opens only if updates exist (currently oxlint 1.93.0 etc. exist, so one should open).
- On failure: isolate the cause. Revert the squash commit and re-run `just sync-agents all` only if this change itself caused the failure (unable to parse bunfig, or 7-day wait failing to apply). Do not revert on failures in other ecosystems or network errors (reverting brings back the `"7d"` parse failure); re-run or fix separately.

## Out of scope

- Filing an issue on dependabot-core (external posting; only if requested by owner).
- CLI `--minimum-release-age 7d` (read by local latest bun, not Dependabot).

## Review record

### Codex round 1 (2026-11-17)

| # | Finding | Decision | Verified |
|---|---|---|---|
| 1 | "All jobs pass and weekly PR opens" is too broad as a completion criterion; unrelated failures would cause reverting and bring back `"7d"` failures | Adopted | Narrowed completion criterion to the bun job clearing its syntax error and finishing; revert only when proven caused by this change |
| 2 | `just sync-agents` without arguments distributes only to `~/.claude`, leaving stale examples in other agents | Adopted | Added `just sync-agents-preview all` check followed by `just sync-agents all` |
